"""Shipped templates own their model definitions inside the captured project."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stud.contracts import read_json
from stud.session import Session
from stud_cli import init_project


class ExampleProjectTests(unittest.TestCase):
    def test_copied_model_helpers_run_and_local_edits_are_captured(self):
        examples=Path(__file__).resolve().parents[1]/'examples'
        with tempfile.TemporaryDirectory() as temporary,patch('stud_cli.register'):
            for name,module,count in [('workbench','workbench.py',12),('opening','opening.py',4),
                                      ('roof-joint','roof_joint.py',2),('hip-roof','hip_roof.py',69),('shed','shed.py',181),
                                      ('foundations','foundations.py',5)]:
                with self.subTest(example=name):
                    root=Path(temporary)/name;init_project(root,example=name)
                    original=(examples/('cadquery-'+name)/module).read_bytes()
                    self.assertEqual((root/module).read_bytes(),original)
                    with Session(root) as session:
                        request=session.begin(key='example',expected_head=session.snapshot()['option']['head'],intent='Use the copied example')
                        helper=Path(request['workspace'])/module
                        if name=='workbench':
                            helper.write_text(helper.read_text().replace('    imperial_model(model)\n','    imperial_model(model)\n    width += 1\n'),encoding='utf-8')
                        source=session.source(request['id'])
                        self.assertEqual((Path(source['path'])/'files'/module).read_bytes(),helper.read_bytes())
                        session.wait(session.evaluate(request['id'],source['source_id'])['id'],timeout=120)
                        result=session.wait(session.finish(request['id'],expected_source=source['source_id'],summary='Save project-owned example')['id'],timeout=120)
                        self.assertEqual(result['status'],'complete',result)
                        build=session.job(result['build_id']);manifest=read_json(Path(build['artifact_path'])/'manifest.json')
                        self.assertEqual(len(manifest['objects']),count)
                        if name=='hip-roof':
                            failures=[f for f in manifest['checks']['findings'] if f['status']!='passed']
                            self.assertEqual(len(failures),16)
                            self.assertTrue(all(f['kind']=='panel_edge_support' and f['status']=='failed' for f in failures))
                        else:
                            self.assertTrue(manifest['checks']['all_passed'])
                        if name=='workbench':
                            top=next(obj for obj in manifest['objects'] if obj['id']=='bench.top')
                            self.assertEqual(top['blank']['size'][0],73)
                    self.assertEqual((examples/('cadquery-'+name)/module).read_bytes(),original)
