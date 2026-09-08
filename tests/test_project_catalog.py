import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stud.projects import list_projects, register
from stud_cli import main


class ProjectCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, STUD_DATA_DIR=str(self.root / 'catalog'))
        env.start()
        self.addCleanup(env.stop)

    def test_init_persists_name_and_deduplicates(self):
        project = self.root / 'bench'
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['init', str(project), '--name', 'Garage bench']), 0)
        register(project / '.')
        rows = list_projects()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], 'Garage bench')
        self.assertTrue(rows[0]['available'])
        (project / 'design.py').unlink()
        self.assertFalse(list_projects()[0]['available'])

    def test_registration_does_not_execute_design(self):
        project = self.root / 'existing'
        project.mkdir()
        (project / 'design.py').write_text('raise RuntimeError("must not execute")')
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['projects', '--add', str(project), '--json']), 0)
        self.assertIn('existing', output.getvalue())

    def test_invalid_directory_is_not_registered(self):
        self.assertEqual(list_projects(), [])
        with self.assertRaises(ValueError):
            register(self.root / 'missing')
        self.assertEqual(list_projects(), [])

    def test_symlink_deduplicates(self):
        project = self.root / 'original'
        project.mkdir()
        (project / 'design.py').touch()
        link = self.root / 'alias'
        try:
            link.symlink_to(project, target_is_directory=True)
        except OSError:
            self.skipTest('Symlinks unavailable')
        register(project)
        register(link)
        self.assertEqual(len(list_projects()), 1)
