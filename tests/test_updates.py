import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from updates import UpdateNotice, stable_version


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'version.json').write_text(json.dumps({'version': '1.2.0', 'repository': 'owner/stud'}))
        self.notice = UpdateNotice(self.root)

    def response(self, version):
        response = MagicMock()
        response.__enter__.return_value = response
        response.url = 'https://release-assets.githubusercontent.com/asset'
        response.read.return_value = json.dumps({'version': version}).encode()
        return response

    def test_newer_version_and_shared_cache(self):
        with patch('updates.urlopen', return_value=self.response('1.10.0')) as fetch:
            self.assertEqual(self.notice.check(), {'available': True, 'version': '1.10.0', 'url': 'https://github.com/owner/stud/releases/latest'})
            self.notice.check()
            fetch.assert_called_once()
        self.notice.next_check = 0
        with patch('updates.urlopen', side_effect=OSError('offline')):
            self.assertTrue(self.notice.check()['available'])

    def test_current_older_and_prerelease_do_not_notify(self):
        for version in ['1.2.0', '1.1.9', '2.0.0-beta.1', '<bad>']:
            self.notice.next_check = 0
            with patch('updates.urlopen', return_value=self.response(version)):
                self.assertFalse(self.notice.check()['available'])
        self.assertGreater(stable_version('1.10.0'), stable_version('1.9.0'))

    def test_offline_and_unconfigured_are_quiet(self):
        with patch('updates.urlopen', side_effect=OSError('offline')) as fetch:
            self.assertEqual(self.notice.check(), {'available': False})
            self.notice.check()
            fetch.assert_called_once()
        self.notice.repository = ''
        with patch('updates.urlopen') as fetch:
            self.notice.check()
            fetch.assert_not_called()
