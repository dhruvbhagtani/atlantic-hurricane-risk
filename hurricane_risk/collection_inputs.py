"""Acquire the next registered collection, checking identity without reading wind values."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd
import requests

from .artifacts import output_directory, output_hashes, sha256
from .confirmation_inputs import acquire
from .confirmation_study import entries_at
from .observation_inventory import verify_collection, COLLECTION


AMENDMENT = COLLECTION/'provider_id_amendment_v1.json'
AMENDMENT_SHA256 = '2a5035fdacba7ebe51b4a813ca666628d30d06ff4674e6cefd56ca64e594b110'


def apply_provider_amendment(plan, path=AMENDMENT):
    """Apply only the pinned identity correction; retain the original plan."""
    path = Path(path)
    if sha256(path) != AMENDMENT_SHA256:
        raise ValueError('Provider identifier amendment changed')
    amendment = json.loads(path.read_text())
    if (amendment['original_plan_sha256'] != sha256(COLLECTION/'plan.json')
            or amendment['original_registration_sha256'] != sha256(COLLECTION/'registration.json')
            or amendment['wind_values_inspected'] is not False):
        raise ValueError('Provider identifier amendment does not match original registration')
    amended = deepcopy(plan)
    seen = set()
    for correction in amendment['corrections']:
        key = (correction['storm_id'], correction['station_id'])
        matches = [station for event in amended['events'] if event['storm_id'] == key[0]
                   for station in event['stations'] if station['station_id'] == key[1]]
        if len(matches) != 1 or key in seen:
            raise ValueError('Provider identifier amendment requires one registered station')
        seen.add(key)
        station = matches[0]
        if (station['expected_ncei_id'] != correction['old_expected_ncei_id']
                or sha256(correction['metadata_source_path']) != correction['metadata_source_sha256']):
            raise ValueError('Provider identifier amendment identity evidence changed')
        for name in ['expected_ncei_id', 'annual_url', 'annual_path']:
            station[name] = correction[name]
    return amended

def effective_collection():
    return apply_provider_amendment(verify_collection())


def validate_history(path, station, event):
    document = json.loads(Path(path).read_text())
    for date in [event['window_start'], event['window_end']]:
        # HOMR dates are naive calendar dates; compare in UTC with timezone removed.
        at = pd.Timestamp(date).tz_convert('UTC').tz_localize(None)
        matches = []
        for record in document['stationCollection']['stations']:
            ids = entries_at(record.get('identifiers', []), at)
            platforms = entries_at(record.get('platforms', []), at)
            if (any(i['idType'] == 'WBAN' and i['id'] == station['wban'] for i in ids)
                    and any(i['idType'] == 'ICAO' and i['id'] == station['station_id'] for i in ids)
                    and any(p['platform'] == 'ASOS' for p in platforms)
                    and entries_at(record['location']['latLonPairs'], at)):
                matches.append(record)
        if len(matches) != 1:
            raise ValueError('Require a unique dated ASOS identity and coordinates throughout the event window')


def validate_annual_identity(path, station, event):
    # Deliberately omit WND and all other measurement columns. No observed winds,
    # wind completeness or candidate scores are inspected by acquisition.
    data = pd.read_csv(path, dtype=str, keep_default_na=False, usecols=['STATION', 'DATE', 'CALL_SIGN'])
    dates = pd.to_datetime(data.DATE, utc=True, errors='raise')
    if data.empty or not data.STATION.eq(station['expected_ncei_id']).all():
        raise ValueError('Annual file station identity mismatch or empty file')
    if dates.isna().any() or not dates.dt.year.eq(int(event['storm_id'][-4:])).all():
        raise ValueError('Annual file year mismatch or missing timestamp')
    selected = data.loc[dates.between(pd.Timestamp(event['window_start']), pd.Timestamp(event['window_end']))]
    if selected.empty or not selected.CALL_SIGN.str.strip().eq(station['station_id']).any():
        raise ValueError('No matching call sign in the registered event window')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--out', type=Path, required=True, help='Fresh acquisition receipt directory')
    args = parser.parse_args()
    plan = effective_collection()
    started = datetime.now(timezone.utc).isoformat()
    records = []
    with output_directory(args.out) as out:
        for event in plan['events']:
            for station in event['stations']:
                for kind, validator in [('homr', validate_history), ('annual', validate_annual_identity)]:
                    path, url = Path(station[kind+'_path']), station[kind+'_url']
                    record = {'storm_id': event['storm_id'], 'station_id': station['station_id'],
                              'kind': kind, 'path': str(path), 'url': url,
                              'access_started_utc': datetime.now(timezone.utc).isoformat()}
                    try:
                        record['status'] = acquire(url, path, lambda p: validator(p, station, event), check_only=args.check_only)
                        record['sha256'] = sha256(path)
                    except (OSError, ValueError, KeyError, requests.RequestException) as error:
                        record['status'] = 'unavailable_or_invalid'; record['error'] = str(error)
                    records.append(record)
                    print(f"{path}: {record['status']}")
        receipt = {'schema_version': 1, 'collection_id': plan['collection_id'], 'started_utc': started,
                   'finished_utc': datetime.now(timezone.utc).isoformat(), 'check_only': args.check_only,
                   'registration_sha256': sha256(COLLECTION/'registration.json'),
                   'provider_id_amendment_sha256': sha256(AMENDMENT),
                   'wind_values_inspected': False, 'instrument_eligibility_verified': False,
                   'limitations': 'Identity-only input readiness. Wind QC, complete annual/event coverage, instrument height/duration, roughness and uptime are not certified.',
                   'inputs': records}
        (out/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        (out/'manifest.json').write_text(json.dumps({'outputs_sha256': output_hashes(out)}, indent=2)+'\n')
    if any(r['status'] == 'unavailable_or_invalid' for r in records):
        parser.exit(1, f'Some inputs are missing or invalid; see {args.out}/receipt.json. Existing files were preserved.\n')
    print('Identity checks passed. Instrument metadata audit and a frozen evaluation implementation are still required before wind scoring.')


if __name__ == '__main__':
    main()
