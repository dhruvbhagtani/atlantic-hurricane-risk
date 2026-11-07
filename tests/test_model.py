import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from hurricane_risk.model import (read_hurdat, rankine_wind, distance_km, interpolate_track,
                                 property_losses, annual_losses, sample_annual_blocks,
                                 ep_curve, loss_metrics)


class RiskTests(unittest.TestCase):
    def test_hurdat_units_missing_rmw_and_special_fix(self):
        # Includes an unscheduled landfall fix and the modern RMW field.
        lines = ["AL012000, FIXTURE, 2,",
                 ",".join(["20000801", "0000", "", "HU", "25N", "80W", "100", "960"] + ["-999"]*12 + ["20", ""]),
                 ",".join(["20000801", "0315", "L", "HU", "26N", "81W", "90", "970"] + ["-999"]*12 + ["-999", ""])]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "track.txt"
            path.write_text("\n".join(lines))
            tr = read_hurdat(path)
            self.assertAlmostEqual(tr.vmax_ms.iloc[0], 51.4444)
            self.assertAlmostEqual(tr.rmw_km.iloc[0], 37.04)
            self.assertTrue(np.isnan(tr.rmw_km.iloc[1]))
            lat, lon, wind, rmw = interpolate_track(tr, 60, 35)
            self.assertEqual(len(lat), 5)
            self.assertEqual(lon[-1], -81)
            self.assertEqual(rmw[-1], 35)
            path.write_text("AL012000, FIXTURE, 3,\n" + "\n".join(lines[1:]))
            with self.assertRaisesRegex(ValueError, "Truncated"):
                read_hurdat(path)
            for sentinel in [-99, -999]:
                path.write_text("\n".join(lines).replace(",100,", f",{sentinel},"))
                self.assertTrue(np.isnan(read_hurdat(path).vmax_ms.iloc[0]))

    def test_radial_profile_and_distance(self):
        v = rankine_wind(np.array([0, 17.5, 35, 70]), 60, 35)
        np.testing.assert_allclose(v, [0, 30, 60, 60*2**(-.6)])
        self.assertAlmostEqual(distance_km(0, 0, 0, 1), 111.19508, places=4)

    def test_policy_terms_and_monotonic_damage(self):
        p = pd.DataFrame({"construction": ["wood"], "replacement_value_usd": [1000.],
                          "deductible_fraction": [.02], "limit_fraction": [.5]})
        ground, insured = property_losses(np.array([[0.], [40.], [100.]]), p)
        np.testing.assert_allclose(ground[:, 0], [0, 80, 1000])
        np.testing.assert_allclose(insured[:, 0], [0, 60, 500])
        self.assertTrue(np.all(np.diff(insured[:, 0]) >= 0))

    def test_annual_occurrence_aggregate_zero_years(self):
        a, o = annual_losses([10, 20, 7], [2000, 2000, 2002], np.arange(2000, 2004))
        np.testing.assert_array_equal(a, [30, 0, 7, 0])
        np.testing.assert_array_equal(o, [20, 0, 7, 0])
        np.testing.assert_array_equal(ep_curve(a, [0, 7, 30]), [.5, .25, 0])
        self.assertTrue(np.all(ep_curve(a, [0, 10, 20]) >= ep_curve(o, [0, 10, 20])))
        self.assertEqual(loss_metrics(a, o, [2])["aal_usd"], 9.25)

    def test_frequency_blocks_identity_and_superposition(self):
        a = np.array([0, 30, 10])
        o = np.array([0, 20, 10])
        idx = np.array([[0, 1, 2], [1, 2, 0], [2, 0, 1]])
        u = np.array([.1, .4, .8])
        a1, o1 = sample_annual_blocks(a, o, idx, u, 1)
        np.testing.assert_array_equal(a1, a)
        np.testing.assert_array_equal(o1, o)
        a2, o2 = sample_annual_blocks(a, o, idx, u, 2)
        np.testing.assert_array_equal(a2, [30, 40, 10])
        np.testing.assert_array_equal(o2, [20, 20, 10])
        self.assertTrue(np.all(a2 >= o2))
        a12, _ = sample_annual_blocks(a, o, idx, u, 1.2)
        np.testing.assert_array_equal(a12, [30, 30, 10])


if __name__ == "__main__":
    unittest.main()
