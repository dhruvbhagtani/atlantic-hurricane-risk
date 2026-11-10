import json
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from hurricane_risk.timing_diagnostic import geometry, perturbation_predictions, peak_summary
from hurricane_risk.time_series_validation import modeled_at_times


class TimingDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.track = pd.DataFrame({'time': pd.to_datetime(['2000-09-01T00:00', '2000-09-01T01:00']),
                                   'lat': [25., 25.], 'lon': [-80., -80.],
                                   'vmax_ms': [40., 60.], 'rmw_km': [np.nan, np.nan]})
        self.station = {'lat': 25., 'lon': -79.9}
        self.cfg = json.loads(Path('config.json').read_text())

    def test_time_shift_direction_and_common_support(self):
        times = pd.date_range('2000-09-01T00:00Z', periods=5, freq='15min')
        cases = [{'name': 'baseline'}, {'name': 'later', 'time_shift_minutes': 15},
                 {'name': 'earlier', 'time_shift_minutes': -15}]
        predicted, common = perturbation_predictions(self.track, self.station, times, self.cfg, cases)
        np.testing.assert_array_equal(common, [False, True, True, True, False])
        for name in ['baseline', 'later', 'earlier']:
            self.assertEqual(len(predicted[predicted.case.eq(name)]), 3)
        later = predicted[predicted.case.eq('later')]
        expected = modeled_at_times(self.track, self.station, times[common]+pd.Timedelta(minutes=15), self.cfg)
        np.testing.assert_allclose(later.modeled_ms, expected)
        self.assertTrue((later.model_evaluation_time_utc-later.time_utc).eq(pd.Timedelta(minutes=15)).all())

    def test_geometry_uses_effective_radius_and_position_shift_preserves_input(self):
        times = pd.date_range('2000-09-01T00:15Z', periods=3, freq='15min')
        geom = geometry(self.track, self.station, times, self.cfg)
        np.testing.assert_allclose(geom.effective_rmw_km, 35)
        np.testing.assert_allclose(geom.distance_over_rmw, geom.center_distance_km/35)
        original = self.track.copy(deep=True)
        predictions, _ = perturbation_predictions(self.track, self.station, times, self.cfg,
                                                   [{'name': 'baseline'}, {'name': 'east', 'east_km': 10}])
        pd.testing.assert_frame_equal(original, self.track)
        self.assertFalse(np.allclose(predictions[predictions.case.eq('baseline')].modeled_ms,
                                     predictions[predictions.case.eq('east')].modeled_ms))

    def test_peak_ties_are_counted_and_first_time_is_explicit(self):
        frame = pd.DataFrame({'time_utc': pd.date_range('2000-01-01', periods=3, freq='h'),
                              'value': [10, 20, 20]})
        peak, time, ties = peak_summary(frame, 'value')
        self.assertEqual((peak, time, ties), (20, frame.time_utc.iloc[1], 2))
