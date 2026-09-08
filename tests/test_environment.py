import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stud import Project
from build import compile_project, parts_csv
from validate import validate


class EnvironmentTests(unittest.TestCase):
    def test_context_does_not_change_construction(self):
        project = Project('test')
        project.stock('wood', 'wood', '#ffffff', section=(2, 4), lengths=(96,))
        project.box('a', 'frame', 'wood', (2, 4, 80), (0, 0, 0))
        before = project.export()
        project.context_asset('tree', source='assets/tree.js', parameters={'diameter': 24})
        after = project.export()
        for key in ('parts', 'materials', 'stocks'):
            self.assertEqual(before[key], after[key])
        self.assertEqual(parts_csv(before), parts_csv(after))
        self.assertEqual(validate(before), validate(after))

    def test_resource_io_error_does_not_abort_construction(self):
        from stud.environment import snapshot_environment, environment_stamp
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'assets').mkdir()
            (root/'assets/tree.js').write_text('export function create() {}')
            registration = {'id': 'tree', 'source': 'assets/tree.js'}
            with patch.object(Path, 'read_bytes', side_effect=PermissionError('unreadable')):
                result = snapshot_environment(root, [registration])
            self.assertIn('unreadable', result[0]['error'])
            with patch.object(Path, 'stat', side_effect=FileNotFoundError('deleted')):
                self.assertIsInstance(environment_stamp(root), tuple)

    def test_registration_validation(self):
        for source in ('../tree.js', '/assets/tree.js', 'assets/../secret.js', 'tree.js', 'assets/tree.py', 'assets\\tree.js'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                Project('test').context_asset('tree', source=source)
        for kwargs in ({'origin': (0, 0, float('inf'))}, {'parameters': {'x': float('nan')}}, {'parameters': []}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Project('test').context_asset('tree', source='assets/tree.js', **kwargs)
        project = Project('test')
        project.context_asset('tree', source='assets/tree.js')
        with self.assertRaises(ValueError):
            project.context_asset('tree', source='assets/other.js')

    def test_snapshots_helpers_missing_modules_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'assets').mkdir()
            (root / 'design.py').write_text("from stud import Project\nproject=Project('test')\nproject.stock('s','s','#fff')\nproject.box('p','a','s',(1,1,1),(0,0,0))\nproject.context_asset('tree',source='assets/tree.js')\n")
            missing = compile_project(root)
            self.assertIn('error', missing['environment'][0])
            (root / 'assets/tree.js').write_text("import './helper.js';")
            (root / 'assets/helper.js').write_text('export const radius = 12;')
            (root / 'secret.txt').write_text('private')
            (root / 'assets/link.txt').symlink_to(root / 'secret.txt')
            first = compile_project(root)
            entry = first['environment'][0]
            snapshot = root / 'output/environment' / entry['revision']
            self.assertFalse((snapshot / 'assets/link.txt').exists())
            (root / 'assets/helper.js').write_text('export const radius = 15;')
            second = compile_project(root)
            self.assertNotEqual(first['revision'], second['revision'])
            self.assertEqual((snapshot / 'assets/helper.js').read_text(), 'export const radius = 12;')
            self.assertEqual(second, compile_project(root))
            (root / 'assets/tree.js').unlink()
            self.assertIn('error', compile_project(root)['environment'][0])


if __name__ == '__main__':
    unittest.main()
