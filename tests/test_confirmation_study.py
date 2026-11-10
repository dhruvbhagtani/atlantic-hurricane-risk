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
        s={'ncdcStnId':'fixture','identifiers':[{'idType':'WBAN','id':'03937','date':date},
                                              {'idType':'ICAO','id':'KLCH','date':date}],
           'location':{'latLonPairs':[{'latitude_dec':'30.125','longitude_dec':'-93.22','date':date}]}}
        doc={'stationCollection':{'stations':[s]}}
        result=station_metadata(doc,{'ncei_id':'72240003937'})
        self.assertEqual(result['height_m'],10)
        self.assertEqual(result['lat'],30.125)
        s['identifiers'][0]['id']='wrong'
        with self.assertRaisesRegex(ValueError,'identity'):
            station_metadata(doc,{'ncei_id':'72240003937'})
