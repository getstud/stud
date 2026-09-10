import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from stud.client import Client
from stud.contracts import StudError


class ClientErrorTests(unittest.TestCase):
    def request_error(self, payload):
        client = Client.__new__(Client)
        client.url = 'http://127.0.0.1:1234'
        response = HTTPError(client.url, 422, 'Unprocessable Content', {}, io.BytesIO(payload))
        with patch('stud.client.urlopen', side_effect=response):
            with self.assertRaises(StudError) as caught:
                client.command('finish', {})
        return caught.exception

    def test_evaluation_required_retains_actionable_server_error(self):
        original = dict(category='evaluation_required', message='Evaluate the current source before finishing.',
                        expected='source-new', current={'source_id': 'source-old'}, retryable=True)
        error = self.request_error(json.dumps({'error': original}).encode())
        result = error.as_dict()
        for key, value in original.items():
            self.assertEqual(result[key], value)

    def test_malformed_server_errors_remain_transport_errors(self):
        for payload in (b'not JSON', b'{}', b'{"error":null}', b'{"error":{}}'):
            with self.subTest(payload=payload):
                self.assertEqual(self.request_error(payload).category, 'transport_error')
