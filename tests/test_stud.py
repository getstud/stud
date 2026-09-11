from unittest.mock import patch
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from stud_cli import init_project
from stud.contracts import StudError
from stud.source import manifest_at

ROOT = Path(__file__).resolve().parents[1]


class StudTests(unittest.TestCase):
    def setUp(self):
        catalog = tempfile.TemporaryDirectory()
        self.addCleanup(catalog.cleanup)
        env = patch.dict(os.environ, STUD_DATA_DIR=catalog.name)
        env.start()
        self.addCleanup(env.stop)

    def test_uninitialized_projects_are_rejected_without_executing_python(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Cover both an old-style file and an interrupted current init.
            for export in ('project', 'model'):
                (root/'design.py').write_text("from pathlib import Path\nPath('executed').touch()\n"+export+' = object()\n')
                for command in ([ROOT/'stud_cli.py','build',root],
                                [ROOT/'stud_cli.py','validate',root,'--json'],
                                [ROOT/'stud_cli.py','serve',root,'--port','0','--no-open'],
                                [ROOT/'build.py'], [ROOT/'validate.py','--json'],
                                [ROOT/'serve.py','--port','0','--no-open']):
                    with self.subTest(export=export, command=command):
                        result=subprocess.run([sys.executable,*map(str,command)],cwd=root,capture_output=True,text=True,timeout=15)
                        self.assertEqual(result.returncode,1,result.stdout+result.stderr)
                        self.assertIn('stud.json',result.stderr)
                        self.assertNotIn('Traceback',result.stderr)
                        self.assertFalse((root/'executed').exists())
                        self.assertFalse((root/'output').exists())
                        self.assertFalse((root/'.stud').exists())

    def test_manifest_rejects_other_engines(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'stud.json').write_text(json.dumps({'schema_version':1,'engine':'parts'}))
            with self.assertRaises(StudError) as caught:manifest_at(root)
            self.assertEqual(caught.exception.category,'unsupported_project')

    def test_init_never_overwrites_existing_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            project = init_project(Path(directory)/'new')
            original = (project/'design.py').read_bytes()
            with self.assertRaises(ValueError):init_project(project)
            self.assertEqual((project/'design.py').read_bytes(),original)

    def test_nested_init_fails_before_creating_a_partial_project(self):
        from stud.history import History
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);History(root).git('init')
            destination=root/'nested'/'new'
            with self.assertRaises(StudError) as caught:init_project(destination)
            self.assertEqual(caught.exception.category,'nested_repository')
            self.assertFalse(destination.exists())

    def test_generated_python_is_utf8_under_windows_locale(self):
        write_text = Path.write_text
        def windows_write(path,data,encoding=None,errors=None,newline=None):
            return write_text(path,data,encoding=encoding or 'cp1252',errors=errors,newline=newline)
        with tempfile.TemporaryDirectory() as directory, patch.object(Path,'write_text',windows_write):
            project=init_project(Path(directory)/'new','Café 工作台')
            source=(project/'design.py').read_bytes()
            self.assertIn('Café 工作台',source.decode('utf-8'))
            compile(source,str(project/'design.py'),'exec')
            self.assertIn('Café 工作台',(project/'README.md').read_text(encoding='utf-8'))

    def test_viewer_delegates_to_coordinator_without_executing_source(self):
        import serve
        with tempfile.TemporaryDirectory() as directory:
            root=init_project(Path(directory)/'project')
            (root/'design.py').write_text("raise AssertionError('must not execute here')")
            with patch('stud.session_http.serve_project',return_value='served') as coordinator:
                self.assertEqual(serve.serve(root,8765,open_browser=False),'served')
                coordinator.assert_called_once_with(root,8765,open_browser=False)

    def test_loopback_server_startup_does_not_use_dns(self):
        from serve import ViewerServer, Handler
        with patch('socket.getfqdn',side_effect=AssertionError('Loopback startup must not query DNS')):
            server=ViewerServer(('127.0.0.1',0),Handler)
            try:
                self.assertEqual(server.server_name,'127.0.0.1')
                self.assertGreater(server.server_port,0)
            finally:server.server_close()
