import json
from pathlib import Path
import unittest
import numpy as np
from hurricane_risk.model import holland_wind, surface_wind, rankine_wind
from hurricane_risk.__main__ import validate_config


class HollandTests(unittest.TestCase):
    def test_analytic_values_and_extreme_radii(self):
        r = np.array([0., 17.5, 35., 70., 1e-100, 1e100])
        with np.errstate(all='raise', under='ignore'):
            wind = holland_wind(r, 60., 35., 1.5)
        x = np.array([2**1.5, 1., 2**-1.5])
        np.testing.assert_allclose(wind[1:4], 60*np.sqrt(x*np.exp(1-x)))
        self.assertEqual(wind[0], 0)
        self.assertTrue(np.isfinite(wind).all())
        self.assertTrue((wind <= 60).all())

    def test_broadcast_peak_and_shape(self):
        r = np.array([17.5, 35., 70.])[None, :]
        w = holland_wind(r, np.array([40., 60.])[:, None], 35.)
        np.testing.assert_allclose(w[:, 1], [40., 60.])
        self.assertGreater(holland_wind(100., 60., 35., 1.), holland_wind(100., 60., 35., 2.))
        self.assertGreater(holland_wind(70., 60., 50.), holland_wind(70., 60., 25.))

    def test_dispatch_legacy_and_parameter_validation(self):
        cfg = json.loads(Path('config.json').read_text())
        self.assertEqual(cfg['wind_profile'], 'holland')
        actual = surface_wind(70., 60., 35., 25., -80., 25., -81., cfg)
        self.assertAlmostEqual(actual, holland_wind(70., 60., 35.)*.85)
        cfg.pop('wind_profile')
        self.assertAlmostEqual(surface_wind(70., 60., 35., 25., -80., 25., -81., cfg), rankine_wind(70., 60., 35.)*.85)
        for change in [{'wind_profile': 'bad'}, {'holland_b': 0}, {'holland_b': float('nan')}, {'holland_b': True}]:
            with self.assertRaises(ValueError):
                validate_config({**cfg, **change})
        for args in [(-1, 60, 35), (1, -1, 35), (1, 60, 0), (1, 60, 35, 0)]:
            with self.assertRaises(ValueError):
                holland_wind(*args)
