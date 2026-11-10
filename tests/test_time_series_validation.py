import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from hurricane_risk.model import interpolate_track
from hurricane_risk.time_series_validation import modeled_at_times, evaluate_series


class TimeSeriesTests(unittest.TestCase):
    def track(self):
        return pd.DataFrame({'storm_id': ['AL012000']*2, 'time': pd.to_datetime(['2000-09-01', '2000-09-01T01:00:00'], format='mixed'),
                             'lat': [25., 25.], 'lon': [-80., -80.], 'vmax_ms': [40., 60.], 'rmw_km': [35., 35.]})

    def test_interpolation_at_actual_report_times_and_no_extrapolation(self):
        tr = self.track()
        times = pd.to_datetime(['2000-09-01T00:17:00Z', '2000-09-01T00:43:00Z'])
        _, _, wind, _ = interpolate_track(tr, 30, 35, times)
        np.testing.assert_allclose(wind, 40+20*np.array([17, 43])/60)
        with self.assertRaisesRegex(ValueError, 'within the track'):
            interpolate_track(tr, 30, 35, pd.to_datetime(['2000-09-01T02:00:00Z']))

    def test_scores_use_good_samples_at_their_times_and_clip_model_support(self):
        cfg = json.loads(Path('config.json').read_text())
        station = {'station_id': 'TEST', 'lat': 25., 'lon': -79.9, 'height_m': None,
                   'averaging_minutes': 2, 'exposure': 'unknown', 'cadence_minutes': 10,
                   'uptime_confirmed': False, 'metadata_reference': '', 'uptime_reference': ''}
        event = {'storm_id': 'AL012000', 'name': 'FABRICATED', 'split': 'development',
                 'window_start': '2000-09-01T00:00:00Z', 'window_end': '2000-09-01T02:00:00Z',
                 'product': 'fixture', 'url': 'https://example.invalid',
                 'best_track_provenance': 'fabricated', 'stations': [station]}
        plan = {'quality_control_description': 'fixture', 'quality_control_reference': 'fixture', 'events': [event]}
        times = pd.date_range(event['window_start'], periods=7, freq='10min')
        values = modeled_at_times(self.track(), station, times, cfg)
        series = pd.DataFrame({'storm_id': 'AL012000', 'station_id': 'TEST', 'time_utc': times,
                               'sustained_ms': values, 'quality_flag': 'good'})
        series.loc[3, 'sustained_ms'] = 120
        series.loc[3, 'quality_flag'] = 'suspect'
        with tempfile.TemporaryDirectory() as tmp:
            metrics = evaluate_series(series, plan, self.track(), cfg, Path(tmp))
            self.assertEqual(metrics.n.iloc[0], 6)
            self.assertAlmostEqual(metrics.rmse_ms.iloc[0], 0)
            self.assertTrue(metrics.incomplete_peak.eq(1).all())
            dense = pd.read_csv(Path(tmp)/'modeled_time_series.csv')
            self.assertEqual(pd.to_datetime(dense.time_utc, utc=True).max(), times[-1])
