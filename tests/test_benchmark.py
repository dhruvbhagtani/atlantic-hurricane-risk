import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from hurricane_risk.__main__ import demo_tracks
from hurricane_risk.benchmark import assign_splits, run_benchmark, validate_variants
from hurricane_risk.inputs import load_vulnerability
from hurricane_risk.model import read_hurdat, synthetic_portfolio


class BenchmarkTests(unittest.TestCase):
    def test_every_case_uses_same_exposure_and_fine_reference(self):
        cfg = json.loads(Path('config.json').read_text())
        cfg.update(start_year=2000, end_year=2003, properties=6, return_periods=[2])
        variants = [{'name': 'baseline', 'overrides': {}},
                    {'name': 'larger', 'overrides': {'rmw_km': 45.}}]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            path = out/'track.txt'
            path.write_text(demo_tracks(cfg))
            tracks = read_hurdat(path)
            sources, observations = {}, []
            for i, (sid, tr) in enumerate(list(tracks.groupby('storm_id'))[:2]):
                source_id = f'source{i}'
                sources[source_id] = {'storm_id': sid, 'window_start': str(tr.time.min()),
                                      'window_end': str(tr.time.max())}
                observations.append({'storm_id': sid, 'station_id': 'fixture', 'source_id': source_id,
                                     'lat': tr.lat.mean(), 'lon': tr.lon.mean(), 'observed_ms': 25.,
                                     'primary': True, 'split': 'test' if i else 'development'})
            summary, convergence = run_benchmark(tracks, pd.DataFrame(observations), {'sources': sources},
                                                 cfg, synthetic_portfolio(6, cfg['seed']),
                                                 load_vulnerability(), variants, [30, 5], out)
            self.assertEqual(len(summary), 4)
            reference = convergence[convergence.is_reference]
            np.testing.assert_array_equal(reference.delta_usd, 0)
            self.assertTrue(reference.within_tolerance.all())
            self.assertTrue(convergence.reference_minutes.eq(5).all())
            annual = pd.read_csv(out/'annual_losses.csv')
            self.assertEqual(len(annual), 16)
            self.assertTrue((annual.aggregate_insured_usd >= annual.occurrence_insured_usd).all())
            station = pd.read_csv(out/'station_pairs.csv')
            self.assertEqual(len(station), 8)
            self.assertTrue(station.closest_distance_km.ge(0).all())
            self.assertTrue((out/'benchmark.png').exists())

    def test_split_membership_and_variants_are_strict(self):
        cfg = json.loads(Path('config.json').read_text())
        with self.assertRaises(ValueError):
            validate_variants([{'name': 'baseline', 'overrides': {'seed': 1}}], cfg)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'splits.json'
            path.write_text(json.dumps({'development': ['A'], 'test': ['A']}))
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                assign_splits(pd.DataFrame({'storm_id': ['A']}), path)
