import tempfile
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import requests

from hurricane_risk.confirmation_inputs import acquire, validate_annual


class ConfirmationInputTests(unittest.TestCase):
    def test_interrupted_download_is_removed_and_retry_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'annual.csv'
            response = MagicMock()
            response.__enter__.return_value = response

            def interrupted(**kwargs):
                yield b'partial'
                raise requests.ConnectionError('transfer interrupted')

            response.iter_content.side_effect = interrupted
            with patch('hurricane_risk.confirmation_inputs.requests.get', return_value=response):
                with self.assertRaises(requests.ConnectionError):
                    acquire('https://example.test/data', destination, lambda path: None)
                self.assertEqual(list(Path(directory).iterdir()), [])
                response.iter_content.side_effect = None
                response.iter_content.return_value = [b'complete']
                acquire('https://example.test/data', destination, lambda path: None)
            self.assertEqual(destination.read_bytes(), b'complete')
            self.assertEqual(list(Path(directory).iterdir()), [destination])

    def test_invalid_response_is_never_published(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'annual.csv'
            response = MagicMock()
            response.__enter__.return_value = response
            response.iter_content.return_value = [b'<html>not a CSV</html>']
            def reject(path):
                raise ValueError('invalid input')
            with patch('hurricane_risk.confirmation_inputs.requests.get', return_value=response):
                with self.assertRaisesRegex(ValueError, 'invalid input'):
                    acquire('https://example.test/data', destination, reject)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_existing_files_are_checked_without_network_or_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'annual.csv'
            destination.write_bytes(b'existing')
            with patch('hurricane_risk.confirmation_inputs.requests.get') as get:
                def reject(path):
                    raise ValueError('invalid existing input')
                with self.assertRaisesRegex(ValueError, 'invalid existing'):
                    acquire('https://example.test/data', destination, reject)
                acquire('https://example.test/data', destination, lambda path: None)
                with self.assertRaises(FileNotFoundError):
                    acquire('https://example.test/data', Path(directory) / 'missing',
                            lambda path: None, check_only=True)
                get.assert_not_called()
            self.assertEqual(destination.read_bytes(), b'existing')

    def test_annual_validation_requires_registered_station_year_and_window(self):
        event = {'storm_id': 'AL132020', 'station_id': 'KLCH', 'ncei_id': '72240003937',
                 'window_start': '2020-08-26T00:00:00Z', 'window_end': '2020-08-29T00:00:00Z'}
        header = 'STATION,DATE,WND,REPORT_TYPE,CALL_SIGN,LATITUDE,LONGITUDE\n'
        row = '72240003937,2020-08-27T06:00:00,"090,1,N,0200,1",FM-15,KLCH,30.12,-93.22\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'annual.csv'
            path.write_text(header + row)
            validate_annual(path, event)
            for changed in (row.replace('72240003937', '00000000000'),
                            row.replace('2020-', '2021-'), row.replace('08-27', '01-01')):
                path.write_text(header + changed)
                with self.assertRaises(ValueError):
                    validate_annual(path, event)


if __name__ == '__main__':
    unittest.main()
