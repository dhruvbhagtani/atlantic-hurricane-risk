import unittest

import numpy as np
import pandas as pd

from hurricane_risk.model import synthetic_portfolio
from hurricane_risk.portfolio import land_only_portfolio


class PortfolioTests(unittest.TestCase):
    def test_relocation_preserves_financial_exposure_and_is_reproducible(self):
        path='data/geography/natural_earth_10m_atlantic.geojson.gz'
        a,audit=land_only_portfolio(12,7319,path)
        b,_=land_only_portfolio(12,7319,path)
        pd.testing.assert_frame_equal(a,b)
        original=synthetic_portfolio(12,7319)
        pd.testing.assert_frame_equal(a.drop(columns=['lat','lon']),original.drop(columns=['lat','lon']))
        self.assertTrue(audit.signed_coast_km.ge(2).all())
        self.assertTrue(audit.displacement_km.le(12).all())
