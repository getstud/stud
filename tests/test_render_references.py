import base64
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from stud.contracts import StudError
from stud.render_references import save_render_reference


PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='


class RenderReferenceTests(unittest.TestCase):
    def test_native_display_binds_finish_demands_to_their_objects_and_product(self):
        import cadquery as cq
        from stud.cad import Model, publication_context
        from stud.display import model_from_manifest
        with tempfile.TemporaryDirectory() as root:
            with publication_context(lambda *args:None, root, {'id':'render-fixture'}, {}, units='in'):
                model=Model('Paint assignments',units='in')
                panel=cq.Workplane('XY').box(12,1,12)
                for name in ['front','back','unspecified']:
                    model.part(name,panel,material='siding')
                model.demand('front-red',product_id='siding',object_ids=['front'],specification={'finish':'red paint'},quantity=1)
                model.demand('back-blue',product_id='siding',object_ids=['back'],specification={'finish':'blue paint'},quantity=1)
                model.demand('front-grain',product_id='siding',object_ids=['front'],specification={'grain':'vertical'},quantity=1)
                model.demand('hardware',product_id='screw',object_ids=['front'],specification={'finish':'zinc'},quantity=4)
            manifest=model.export()
            manifest.update(project_id='test',build_id='build',source_id='source',completion={'geometry':'complete'})
            session=SimpleNamespace(state={'latest_build':None,'view_mode':'live'})
            projected=model_from_manifest(session,manifest,{'id':'build','status':'complete'},inputs={})
            parts={part['id']:part for part in projected['parts']}
            self.assertEqual(parts['front']['material_specifications'],[{'finish':'red paint','length_unit':'in'},{'grain':'vertical','length_unit':'in'}])
            self.assertEqual(parts['back']['material_specifications'],[{'finish':'blue paint','length_unit':'in'}])
            self.assertEqual(parts['unspecified']['material_specifications'],[])
            self.assertNotIn('specification',projected['stocks']['siding'])

    def payload(self):
        return dict(image=PNG, brief=dict(schema_version=1, kind='stud-render-reference',
            revision='build:final', prompt='Preserve the geometry.', displayed=dict(checkpoint='saved')))

    def test_saved_artifacts_are_immutable_project_local_inputs(self):
        with tempfile.TemporaryDirectory() as root:
            first = save_render_reference(root, self.payload())
            second = save_render_reference(root, self.payload())
            self.assertNotEqual(first['reference_id'], second['reference_id'])
            reference = Path(first['reference_path'])
            self.assertTrue(reference.is_relative_to(Path(root).resolve() / 'exports/render-references'))
            self.assertEqual(reference.read_bytes(), base64.b64decode(PNG.split(',')[1]))
            brief = json.loads(Path(first['brief_path']).read_text())
            self.assertEqual(brief['displayed']['checkpoint'], 'saved')
            self.assertEqual(brief['image']['width'], 1)
            self.assertEqual(len(brief['image']['sha256']), 64)
            self.assertFalse((Path(root) / 'records').exists())

    def test_invalid_payloads_and_paths_are_rejected_before_writing(self):
        for change in [dict(image='invalid'), dict(brief={}), dict(path='../escape.png'),
                       dict(brief={**self.payload()['brief'], 'prompt':'x'*(1024*1024)}),
                       dict(brief={**self.payload()['brief'], 'camera':float('nan')})]:
            with self.subTest(change=list(change)), tempfile.TemporaryDirectory() as root:
                with self.assertRaises(ValueError):
                    save_render_reference(root, {**self.payload(), **change})
                self.assertEqual(list(Path(root).iterdir()), [])

    def test_export_symlink_cannot_escape_project(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            (Path(root) / 'exports').symlink_to(other, target_is_directory=True)
            with self.assertRaises(StudError) as caught:
                save_render_reference(root, self.payload())
            self.assertIn('path', str(caught.exception).lower())
            self.assertEqual(list(Path(other).iterdir()), [])


class RenderReferenceHTTPTests(unittest.TestCase):
    def test_capture_route_enforces_origin_and_json_limits(self):
        import serve
        from stud.session_http import make_handler
        with tempfile.TemporaryDirectory() as root:
            # Any attempt to execute design/session work on this route fails:
            # the adapter needs only a root and the error-envelope identity.
            session=SimpleNamespace(root=Path(root),manifest={'project_id':'render-http-fixture'})
            handler=make_handler(session)
            server=serve.ViewerServer(('127.0.0.1',0),handler)
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            url=f'http://127.0.0.1:{server.server_port}/api/render-references'
            payload=RenderReferenceTests().payload()
            def post(data=payload,headers=None):
                request=Request(url,json.dumps(data).encode(),headers=headers or {'Content-Type':'application/json'},method='POST')
                with urlopen(request,timeout=5) as response:return json.load(response)
            try:
                result=post()
                self.assertTrue(Path(result['reference_path']).is_file())
                self.assertEqual(result['revision'],'build:final')
                for headers,status in [({'Content-Type':'application/json','Origin':'https://other.example'},403),
                                       ({'Content-Type':'text/plain'},415),
                                       ({'Content-Type':'application/json','Host':'other.example'},403)]:
                    with self.assertRaises(HTTPError) as caught:post(headers=headers)
                    self.assertEqual(caught.exception.code,status)
                with self.assertRaises(HTTPError) as caught:post({'image':'bad','brief':payload['brief']})
                self.assertEqual(caught.exception.code,422)
                with self.assertRaises(HTTPError) as caught:post(headers={'Content-Type':'application/json','Content-Length':str(8*1024*1024+1)})
                self.assertEqual(caught.exception.code,422)
                self.assertEqual(len(list((Path(root)/'exports/render-references').iterdir())),1)
            finally:
                server.shutdown();server.server_close();worker.join(timeout=5)
