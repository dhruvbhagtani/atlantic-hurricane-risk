"""Evaluate every registered station and frozen candidate, retaining failures and censoring."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .artifacts import output_directory, output_hashes, sha256
from .collection_inputs import effective_collection, validate_history, validate_annual_identity, AMENDMENT
from .global_hourly import normalize_global_hourly
from .model import read_hurdat, KNOT_TO_MS
from .observation_inventory import COLLECTION
from .observations import prepare_observations
from .time_series_validation import modeled_at_times, plt
from .validation import scores

AUDIT = COLLECTION/'station_metadata_audit_v1.json'
CODE_FILES = ['collection_study.py', 'collection_inputs.py', 'global_hourly.py', 'observations.py',
              'model.py', 'geography.py', 'time_series_validation.py', 'validation.py', 'artifacts.py',
              'observation_inventory.py', 'confirmation_inputs.py', 'confirmation_study.py']


def primary_eligibility(audit):
    return (audit.get('height_m') == 10 and audit.get('height_matches_event_site') is True
            and bool(audit.get('height_source_url')) and audit.get('averaging_minutes') in [1, 2]
            and bool(audit.get('duration_source_url')))


def summarize(performance, plan):
    """Registered station-then-storm weighting; never silently drop a planned pair."""
    event_rows, totals = [], []
    for candidate in plan['candidates']:
        name = candidate['name']
        frame = performance[performance.variant.eq(name)]
        for event in plan['events']:
            group = frame[frame.storm_id.eq(event['storm_id'])]
            expected = len(event['stations'])
            complete = len(group) == expected and group.primary_eligible.all() and group.rmse_ms.notna().all()
            available = group[group.rmse_ms.notna()]
            event_rows.append({'variant': name, 'storm_id': event['storm_id'], 'planned_stations': expected,
                               'scored_stations': len(available), 'primary_stations': int(group.primary_eligible.sum()),
                               'primary_complete': bool(complete),
                               'primary_rmse_ms': float(group.rmse_ms.mean()) if complete else np.nan,
                               'available_case_rmse_ms': float(available.rmse_ms.mean()),
                               'available_case_bias_ms': float(available.bias_ms.mean()),
                               'eligible_reports': int(group.n.sum()), 'hurricane_force_reports': int(group.high_n.sum())})
        events = pd.DataFrame(event_rows); events = events[events.variant.eq(name)]
        complete = len(events) == len(plan['events']) and events.primary_complete.all()
        totals.append({'variant': name, 'planned_storms': len(plan['events']),
                       'scored_storms': int(events.available_case_rmse_ms.notna().sum()),
                       'primary_complete_storms': int(events.primary_complete.sum()),
                       'registered_primary_complete': bool(complete),
                       'registered_primary_rmse_ms': float(events.primary_rmse_ms.mean()) if complete else np.nan,
                       'available_case_storm_balanced_rmse_ms': float(events.available_case_rmse_ms.mean()),
                       'available_case_storm_balanced_bias_ms': float(events.available_case_bias_ms.mean()),
                       'eligible_reports': int(events.eligible_reports.sum()),
                       'hurricane_force_reports': int(events.hurricane_force_reports.sum())})
    return pd.DataFrame(event_rows), pd.DataFrame(totals)


def input_files(plan):
    files = [COLLECTION/'plan.json', COLLECTION/'registration.json', AMENDMENT, AUDIT,
             Path('examples/structural_config.json'), Path('data/hurdat2-1851-2024-040425.txt')]
    for event in plan['events']:
        for station in event['stations']:
            files += [Path(station['homr_path']), Path(station['annual_path'])]
    return files


def freeze_evaluation(destination, plan):
    with output_directory(destination) as out:
        lock = {'schema_version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
                'purpose': 'Evaluation implementation and metadata locked before first collection wind inspection. No model parameter changes.',
                'inputs_sha256': {str(p): sha256(p) for p in input_files(plan) if p.exists()},
                'missing_inputs': [str(p) for p in input_files(plan) if not p.exists()],
                'code_sha256': {n: sha256(Path(__file__).parent/n) for n in CODE_FILES},
                'rule': 'Never replace this lock after wind inspection. Keep all declared pairs and label unavailable primary metrics.'}
        (out/'evaluation_lock.json').write_text(json.dumps(lock, indent=2)+'\n')
    print(f'Evaluation frozen: {destination}/evaluation_lock.json')


def verify_evaluation(path):
    lock = json.loads(Path(path).read_text())
    for name, digest in lock['inputs_sha256'].items():
        if sha256(name) != digest:
            raise ValueError(f'Evaluation input changed after lock: {name}')
    for name, digest in lock['code_sha256'].items():
        if sha256(Path(__file__).parent/name) != digest:
            raise ValueError(f'Evaluation source changed after lock: {name}')
    for name in lock['missing_inputs']:
        if Path(name).exists():
            raise ValueError(f'Previously missing input arrived; freeze a supplemental pre-inspection lock: {name}')
    return lock


def evaluate(plan, audits, tracks, cfg, out):
    all_pairs, raw_series, qc_rows, coverage_rows, performance, dense_rows = [], [], [], [], [], []
    for event in plan['events']:
        track = tracks[tracks.storm_id.eq(event['storm_id'])]
        for target in event['stations']:
            audit = next(a for a in audits if a['storm_id'] == event['storm_id'] and a['station_id'] == target['station_id'])
            station = {'station_id': target['station_id'], **{k: audit['coordinates'][k] for k in ['lat', 'lon']},
                       'height_m': audit['height_m'], 'averaging_minutes': audit['averaging_minutes'],
                       'exposure': 'unknown', 'cadence_minutes': plan['eligibility']['cadence_minutes'],
                       'uptime_confirmed': False, 'metadata_reference': audit['height_source_url'],
                       'uptime_reference': ''}
            failure = ''
            try:
                validate_history(Path(target['homr_path']), target, event)
                validate_annual_identity(Path(target['annual_path']), target, event)
                raw = pd.read_csv(target['annual_path'], dtype=str, keep_default_na=False)
                raw['raw_file'] = target['annual_path']
                series, qc, selected = normalize_global_hourly(raw, event['storm_id'], target['station_id'], target['expected_ncei_id'], event['window_start'], event['window_end'])
                event_plan = {'quality_control_description': 'Frozen conservative Global Hourly QC',
                              'quality_control_reference': 'https://www.ncei.noaa.gov/pub/data/noaa/isd-format-document.pdf',
                              'events': [{**event, 'product': 'NOAA Global Hourly METAR/SPECI sustained winds',
                                          'url': target['annual_url'], 'best_track_provenance': plan['access_protocol']['independence'], 'stations': [station]}]}
                _, coverage, _, _ = prepare_observations(series, event_plan)
                coverage['primary_metadata_eligible'] = primary_eligibility(audit)
                coverage_rows.append(coverage); raw_series.append(series); qc_rows.append(qc)
                selected.to_csv(out/f"raw_{event['storm_id']}_{target['station_id']}.csv", index=False)
                if len(track) < 2:
                    raise ValueError('Missing best-track support')
            except (OSError, ValueError, KeyError) as error:
                failure = str(error)
            for candidate in plan['candidates']:
                row = {'variant': candidate['name'], 'storm_id': event['storm_id'], 'station_id': target['station_id'],
                       'primary_eligible': False, 'failure': failure, 'n': 0, 'high_n': 0,
                       'rmse_ms': np.nan, 'bias_ms': np.nan, 'mae_ms': np.nan, 'high_rmse_ms': np.nan, 'high_bias_ms': np.nan}
                if not failure:
                    run_cfg = {**cfg, **candidate['overrides']}
                    frame = series.copy(); frame['time_utc'] = pd.to_datetime(frame.time_utc, utc=True)
                    support = frame.time_utc.between(pd.Timestamp(track.time.min(), tz='UTC'), pd.Timestamp(track.time.max(), tz='UTC'))
                    frame['modeled_ms'] = np.nan
                    frame.loc[support, 'modeled_ms'] = modeled_at_times(track, station, frame.loc[support, 'time_utc'], run_cfg)
                    frame['sample_eligible'] = frame.quality_flag.eq('good') & support & np.isfinite(frame.sustained_ms)
                    frame['primary_sample_eligible'] = frame.sample_eligible & primary_eligibility(audit)
                    frame['residual_ms'] = frame.modeled_ms-frame.sustained_ms
                    frame['variant'] = candidate['name']; all_pairs.append(frame)
                    good = frame[frame.sample_eligible].sort_values('time_utc')
                    if len(good):
                        row.update(scores(good.sustained_ms, good.modeled_ms))
                        row['primary_eligible'] = primary_eligibility(audit)
                        row['metadata_limitation'] = audit['height_limitation']
                        high = good[good.sustained_ms >= plan['eligibility']['high_wind_threshold_ms']]
                        row['high_n'] = len(high)
                        if len(high):
                            values = scores(high.sustained_ms, high.modeled_ms)
                            row.update(high_rmse_ms=values['rmse_ms'], high_bias_ms=values['bias_ms'])
                        observed = good.loc[good.sustained_ms.idxmax()]
                        modeled = good.loc[good.modeled_ms.idxmax()]
                        times = pd.date_range(max(pd.Timestamp(event['window_start']), pd.Timestamp(track.time.min(), tz='UTC')),
                                              min(pd.Timestamp(event['window_end']), pd.Timestamp(track.time.max(), tz='UTC')), freq='1min')
                        dense = pd.DataFrame({'time_utc': times, 'modeled_ms': modeled_at_times(track, station, times, run_cfg),
                                              'variant': candidate['name'], 'storm_id': event['storm_id'], 'station_id': target['station_id']})
                        dense_rows.append(dense); peak = dense.loc[dense.modeled_ms.idxmax()]
                        row.update(observed_sampled_peak_ms=observed.sustained_ms, observed_peak_time_utc=observed.time_utc,
                                   observed_peak_ties=int(good.sustained_ms.eq(observed.sustained_ms).sum()),
                                   modeled_report_peak_ms=modeled.modeled_ms, modeled_report_peak_time_utc=modeled.time_utc,
                                   report_peak_ties=int(good.modeled_ms.eq(modeled.modeled_ms).sum()),
                                   modeled_dense_peak_ms=peak.modeled_ms, modeled_dense_peak_time_utc=peak.time_utc,
                                   dense_peak_ties=int(dense.modeled_ms.eq(peak.modeled_ms).sum()),
                                   peak_offset_minutes=(peak.time_utc-observed.time_utc).total_seconds()/60,
                                   incomplete_peak=True, good_reports_outside_track=int((frame.quality_flag.eq('good') & ~support).sum()))
                    else:
                        row['failure'] = 'No eligible good-QC reports in track support'
                performance.append(row)
    perf = pd.DataFrame(performance)
    base = perf[perf.variant.eq('baseline')][['storm_id', 'station_id', 'rmse_ms', 'bias_ms']]
    perf = perf.merge(base, on=['storm_id', 'station_id'], suffixes=('', '_baseline'), validate='many_to_one')
    perf['paired_rmse_change_ms'] = perf.rmse_ms-perf.rmse_ms_baseline
    event_scores, summary = summarize(perf, plan)
    perf.to_csv(out/'station_scores.csv', index=False); event_scores.to_csv(out/'storm_scores.csv', index=False)
    summary.to_csv(out/'summary.csv', index=False)
    for name, tables in [('time_matched_pairs', all_pairs), ('observed_time_series', raw_series), ('qc_audit', qc_rows),
                         ('coverage', coverage_rows), ('modeled_time_series', dense_rows)]:
        if tables:
            pd.concat(tables, ignore_index=True).to_csv(out/f'{name}.csv', index=False)
    if all_pairs and dense_rows:
        plot_collection(pd.concat(all_pairs), pd.concat(dense_rows), plan, out)
    return perf, summary


def plot_collection(pairs, dense, plan, out):
    fig, axes = plt.subplots(3, 2, figsize=(16, 11))
    for axis, (event, station) in zip(axes.flat, [(e, s) for e in plan['events'] for s in e['stations']]):
        frame = pairs[pairs.storm_id.eq(event['storm_id']) & pairs.station_id.eq(station['station_id'])]
        model = dense[dense.storm_id.eq(event['storm_id']) & dense.station_id.eq(station['station_id'])]
        for variant, group in model.groupby('variant', sort=False):
            axis.plot(group.time_utc, group.modeled_ms, label=variant, lw=1)
        good = frame[frame.variant.eq('baseline') & frame.sample_eligible]
        axis.scatter(good.time_utc, good.sustained_ms, s=7, c='black', label='Observed good reports')
        edges = pd.DatetimeIndex([pd.Timestamp(event['window_start']), *good.time_utc, pd.Timestamp(event['window_end'])]).sort_values()
        for start, end in zip(edges[:-1], edges[1:]):
            if (end-start).total_seconds() > 120*60:
                axis.axvspan(start, end, color='gray', alpha=.15)
        axis.axhline(64*KNOT_TO_MS, color='gray', ls=':', lw=.8)
        axis.set(title=f"{event['name']} / {station['station_id']}", ylabel='Sustained wind (m/s)', xlabel='UTC')
        axis.tick_params(axis='x', labelrotation=25)
        if frame.empty:
            axis.text(.5, .5, 'Unavailable; see station_scores.csv', transform=axis.transAxes, ha='center')
    axes.flat[0].legend(fontsize=7, ncol=2)
    fig.suptitle('Frozen collection: report-time observations, model curves, and gaps >2 hours')
    fig.tight_layout(rect=(0, 0, 1, .97)); fig.savefig(out/'time_series.png', dpi=160); plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--lock', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); plan = effective_collection()
    if args.freeze:
        freeze_evaluation(args.out, plan); return
    if args.lock is None:
        parser.error('--lock is required for evaluation')
    lock = verify_evaluation(args.lock)
    audits = json.loads(AUDIT.read_text())['station_audits']
    cfg = json.loads(Path('examples/structural_config.json').read_text())
    tracks = read_hurdat(Path('data/hurdat2-1851-2024-040425.txt'))
    with output_directory(args.out) as out:
        # Persist the access timestamp before opening any measurement columns.
        access = {'first_evaluation_access_utc': datetime.now(timezone.utc).isoformat(),
                  'collection_id': plan['collection_id'], 'evaluation_lock_sha256': sha256(args.lock),
                  'future_tuning_role': 'examined; requires new held-out events for future tuning'}
        (out/'wind_access.json').write_text(json.dumps(access, indent=2)+'\n')
        perf, summary = evaluate(plan, audits, tracks, cfg, out)
        (out/'station_metadata_audit.json').write_text(AUDIT.read_text())
        (out/'effective_plan.json').write_text(json.dumps(plan, indent=2)+'\n')
        text = ['# Frozen multistation validation: Sally, Ida and Florence', '',
                'All five candidates and the six station/event pairs were registered before their winds or residuals were inspected. A dated provider-ID amendment corrects Wilmington without changing its station or window.',
                'No candidate is fitted, selected or promoted. These results are held out from this project’s model development, not necessarily independent of NHC best-track construction.',
                'The registered primary metric weights stations equally within each storm, then storms equally. It is unavailable unless all planned pairs meet instrument/sample eligibility.',
                'Available-case scores include nominal-instrument conditional comparisons and retain explicit station counts; they are not the complete registered primary metric.', '',
                '| Candidate | Complete primary storms | Registered primary RMSE (m/s) | Available-case storm-balanced RMSE (m/s) | Reports | Hurricane-force reports |',
                '|---|---:|---:|---:|---:|---:|']
        for r in summary.itertuples():
            primary = f'{r.registered_primary_rmse_ms:.2f}' if pd.notna(r.registered_primary_rmse_ms) else 'unavailable'
            text.append(f'| {r.variant} | {r.primary_complete_storms}/{r.planned_storms} | {primary} | {r.available_case_storm_balanced_rmse_ms:.2f} | {r.eligible_reports} | {r.hurricane_force_reports} |')
        text += ['', '| Storm | Station | Primary eligible | Reports | High-wind reports | Baseline RMSE (m/s) | High-wind RMSE (m/s) | Failure |',
                 '|---|---|---|---:|---:|---:|---:|---|']
        for r in perf[perf.variant.eq('baseline')].itertuples():
            text.append(f'| {r.storm_id} | {r.station_id} | {r.primary_eligible} | {r.n} | {r.high_n} | {r.rmse_ms:.2f} | {r.high_rmse_ms:.2f} | {r.failure} |')
        text += ['', 'High-wind subsets use exactly 64 kt (32.924416 m/s). Absent subsets retain missing errors rather than zero. Report counts are not independent storm replicates.',
                 'Every event peak is censored: complete uptime is unverified. Peak magnitudes and timing offsets describe sampled observations, not continuously observed event maxima.',
                 'Coordinates use the applicable dated surface history. Nominal heights have station-specific source citations in station_metadata_audit.json; any site-continuity limitation excludes that pair from the primary metric.',
                 'Station roughness remains unknown; model one-minute and ASOS two-minute durations are retained without a fitted conversion.',
                 'See station_scores.csv for all candidates, paired changes, high-wind errors and peak timing; coverage.csv for gaps; qc_audit.csv for exclusions.', '',
                 '![Observations and frozen model curves](time_series.png)', '']
        (out/'report.md').write_text('\n'.join(text))
        (out/'manifest.json').write_text(json.dumps({'schema_version': 1, 'lock': lock,
            'evaluation_lock_sha256': sha256(args.lock), 'registration_sha256': sha256(COLLECTION/'registration.json'),
            'amendment_sha256': sha256(AMENDMENT), 'wind_access': access, 'outputs_sha256': output_hashes(out)}, indent=2)+'\n')
    print(summary.to_string(index=False)); print(f'Report: {args.out}/report.md')


if __name__ == '__main__':
    main()
