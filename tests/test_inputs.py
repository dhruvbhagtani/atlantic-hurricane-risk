import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from hurricane_risk.artifacts import output_directory
from hurricane_risk.inputs import load_portfolio, load_vulnerability
from hurricane_risk.model import annual_losses, property_losses


class InputTests(unittest.TestCase):
    def test_custom_curves_and_integer_winds_preserve_fractional_damage(self):
        curves = load_vulnerability('examples/vulnerability.json')
        p = load_portfolio('examples/portfolio.csv', curves).iloc[:1].copy()
        p['construction'] = 'wood'
        ground, _ = property_losses(np.array([[40]]), p, vulnerability=curves)
        self.assertAlmostEqual(ground[0, 0], .08 * p.replacement_value_usd.iloc[0])
        p['construction'] = 'typo'
        with self.assertRaisesRegex(ValueError, 'Unknown construction'):
            property_losses(np.array([[40]]), p)

    def test_incompatible_and_nonmonotone_curves_fail(self):
        curves = json.loads(Path('examples/vulnerability.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'curve.json'
            curves['metadata']['wind_type'] = 'gust'
            path.write_text(json.dumps(curves))
            with self.assertRaisesRegex(ValueError, 'wind_type'):
                load_vulnerability(path)
            curves['metadata']['wind_type'] = 'sustained'
            curves['damage_nodes']['wood'][2] = .9
            path.write_text(json.dumps(curves))
            with self.assertRaisesRegex(ValueError, 'damage curve'):
                load_vulnerability(path)

    def test_bad_years_cannot_silently_reassign_losses(self):
        for years, events in [([2000, 2002], [2000]), ([2000, 2001], [1999]),
                              ([2000, 2001], [2000.5])]:
            with self.assertRaises(ValueError):
                annual_losses([10], events, years)

    def test_outputs_publish_on_success_and_preserve_existing_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'run'
            with self.assertRaisesRegex(RuntimeError, 'failed'):
                with output_directory(target) as stage:
                    (stage / 'partial').write_text('x')
                    raise RuntimeError('failed')
            self.assertFalse(target.exists())
            with output_directory(target) as stage:
                (stage / 'complete').write_text('ok')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                with output_directory(target):
                    pass
            self.assertEqual((target / 'complete').read_text(), 'ok')
