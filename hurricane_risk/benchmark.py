"""Compare predeclared wind variants and timestep convergence without fitting observations."""
from __future__ import annotations

import argparse
import json
import platform
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/hurricane-risk-matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .__main__ import validate_config
from .artifacts import output_directory, output_hashes, sha256
from .diagnostics import station_geometry, grouped_errors
from .inputs import load_portfolio, load_vulnerability, portfolio_from_config
from .model import (read_hurdat, synthetic_portfolio, hazard_catalog, property_losses,
                    annual_losses, loss_metrics)
from .validation import load_observations, scores, uncertainty_bands


DEFAULT_VARIANTS = [
    {'name': 'baseline', 'overrides': {}},
    {'name': 'fallback_rmw_25km', 'overrides': {'rmw_km': 25.}},
    {'name': 'fallback_rmw_45km', 'overrides': {'rmw_km': 45.}},
    {'name': 'outer_decay_0.5', 'overrides': {'rankine_alpha': .5}},
    {'name': 'outer_decay_0.7', 'overrides': {'rankine_alpha': .7}},
]


def validate_variants(variants, cfg):
    if not isinstance(variants, list) or not variants or variants[0] != {'name': 'baseline', 'overrides': {}}:
        raise ValueError('First variant must be baseline with empty overrides')
    names = set()
    for variant in variants:
        if set(variant) != {'name', 'overrides'} or not isinstance(variant['name'], str) or not variant['name'].strip():
            raise ValueError('Each variant needs a nonempty name and overrides')
        if variant['name'] in names:
            raise ValueError('Variant names must be unique')
        names.add(variant['name'])
        if not isinstance(variant['overrides'], dict) or set(variant['overrides']) - {'rmw_km', 'rankine_alpha', 'land_exposure_factor', 'translation_fraction', 'asymmetry_cap', 'inland_decay_km'}:
            raise ValueError('Variant overrides may change only declared wind-model parameters')
        validate_config({**cfg, **variant['overrides']})


def station_predictions(obs, tracks, sources, cfg):
    result = obs.copy()
    for source_id, group in obs.groupby('source_id'):
        source = sources['sources'][source_id]
        tr = tracks[(tracks.storm_id == source['storm_id']) &
                    tracks.time.between(source['window_start'], source['window_end'])]
        if len(tr) < 2:
            raise ValueError(f'Missing validation track: {source_id}')
        _, hazard = hazard_catalog(tr, group, cfg)
        for j, column in enumerate(['rmw_low_ms', 'modeled_ms', 'rmw_high_ms']):
            result.loc[group.index, column] = hazard[0, j]
    if result.empty:
        raise ValueError('Need station observations')
    return uncertainty_bands(result, cfg['seed']+10, cfg['land_exposure_factor'])


def assign_splits(obs, split_path=None):
    if split_path is None:
        return obs.assign(split='development'), {'development': sorted(obs.storm_id.unique()), 'test': []}
    splits = json.loads(Path(split_path).read_text())
    if set(splits) != {'development', 'test'} or any(not isinstance(v, list) for v in splits.values()):
        raise ValueError('Split file requires development and test storm lists')
    all_ids = splits['development'] + splits['test']
    if len(all_ids) != len(set(all_ids)) or set(all_ids) != set(obs.storm_id):
        raise ValueError('Every observed storm must appear in exactly one split')
    if not splits['development']:
        raise ValueError('Explicit splits require development storms; test may be empty')
    return obs.assign(split=np.where(obs.storm_id.isin(splits['test']), 'test', 'development')), splits


def percent_change(value, baseline):
    return 100*(value/baseline-1) if baseline else np.nan


def run_benchmark(tracks, obs, sources, cfg, portfolio, vulnerability, variants, timesteps, out,
                  wind_tolerance_ms=1., loss_tolerance_pct=1.):
    validate_variants(variants, cfg)
    if not timesteps or any(isinstance(t, bool) or not isinstance(t, (int, float)) or not np.isfinite(t) or t <= 0 for t in timesteps) or len(set(timesteps)) != len(timesteps):
        raise ValueError('Timesteps must be unique positive minutes')
    if any(not np.isfinite(v) or v < 0 for v in [wind_tolerance_ms, loss_tolerance_pct]):
        raise ValueError('Convergence tolerances must be finite and nonnegative')
    if tracks.season.min() > cfg['start_year'] or tracks.season.max() < cfg['end_year']:
        raise ValueError('Tracks do not span the loss-analysis years')
    selected = tracks[tracks.season.between(cfg['start_year'], cfg['end_year'])]
    ids = selected.loc[selected.status.eq('HU'), 'storm_id'].unique()
    selected = selected[selected.storm_id.isin(ids)]
    years = np.arange(cfg['start_year'], cfg['end_year']+1)
    summaries, metrics, all_pairs, all_groups, annual_tables, event_tables, convergence = [], [], [], [], [], [], []
    # Finest case for each variant is the numerical reference, never ground truth.
    for variant in variants:
        reference = None
        for minutes in sorted(timesteps):
            case = {'variant': variant['name'], 'interpolation_minutes': minutes}
            run_cfg = {**cfg, **variant['overrides'], 'interpolation_minutes': minutes}
            print(f"Benchmark {variant['name']}, {minutes} min", flush=True)
            pairs = station_predictions(obs, tracks, sources, run_cfg)
            pairs = station_geometry(pairs, tracks, sources, run_cfg)
            lower_bound = pairs.incomplete.eq(1) & pairs.observed_ms.notna() & pairs.metadata_issue.eq('')
            pairs['peak_comparison_class'] = np.select(
                [pairs.primary, lower_bound], ['primary_peak', 'lower_bound_only'], default='excluded_metadata_or_missing')
            pairs['lower_bound_violation'] = pd.Series(pd.NA, index=pairs.index, dtype='boolean')
            pairs.loc[lower_bound, 'lower_bound_violation'] = pairs.loc[lower_bound, 'modeled_ms'] < pairs.loc[lower_bound, 'observed_ms']
            # An incomplete peak cannot supply an ordinary signed peak error.
            pairs.loc[~pairs.primary, 'residual_ms'] = np.nan
            all_pairs.append(pairs.assign(**case))
            all_groups.append(grouped_errors(pairs).assign(**case))
            station_scores = {}
            for sample, group in [('pooled', pairs[pairs.primary]),
                                  *[(label, g[g.primary]) for label, g in pairs.groupby('split')]]:
                if group.empty:
                    continue
                values = scores(group.observed_ms, group.modeled_ms)
                metrics.append({**case, 'sample': sample, **values,
                                'prior_90pct_coverage': group.within_prior_90pct.mean()})
                if sample == 'pooled':
                    station_scores = values
            if not station_scores:
                raise ValueError('No eligible primary observations')
            events, hazard = hazard_catalog(selected, portfolio, run_cfg)
            nominal = hazard[:, 1, :]
            ground, insured = property_losses(nominal, portfolio, vulnerability=vulnerability)
            aggregate, occurrence = annual_losses(insured.sum(axis=1), events.year, years)
            losses = loss_metrics(aggregate, occurrence, cfg['return_periods'])
            annual_tables.append(pd.DataFrame({'year': years, 'aggregate_insured_usd': aggregate,
                                               'occurrence_insured_usd': occurrence}).assign(**case))
            event_tables.append(events.assign(ground_up_usd=ground.sum(axis=1), insured_usd=insured.sum(axis=1), **case))
            summaries.append({**case, **station_scores, **losses, 'ground_up_aal_usd': ground.sum()/len(years)})
            if reference is None:
                reference = (nominal.copy(), pairs.modeled_ms.to_numpy(), losses, minutes)
            wind_ref, station_ref, loss_ref, fine_step = reference
            wind_delta = np.abs(nominal-wind_ref)
            primary_delta = np.abs(pairs.loc[pairs.primary, 'modeled_ms'].to_numpy()-station_ref[pairs.primary.to_numpy()])
            for metric, value in losses.items():
                absolute = value-loss_ref[metric]
                relative = percent_change(value, loss_ref[metric])
                passed = (abs(relative) <= loss_tolerance_pct if loss_ref[metric] else absolute == 0)
                convergence.append({**case, 'reference_minutes': fine_step, 'metric': metric,
                                    'value_usd': value, 'reference_usd': loss_ref[metric],
                                    'delta_usd': absolute, 'delta_pct': relative,
                                    'max_property_wind_delta_ms': wind_delta.max(),
                                    'p95_property_wind_delta_ms': np.quantile(wind_delta, .95),
                                    'max_primary_station_wind_delta_ms': primary_delta.max(),
                                    'within_tolerance': bool(passed and wind_delta.max() <= wind_tolerance_ms),
                                    'is_reference': minutes == fine_step})
    summary = pd.DataFrame(summaries)
    baseline = summary[summary.variant.eq('baseline')].set_index('interpolation_minutes')
    summary['aal_change_vs_baseline_pct'] = [percent_change(r.aal_usd, baseline.loc[r.interpolation_minutes, 'aal_usd']) for r in summary.itertuples()]
    summary.to_csv(out/'summary.csv', index=False)
    pd.DataFrame(metrics).to_csv(out/'station_skill.csv', index=False)
    pd.concat(all_pairs, ignore_index=True).to_csv(out/'station_pairs.csv', index=False)
    pd.concat(all_groups, ignore_index=True).to_csv(out/'grouped_errors.csv', index=False)
    pd.concat(annual_tables, ignore_index=True).to_csv(out/'annual_losses.csv', index=False)
    pd.concat(event_tables, ignore_index=True).to_csv(out/'event_losses.csv', index=False)
    convergence = pd.DataFrame(convergence)
    convergence.to_csv(out/'convergence.csv', index=False)
    portfolio.to_csv(out/'portfolio.csv', index=False)
    write_report(summary, convergence, out, wind_tolerance_ms, loss_tolerance_pct)
    return summary, convergence


def write_report(summary, convergence, out, wind_tolerance, loss_tolerance):
    lines = ['# Wind and loss benchmark', '',
             'Predeclared sensitivity experiments; no parameters are fitted and no winning model is selected.',
             'Current report peaks are development diagnostics. A test split records event separation,',
             'but does not establish independence from NHC best-track construction or prior analyst use.', '',
             '| Variant | Step (min) | Station RMSE (m/s) | Bias (m/s) | Insured AAL | AAL change vs baseline |',
             '|---|---:|---:|---:|---:|---:|']
    for row in summary.itertuples():
        lines.append(f'| {row.variant} | {row.interpolation_minutes} | {row.rmse_ms:.2f} | {row.bias_ms:.2f} | ${row.aal_usd:,.0f} | {row.aal_change_vs_baseline_pct:+.2f}% |')
    tested = convergence[~convergence.is_reference]
    lines += ['', f'Convergence thresholds: maximum property wind change ≤ {wind_tolerance:g} m/s and absolute',
              f'percentage loss-metric change ≤ {loss_tolerance:g}% relative to the finest tested timestep.',
              'A zero reference loss passes only if its absolute change is zero; percentage change is missing.',
              f'{int(tested.within_tolerance.sum())} of {len(tested)} non-reference metric comparisons pass both thresholds.',
              'These are user-set numerical criteria. The finest timestep is a reference, not proof of convergence.',
              'Return losses use exact annual empirical quantiles, preserving zero years; no annual resampling noise is introduced.',
              'Losses use the full configured hurricane catalog and fixed exposure/policy terms; station skill uses source windows.',
              'Fallback-RMW variants change missing RMW only. Observed positive RMW is preserved.',
              'Track-side and distance diagnostics are geometric. When a coastline is configured, signed coastal distances and inland bins are included.',
              'Translation and local inland attenuation are declared structural sensitivities; they are not calibrated replacements.',
              'The prior wind envelope remains an assumed parameter ensemble, not a calibrated predictive interval.',
              'No claim validation, physical climate attribution, or high-wind validation follows from these comparisons.', '',
              '![Benchmark comparison](benchmark.png)', '']
    (out/'report.md').write_text('\n'.join(lines))
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for name, group in summary.groupby('variant', sort=False):
        axes[0].plot(group.interpolation_minutes, group.rmse_ms, marker='o', label=name)
        axes[1].plot(group.interpolation_minutes, group.aal_usd/1e6, marker='o', label=name)
    axes[0].set(xlabel='Timestep (minutes)', ylabel='Station RMSE (m/s)')
    axes[1].set(xlabel='Timestep (minutes)', ylabel='Insured AAL (USD millions)')
    axes[1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(out/'benchmark.png', dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tracks', type=Path, default=Path('data/hurdat2-1851-2024-040425.txt'))
    parser.add_argument('--observations', type=Path, default=Path('data/validation/station_peaks.csv'))
    parser.add_argument('--sources', type=Path, default=Path('data/validation/sources.json'))
    parser.add_argument('--config', type=Path, default=Path('config.json'))
    parser.add_argument('--portfolio', type=Path)
    parser.add_argument('--vulnerability', type=Path)
    parser.add_argument('--variants', type=Path, help='JSON list of named wind-parameter overrides')
    parser.add_argument('--splits', type=Path, help='JSON with development/test storm lists')
    parser.add_argument('--timesteps', type=float, nargs='+', default=[30, 5, 1])
    parser.add_argument('--wind-tolerance-ms', type=float, default=1.)
    parser.add_argument('--loss-tolerance-pct', type=float, default=1.)
    parser.add_argument('--out', type=Path, default=Path('outputs/benchmark'))
    args = parser.parse_args()
    execution_source_hashes = {p.name: sha256(p) for p in Path(__file__).parent.glob("*.py")}
    cfg = json.loads(args.config.read_text())
    validate_config(cfg)
    variants = json.loads(args.variants.read_text()) if args.variants else DEFAULT_VARIANTS
    validate_variants(variants, cfg)
    curves = load_vulnerability(args.vulnerability)
    portfolio, location_audit = portfolio_from_config(cfg, curves, args.portfolio)
    sources = json.loads(args.sources.read_text())
    obs, splits = assign_splits(load_observations(args.observations, sources), args.splits)
    tracks = read_hurdat(args.tracks)
    with output_directory(args.out) as out:
        run_benchmark(tracks, obs, sources, cfg, portfolio, curves, variants, args.timesteps, out,
                      args.wind_tolerance_ms, args.loss_tolerance_pct)
        if location_audit is not None:
            location_audit.to_csv(out/'exposure_location_audit.csv', index=False)
        manifest = {'purpose': __doc__, 'config': cfg, 'variants': variants, 'timesteps': args.timesteps,
                    'coastline_sha256': sha256(cfg['coastline_path']) if cfg.get('coastline_path') else None,
                    'splits': splits, 'wind_tolerance_ms': args.wind_tolerance_ms,
                    'loss_tolerance_pct': args.loss_tolerance_pct,
                    'inputs_sha256': {str(p): sha256(p) for p in [args.tracks, args.observations, args.sources,
                                      args.config, args.portfolio, args.vulnerability, args.variants, args.splits] if p},
                    'code_sha256': execution_source_hashes,
                    'versions': {'python': platform.python_version(), 'numpy': np.__version__,
                                 'pandas': pd.__version__, 'matplotlib': matplotlib.__version__},
                    'vulnerability_metadata': curves['metadata'],
                    'outputs_sha256': output_hashes(out)}
        (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'Benchmark: {args.out.resolve()}/report.md')


if __name__ == '__main__':
    main()
