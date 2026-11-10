"""Acquire and check the registered Laura inputs without evaluating wind skill."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

import pandas as pd
import requests

from .artifacts import sha256
from .confirmation_study import REGISTRATION_SHA256, station_metadata, validate_frozen_model
from .global_hourly import normalize_global_hourly

HOMR_URL = ('https://www.ncei.noaa.gov/access/homr/services/station/search'
            '?qid=WBAN:03937&date=all&definitions=false&phrData=true')


def validate_annual(path, event):
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    dates = pd.to_datetime(raw['DATE'], utc=True, errors='raise')
    if raw.empty or dates.isna().any() or not dates.dt.year.eq(2020).all():
        raise ValueError('Expected nonempty 2020 station-year observations')
    # Validate provider schema, station identity and event-window availability.
    # This does not print winds or compute candidate errors.
    normalize_global_hourly(raw, event['storm_id'], event['station_id'], event['ncei_id'],
                           event['window_start'], event['window_end'])


def acquire(url, destination, validator, *, check_only=False):
    """Publish only validated downloads; never replace an existing input."""
    destination = Path(destination)
    if destination.exists():
        validator(destination)
        return 'validated existing input'
    if check_only:
        raise FileNotFoundError(f'Missing input: {destination}\nDownload: {url}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f'.{destination.name}-', suffix='.part',
                                         dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            with requests.get(url, stream=True, timeout=(15, 30)) as response:
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    stream.write(chunk)
        validator(temporary)
        # A hard link publishes atomically and refuses concurrent overwrites.
        destination.hardlink_to(temporary)
        return 'downloaded and validated input'
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true', help='Validate local inputs without network access')
    args = parser.parse_args()
    registration = Path('data/validation/laura_confirmation_registration.json')
    if sha256(registration) != REGISTRATION_SHA256:
        parser.exit(1, 'Confirmation registration changed\n')
    event = json.loads(registration.read_text())
    validate_frozen_model(event, Path('data/validation/structural_study_lock.json'))

    def validate_history(path):
        station_metadata(json.loads(path.read_text()), event)

    inputs = [
        (event['annual_url'], Path('data/raw/global_hourly/2020/72240003937.csv'),
         lambda path: validate_annual(path, event)),
        (HOMR_URL, Path('data/raw/metadata/homr_KLCH.json'), validate_history),
    ]
    failures = []
    for url, destination, validator in inputs:
        try:
            status = acquire(url, destination, validator, check_only=args.check_only)
            print(f'{destination}: {status}; SHA-256 {sha256(destination)}')
        except (OSError, ValueError, KeyError, requests.RequestException) as error:
            failures.append(f'{destination}: {error}')
    if failures:
        parser.exit(1, '\n'.join(failures) + '\nExisting inputs were preserved. '
                    'Move invalid files aside before retrying.\n')
    print('Laura inputs ready. Run python -m hurricane_risk.confirmation_study '
          '--out outputs/laura-confirmation-run1')


if __name__ == '__main__':
    main()
