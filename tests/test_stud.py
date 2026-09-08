from unittest.mock import patch
import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import os
import py_compile
import unittest
import urllib.request
import uuid

from stud_cli import init_project

ROOT = Path(__file__).resolve().parents[1]


class StudTests(unittest.TestCase):
    def setUp(self):
        catalog = tempfile.TemporaryDirectory()
        self.addCleanup(catalog.cleanup)
        env = patch.dict(os.environ, STUD_DATA_DIR=catalog.name)
        env.start()
        self.addCleanup(env.stop)

    def command(self, *args):
        return subprocess.run([sys.executable, str(ROOT/'stud_cli.py'), *map(str, args)],
                              cwd=tempfile.gettempdir(), capture_output=True, text=True)

    def test_external_project_build_and_failed_build_preserves_exports(self):
        with tempfile.TemporaryDirectory() as directory:
            project = init_project(Path(directory)/'external project', 'A new project')
            design = project/'design.py'
            with design.open('a') as stream:
                stream.write('\nimport helper\nproject.name = helper.NAME\n')
            (project/'helper.py').write_text("from pathlib import Path\nNAME = Path('title.txt').read_text()\n")
            (project/'title.txt').write_text('From a helper')
            result = self.command('build', project)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            exported = project/'output/model/model.json'
            previous = exported.read_bytes()
            self.assertEqual(json.loads(previous)['name'], 'From a helper')
            result = self.command('validate', project, '--strict', '--json')
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(json.loads(result.stdout)['counts']['UNVERIFIED'], 1)
            with design.open('a') as stream:
                stream.write("\nproject.validation = {'version': 999}\n")
            result = self.command('build', project)
            self.assertEqual(result.returncode, 1)
            self.assertIn('FAIL', result.stdout)
            self.assertEqual(exported.read_bytes(), previous)

    def test_entry_points_default_to_working_project(self):
        with tempfile.TemporaryDirectory() as directory:
            project = init_project(Path(directory)/'working-project', 'Working project')
            for script, arguments in [('stud_cli.py', ['build']), ('build.py', []),
                                      ('validate.py', ['--json'])]:
                result = subprocess.run([sys.executable, str(ROOT/script), *arguments],
                                        cwd=project, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            model = json.loads((project/'output/model/model.json').read_text())
            self.assertEqual(model['name'], 'Working project')

    def test_missing_design_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.command('build', directory)
            self.assertEqual(result.returncode, 1)
            self.assertFalse((Path(directory)/'output').exists())

    def test_init_never_overwrites_existing_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            project = init_project(Path(directory)/'new')
            original = (project/'design.py').read_bytes()
            with self.assertRaises(ValueError):
                init_project(project)
            self.assertEqual((project/'design.py').read_bytes(), original)

    def test_viewer_opens_before_any_build(self):
        from unittest.mock import patch, MagicMock
        import serve
        with tempfile.TemporaryDirectory() as directory:
            project = init_project(Path(directory)/'startup')
            (project/'design.py').write_text('this is an unfinished design')
            server = MagicMock(server_port=8765)
            with patch.object(serve, 'ViewerServer', return_value=server), \
                 patch.object(serve, 'model') as build, \
                 patch.object(serve.webbrowser, 'open') as open_browser:
                serve.serve(project)
                open_browser.assert_called_once_with('http://127.0.0.1:8765')
                build.assert_not_called()
                server.serve_forever.assert_called_once()
                server.server_close.assert_called_once()

    def test_server_project_storage_and_helper_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            project = init_project(Path(directory)/'served')
            other = init_project(Path(directory)/'other')
            with (project/'design.py').open('a') as stream:
                stream.write('\nimport helper\nproject.name = helper.NAME\n')
            (project/'helper.py').write_text("NAME = 'Before'\n")
            second = (project/'helper.py').stat().st_mtime_ns // 1_000_000_000 * 1_000_000_000
            os.utime(project/'helper.py', ns=(second, second + 100_000_000))
            py_compile.compile(str(project/'helper.py'))
            helper_stat = (project/'helper.py').stat()
            process = subprocess.Popen([sys.executable, str(ROOT/'stud_cli.py'), 'serve',
                                        str(project), '--port', '0', '--no-open'],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                import queue
                import threading
                ready = queue.Queue()
                reader = threading.Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True)
                reader.start()
                try:
                    line = ready.get(timeout=15)
                except queue.Empty:
                    process.terminate()
                    reader.join(timeout=5)
                    _, error = process.communicate(timeout=10)
                    self.fail(f'Server did not start (exit {process.returncode}): {error}')
                self.assertIn('http://', line)
                url = 'http://' + line.split('http://', 1)[1].strip()

                def get(path):
                    with urllib.request.urlopen(url+path, timeout=10) as response:
                        return response.read()

                self.assertIn(b'<b>stud</b>', get('/'))
                self.assertFalse((project/'output/model/model.json').exists())
                model = json.loads(get('/api/model'))
                self.assertEqual(model['name'], 'Before')
                report=json.loads(get('/api/validation'))
                self.assertEqual(report['revision'],model['revision'])
                self.assertEqual(report['coverage']['total_parts'],1)
                self.assertIn('validation_results',model)
                payload = dict(id=str(uuid.uuid4()), part_id='frame.stud.01', text='Keep this note')
                request = urllib.request.Request(url+'/api/comments', json.dumps(payload).encode(),
                                                 {'Content-Type': 'application/json'})
                with urllib.request.urlopen(request, timeout=10) as response:
                    self.assertEqual(response.status, 200)
                self.assertTrue((project/'annotations/comments.json').is_file())
                self.assertFalse((other/'annotations').exists())
                (project/'helper.py').write_text("NAME = 'After!'\n")
                os.utime(project/'helper.py', ns=(helper_stat.st_atime_ns, second + 200_000_000))
                edited = (project/'helper.py').stat()
                self.assertNotEqual(helper_stat.st_mtime_ns, edited.st_mtime_ns)
                self.assertEqual(int(helper_stat.st_mtime), int(edited.st_mtime))
                self.assertEqual(helper_stat.st_size, edited.st_size)
                self.assertEqual(json.loads(get('/api/model'))['name'], 'After!')
                self.assertIn(b'<b>stud</b>', get('/'))
                self.assertIn(b'frame.stud.01', get('/api/parts.csv'))
                self.assertTrue(get('/vendor/three.js'))
                self.assertIn(b'createShowTool', get('/show.js'))
                self.assertIn(b'outlineGeometry', get('/profile-geometry.js'))
                self.assertIn(b'installAreaCapture', get('/area-capture.js'))
                self.assertIn(b'createEnvironment', get('/environment.js'))
                (project/'assets').mkdir()
                (project/'assets/tree.js').write_text("import './helper.mjs'; export function create() {}")
                (project/'assets/helper.mjs').write_text('export const radius = 12;')
                with (project/'design.py').open('a') as stream:
                    stream.write("\nproject.context_asset('tree', source='assets/tree.js')\n")
                environment_model = json.loads(get('/api/model'))
                asset = environment_model['environment'][0]
                asset_url = '/environment/' + asset['revision'] + '/assets/'
                self.assertIn(b'create()', get(asset_url + 'tree.js'))
                with urllib.request.urlopen(url+asset_url+'helper.mjs') as response:
                    self.assertEqual(response.headers['Content-Type'], 'text/javascript')
                (project/'assets/helper.mjs').write_text('export const radius = 24;')
                updated = json.loads(get('/api/model'))
                self.assertNotEqual(updated['revision'], environment_model['revision'])
                self.assertEqual(get(asset_url+'helper.mjs'), b'export const radius = 12;')
                for forbidden in ('/environment/%2e%2e/%2e%2e/design.py', '/environment/%2fetc/passwd'):
                    with self.assertRaises(urllib.error.HTTPError) as denied:
                        get(forbidden)
                    self.assertEqual(denied.exception.code, 404)
                (project/'assets/tree.js').unlink()
                self.assertIn('error', json.loads(get('/api/model'))['environment'][0])
                # Area captures retain the viewed revision, even if the next build fails.
                from test_area_comments import area_payload, png
                screenshot = area_payload(png(100, 100))
                request = urllib.request.Request(url+'/api/comments', json.dumps(screenshot).encode(),
                                                 {'Content-Type': 'application/json'})
                with urllib.request.urlopen(request, timeout=10) as response:
                    self.assertEqual(response.status, 200)
                self.assertEqual(get('/api/comment-images/'+screenshot['id']), png(100, 100))
                last_good=(project/'output/model/model.json').read_bytes()
                with (project/'design.py').open('a') as stream:
                    stream.write("\nproject.box('collision', 'Frame', '2x4', (1.5, 3.5, 80), (0, 0, 0))\n")
                report=json.loads(get('/api/validation'))
                self.assertIn('build_error',report)
                self.assertTrue(any(f['status']=='FAIL' and f['rule']=='solid_collision' for f in report['findings']))
                self.assertEqual((project/'output/model/model.json').read_bytes(),last_good)
                screenshot['id'] = str(uuid.uuid4())
                request = urllib.request.Request(url+'/api/comments', json.dumps(screenshot).encode(),
                                                 {'Content-Type': 'application/json'})
                with urllib.request.urlopen(request, timeout=10) as response:
                    self.assertEqual(response.status, 200)
                self.assertEqual(get('/api/comment-images/'+screenshot['id']), png(100, 100))

            finally:
                process.terminate()
                process.communicate(timeout=10)

    def test_loopback_server_startup_does_not_use_dns(self):
        from serve import ViewerServer, Handler
        with patch('socket.getfqdn', side_effect=AssertionError('Loopback startup must not query DNS')):
            server = ViewerServer(('127.0.0.1', 0), Handler)
            try:
                self.assertEqual(server.server_name, '127.0.0.1')
                self.assertGreater(server.server_port, 0)
            finally:
                server.server_close()
