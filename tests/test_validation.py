import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from hurricane_risk.validation import (load_observations, leave_one_storm_out,
                                       bootstrap_metrics, scores)


class ValidationTests(unittest.TestCase):
    def test_new_downloaded_events_remain_censored_with_unverified_metadata(self):
        sources = json.loads(Path('data/validation/expanded_sources.json').read_text())
        obs = load_observations(Path('data/validation/expanded_station_peaks.csv'), sources)
        self.assertEqual(len(obs), 51)
        self.assertEqual(obs.storm_id.nunique(), 5)
        self.assertEqual(int(obs.primary.sum()), 22)
        new = obs[obs.storm_id.isin(['AL102023', 'AL092024'])]
        self.assertEqual(len(new), 2)
        self.assertTrue(new.incomplete.eq(1).all())
        self.assertFalse(new.primary.any())
        self.assertTrue(new.exclusion_reason.eq('incompatible_or_unverified_metadata').all())

    def test_curation_excludes_censored_missing_and_suspect_peaks(self):
        sources = json.loads(Path('data/validation/sources.json').read_text())
        obs = load_observations(Path('data/validation/station_peaks.csv'), sources)
        self.assertEqual(len(obs), 49)
        self.assertEqual(int(obs.primary.sum()), 22)
        self.assertFalse(obs.loc[obs.incomplete.eq(1), 'primary'].any())
        self.assertFalse(obs.loc[obs.metadata_issue.ne(''), 'primary'].any())
        # Ian remarks override row flags: PGD's wind row itself lacks I.
        pgd = obs[(obs.storm_id == 'AL092022') & (obs.station_id == 'KPGD')].iloc[0]
        self.assertEqual(pgd.exclusion_reason, 'incomplete_peak_lower_bound')

    @staticmethod
    def sample():
        return pd.DataFrame({'storm_id': ['A', 'A', 'B', 'C'],
                             'observed_ms': [20., 20., 30., 40.],
                             'modeled_ms': [10., 10., 10., 10.]})

    def test_held_out_observations_do_not_affect_their_fitted_factor(self):
        data = self.sample()
        original = leave_one_storm_out(data)
        changed = data.copy()
        changed.loc[changed.storm_id == 'A', 'observed_ms'] *= 100
        new = leave_one_storm_out(changed)
        np.testing.assert_allclose(original.loc[data.storm_id == 'A', 'loeo_factor'],
                                   new.loc[data.storm_id == 'A', 'loeo_factor'])
        self.assertAlmostEqual(original.loeo_factor.iloc[0], np.sqrt(3*4))

    def test_storm_block_bootstrap_reproducibility_and_balanced_factor(self):
        a = bootstrap_metrics(self.sample(), 100, 1)
        b = bootstrap_metrics(self.sample(), 100, 1)
        pd.testing.assert_frame_equal(a, b)
        self.assertTrue(a.wind_correction_factor.between(2-1e-12, 4+1e-12).all())
        self.assertTrue((a.n >= 3).all())
        self.assertTrue((a.n <= 6).all())

    def test_metrics_use_signed_error_and_not_squared_correlation(self):
        metric = scores([10, 20, 30], [12, 22, 32])
        self.assertEqual(metric['bias_ms'], 2)
        self.assertEqual(metric['mae_ms'], 2)
        self.assertEqual(metric['rmse_ms'], 2)
        self.assertAlmostEqual(metric['correlation'], 1)


if __name__ == '__main__':
    unittest.main()
