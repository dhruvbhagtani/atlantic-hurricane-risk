import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from hurricane_risk.artifacts import sha256
from hurricane_risk.observation_inventory import build_inventory, verify_collection


class InventoryTests(unittest.TestCase):
    def test_unknown_counts_are_missing_and_examined_tests_are_not_relabelled(self):
        peaks = pd.DataFrame([{'storm_id': 'OLD', 'station_id': 'A', 'incomplete': 1,
                               'metadata_issue': '', 'sustained_kt': 80},
                              {'storm_id': 'PEAK', 'station_id': 'B', 'incomplete': 0,
                               'metadata_issue': '', 'sustained_kt': 80}])
        coverage = pd.DataFrame([{'storm_id': 'OLD', 'station_id': 'A', 'split': 'test',
                                  'reports': 2, 'good_reports': 2, 'coverage': .5,
                                  'max_gap_minutes': 120, 'incomplete': 1, 'height_m': 10,
                                  'averaging_minutes': 2, 'uptime_confirmed': False, 'metadata_issue': 'unknown_site_exposure'}])
        pairs = pd.DataFrame({'storm_id': ['OLD']*4, 'station_id': ['A']*4,
                              'variant': ['baseline', 'baseline', 'other', 'other'],
                              'sample_eligible': [True]*4, 'sustained_ms': [33, 10, 33, 10]})
        plan = {'events': [{'storm_id': 'NEW', 'stations': [{'station_id': 'C', 'metadata_status': 'pending'}]}]}
        result = build_inventory(peaks, [(coverage, pairs, 'fixture')], plan).set_index('storm_id')
        self.assertEqual(result.loc['OLD', 'hurricane_force_reports'], 1)
        self.assertEqual(result.loc['OLD', 'historical_role'], 'test')
        self.assertEqual(result.loc['OLD', 'future_tuning_role'], 'development_only')
        self.assertTrue(pd.isna(result.loc['PEAK', 'hurricane_force_reports']))
        self.assertTrue(pd.isna(result.loc['NEW', 'good_reports']))
        self.assertEqual(result.loc['NEW', 'future_tuning_role'], 'held_out')
        plan['events'][0]['storm_id'] = 'OLD'; plan['events'][0]['stations'][0]['station_id'] = 'A'
        with self.assertRaisesRegex(ValueError, 'already examined'):
            build_inventory(peaks, [(coverage, pairs, 'fixture')], plan)

    def test_registration_rejects_plan_and_frozen_source_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'model.py'; source.write_text('frozen')
            plan = root/'plan.json'; plan.write_text(json.dumps({'examined_storms_excluded': ['OLD'], 'events': [{'storm_id': 'NEW'}]}))
            lock = root/'registration.json'; lock.write_text(json.dumps({'plan_sha256': sha256(plan), 'frozen_inputs_sha256': {str(source): sha256(source)}}))
            with patch('hurricane_risk.observation_inventory.REGISTRATION_SHA256', sha256(lock)):
                verify_collection(root)
                source.write_text('changed')
                with self.assertRaisesRegex(ValueError, 'frozen input changed'):
                    verify_collection(root)
                source.write_text('frozen'); plan.write_text('{}')
                with self.assertRaisesRegex(ValueError, 'plan changed'):
                    verify_collection(root)
            with self.assertRaisesRegex(ValueError, 'registration changed'):
                verify_collection(root)
