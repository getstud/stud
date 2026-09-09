import contextlib
import csv
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from build import build


class BuildEncodingTests(unittest.TestCase):
    def test_unicode_part_notes_export_on_legacy_windows_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            note = 'Cut a ⅜-inch notch'
            (root / 'design.py').write_text(f'''
from stud import Project
project = Project('Encoding check')
project.stock('2x4', 'Framing', '#ddbd8b', section=(1.5, 3.5), lengths=(96,))
project.box('rail', 'Frame', '2x4', size=(1.5, 3.5, 48), origin=(0, 0, 0), note={note!r})
''', encoding='utf-8')
            original_open = Path.open

            def windows_open(path, mode='r', buffering=-1, encoding=None, errors=None, newline=None):
                if 'b' not in mode and encoding in (None, 'locale'):
                    encoding = 'cp1252'
                return original_open(path, mode, buffering, encoding, errors, newline)

            # Exercise real export writes with Windows' legacy text-file default.
            with patch.object(Path, 'open', windows_open), contextlib.redirect_stdout(io.StringIO()):
                build(root)
            text = (root / 'output/model/parts.csv').read_bytes().decode('utf-8')
            rows = list(csv.DictReader(io.StringIO(text)))
            self.assertEqual(rows[0]['note'], note)
