import contextlib
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from build import build


class BuildEncodingTests(unittest.TestCase):
    def test_coordinator_build_preserves_unicode_manifest(self):
        manifest={'name':'Café 工作台','notes':['Cut a ⅜-inch notch']}
        with patch('build.evaluate_project',return_value=({'status':'complete','id':'build'},manifest)),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(build(Path('project')),manifest)

    def test_generation_failure_exits_without_returning_a_previous_manifest(self):
        with patch('build.evaluate_project',return_value=({'status':'generation_failed'},None)),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as error:build(Path('project'))
            self.assertEqual(error.exception.code,1)
