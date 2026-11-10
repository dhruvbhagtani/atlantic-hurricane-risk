import unittest

from hurricane_risk.confirmation_study import entries_at,station_metadata


class ConfirmationTests(unittest.TestCase):
    def test_history_is_selected_at_the_storm_date(self):
        rows=[{'value':'old','date':{'beginDate':'2000-01-01','endDate':'2021-01-01'}},
              {'value':'new','date':{'beginDate':'2021-01-01','endDate':'Present'}}]
        self.assertEqual(entries_at(rows,'2020-08-27')[0]['value'],'old')
        self.assertEqual(entries_at(rows,'2024-08-27')[0]['value'],'new')

    def test_station_identity_and_dated_coordinates_are_required(self):
        date={'beginDate':'2000-01-01','endDate':'Present'}
        s={'ncdcStnId':'fixture','platforms':[{'platform':'ASOS','date':date}],
           'identifiers':[{'idType':'WBAN','id':'03937','date':date},
                                              {'idType':'ICAO','id':'KLCH','date':date}],
           'location':{'latLonPairs':[{'latitude_dec':'30.125','longitude_dec':'-93.22','date':date}]}}
        doc={'stationCollection':{'stations':[s]}}
        result=station_metadata(doc,{'ncei_id':'72240003937'})
        self.assertEqual(result['height_m'],10)
        self.assertEqual(result['lat'],30.125)
        s['identifiers'][0]['id']='wrong'
        with self.assertRaisesRegex(ValueError,'identity'):
            station_metadata(doc,{'ncei_id':'72240003937'})

    def test_surface_history_is_selected_without_radar_or_upperair_confusion(self):
        from copy import deepcopy
        date={'beginDate':'1996-01-01','endDate':'Present'}
        surface={'ncdcStnId':'surface','platforms':[{'platform':'ASOS','date':date}],
                 'identifiers':[{'idType':'WBAN','id':'03937','date':date},
                                {'idType':'ICAO','id':'KLCH','date':date}],
                 'location':{'latLonPairs':[{'latitude_dec':'30.12472','longitude_dec':'-93.22833','date':date},
                                           {'latitude_dec':'30.12551','longitude_dec':'-93.22771',
                                            'date':{'beginDate':'2021-11-22','endDate':'Present'}}]}}
        radar=deepcopy(surface);radar['ncdcStnId']='radar';radar['platforms'][0]['platform']='NEXRAD'
        upperair=deepcopy(surface);upperair['platforms'][0]['platform']='UPPERAIR'
        doc={'stationCollection':{'stations':[radar,upperair,surface]}}
        result=station_metadata(doc,{'ncei_id':'72240003937'})
        self.assertEqual(result['homr_ncdc_id'],'surface')
        self.assertEqual(result['lat'],30.12472)
        doc['stationCollection']['stations'].append(deepcopy(surface))
        with self.assertRaisesRegex(ValueError,'exactly one dated ASOS'):
            station_metadata(doc,{'ncei_id':'72240003937'})
        surface['platforms'][0]['date']={'beginDate':'2021-01-01','endDate':'Present'}
        doc['stationCollection']['stations']=[surface,radar,upperair]
        with self.assertRaisesRegex(ValueError,'exactly one dated ASOS'):
            station_metadata(doc,{'ncei_id':'72240003937'})
