import unittest
from stud import Project, Stock, pack_lengths
from build import compile_project, parts_csv

from pathlib import Path
import tempfile
from stud_cli import init_project

class ModelTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = init_project(Path(temporary.name)/'test')

    def test_short_piece_uses_correct_length_axis(self):
        p=Project('test');p.stock('wood','wood','#fff',section=(1.5,3.5),lengths=(96,))
        p.box('short','wall','wood',(1.5,3.5,1),(0,0,0))
        self.assertEqual(p.export()['materials'][0]['bins'][0]['cuts'][0]['length'],1)
    def test_invalid_and_duplicate_parts(self):
        p=Project('test');p.stock('wood','wood','#fff',section=(1.5,3.5),lengths=(96,))
        p.box('a','wall','wood',(1.5,3.5,80),(0,0,0))
        with self.assertRaises(ValueError):p.box('a','wall','wood',(1.5,3.5,80),(0,0,0))
        with self.assertRaises(ValueError):p.box('b','wall','wood',(2,4,80),(0,0,0))
        with self.assertRaises(ValueError):p.box('c','wall','wood',(1.5,3.5,float('nan')),(0,0,0))
    def test_kerf_prevents_impossible_two_halves(self):
        self.assertEqual(len(pack_lengths([('a',48),('b',48)],(96,))),2)
    def test_full_stock_and_leftover(self):
        self.assertEqual(pack_lengths([('a',96)],(96,))[0]['remaining'],0)
        b=pack_lengths([('a',48),('b',47.875)],(96,))
        self.assertEqual(len(b),1);self.assertEqual(b[0]['remaining'],0)
    def test_oversize_rejected(self):
        with self.assertRaises(ValueError):pack_lengths([('a',100)],(96,))
    def test_project_exports_reconcile(self):
        d=compile_project(self.project)
        self.assertEqual(sum(r['parts'] for r in d['materials']),len(d['parts']))
        self.assertEqual(len(d['parts']),len({p['id'] for p in d['parts']}))
        self.assertEqual(d['dimensions'][0]['inches'],80)
        self.assertEqual(len(parts_csv(d).splitlines()),len(d['parts'])+1)
        for r in d['materials']:
            for b in r.get('bins',[]): self.assertGreaterEqual(b['remaining'],0)
        self.assertTrue(all(p['status']=='proposed' for p in d['parts']))
    def test_coverage_uses_largest_face_regardless_of_name_or_rotation(self):
        for size in [(96, 48, .25), (96, .25, 48), (.25, 96, 48)]:
            for assembly in ['Roof surface', 'Canopy', 'Furniture']:
                with self.subTest(size=size, assembly=assembly):
                    project = Project('Coverage')
                    project.stock('cover', 'Covering', '#fff', coverage_sq_ft=10)
                    project.box('panel', assembly, 'cover', size, (0, 0, 0),
                                rotation=(25, 40, 15))
                    row = project.export()['materials'][0]
                    self.assertEqual(row['square_ft'], 32)
                    self.assertEqual(row['quantity'], 4)

    def test_profile_coverage_uses_sloped_face_or_trapezoidal_side(self):
        import math
        for width, depth, bottom, top, expected in [
                (96, 48, (0, 36), (.25, 36.25), 40),
                (.25, 48, (0, 0), (48, 96), 24),
                (96, 48, (0, 36), (48, 48), 40)]:
            project = Project('Profile coverage')
            project.stock('cover', 'Covering', '#fff', coverage_sq_ft=10, waste_factor=.1)
            project.profile_box('panel', 'Canopy', 'cover', width, depth,
                                (0, 0, 0), bottom, top)
            row = project.export()['materials'][0]
            self.assertEqual(row['square_ft'], expected)
            self.assertEqual(row['quantity'], math.ceil(expected * 1.1 / 10))
            project.parts[0]['assembly'] = 'Roof surface'
            self.assertEqual(project.export()['materials'][0], row)

    def test_revision_deterministic(self):
        self.assertEqual(compile_project(self.project)['revision'],compile_project(self.project)['revision'])

if __name__=='__main__':unittest.main()
