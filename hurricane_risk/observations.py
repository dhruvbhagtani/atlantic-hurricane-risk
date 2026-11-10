"""Prepare auditable station peaks from quality-flagged UTC time series and an event plan."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .artifacts import output_directory, output_hashes, sha256
from .model import KNOT_TO_MS


def prepare_observations(series, plan, min_coverage=.95, max_gap_intervals=2.):
    required = {'storm_id', 'station_id', 'time_utc', 'sustained_ms', 'quality_flag'}
    if not required.issubset(series.columns) or series.empty:
        raise ValueError(f'Need nonempty time series with columns {sorted(required)}')
    if not 0 < min_coverage <= 1 or not np.isfinite(max_gap_intervals) or max_gap_intervals < 1:
        raise ValueError('Coverage must be in (0,1] and maximum gap at least one interval')
    series = series.copy()
    # Reject naive input timestamps instead of silently guessing their timezone.
    if any(pd.Timestamp(t).tzinfo is None for t in series.time_utc):
        raise ValueError('Observation times must contain an explicit UTC offset')
    series['time_utc'] = pd.to_datetime(series.time_utc, utc=True, errors='raise')
    series['sustained_ms'] = pd.to_numeric(series.sustained_ms, errors='raise')
    if series.duplicated(['storm_id', 'station_id', 'time_utc']).any():
        raise ValueError('Duplicate event/station/timestamp')
    if not series.quality_flag.isin(['good', 'suspect', 'missing']).all():
        raise ValueError('Quality flags must be good, suspect or missing')
    good = series.quality_flag.eq('good')
    if not np.isfinite(series.loc[good, 'sustained_ms']).all() or not series.loc[good, 'sustained_ms'].between(0, 130).all():
        raise ValueError('Good sustained winds must be finite and in [0,130] m/s')
    if not isinstance(plan.get('events'), list) or not plan['events']:
        raise ValueError('Plan must contain events')
    if not plan.get('quality_control_description') or not plan.get('quality_control_reference'):
        raise ValueError('Plan requires a quality-control description and reference')
    peaks, audit, sources, splits, declared = [], [], {}, {'development': [], 'test': []}, set()
    for event in plan['events']:
        sid = event['storm_id']
        if sid in sources or event['split'] not in splits:
            raise ValueError('Each storm must have one development/test assignment')
        if not isinstance(event.get('best_track_provenance'), str) or not event['best_track_provenance'].strip():
            raise ValueError('Document possible use of station observations in best-track construction')
        start, end = pd.Timestamp(event['window_start']), pd.Timestamp(event['window_end'])
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError('Event windows need explicit UTC offsets')
        if start >= end:
            raise ValueError('Event windows need explicit UTC offsets and start < end')
        start, end = start.tz_convert('UTC'), end.tz_convert('UTC')
        source_id = sid
        sources[source_id] = {'storm_id': sid, 'name': event['name'],
                              'window_start': start.tz_localize(None).isoformat(),
                              'window_end': end.tz_localize(None).isoformat(),
                              'product': event['product'], 'url': event['url'],
                              'section': 'Quality-flagged time series; see coverage.csv and input plan',
                              'best_track_provenance': event['best_track_provenance']}
        splits[event['split']].append(sid)
        if not event['stations']:
            raise ValueError('Each event requires predeclared stations')
        for station in event['stations']:
            station_id = station['station_id']
            key = (sid, station_id)
            if key in declared:
                raise ValueError('Duplicate station in event plan')
            declared.add(key)
            lat, lon = station['lat'], station['lon']
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError('Invalid station coordinates')
            cadence = station['cadence_minutes']
            if not isinstance(cadence, (int, float)) or not np.isfinite(cadence) or cadence <= 0:
                raise ValueError('Station cadence must be finite and positive')
            delta = pd.Timedelta(minutes=cadence)
            expected = pd.date_range(start, end, freq=delta)
            frame = series[series.storm_id.eq(sid) & series.station_id.eq(station_id)]
            if not frame.time_utc.between(start, end).all():
                raise ValueError(f'Time series outside declared window: {key}')
            valid = frame[frame.quality_flag.eq('good')].sort_values('time_utc')
            # Count at most one good report per expected cadence bin.
            bins = ((valid.time_utc-start) // delta).nunique()
            coverage = bins/len(expected)
            times = pd.DatetimeIndex([start, *valid.time_utc, end]).sort_values()
            max_gap = float(np.max(np.diff(times.asi8))/60e9)
            if type(station.get('uptime_confirmed')) is not bool:
                raise ValueError('uptime_confirmed must explicitly be true or false')
            incomplete = (coverage < min_coverage or max_gap > max_gap_intervals*cadence
                          or not station['uptime_confirmed'])
            issues = []
            if station.get('height_m') != 10:
                issues.append('height_not_confirmed_10m')
            if station.get('averaging_minutes') not in [1, 2]:
                issues.append('duration_not_1_or_2min_sustained')
            if not isinstance(station.get('exposure'), str) or not station['exposure'].strip() or station['exposure'].lower() == 'unknown':
                issues.append('unknown_site_exposure')
            if not station.get('metadata_reference'):
                issues.append('missing_instrument_metadata_reference')
            if not station.get('uptime_reference'):
                issues.append('missing_uptime_reference')
            if len(valid):
                peak = valid.loc[valid.sustained_ms.idxmax()]
                value, timestamp = float(peak.sustained_ms), peak.time_utc
            else:
                value, timestamp = np.nan, start
            # Calm-only or missing series cannot provide a positive peak comparison.
            if value == 0:
                value = np.nan
                issues.append('no_positive_peak')
            peaks.append({'storm_id': sid, 'station_id': station_id, 'lat': lat, 'lon': lon,
                          'sustained_kt': value/KNOT_TO_MS, 'peak_time_utc': timestamp.tz_localize(None).isoformat(),
                          'incomplete': int(incomplete), 'metadata_issue': ';'.join(issues), 'source_id': source_id})
            audit.append({'storm_id': sid, 'station_id': station_id, 'split': event['split'],
                          'expected_reports': len(expected), 'reports': len(frame), 'good_reports': len(valid),
                          'good_cadence_bins': bins, 'coverage': coverage, 'max_gap_minutes': max_gap,
                          'incomplete': int(incomplete), 'metadata_issue': ';'.join(issues),
                          'uptime_confirmed': station['uptime_confirmed'], 'exposure': station.get('exposure', ''),
                          'height_m': station.get('height_m'), 'averaging_minutes': station.get('averaging_minutes')})
    actual = set(zip(series.storm_id, series.station_id))
    if actual - declared:
        raise ValueError(f'Time series contains undeclared event/stations: {sorted(actual-declared)}')
    # Mixed durations are retained per station; no undocumented duration conversion is applied.
    source_document = {'sources': sources, 'quality_control_description': plan['quality_control_description'],
                       'quality_control_reference': plan['quality_control_reference'],
                       'measurement': {'variable': 'maximum of good sustained wind samples', 'units': 'knots',
                                       'height_m': 'per station in plan', 'averaging_minutes': 'per station in plan'},
                       'independence': 'Split membership is not proof of independence from best-track analysis.',
                       'curation': ['All plan stations retained; incomplete or metadata-incompatible peaks excluded from primary scores.']}
    return pd.DataFrame(peaks), pd.DataFrame(audit), source_document, splits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--series', type=Path)
    parser.add_argument('--lock-plan', action='store_true', help='Register the event plan before inspecting test observations')
    parser.add_argument('--registration', type=Path, help='Previously registered plan directory; required for test events')
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--min-coverage', type=float, default=.95)
    parser.add_argument('--max-gap-intervals', type=float, default=2.)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    if args.lock_plan:
        if args.series or args.registration:
            parser.error('--lock-plan is used without --series or --registration')
        with output_directory(args.out) as out:
            (out/'plan.json').write_text(args.plan.read_text())
            (out/'registration.json').write_text(json.dumps({
                'plan_sha256': sha256(args.plan),
                'registered_utc': datetime.now(timezone.utc).isoformat(),
                'purpose': 'Event/station/split declaration before evaluation; not proof of data independence'
            }, indent=2)+'\n')
        print(f'Plan registered: {args.out}/registration.json')
        return
    if not args.series:
        parser.error('--series is required unless using --lock-plan')
    has_test = any(e.get('split') == 'test' for e in plan.get('events', []))
    registration = None
    if args.registration:
        registration = json.loads((args.registration/'registration.json').read_text())
        if registration['plan_sha256'] != sha256(args.plan) or sha256(args.registration/'plan.json') != sha256(args.plan):
            raise ValueError('Plan changed after registration; create a new experiment instead of modifying the test split')
    elif has_test:
        raise ValueError('Test events require --registration from an earlier --lock-plan run')
    series = pd.read_csv(args.series, keep_default_na=False)
    series['sustained_ms'] = series.sustained_ms.replace('', np.nan)
    peaks, audit, sources, splits = prepare_observations(series, plan, args.min_coverage, args.max_gap_intervals)
    sources['registration'] = registration
    with output_directory(args.out) as out:
        peaks.to_csv(out/'station_peaks.csv', index=False)
        audit.to_csv(out/'coverage.csv', index=False)
        series.to_csv(out/'time_series.csv', index=False)
        (out/'sources.json').write_text(json.dumps(sources, indent=2)+'\n')
        (out/'splits.json').write_text(json.dumps(splits, indent=2)+'\n')
        manifest = {'inputs_sha256': {str(p): sha256(p) for p in [args.series, args.plan]},
                    'registration': registration, 'plan': plan, 'min_coverage': args.min_coverage, 'max_gap_intervals': args.max_gap_intervals,
                    'code_sha256': {p.name: sha256(p) for p in Path(__file__).parent.glob('*.py')},
                    'outputs_sha256': output_hashes(out)}
        (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'Prepared {len(peaks)} station/event peaks; coverage audit: {args.out}/coverage.csv')


if __name__ == '__main__':
    main()
