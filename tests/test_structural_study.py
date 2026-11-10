import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from hurricane_risk.artifacts import sha256
from hurricane_risk.structural_study import compare_candidates, verify_registration


class StudyTests(unittest.TestCase):
    def test_reserved_values_cannot_change_development_predictions_or_scores(self):
        cfg=json.loads(Path('examples/structural_config.json').read_text())
        variants=[{'name':'baseline','overrides':{}},
                  {'name':'motion','overrides':{'translation_fraction':.5,'asymmetry_cap':.25}}]
        station={'station_id':'FIXTURE','lat':28.54,'lon':-81.38,'height_m':10,'averaging_minutes':2,
                 'exposure':'unknown','cadence_minutes':10,'uptime_confirmed':False,
                 'metadata_reference':'fixture','uptime_reference':''}
        events=[];observations=[];tracks=[]
        for year,split in [(2000,'development'),(2001,'test')]:
            sid=f'AL01{year}';start=f'{year}-09-01T00:00:00Z';end=f'{year}-09-01T01:00:00Z'
            events.append({'storm_id':sid,'name':'FABRICATED','split':split,'window_start':start,'window_end':end,
                           'product':'fixture','url':'https://example.invalid','best_track_provenance':'fabricated',
                           'stations':[station.copy()]})
            times=pd.date_range(start,end,freq='10min')
            observations.append(pd.DataFrame({'storm_id':sid,'station_id':'FIXTURE','time_utc':times,
                                              'sustained_ms':np.linspace(5,10,len(times)),'quality_flag':'good'}))
            tracks.append(pd.DataFrame({'storm_id':sid,'time':pd.to_datetime([start,end],utc=True).tz_localize(None),
                                        'lat':[28.,28.4],'lon':[-81.,-81.], 'vmax_ms':[40.,50.],'rmw_km':[35.,35.]}))
        plan={'events':events,'quality_control_description':'fixture','quality_control_reference':'fixture'}
        metadata={'height_m':10,'averaging_minutes':2,'wind_tower_coordinate_sensitivity':{'lat':28.541,'lon':-81.381}}
        series=pd.concat(observations,ignore_index=True);track=pd.concat(tracks,ignore_index=True)
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'a',Path(tmp)/'b';a.mkdir();b.mkdir()
            compare_candidates(series,plan,track,cfg,variants,a,metadata)
            series.loc[series.storm_id.eq('AL012001'),'sustained_ms'] *= 2
            compare_candidates(series,plan,track,cfg,variants,b,metadata)
            original=pd.read_csv(a/'performance.csv');changed=pd.read_csv(b/'performance.csv')
            pd.testing.assert_frame_equal(original[original.split.eq('development')],changed[changed.split.eq('development')])
            self.assertTrue((a/'coverage.csv').exists())

    def test_registration_rejects_changed_annual_data_and_model_hashes(self):
        cfg=json.loads(Path('examples/structural_config.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);annual=root/'annual';annual.write_text('fixture')
            registration=root/'registration.json';registration.write_text(json.dumps({'annual_input_sha256':sha256(annual)}))
            lock={'registration_sha256':sha256(registration),'annual_input_sha256':sha256(annual),
                  'coastline_sha256':sha256(cfg['coastline_path']),
                  'model_code_sha256':{'model.py':sha256('hurricane_risk/model.py')}}
            with patch('hurricane_risk.structural_study.REGISTRATION_SHA256',sha256(registration)):
                verify_registration(registration,lock,annual,cfg)
                annual.write_text('changed')
                with self.assertRaisesRegex(ValueError,'Annual observations'):
                    verify_registration(registration,lock,annual,cfg)
