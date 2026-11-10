"""Offline CLI check using fabricated tracks and custom exposure/curves."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from hurricane_risk.artifacts import sha256


class IntegrationTests(unittest.TestCase):
    def test_demo_reproducibility_policy_invariants_and_output_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = json.loads(Path('config.json').read_text())
            cfg.update(start_year=2000, end_year=2003, properties=6,
                       uncertainty_replicates=20, simulation_years=100, return_periods=[2])
            config = root / 'config.json'
            config.write_text(json.dumps(cfg))
            command = [sys.executable, '-m', 'hurricane_risk', '--demo', '--config', str(config),
                       '--portfolio', 'examples/portfolio.csv', '--vulnerability', 'examples/vulnerability.json']
            for name in ['a', 'b']:
                result = subprocess.run(command + ['--out', str(root/name)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            a, b = root/'a', root/'b'
            self.assertEqual(sha256(a/'summary.csv'), sha256(b/'summary.csv'))
            annual = pd.read_csv(a/'historical_annual_losses.csv')
            self.assertEqual(len(annual), 4)
            self.assertTrue((annual.aggregate_insured_usd >= annual.occurrence_insured_usd).all())
            summary = pd.read_csv(a/'summary.csv').set_index('scenario')
            self.assertAlmostEqual(summary.loc['wind_plus_10pct_frequency_plus_20pct', 'aal_usd'],
                                   summary.loc['wind_plus_10pct', 'aal_usd'] * 1.2)
            manifest = json.loads((a/'manifest.json').read_text())
            for path, digest in manifest['outputs_sha256'].items():
                self.assertEqual(sha256(a/path), digest)
            self.assertEqual(Path(manifest['track_path']), a/'SYNTHETIC_tracks.txt')
            before = sha256(a/'manifest.json')
            result = subprocess.run(command + ['--out', str(a)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('already exists', result.stderr)
            self.assertEqual(sha256(a/'manifest.json'), before)
