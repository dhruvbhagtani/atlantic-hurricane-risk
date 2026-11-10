import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hurricane_risk.collection_inputs import (
    AMENDMENT, apply_provider_amendment, validate_annual_identity, validate_history,
)
from hurricane_risk.artifacts import sha256
from hurricane_risk.observation_inventory import COLLECTION


class CollectionInputTests(unittest.TestCase):
    def setUp(self):
        # Acquisition tests must run without ignored NOAA downloads or tracks.
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        evidence = root/'homr_KILM.json'
        evidence.write_text('{"fixture": "station identity evidence"}\n')
        amendment = json.loads(AMENDMENT.read_text())
        for correction in amendment['corrections']:
            correction['metadata_source_path'] = str(evidence)
            correction['metadata_source_sha256'] = sha256(evidence)
        self.amendment_path = root/'amendment.json'
        self.amendment_path.write_text(json.dumps(amendment))
        pin = patch('hurricane_risk.collection_inputs.AMENDMENT_SHA256',
                    sha256(self.amendment_path))
        pin.start()
        self.addCleanup(pin.stop)
        self.plan = json.loads((COLLECTION/'plan.json').read_text())

    def test_amendment_preserves_registered_plan_and_other_stations(self):
        plan = self.plan
        original = json.loads(json.dumps(plan))
        amended = apply_provider_amendment(plan, self.amendment_path)
        self.assertEqual(plan, original)
        changes = []
        for before_event, after_event in zip(plan['events'], amended['events']):
            for before, after in zip(before_event['stations'], after_event['stations']):
                if before != after:
                    changes.append(after['station_id'])
                    self.assertEqual(after['expected_ncei_id'], '72302013748')
                    self.assertEqual(set(k for k in before if before[k] != after[k]),
                                     {'expected_ncei_id', 'annual_path', 'annual_url'})
        self.assertEqual(changes, ['KILM'])

    def test_amendment_rejects_tampering_and_changed_identity_evidence(self):
        plan = self.plan
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'amendment.json'
            path.write_text(self.amendment_path.read_text()+' ')
            with self.assertRaisesRegex(ValueError, 'amendment changed'):
                apply_provider_amendment(plan, path)
        def changed_evidence(path):
            return 'changed' if str(path).endswith('homr_KILM.json') else sha256(path)
        with patch('hurricane_risk.collection_inputs.sha256', side_effect=changed_evidence):
            with self.assertRaisesRegex(ValueError, 'identity evidence changed'):
                apply_provider_amendment(plan, self.amendment_path)

    def test_identity_check_does_not_parse_wind_values(self):
        station = {'station_id': 'TEST', 'expected_ncei_id': '01234567890'}
        event = {'storm_id': 'AL012020', 'window_start': '2020-08-01T00:00:00Z', 'window_end': '2020-08-03T00:00:00Z'}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'annual.csv'
            path.write_text('STATION,DATE,CALL_SIGN,WND\n01234567890,2020-08-02T12:00:00,TEST,INTENTIONALLY_UNPARSED\n')
            validate_annual_identity(path, station, event)
            station['expected_ncei_id'] = 'wrong'
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                validate_annual_identity(path, station, event)

    def test_dated_surface_identity_is_required_for_both_window_ends(self):
        date = {'beginDate': '2000-01-01', 'endDate': 'Present'}
        record = {'identifiers': [{'idType': 'ICAO', 'id': 'TEST', 'date': date},
                                  {'idType': 'WBAN', 'id': '01234', 'date': date}],
                  'platforms': [{'platform': 'ASOS', 'date': date}],
                  'location': {'latLonPairs': [{'date': date}]}}
        station = {'station_id': 'TEST', 'wban': '01234'}
        event = {'window_start': '2020-08-01T00:00:00Z', 'window_end': '2020-08-03T00:00:00Z'}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'history.json'
            path.write_text(json.dumps({'stationCollection': {'stations': [record]}}))
            validate_history(path, station, event)
            record['platforms'][0]['date'] = {'beginDate': '2020-08-02', 'endDate': 'Present'}
            path.write_text(json.dumps({'stationCollection': {'stations': [record]}}))
            with self.assertRaisesRegex(ValueError, 'unique dated ASOS'):
                validate_history(path, station, event)
