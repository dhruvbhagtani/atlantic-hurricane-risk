"""Normalize downloaded NOAA Global Hourly airport wind records, retaining a QC audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .artifacts import output_directory, output_hashes, sha256

ISD_DOCUMENTATION = 'https://www.ncei.noaa.gov/pub/data/noaa/isd-format-document.pdf'


def normalize_global_hourly(raw, storm_id, station_id, ncei_id, start, end):
    required = {'STATION', 'DATE', 'WND', 'REPORT_TYPE', 'CALL_SIGN', 'LATITUDE', 'LONGITUDE'}
    if not required.issubset(raw.columns):
        raise ValueError(f'Global Hourly CSV missing columns: {sorted(required-set(raw.columns))}')
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError('Use an increasing event window with explicit UTC offsets')
    if not raw.STATION.astype(str).eq(ncei_id).all():
        raise ValueError('Downloaded station ID does not match the requested NCEI identifier')
    raw = raw.copy()
    # ISD DATE is UTC by specification, even when CSV strings omit the offset.
    raw['time_utc'] = pd.to_datetime(raw.DATE, utc=True, errors='raise')
    selected = raw[raw.time_utc.between(start, end)].copy()
    if selected.empty:
        raise ValueError('No observations inside the event window')
    rows = []
    for row in selected.itertuples():
        fields = str(row.WND).split(',')
        if len(fields) != 5 or not fields[3].isdigit() or len(fields[3]) != 4:
            raise ValueError(f'Malformed WND field: {row.WND!r}')
        direction, direction_qc, wind_type, speed, speed_qc = fields
        speed = int(speed)
        value = np.nan if speed == 9999 else speed/10.
        reasons = []
        if speed_qc not in ['1', '5']:
            reasons.append('speed_not_passed_all_qc')
        if wind_type not in ['N', 'C', 'V'] and not (wind_type == '9' and speed == 0):
            reasons.append('unsupported_wind_type')
        if str(row.REPORT_TYPE).strip() not in ['FM-15', 'FM-16']:
            reasons.append('not_metar_or_speci')
        if str(row.CALL_SIGN).strip() != station_id:
            reasons.append('call_sign_mismatch')
        if speed != 9999 and not 0 <= value <= 90:
            reasons.append('outside_isd_speed_domain')
        quality = 'missing' if speed == 9999 else ('suspect' if reasons else 'good')
        rows.append({'storm_id': storm_id, 'station_id': station_id, 'time_utc': row.time_utc.isoformat(),
                     'sustained_ms': value, 'quality_flag': quality, 'raw_wnd': row.WND,
                     'ncei_speed_quality': speed_qc, 'ncei_wind_type': wind_type,
                     'report_type': str(row.REPORT_TYPE).strip(), 'qc_reason': ';'.join(reasons),
                     'lat': row.LATITUDE, 'lon': row.LONGITUDE})
    audit = pd.DataFrame(rows)
    normalized = []
    for timestamp, group in audit.groupby('time_utc', sort=True):
        # Never choose the largest of conflicting duplicate observations.
        unique = group[['sustained_ms', 'quality_flag', 'ncei_wind_type']].drop_duplicates()
        row = group.iloc[0].copy()
        row['raw_records_at_timestamp'] = len(group)
        if len(unique) > 1:
            row['quality_flag'] = 'suspect'
            row['sustained_ms'] = np.nan
            row['qc_reason'] = 'conflicting_duplicate_timestamp'
        normalized.append(row)
    return pd.DataFrame(normalized), audit, selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files', type=Path, nargs='+', required=True)
    parser.add_argument('--storm-id', required=True)
    parser.add_argument('--station-id', required=True)
    parser.add_argument('--ncei-id', required=True)
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    frames = []
    for path in args.files:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        frame['raw_file'] = str(path)
        frames.append(frame)
    normalized, audit, selected = normalize_global_hourly(pd.concat(frames, ignore_index=True), args.storm_id,
                                                         args.station_id, args.ncei_id, args.start, args.end)
    with output_directory(args.out) as out:
        normalized.to_csv(out/'time_series.csv', index=False)
        audit.to_csv(out/'qc_audit.csv', index=False)
        selected.to_csv(out/'raw_event_records.csv', index=False)
        manifest = {'inputs_sha256': {str(p): sha256(p) for p in args.files},
                    'storm_id': args.storm_id, 'station_id': args.station_id, 'ncei_id': args.ncei_id,
                    'start': args.start, 'end': args.end, 'documentation': ISD_DOCUMENTATION,
                    'qc_rule': 'Good requires speed QC 1 or 5; normal/variable/calm wind; METAR or SPECI; matching call sign. Other finite values remain suspect.',
                    'limitations': 'No sensor height, averaging duration, exposure or uptime is inferred from Global Hourly. Sampled winds are not event peak maxima.',
                    'code_sha256': {p.name: sha256(p) for p in Path(__file__).parent.glob('*.py')},
                    'outputs_sha256': output_hashes(out)}
        (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'Normalized {len(normalized)} timestamp records; inspect {args.out}/qc_audit.csv')


if __name__ == '__main__':
    main()
