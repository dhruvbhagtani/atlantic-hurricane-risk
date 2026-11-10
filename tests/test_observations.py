import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from hurricane_risk.observations import prepare_observations
from hurricane_risk.validation import load_observations


def fixtures():
    station = {'station_id': 'TEST', 'lat': 25., 'lon': -80., 'height_m': 10,
               'averaging_minutes': 2, 'exposure': 'open airport', 'cadence_minutes': 10,
               'uptime_confirmed': True, 'metadata_reference': 'fixture instrument log',
               'uptime_reference': 'fixture uptime log'}
    event = {'storm_id': 'AL012000', 'name': 'FABRICATED', 'split': 'development',
             'window_start': '2000-09-01T00:00:00Z', 'window_end': '2000-09-01T01:00:00Z',
             'product': 'FABRICATED fixture', 'url': 'https://example.invalid/fixture',
             'best_track_provenance': 'Fabricated tracks; test only', 'stations': [station]}
    plan = {'quality_control_description': 'FABRICATED fixture flags',
            'quality_control_reference': 'fixture only', 'events': [event]}
    series = pd.DataFrame({'storm_id': ['AL012000']*7, 'station_id': ['TEST']*7,
                           'time_utc': pd.date_range(event['window_start'], periods=7, freq='10min'),
                           'sustained_ms': [10., 15., 20., 30., 20., 15., 10.], 'quality_flag': 'good'})
    return series, plan


class ObservationTests(unittest.TestCase):
    def test_quality_flags_and_coverage_preserve_lower_bounds(self):
        series, plan = fixtures()
        peaks, audit, sources, _ = prepare_observations(series, plan)
        self.assertEqual(peaks.incomplete.iloc[0], 0)
        self.assertEqual(audit.coverage.iloc[0], 1)
        series.loc[3, ['quality_flag', 'sustained_ms']] = ['suspect', 120.]
        peaks, audit, sources, _ = prepare_observations(series, plan)
        self.assertEqual(peaks.incomplete.iloc[0], 1)
        self.assertAlmostEqual(peaks.sustained_kt.iloc[0]*.514444, 20.)
        self.assertEqual(audit.max_gap_minutes.iloc[0], 20)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'peaks.csv'
            peaks.to_csv(path, index=False)
            self.assertFalse(load_observations(path, sources).primary.any())

    def test_missing_stations_and_unconfirmed_metadata_remain_excluded(self):
        series, plan = fixtures()
        station = copy.deepcopy(plan['events'][0]['stations'][0])
        station['station_id'] = 'OFFLINE'
        plan['events'][0]['stations'].append(station)
        plan['events'][0]['stations'][0]['height_m'] = 20
        plan['events'][0]['stations'][0]['uptime_confirmed'] = False
        peaks, audit, _, _ = prepare_observations(series, plan)
        self.assertEqual(len(peaks), 2)
        self.assertTrue(peaks.incomplete.eq(1).all())
        self.assertIn('height_not_confirmed', peaks.metadata_issue.iloc[0])
        self.assertEqual(audit.coverage.iloc[1], 0)

    def test_duplicates_and_undeclared_stations_rejected(self):
        series, plan = fixtures()
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            prepare_observations(pd.concat([series, series.iloc[:1]]), plan)
        series.loc[0, 'station_id'] = 'UNDECLARED'
        with self.assertRaisesRegex(ValueError, 'undeclared'):
            prepare_observations(series, plan)

    def test_registered_test_plan_cannot_be_changed(self):
        series, plan = fixtures()
        plan['events'][0]['split'] = 'test'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path, series_path = root/'plan.json', root/'series.csv'
            plan_path.write_text(json.dumps(plan))
            series.to_csv(series_path, index=False)
            base = [sys.executable, '-m', 'hurricane_risk.observations', '--plan', str(plan_path)]
            lock = root/'registration'
            result = subprocess.run(base+['--lock-plan', '--out', str(lock)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            command = base+['--series', str(series_path), '--registration', str(lock), '--out', str(root/'prepared')]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            plan['events'][0]['stations'][0]['lat'] += .1
            plan_path.write_text(json.dumps(plan))
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Plan changed after registration', result.stderr)
