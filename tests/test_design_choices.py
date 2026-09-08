"""Alternative appearances retain the same assembly correctness checks."""
import copy
import unittest
from stud import wall_enclosure
import test_construction_assemblies as wall_cases
from test_construction_assemblies import failures
import test_bird_boxes as roof_cases
from test_roof_assemblies import failures as roof_failures


class DesignChoicesTests(unittest.TestCase):
    def test_siding_alignment_and_offset_preserve_openings_and_backing(self):
        opening=[dict(id='window',wall='front',start=40,width=36,bottom=32,height=36)]
        for angle,inward in ((0,1),(37,-1)):
            for layout,offset in (('centered',0),('start',0),('start',18)):
                with self.subTest(angle=angle,inward=inward,layout=layout,offset=offset):
                    p,w=wall_cases.WallTests().make(angle,inward,openings=opening)
                    wall_enclosure(p,'skin',walls=w,sheathing_stock='sheet',siding_stock='sheet',
                                   trim_stock='trim',siding_layout=layout,siding_offset=offset)
                    self.assertFalse(failures(p),failures(p))
                    panels=[part for part in p.parts if part['id'].startswith('skin.back.siding.')]
                    widths=[part['size'][1] for part in panels]
                    self.assertTrue(all(width<=48 for width in widths))
                    if layout=='centered':self.assertAlmostEqual(widths[0],widths[-1])
                    else:self.assertAlmostEqual(widths[0],offset or 48)
                    changed=copy.deepcopy(p)
                    panel=next(part for part in changed.parts if part['id'].startswith('skin.front.siding.'))
                    panel['origin'][2]+=.25
                    self.assertTrue(failures(changed))

    def test_invalid_layout_does_not_partially_commit(self):
        for options in (dict(siding_layout='diagonal'),dict(siding_offset=2),
                        dict(siding_layout='start',siding_offset=48)):
            p,w=wall_cases.WallTests().make();before=copy.deepcopy(p.parts)
            with self.assertRaises(ValueError):
                wall_enclosure(p,'skin',walls=w,sheathing_stock='sheet',siding_stock='sheet',
                               trim_stock='trim',**options)
            self.assertEqual(p.parts,before)

    def test_siding_stock_errors_remain_actionable(self):
        for stock in ('missing','stud'):
            p,w=wall_cases.WallTests().make()
            with self.assertRaisesRegex(ValueError,'registered sheet stock'):
                wall_enclosure(p,'skin',walls=w,sheathing_stock='sheet',siding_stock=stock,trim_stock='trim')

    def test_boxed_and_triangular_returns_are_both_supported(self):
        for options,vertices in (({},4),(dict(eave_fascia_overlap=.375*1.25**.5,bird_box_return=7),3)):
            p,r=roof_cases.BirdBoxTests().roof(**options)
            self.assertFalse(roof_failures(p),roof_failures(p))
            face=next(part for part in p.parts if part['id']==r.roles['bird_box.0.0.face'])
            self.assertEqual(len(face['outline']),vertices)
