"""Explore Laura timing and geometry without fitting or changing the frozen models."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .artifacts import output_directory, output_hashes, sha256
from .confirmation_study import validate_frozen_model
from .model import distance_km, interpolate_track, read_hurdat, KNOT_TO_MS
from .time_series_validation import modeled_at_times, plt
from .validation import scores


def geometry(track, station, times, cfg):
    lat, lon, vmax, rmw = interpolate_track(track, cfg['interpolation_minutes'], cfg['rmw_km'], times)
    radius = distance_km(lat, lon, station['lat'], station['lon'])
    return pd.DataFrame({'time_utc': pd.to_datetime(times, utc=True), 'center_lat': lat,
                         'center_lon': lon, 'vmax_ms': vmax, 'effective_rmw_km': rmw,
                         'center_distance_km': radius, 'distance_over_rmw': radius/rmw})


def sensitivity_cases():
    # Diagnostic perturbations fixed in code, never searched or ranked by error.
    return ([{'name': 'baseline', 'time_shift_minutes': 0, 'east_km': 0, 'north_km': 0, 'rmw_km': 35}]
            + [{'name': f'time_{x:+d}min', 'time_shift_minutes': x} for x in [-30, -15, 15, 30]]
            + [{'name': f'{axis}_{x:+d}km', axis+'_km': x} for axis in ['east', 'north'] for x in [-10, 10]]
            + [{'name': f'fallback_rmw_{x}km', 'rmw_km': x} for x in [25, 45]])


def perturbation_predictions(track, station, times, cfg, cases):
    """Use one common support mask across cases; positive shift evaluates model later."""
    times = pd.DatetimeIndex(pd.to_datetime(times, utc=True))
    first, last = pd.Timestamp(track.time.min(), tz='UTC'), pd.Timestamp(track.time.max(), tz='UTC')
    common = np.ones(len(times), dtype=bool)
    for case in cases:
        shifted = times + pd.Timedelta(minutes=case.get('time_shift_minutes', 0))
        common &= (shifted >= first) & (shifted <= last)
    rows = []
    for case in cases:
        adjusted = track.copy()
        adjusted['lat'] = track.lat + np.rad2deg(case.get('north_km', 0)/6371.0088)
        adjusted['lon'] = track.lon + np.rad2deg(case.get('east_km', 0)/(6371.0088*np.cos(np.deg2rad(track.lat))))
        shifted = times[common] + pd.Timedelta(minutes=case.get('time_shift_minutes', 0))
        values = modeled_at_times(adjusted, station, shifted, {**cfg, 'rmw_km': case.get('rmw_km', cfg['rmw_km'])})
        rows.append(pd.DataFrame({'case': case['name'], 'time_utc': times[common],
                                  'model_evaluation_time_utc': shifted, 'modeled_ms': values}))
    return pd.concat(rows, ignore_index=True), common


def peak_summary(frame, value_column):
    maximum = frame[value_column].max()
    tied = frame.loc[frame[value_column].eq(maximum), 'time_utc']
    return maximum, tied.iloc[0], len(tied)


def plot_diagnostic(pairs, dense, geom, window, out, name):
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    visible_dense = dense[dense.time_utc.between(*window)]
    visible_geom = geom[geom.time_utc.between(*window)]
    for variant, group in visible_dense.groupby('variant', sort=False):
        axes[0].plot(group.time_utc, group.modeled_ms, label=variant, lw=1.2)
    good = pairs[pairs.sample_eligible & pairs.variant.eq('baseline')]
    visible_good = good[good.time_utc.between(*window)]
    axes[0].scatter(visible_good.time_utc, visible_good.sustained_ms, s=22, c='black', label='Good observed reports', zorder=5)
    axes[0].axhline(64*KNOT_TO_MS, color='gray', ls=':', label='64 kt')
    axes[0].set(ylabel='Sustained wind (m/s)', title='Laura / KLCH: fixed models and observed report times')
    axes[0].legend(fontsize=7, ncol=2)
    axes[1].plot(visible_geom.time_utc, visible_geom.center_distance_km, label='Center distance')
    axes[1].plot(visible_geom.time_utc, visible_geom.effective_rmw_km, label='Effective RMW', ls='--')
    axes[1].set(ylabel='Distance (km)'); axes[1].legend(fontsize=8)
    for variant, group in pairs[pairs.sample_eligible & pairs.time_utc.between(*window)].groupby('variant', sort=False):
        axes[2].scatter(group.time_utc, group.residual_ms, s=14, label=variant)
    axes[2].axhline(0, color='black', lw=.7)
    axes[2].set(ylabel='Model minus observed (m/s)', xlabel='UTC, August 2020', xlim=window)
    boundaries = pd.DatetimeIndex([dense.time_utc.min(), *good.time_utc, dense.time_utc.max()]).sort_values()
    for left, right in zip(boundaries[:-1], boundaries[1:]):
        if (right-left).total_seconds() > 120*60:
            for ax in axes:
                ax.axvspan(left, right, color='gray', alpha=.15)
    fig.text(.01, .005, 'Gray: gaps > 2 hours, including window boundaries. Observations are never interpolated. Models: 1-min sustained; observations: 2-min.', fontsize=8)
    fig.tight_layout(rect=(0, .025, 1, 1)); fig.savefig(out/name, dpi=170); plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, default=Path('reports/laura_confirmation'))
    parser.add_argument('--tracks', type=Path, default=Path('data/hurdat2-1851-2024-040425.txt'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    study = json.loads((args.study/'manifest.json').read_text())
    if output_hashes(args.study) != study['outputs_sha256']:
        raise ValueError('Archived confirmation output hashes changed')
    event, cfg = study['registration'], study['config']
    validate_frozen_model(event, Path('data/validation/structural_study_lock.json'))
    if sha256(args.tracks) != study['inputs_sha256'][str(args.tracks)]:
        raise ValueError('Tracks differ from the confirmation input')
    inputs = [args.tracks, args.study/'manifest.json', args.study/'time_matched_pairs.csv', args.study/'station_metadata.json']
    hashes = {str(p): sha256(p) for p in inputs}
    source_hashes = {p.name: sha256(p) for p in Path(__file__).parent.glob('*.py')}
    station = json.loads((args.study/'station_metadata.json').read_text())
    track = read_hurdat(args.tracks); track = track[track.storm_id.eq(event['storm_id'])]
    pairs = pd.read_csv(args.study/'time_matched_pairs.csv')
    pairs['time_utc'] = pd.to_datetime(pairs.time_utc, utc=True)
    good = pairs[pairs.variant.eq('baseline') & pairs.sample_eligible].sort_values('time_utc')
    times = pd.date_range(event['window_start'], event['window_end'], freq='1min')
    geom = geometry(track, station, times, cfg)
    observed_peak, observed_time, observed_ties = peak_summary(good, 'sustained_ms')
    dense, timing = [], []
    for candidate in event['candidates']:
        variant_cfg = {**cfg, **candidate['overrides']}
        archived = pairs[pairs.variant.eq(candidate['name']) & pairs.sample_eligible].sort_values('time_utc')
        predicted = modeled_at_times(track, station, archived.time_utc, variant_cfg)
        np.testing.assert_allclose(predicted, archived.modeled_ms, rtol=1e-12, atol=1e-12)
        frame = pd.DataFrame({'time_utc': times, 'modeled_ms': modeled_at_times(track, station, times, variant_cfg), 'variant': candidate['name']})
        dense.append(frame)
        peak, at, ties = peak_summary(frame, 'modeled_ms')
        matched_peak, matched_at, matched_ties = peak_summary(archived, 'modeled_ms')
        timing.append({'variant': candidate['name'], 'observed_sampled_peak_ms': observed_peak,
                       'observed_sampled_peak_time_utc': observed_time, 'observed_peak_ties': observed_ties,
                       'modeled_dense_peak_ms': peak, 'modeled_dense_peak_time_utc': at, 'dense_peak_ties': ties,
                       'dense_peak_offset_from_sampled_peak_minutes': (at-observed_time).total_seconds()/60,
                       'modeled_report_time_peak_ms': matched_peak, 'modeled_report_time_peak_utc': matched_at,
                       'report_peak_offset_from_sampled_peak_minutes': (matched_at-observed_time).total_seconds()/60,
                       'report_peak_ties': matched_ties})
    dense = pd.concat(dense, ignore_index=True)
    cases = sensitivity_cases()
    predictions, common = perturbation_predictions(track, station, good.time_utc, cfg, cases)
    predictions = predictions.merge(good[['time_utc', 'sustained_ms']], on='time_utc', validate='many_to_one')
    predictions['residual_ms'] = predictions.modeled_ms-predictions.sustained_ms
    metrics = []
    for case, group in predictions.groupby('case', sort=False):
        for subset, mask in [('all_common_good_reports', np.ones(len(group), bool)), ('hurricane_force', group.sustained_ms >= 64*KNOT_TO_MS)]:
            sub = group[mask]
            metrics.append({'case': case, 'subset': subset, **(scores(sub.sustained_ms, sub.modeled_ms) if len(sub) else {'n': 0, 'bias_ms': np.nan, 'rmse_ms': np.nan})})
    metrics = pd.DataFrame(metrics)
    closest = geom.loc[geom.center_distance_km.idxmin()]
    high = good[good.sustained_ms >= 64*KNOT_TO_MS].merge(geometry(track, station, good[good.sustained_ms >= 64*KNOT_TO_MS].time_utc, cfg), on='time_utc', validate='one_to_one')
    with output_directory(args.out) as out:
        geom.to_csv(out/'track_geometry.csv', index=False)
        dense.to_csv(out/'modeled_time_series.csv', index=False)
        pd.DataFrame(timing).to_csv(out/'peak_timing.csv', index=False)
        high.to_csv(out/'hurricane_force_geometry.csv', index=False)
        predictions.to_csv(out/'sensitivity_pairs.csv', index=False)
        metrics.to_csv(out/'sensitivity_scores.csv', index=False)
        (out/'sensitivity_plan.json').write_text(json.dumps({'cases': cases, 'positive_time_shift': 'Model evaluated at observation time plus shift; observations never shifted or interpolated.', 'rule': 'All one-factor perturbations retained in declared order; no fit, ranking or production parameter change.'}, indent=2)+'\n')
        plot_diagnostic(pairs, dense, geom, (times[0], times[-1]), out, 'full_window.png')
        plot_diagnostic(pairs, dense, geom, (pd.Timestamp('2020-08-27T03:00Z'), pd.Timestamp('2020-08-27T10:00Z')), out, 'core_passage.png')
        text = ['# Laura timing and geometry diagnostic', '',
                'This is an exploratory diagnostic of already examined observations. All five registered candidate predictions reproduce the archived confirmation at eligible report times.',
                'No parameter is fitted, no perturbation is selected, and production defaults and frozen model code remain unchanged.', '',
                f"Interpolated closest approach is {closest.center_distance_km:.2f} km at {closest.time_utc}. Effective RMW there is {closest.effective_rmw_km:.2f} km.",
                f"Track fixes missing RMW: {track.rmw_km.isna().mean():.1%}; the effective radius includes the declared fallback.",
                f'Observed sampled maximum is {observed_peak:.2f} m/s at {observed_time}. Missing uptime means its timing is not a known complete-event peak time.', '',
                f"The baseline dense maximum is {timing[0]['modeled_dense_peak_ms']:.2f} m/s at {timing[0]['modeled_dense_peak_time_utc']}, with a signed offset of {timing[0]['dense_peak_offset_from_sampled_peak_minutes']:+.0f} minutes relative to the observed sampled maximum.", '',
                '| UTC report | Observed (m/s) | Baseline (m/s) | Residual (m/s) | Center distance (km) | Distance/RMW |',
                '|---|---:|---:|---:|---:|---:|']
        for r in high.itertuples():
            text.append(f'| {r.time_utc} | {r.sustained_ms:.2f} | {r.modeled_ms:.2f} | {r.residual_ms:+.2f} | {r.center_distance_km:.2f} | {r.distance_over_rmw:.2f} |')
        text += ['', '![Core passage](core_passage.png)', '',
                 'The sign change is consistent with a timing or geometry mismatch; this does not identify a cause. The idealized vortex also imposes an eyewall and calm-center structure.',
                 'Positive time shifts evaluate the model later than the report; east/north shifts move every original track fix by the stated small displacement.',
                 'RMW cases change the missing-value fallback only. All perturbations are one-factor exploratory sensitivities, not estimated uncertainty bounds or proposed corrections.',
                 f'All sensitivities use the same {int(common.sum())} eligible reports; {int((~common).sum())} reports lack common shifted-track support.', '',
                 '| Case | Reports | Overall RMSE (m/s) | Hurricane-force RMSE (m/s) |', '|---|---:|---:|---:|']
        for case in cases:
            group = metrics[metrics.case.eq(case['name'])].set_index('subset')
            text.append(f"| {case['name']} | {group.loc['all_common_good_reports','n']:.0f} | {group.loc['all_common_good_reports','rmse_ms']:.2f} | {group.loc['hurricane_force','rmse_ms']:.2f} |")
        text += ['', 'The diagnostic table retains the declared order; it must not be used to choose a correction on Laura.',
                 'Peak timing tables report the first occurrence and tie counts for dense model maxima and model maxima at actual eligible reports. Timing offsets are descriptive comparisons to a censored sampled peak.',
                 'One-minute curves interpolate best tracks; they do not reconstruct unobserved rapid changes. Wind averaging duration and unknown site exposure remain limitations.', '',
                 '![Full registered window and gaps](full_window.png)', '']
        (out/'report.md').write_text('\n'.join(text))
        (out/'manifest.json').write_text(json.dumps({'schema_version': 1, 'inputs_sha256': hashes, 'code_sha256': source_hashes, 'config': cfg, 'outputs_sha256': output_hashes(out)}, indent=2)+'\n')
    print(f'Timing diagnostic: {args.out}/report.md')


if __name__ == '__main__':
    main()
