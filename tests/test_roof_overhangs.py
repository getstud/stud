"""Native overhang geometry, backing, cuts and composed placements."""
import math
import unittest

import cadquery as cq

from stud.buildings import gable_roof
from stud.cad import Model
from stud.checks import check_model, contact_area
from stud.construction import cut_rafter
from stud.fabrication import audit_fabrication


def roof_fixture(**options):
    model=Model('Roof overhang fixture',units='in')
    transform=options.pop('transform',cq.Location())
    model.assembly('building',location=transform)
    length,depth=64,72
    for side,size,origin in [('front',(length,3.5,3),(0,0,97)),('back',(length,3.5,3),(0,depth-3.5,97)),
                             ('left',(3.5,depth-7,3),(0,3.5,97)),('right',(3.5,depth-7,3),(length-3.5,3.5,97))]:
        model.part('plate.'+side,cq.Workplane('XY').box(*size,centered=(False,False,False)),parent='building',location=cq.Location(cq.Vector(*origin)))
    roof=gable_roof(model,object_id='roof',length=length,depth=depth,wall_top=100,parent='building',
                    bearing_parts={s:'plate.'+s for s in ('front','back')},
                    end_bearing_parts={s:'plate.'+s for s in ('left','right')},**options)
    model.requirement('roof.interference','collision_free',roof['parts']+roof['panels']+roof['gable_panels'],threshold=0)
    return model,roof


class RoofOverhangTests(unittest.TestCase):
    def assert_native_checks(self,model):
        checks=check_model(model,reuse=False)
        failures=[(f['requirement_id'],f['status'],f['measured'],f.get('error')) for f in checks['findings'] if f['status']!='passed']
        self.assertEqual(failures,[])
        audit=audit_fabrication({'units':'in','objects':list(model.objects.values()),'demands':list(model.demands.values()),'connections':list(model.connections.values())})
        self.assertEqual([f for f in audit if f['target'].startswith('roof')],[])

    def test_rafter_tail_preserves_seat_and_stock_frame(self):
        for eave in (0,8):
            shape,place,blank=cut_rafter(slope=.5,run=35.25,eave_overhang=eave)
            world=shape.moved(place)
            self.assertAlmostEqual(world.BoundingBox().ymin,-eave,places=6)
            self.assertAlmostEqual(world.BoundingBox().ymax,35.25,places=6)
            stock=cq.Workplane('XY').box(*blank['size'],centered=(False,False,False)).val()
            self.assertLess(shape.cut(stock).Volume(),1e-7)
            plate=cq.Workplane('XY').box(1.5,3.5,3,centered=(False,False,False)).translate((0,0,1.75-3)).val()
            self.assertAlmostEqual(contact_area(world,plate,1e-5,direction=cq.Vector(0,0,-1)),1.5*3.5,places=5)
            endpoints=blank['operations'][1]['stock_seat_endpoints']
            self.assertAlmostEqual(math.dist(*endpoints),3.5,places=6)

    def test_default_roof_remains_flush(self):
        model,roof=roof_fixture()
        self.assertFalse(any('.ladder.' in p or '.cap.' in p for p in roof['parts']))
        self.assertAlmostEqual(model.shapes[roof['rafters']['front'][0]]['world'].BoundingBox().ymin,0,places=6)
        self.assertAlmostEqual(model.shapes[roof['panels'][0]]['world'].BoundingBox().xmin,0,places=6)
        self.assert_native_checks(model)

    def test_overhangs_have_backed_deck_and_ladders_meeting_at_peak(self):
        model,roof=roof_fixture(eave_overhang=8,rake_overhang=8)
        self.assertAlmostEqual(model.shapes[roof['rafters']['front'][0]]['world'].BoundingBox().ymin,-8,places=6)
        self.assertAlmostEqual(model.shapes[roof['panels'][0]]['world'].BoundingBox().xmin,-8,places=6)
        for end in ('left','right'):
            for role in ('fly','rail'):
                a=model.shapes[f'roof.ladder.{end}.front.{role}']['world']
                b=model.shapes[f'roof.ladder.{end}.back.{role}']['world']
                self.assertGreater(contact_area(a,b,1e-5),1)
        self.assert_native_checks(model)

    def test_steep_one_ended_roof_with_small_eave_under_parent_transform(self):
        transform=cq.Location(cq.Vector(200,-40,17),cq.Vector(0,0,1),37)
        model,roof=roof_fixture(slope=.75,eave_overhang=.5,rake_overhang=6,gable_ends=('left',),transform=transform)
        self.assertTrue(roof['ladders']['front']['left'])
        self.assertEqual(roof['ladders']['front']['right'],[])
        self.assert_native_checks(model)

    def test_eave_only_and_omitted_gables_do_not_add_rake_geometry(self):
        for options in ({'eave_overhang':8},{'eave_overhang':8,'rake_overhang':8,'gable_ends':()}):
            with self.subTest(options=options):
                model,roof=roof_fixture(**options)
                self.assertFalse(any('.ladder.' in p or '.cap.' in p for p in roof['parts']))
                self.assert_native_checks(model)

    def test_narrow_ladder_and_returned_peak_height(self):
        model,roof=roof_fixture(eave_overhang=8,rake_overhang=3.6)
        self.assert_native_checks(model)
        actual=max(model.shapes[p]['world'].BoundingBox().zmax for p in roof['panels'])-100
        self.assertAlmostEqual(roof['height'],actual,places=5)

    def test_oversized_deck_reports_actual_extended_dimensions(self):
        model,roof=roof_fixture(eave_overhang=60,rake_overhang=40)
        demand=model.demands['roof.deck']
        self.assertTrue(demand['unresolved'])
        self.assertTrue(any(row['size'][0]>48 or row['size'][1]>96 for sheet in demand['sheets'] for row in sheet['panels']))

    def test_invalid_overhangs_reject_before_registering_geometry(self):
        for options in ({'eave_overhang':-1},{'rake_overhang':float('nan')},{'rake_overhang':3},{'ladder_spacing':0}):
            model=Model('Invalid',units='in')
            with self.assertRaises(ValueError):gable_roof(model,object_id='roof',length=64,depth=72,wall_top=100,**options)
            self.assertFalse(model.objects)
        for options in ({'eave_overhang':-1},{'eave_overhang':float('inf')},{'height':0}):
            with self.assertRaises(ValueError):cut_rafter(slope=.5,run=35.25,**options)


if __name__=='__main__':unittest.main()
