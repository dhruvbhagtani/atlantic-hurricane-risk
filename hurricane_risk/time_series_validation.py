"""Compare station winds at report times, retaining outages and metadata limitations."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform

os.environ.setdefault('MPLCONFIGDIR', '/tmp/hurricane-risk-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .__main__ import validate_config
from .artifacts import output_directory, output_hashes, sha256
from .model import read_hurdat, interpolate_track, distance_km, rankine_wind
from .observations import prepare_observations
from .validation import scores


def modeled_at_times(track, station, times, cfg):
    lat, lon, vmax, rmw = interpolate_track(track, cfg['interpolation_minutes'], cfg['rmw_km'], times)
    radius = distance_km(lat, lon, station['lat'], station['lon'])
    return rankine_wind(radius, vmax, rmw, cfg['rankine_alpha'])*cfg['land_exposure_factor']


def evaluate_series(series, plan, tracks, cfg, out):
    peaks, coverage, _, _ = prepare_observations(series, plan)
    pairs, dense_tables, metrics = [], [], []
    for event in plan['events']:
        track = tracks[tracks.storm_id.eq(event['storm_id'])]
        if len(track) < 2:
            raise ValueError(f"Missing track for {event['storm_id']}")
        for station in event['stations']:
            frame = series[series.storm_id.eq(event['storm_id']) & series.station_id.eq(station['station_id'])].copy()
            frame['time_utc'] = pd.to_datetime(frame.time_utc, utc=True)
            frame = frame.sort_values('time_utc')
            track_start = pd.Timestamp(track.time.min()).tz_localize('UTC')
            track_end = pd.Timestamp(track.time.max()).tz_localize('UTC')
            supported = frame.time_utc.between(track_start, track_end)
            frame['modeled_ms'] = np.nan
            frame.loc[supported, 'modeled_ms'] = modeled_at_times(track, station, frame.loc[supported, 'time_utc'], cfg)
            frame['residual_ms'] = frame.modeled_ms-frame.sustained_ms
            audit = coverage[coverage.storm_id.eq(event['storm_id']) & coverage.station_id.eq(station['station_id'])].iloc[0]
            frame['metadata_issue'] = audit.metadata_issue
            frame['split'] = event['split']
            # These metrics are explicitly conditional on nominal instrument/exposure assumptions.
            good = frame[frame.quality_flag.eq('good') & frame.modeled_ms.notna()]
            if good.empty:
                raise ValueError('No good-quality samples for time-matched comparison')
            dense_times = pd.date_range(max(pd.Timestamp(event['window_start']), track_start),
                                        min(pd.Timestamp(event['window_end']), track_end), freq='1min')
            dense = pd.DataFrame({'time_utc': dense_times,
                                  'modeled_ms': modeled_at_times(track, station, dense_times, cfg),
                                  'storm_id': event['storm_id'], 'station_id': station['station_id']})
            dense_tables.append(dense)
            metrics.append({'storm_id': event['storm_id'], 'station_id': station['station_id'], 'split': event['split'],
                            'comparison': 'good_qc_samples_assuming_nominal_instrument_and_exposure',
                            'good_samples_outside_track': int((frame.quality_flag.eq('good') & ~supported).sum()),
                            'modeled_window_start': dense_times[0].isoformat(),
                            'modeled_window_end': dense_times[-1].isoformat(),
                            **scores(good.sustained_ms, good.modeled_ms),
                            'observed_sampled_peak_ms': good.sustained_ms.max(),
                            'modeled_peak_at_good_report_times_ms': good.modeled_ms.max(),
                            'modeled_peak_at_1min_ms': dense.modeled_ms.max(),
                            'incomplete_peak': int(audit.incomplete), 'metadata_issue': audit.metadata_issue,
                            'coverage': audit.coverage, 'max_gap_minutes': audit.max_gap_minutes})
            pairs.append(frame)
    pairs = pd.concat(pairs, ignore_index=True)
    metrics = pd.DataFrame(metrics)
    dense = pd.concat(dense_tables, ignore_index=True)
    pairs.to_csv(out/'time_matched_pairs.csv', index=False)
    dense.to_csv(out/'modeled_time_series.csv', index=False)
    metrics.to_csv(out/'performance.csv', index=False)
    coverage.to_csv(out/'coverage.csv', index=False)
    peaks.to_csv(out/'sampled_peaks.csv', index=False)
    plot_series(pairs, dense, plan, out)
    report(metrics, out)
    return metrics


def plot_series(pairs, dense, plan, out):
    groups = list(pairs.groupby(['storm_id', 'station_id'], sort=False))
    fig, axes = plt.subplots(len(groups), 1, figsize=(12, 3.5*len(groups)), squeeze=False)
    for ax, ((sid, station_id), frame) in zip(axes[:, 0], groups):
        event = next(e for e in plan['events'] if e['storm_id'] == sid)
        station = next(s for s in event['stations'] if s['station_id'] == station_id)
        model = dense[dense.storm_id.eq(sid) & dense.station_id.eq(station_id)]
        good = frame[frame.quality_flag.eq('good')]
        ax.plot(model.time_utc, model.modeled_ms, label='Model at 1-min intervals', color='C0')
        ax.scatter(good.time_utc, good.sustained_ms, label='Observed samples passing QC', color='black', s=14, zorder=3)
        boundaries = pd.DatetimeIndex([pd.Timestamp(event['window_start']), *good.time_utc,
                                       pd.Timestamp(event['window_end'])]).sort_values()
        first_gap = True
        for start, end in zip(boundaries[:-1], boundaries[1:]):
            if (end-start).total_seconds() > 2*60*station['cadence_minutes']:
                ax.axvspan(start, end, color='gray', alpha=.18,
                           label='Gap exceeding 2 reporting intervals' if first_gap else None)
                first_gap = False
        ax.set(title=f"{event['name']} / {station_id}: conditional comparison; instrument metadata incomplete",
               ylabel='Sustained wind (m/s)', xlabel='UTC')
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out/'time_series.png', dpi=170)
    plt.close(fig)


def report(metrics, out):
    text = ['# Time-matched station wind diagnostics', '',
            'Good provider quality flags permit a conditional sample comparison. They do not establish',
            'station-specific instrument height, site exposure, continuous uptime or event-peak capture.',
            'The model assumes local 10-m, one-minute winds and the configured uniform exposure factor;',
            'the ASOS observations use the nominal two-minute convention. No duration or height correction is fitted.',
            'All events in this run are development diagnostics; no independent test-skill claim is made.', '',
            '| Storm | Station | Good samples | Bias (m/s) | RMSE (m/s) | Observed sampled peak | Model at report times | Model at 1-min intervals |',
            '|---|---|---:|---:|---:|---:|---:|---:|']
    for r in metrics.itertuples():
        text.append(f'| {r.storm_id} | {r.station_id} | {r.n} | {r.bias_ms:.2f} | {r.rmse_ms:.2f} | {r.observed_sampled_peak_ms:.2f} | {r.modeled_peak_at_good_report_times_ms:.2f} | {r.modeled_peak_at_1min_ms:.2f} |')
    text += ['', 'Wind peaks in the table are in m/s. Observed sampled peaks are lower bounds when coverage is incomplete.',
             'A model maximum above a lower-bound observation is not evidence of peak overprediction.',
             'Sample residuals are computed only at actual reports that pass QC, without interpolating observed winds',
             'through outages. They are conditional diagnostics, not primary peak-validation scores.',
             'Model values outside the best-track time span are missing; model windows and unsupported sample counts are saved.',
             'Dense model curves evaluate the same interpolated-track Rankine equations at one-minute intervals.',
             'They do not reconstruct unobserved intensity changes or certify convergence below one minute.',
             'Coverage and metadata issues are retained in coverage.csv and performance.csv.', '',
             '![Time-matched station observations and model](time_series.png)', '']
    (out/'report.md').write_text('\n'.join(text))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--series', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--tracks', type=Path, default=Path('data/hurdat2-1851-2024-040425.txt'))
    parser.add_argument('--config', type=Path, default=Path('config.json'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    validate_config(cfg)
    series = pd.read_csv(args.series)
    plan = json.loads(args.plan.read_text())
    # A genuinely held-out protocol uses observations registration before evaluation.
    if any(e['split'] != 'development' for e in plan['events']):
        raise ValueError('This exploratory time-series diagnostic accepts development events only')
    tracks = read_hurdat(args.tracks)
    with output_directory(args.out) as out:
        evaluate_series(series, plan, tracks, cfg, out)
        manifest = {'purpose': __doc__, 'config': cfg, 'plan': plan,
                    'inputs_sha256': {str(p): sha256(p) for p in [args.series, args.plan, args.tracks, args.config]},
                    'code_sha256': {p.name: sha256(p) for p in Path(__file__).parent.glob('*.py')},
                    'versions': {'python': platform.python_version(), 'numpy': np.__version__,
                                 'pandas': pd.__version__, 'matplotlib': matplotlib.__version__},
                    'outputs_sha256': output_hashes(out)}
        (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'Time-series diagnostics: {args.out}/report.md')


if __name__ == '__main__':
    main()
