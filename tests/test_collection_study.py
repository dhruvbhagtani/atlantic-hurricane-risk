import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from hurricane_risk.collection_study import summarize, primary_eligibility, evaluate


class CollectionStudyTests(unittest.TestCase):
    def test_registered_weights_are_station_then_storm_and_missing_pairs_invalidate_primary(self):
        plan = {'candidates': [{'name': 'baseline'}], 'events': [
            {'storm_id': 'A', 'stations': ['one', 'two']}, {'storm_id': 'B', 'stations': ['three', 'four']}]}
        perf = pd.DataFrame({'variant': ['baseline']*4, 'storm_id': ['A', 'A', 'B', 'B'],
                             'primary_eligible': [True]*4, 'rmse_ms': [2, 4, 10, 20],
                             'bias_ms': [1]*4, 'n': [1000, 1, 1, 1], 'high_n': [0]*4})
        events, total = summarize(perf, plan)
        self.assertEqual(total.registered_primary_rmse_ms.iloc[0], 9)
        self.assertTrue(total.registered_primary_complete.iloc[0])
        perf.loc[3, 'primary_eligible'] = False
        events, total = summarize(perf, plan)
        self.assertTrue(pd.isna(total.registered_primary_rmse_ms.iloc[0]))
        self.assertEqual(total.available_case_storm_balanced_rmse_ms.iloc[0], 9)
        events, total = summarize(perf.iloc[:3], plan)
        self.assertFalse(total.registered_primary_complete.iloc[0])

    def test_nominal_height_does_not_establish_relocated_site_eligibility(self):
        audit = {'height_m': 10, 'height_matches_event_site': False, 'height_source_url': 'fixture',
                 'averaging_minutes': 2, 'duration_source_url': 'fixture'}
        self.assertFalse(primary_eligibility(audit))
        audit['height_matches_event_site'] = True
        self.assertTrue(primary_eligibility(audit))

    def test_evaluation_retains_failures_qc_and_common_candidate_support(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            annual = root/'annual.csv'
            annual.write_text('STATION,DATE,WND,REPORT_TYPE,CALL_SIGN,LATITUDE,LONGITUDE\n'
                              '01234567890,2000-09-01T00:30:00,"090,1,N,0350,1",FM-15,TEST,25,-79.9\n'
                              '01234567890,2000-09-01T01:00:00,"090,1,N,0800,9",FM-15,TEST,25,-79.9\n'
                              '01234567890,2000-09-01T01:30:00,"090,1,N,0100,1",FM-15,TEST,25,-79.9\n'
                              '01234567890,2000-09-01T03:00:00,"090,1,N,0150,1",FM-15,TEST,25,-79.9\n')
            date = {'beginDate': '1990-01-01', 'endDate': 'Present'}
            homr = root/'history.json'
            homr.write_text(json.dumps({'stationCollection': {'stations': [{
                'identifiers': [{'idType': 'WBAN', 'id': '01234', 'date': date}, {'idType': 'ICAO', 'id': 'TEST', 'date': date}],
                'platforms': [{'platform': 'ASOS', 'date': date}], 'location': {'latLonPairs': [{'date': date}]}}]}}))
            station = {'station_id': 'TEST', 'wban': '01234', 'expected_ncei_id': '01234567890',
                       'homr_path': str(homr), 'annual_path': str(annual), 'annual_url': 'https://example.invalid'}
            event = {'storm_id': 'AL012000', 'name': 'FABRICATED', 'split': 'test',
                     'window_start': '2000-09-01T00:00:00Z', 'window_end': '2000-09-01T04:00:00Z',
                     'stations': [station, {**station, 'station_id': 'MISSING', 'annual_path': str(root/'missing.csv')}]}
            plan = {'events': [event], 'candidates': [{'name': 'baseline', 'overrides': {}},
                                                     {'name': 'lower', 'overrides': {'land_exposure_factor': .8}}],
                    'eligibility': {'cadence_minutes': 60, 'high_wind_threshold_ms': 32.924416},
                    'access_protocol': {'independence': 'fabricated'}}
            audits = [{'storm_id': 'AL012000', 'station_id': name, 'coordinates': {'lat': 25, 'lon': -79.9},
                       'height_m': 10, 'averaging_minutes': 2, 'height_matches_event_site': True,
                       'height_source_url': 'fixture', 'duration_source_url': 'fixture', 'height_limitation': 'fixture'}
                      for name in ['TEST', 'MISSING']]
            tracks = pd.DataFrame({'storm_id': ['AL012000']*2,
                                   'time': pd.to_datetime(['2000-09-01T00:00', '2000-09-01T02:00']),
                                   'lat': [25., 25.], 'lon': [-80., -80.], 'vmax_ms': [40., 60.], 'rmw_km': [np.nan, np.nan]})
            cfg = {'interpolation_minutes': 1, 'rmw_km': 35., 'rankine_alpha': .6, 'land_exposure_factor': .85}
            out = root/'out'; out.mkdir()
            perf, summary = evaluate(plan, audits, tracks, cfg, out)
            present = perf[perf.station_id.eq('TEST')]
            self.assertTrue(present.n.eq(2).all())
            self.assertTrue(present.high_n.eq(1).all())
            self.assertTrue(present.good_reports_outside_track.eq(1).all())
            self.assertEqual(len(perf), 4)
            self.assertTrue(perf[perf.station_id.eq('MISSING')].failure.str.len().gt(0).all())
            self.assertTrue(summary.registered_primary_rmse_ms.isna().all())
            self.assertTrue(present.incomplete_peak.all())
            pairs = pd.read_csv(out/'time_matched_pairs.csv')
            for name in ['baseline', 'lower']:
                group = pairs[pairs.variant.eq(name)]
                self.assertEqual(group[group.sample_eligible].sustained_ms.tolist(), [35, 10])
