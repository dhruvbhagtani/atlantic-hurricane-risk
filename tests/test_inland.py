import json
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from hurricane_risk.model import inland_wind_factor, inland_profile, hazard_catalog, interpolation_times
from hurricane_risk.__main__ import validate_config
from hurricane_risk.time_series_validation import modeled_at_times


class InlandTests(unittest.TestCase):
    def test_published_transition_equation_limits_and_monotonicity(self):
        cfg = {'inland_profile': 'coastal_transition'}
        floor = .78/.89
        d = np.array([-20., 0., 1.852, 9.26, 18.52, 1000.])
        q = np.array([1., 1., 1-.195+.0095, 1-.195*5+.0095*25, 0., 0.])
        factor = inland_wind_factor(d, cfg)
        np.testing.assert_allclose(factor, floor+(1-floor)*q)
        self.assertTrue((np.diff(factor) <= 0).all())
        self.assertTrue((factor >= floor).all())
        self.assertEqual(factor[-1], floor)
        self.assertEqual(factor[0], 1.)

    def test_explicit_selection_and_legacy_exponential(self):
        d = np.array([-10., 0., 100.])
        legacy = {'inland_decay_km': 100.}
        self.assertEqual(inland_profile(legacy), 'exponential')
        np.testing.assert_allclose(inland_wind_factor(d, legacy), [1., 1., 1/np.e])
        np.testing.assert_allclose(inland_wind_factor(d, {**legacy, 'inland_profile': 'none'}), 1.)
        self.assertEqual(inland_profile({}), 'none')
        bounded = {**legacy, 'inland_profile': 'coastal_transition', 'inland_equilibrium_factor': 1.}
        np.testing.assert_allclose(inland_wind_factor(d, bounded), 1.)

    def test_validation_and_coastline_requirement(self):
        cfg = json.loads(Path('config.json').read_text())
        validate_config(cfg)
        for change in [{'inland_profile': 'bad'}, {'inland_equilibrium_factor': 0.},
                       {'inland_equilibrium_factor': 1.1}, {'inland_equilibrium_factor': True},
                       {'inland_profile': 'exponential', 'inland_decay_km': 0}, {'coastline_path': None}]:
            with self.assertRaises(ValueError):
                validate_config({**cfg, **change})
        with self.assertRaises(ValueError):
            inland_wind_factor([np.nan], cfg)

    def test_holland_with_coastal_friction_shared_station_and_hazard_kernels(self):
        cfg = json.loads(Path('config.json').read_text())
        cfg['interpolation_minutes'] = .5
        tr = pd.DataFrame({'storm_id': 'AL012000', 'name': 'FIXTURE', 'season': 2000,
                           'time': pd.date_range('2000-09-01', periods=2, freq='h'),
                           'lat': [28., 28.4], 'lon': [-81., -81.], 'vmax_ms': [40., 50.], 'rmw_km': [35., 35.]})
        for station in [{'lat': 28.54, 'lon': -81.38}, {'lat': 28., 'lon': -70.}]:
            _, wind = hazard_catalog(tr, pd.DataFrame([station]), cfg)
            times = pd.to_datetime(interpolation_times(tr, .5), unit='s', utc=True)
            sampled = modeled_at_times(tr, station, times, cfg)
            self.assertAlmostEqual(wind[0, 1, 0], sampled.max())
            unadjusted = modeled_at_times(tr, station, times, {**cfg, 'inland_profile': 'none'})
            ratio = sampled.max()/unadjusted.max()
            self.assertAlmostEqual(ratio, .78/.89 if station['lon'] == -81.38 else 1.)
