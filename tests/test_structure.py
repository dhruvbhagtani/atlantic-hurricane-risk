import json
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from hurricane_risk.__main__ import validate_config
from hurricane_risk.geography import coast_distances
from hurricane_risk.model import (surface_wind, hazard_catalog, interpolation_times)
from hurricane_risk.time_series_validation import modeled_at_times


class StructureTests(unittest.TestCase):
    def config(self):
        return json.loads(Path('examples/structural_config.json').read_text())

    def test_translation_favored_side_preserves_vmax_and_stationary_limit(self):
        cfg=self.config();cfg.update(translation_fraction=.5,asymmetry_cap=.25)
        wind=surface_wind(np.array([35.,35.]),40.,35.,0.,0.,0.,np.array([.315,-.315]),cfg,0.,10.)
        np.testing.assert_allclose(wind,[34.,34.*(.875/1.125)],rtol=1e-5)
        stationary=surface_wind(np.array([35.,35.]),40.,35.,0.,0.,0.,np.array([.315,-.315]),cfg,0.,0.)
        np.testing.assert_allclose(stationary,[34,34])
        center=surface_wind(0.,40.,35.,0.,0.,0.,0.,cfg,0.,10.)
        self.assertEqual(center,0)

    def test_inland_attenuation_is_local_and_does_not_decay_over_water(self):
        cfg=self.config();cfg['inland_decay_km']=100.
        wind=surface_wind(np.array([35.,35.,35.]),40.,35.,25.,-80.,25.,-80.,cfg,
                          inland_distance_km=np.array([-20.,0.,100.]))
        np.testing.assert_allclose(wind,[34.,34.,34./np.e])

    def test_shared_kernel_matches_event_maximum_at_subminute_resolution(self):
        cfg=self.config();cfg.update(translation_fraction=.5,asymmetry_cap=.25,
                                    inland_decay_km=100.,interpolation_minutes=.5)
        track=pd.DataFrame({'storm_id':'AL012000','name':'FIXTURE','season':2000,
                            'time':pd.to_datetime(['2000-09-01','2000-09-01T01:00:00'],format='mixed'),
                            'lat':[28.,28.4],'lon':[-81.,-81.],'vmax_ms':[40.,50.],'rmw_km':[35.,35.]})
        station={'lat':28.54,'lon':-81.38}
        _,wind=hazard_catalog(track,pd.DataFrame([station]),cfg)
        times=pd.to_datetime(interpolation_times(track,.5),unit='s',utc=True)
        exact=modeled_at_times(track,station,times,cfg)
        self.assertAlmostEqual(wind[0,1,0],exact.max())

    def test_fine_coastline_land_labels_and_bounds(self):
        cfg=self.config()
        distance,land=coast_distances([25.76,28.54,30.77629,28.],[-80.2,-81.38,-83.27393,-70.],cfg['coastline_path'])
        np.testing.assert_array_equal(land,[True,True,True,False])
        self.assertTrue(0 < distance[0] < 5)
        self.assertTrue(40 < distance[1] < 75)
        self.assertTrue(75 < distance[2] < 125)
        with self.assertRaisesRegex(ValueError,'bounds'):
            coast_distances([80.],[-80.],cfg['coastline_path'])

    def test_parameter_validation_and_subminute_config(self):
        cfg=self.config();cfg['interpolation_minutes']=.25
        validate_config(cfg)
        for changes in [{'translation_fraction':2},{'asymmetry_cap':1},
                        {'inland_decay_km':-1},{'interpolation_minutes':float('nan')}]:
            with self.assertRaises(ValueError):
                validate_config({**cfg,**changes})
