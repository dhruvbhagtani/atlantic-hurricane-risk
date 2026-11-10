import unittest

import numpy as np
import pandas as pd

from hurricane_risk.global_hourly import normalize_global_hourly


class GlobalHourlyTests(unittest.TestCase):
    def sample(self):
        return pd.DataFrame({'STATION': '72216693845', 'CALL_SIGN': 'KVLD', 'REPORT_TYPE': 'FM-15',
                             'LATITUDE': '30.78', 'LONGITUDE': '-83.28',
                             'DATE': pd.date_range('2023-08-30', periods=5, freq='h').astype(str),
                             'WND': ['090,1,N,0150,1', '090,1,N,0200,5', '090,1,N,0700,3',
                                     '999,9,9,9999,9', '090,1,H,0250,1']})

    def normalize(self, raw):
        return normalize_global_hourly(raw, 'AL102023', 'KVLD', '72216693845',
                                       '2023-08-30T00:00:00Z', '2023-08-30T23:00:00Z')

    def test_speed_units_quality_and_unsupported_duration(self):
        result, audit, raw = self.normalize(self.sample())
        np.testing.assert_allclose(result.sustained_ms.iloc[:3], [15, 20, 70])
        self.assertEqual(result.quality_flag.tolist(), ['good', 'good', 'suspect', 'missing', 'suspect'])
        self.assertEqual(len(audit), len(raw))
        self.assertIn('unsupported_wind_type', result.qc_reason.iloc[-1])

    def test_duplicate_conflicts_are_not_selected_by_wind_maximum(self):
        raw = self.sample()
        duplicate = raw.iloc[:1].copy()
        duplicate['WND'] = '090,1,N,0500,1'
        result, audit, _ = self.normalize(pd.concat([raw, duplicate], ignore_index=True))
        self.assertEqual(result.quality_flag.iloc[0], 'suspect')
        self.assertTrue(np.isnan(result.sustained_ms.iloc[0]))
        self.assertEqual(result.raw_records_at_timestamp.iloc[0], 2)
        self.assertEqual(len(audit), 6)

    def test_wrong_station_is_rejected(self):
        raw = self.sample()
        raw['STATION'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'station ID'):
            self.normalize(raw)
