"""Native benchmark comparison tolerates representation noise, not design edits."""
from copy import deepcopy
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

import cadquery as cq

from scripts.native_evidence import compare_native_evidence, equivalent_solids
from stud.cad import Model, publication_context
from stud.checks import check_model
from stud.contracts import read_json, write_json
from stud.source import evaluated_identity


class NativeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)

    def archive(self,name,shape):
        directory=self.root/name;directory.mkdir()
        with publication_context(lambda *args:None,directory,{'id':'test-runtime'},{},units='in'):
            model=Model('Native fixture',units='in')
            model.part('part',shape,blank={'size':[13.75,1.5,5.5]})
            model.requirement('valid','solid_valid',['part'])
            model.demand('supply',product_id='sample',specification={},object_ids=['part'],quantity=1)
        manifest=model.export()
        manifest.update(source_id='test-source',runtime={'id':'test-runtime'},settings={'full_checks':False},
                        checks=check_model(model),fabrication_findings=[],completion={'geometry':'complete'})
        write_json(directory/'manifest.json',manifest)
        return directory

    def test_observed_native_variants_prove_equal_without_weakening_history(self):
        fixture=Path(__file__).parent/'fixtures/native-reproduction'
        paths=[self.archive(name,cq.Shape.importBrep(str(fixture/(name+'.brep')))) for name in ('a','b')]
        manifests=[read_json(path/'manifest.json') for path in paths]
        self.assertNotEqual(evaluated_identity(manifests[0]),evaluated_identity(manifests[1]))
        result=compare_native_evidence(*paths)
        self.assertTrue(result['equivalent']);self.assertFalse(result['byte_identity_matches'])
        self.assertEqual(result['native_difference_pairs'],1)
        with patch('scripts.native_evidence._empty_difference',side_effect=RuntimeError('kernel failed')):
            with self.assertRaisesRegex(RuntimeError,'kernel failed'):compare_native_evidence(*paths)

    def test_small_bore_and_moved_equal_volume_bore_are_not_equivalent(self):
        box=cq.Workplane('XY').box(2,2,1,centered=(False,False,False)).val()
        def bore(x):return box.cut(cq.Workplane('XY').center(x,.5).circle(.001).extrude(1).val())
        one,two=bore(.5),bore(.6)
        self.assertAlmostEqual(one.Volume(),two.Volume(),places=12)
        self.assertFalse(equivalent_solids(box,one))
        self.assertFalse(equivalent_solids(one,two))

    def test_touching_split_solids_are_not_one_physical_solid(self):
        box=cq.Workplane('XY').box(1,2,3,centered=(False,False,False)).val()
        half=cq.Workplane('XY').box(.5,2,3,centered=(False,False,False)).val()
        split=cq.Compound.makeCompound([half,half.translate((.5,0,0))])
        self.assertAlmostEqual(box.Volume(),split.Volume(),places=12)
        self.assertTrue(split.isValid())
        self.assertEqual(len(split.Solids()),2)
        self.assertFalse(equivalent_solids(box,split))

    def test_semantic_edits_and_corrupt_archives_fail_closed(self):
        shape=cq.Workplane('XY').box(1,1,1).val()
        a,b=[self.archive(name,shape) for name in ('a','b')]
        original=read_json(b/'manifest.json')
        mutations=[lambda m:m['objects'][0]['placement'][0].__setitem__(3,1e-10),
                   lambda m:m['demands'][0].__setitem__('quantity',2),
                   lambda m:m['requirements'][0].__setitem__('threshold',1e-12),
                   lambda m:m['checks']['findings'][0].__setitem__('status','failed'),
                   lambda m:m['objects'][0]['bounds']['max'].__setitem__(0,1)]
        for mutate in mutations:
            manifest=deepcopy(original);mutate(manifest);write_json(b/'manifest.json',manifest)
            with self.assertRaises(AssertionError):compare_native_evidence(a,b)
        write_json(b/'manifest.json',original)
        asset=next(iter(original['assets'].values()))
        (b/asset['native']).write_bytes(b'corrupt')
        with self.assertRaisesRegex(AssertionError,'Corrupt native asset'):compare_native_evidence(a,b)

    def test_optimized_python_cannot_skip_the_equivalence_guards(self):
        shape=cq.Workplane('XY').box(1,1,1).val()
        a,b=[self.archive(name,shape) for name in ('a','b')]
        manifest=read_json(b/'manifest.json');manifest['demands'][0]['quantity']=999
        write_json(b/'manifest.json',manifest)
        result=subprocess.run([sys.executable,'-O','-c',
            'import sys;from scripts.native_evidence import compare_native_evidence;compare_native_evidence(*sys.argv[1:])',str(a),str(b)],
            cwd=Path(__file__).resolve().parents[1],text=True,capture_output=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Different demands',result.stderr)
