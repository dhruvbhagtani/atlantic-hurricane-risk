import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np
import pandas as pd
from hurricane_risk.model import read_hurdat, supplement_rmw, interpolate_track
from hurricane_risk.__main__ import demo_tracks
from hurricane_risk.artifacts import sha256


class IBTrACSTests(unittest.TestCase):
    def tracks(self):
        return pd.DataFrame({'storm_id': ['AL012000']*3, 'time': pd.date_range('2000-08-01', periods=3, freq='3h'),
                             'rmw_km': [25., np.nan, np.nan], 'lat': 25., 'lon': -80., 'vmax_ms': 50.})

    def write(self, path, radii=('20', '30', '-999'), extra=None):
        frame = pd.DataFrame({'USA_ATCF_ID': ['AL012000']*3,
                              'ISO_TIME': ['2000-08-01 00:00:00', '2000-08-01 03:00:00', '2000-08-01 06:00:00'],
                              'USA_RMW': radii, 'TRACK_TYPE': 'MAIN', 'USA_AGENCY': 'ATCF', 'IFLAG': 'O______________'})
        if extra is not None:
            frame = pd.concat([frame, extra], ignore_index=True)
        units = pd.DataFrame([{'USA_ATCF_ID': '', 'ISO_TIME': 'UTC', 'USA_RMW': 'nmile'}]).reindex(columns=frame.columns).fillna('')
        pd.concat([units, frame], ignore_index=True).to_csv(path, index=False)
        return frame

    def test_precedence_units_missing_and_no_time_extrapolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'ib.csv'; self.write(p)
            source = self.tracks(); result = supplement_rmw(source, p)
            np.testing.assert_allclose(result.rmw_km[:2], [25., 30*1.852])
            self.assertTrue(np.isnan(result.rmw_km.iloc[2]))
            self.assertEqual(result.rmw_source.tolist(), ['HURDAT2', 'IBTrACS:USA_RMW', 'fallback'])
            self.assertEqual(result.rmw_agency.tolist(), ['', 'ATCF', ''])
            self.assertEqual(result.rmw_iflag.iloc[1], 'O______________')
            self.assertTrue(np.isnan(source.rmw_km.iloc[1]))
            self.assertEqual(interpolate_track(result, 60, 35)[3][-1], 35.)
            for invalid in ['0', '-99', '', '999', 'inf']:
                self.write(p, ('20', invalid, invalid))
                self.assertTrue(supplement_rmw(source, p).rmw_km.iloc[1:].isna().all())

    def test_spurs_aliases_duplicates_and_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'ib.csv'; frame = self.write(p)
            spur = frame.iloc[[1]].copy(); spur['TRACK_TYPE'] = 'spur'
            self.write(p, extra=spur)
            self.assertAlmostEqual(supplement_rmw(self.tracks(), p).rmw_km.iloc[1], 55.56)
            self.write(p, extra=frame.iloc[[1]])
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                supplement_rmw(self.tracks(), p)
            frame['USA_ATCF_ID'] = 'EP012000:AL012000'; frame.to_csv(p, index=False)
            self.assertAlmostEqual(supplement_rmw(self.tracks(), p).rmw_km.iloc[1], 55.56)
            frame['ISO_TIME'] = '2000-08-02 00:00:00'; frame['USA_RMW'] = ''
            frame.to_csv(p, index=False)
            self.assertTrue(supplement_rmw(self.tracks(), p).rmw_km.iloc[1:].isna().all())
            p.write_text('USA_ROCI\n20\n')
            with self.assertRaisesRegex(ValueError, 'missing columns'):
                supplement_rmw(self.tracks(), p)

    def test_loss_cli_records_used_file_and_radius_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = json.loads(Path('config.json').read_text())
            cfg.update(start_year=2000, end_year=2003, properties=3, uncertainty_replicates=20,
                       simulation_years=50, return_periods=[2])
            (root/'cfg.json').write_text(json.dumps(cfg))
            (root/'tracks.txt').write_text(demo_tracks(cfg))
            tracks = read_hurdat(root/'tracks.txt')
            pd.DataFrame({'USA_ATCF_ID': tracks.storm_id, 'ISO_TIME': tracks.time, 'USA_RMW': 20}).to_csv(root/'ib.csv', index=False)
            out = root/'run'
            r = subprocess.run([sys.executable, '-m', 'hurricane_risk', '--config', str(root/'cfg.json'),
                                '--tracks', str(root/'tracks.txt'), '--ibtracs', str(root/'ib.csv'), '--out', str(out)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            manifest = json.loads((out/'manifest.json').read_text())
            self.assertEqual(manifest['ibtracs_sha256'], sha256(root/'ib.csv'))
            self.assertEqual(manifest['rmw_missing_fraction'], 0.)
            audit = pd.read_csv(out/'track_rmw_audit.csv')
            self.assertTrue(audit.rmw_source.eq('IBTrACS:USA_RMW').all())
            np.testing.assert_allclose(audit.rmw_km, 37.04)
