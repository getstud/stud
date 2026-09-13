"""Independent geometry, purchasing and composition oracles for foundations."""
from decimal import Decimal
import math
from pathlib import Path
import runpy
import unittest

import cadquery as cq

from stud.bulk import volume_demand
from stud.cad import Model
from stud.checks import check_model, resolve_point
from stud.estimate import purchase_lines
from stud.fabrication import audit_fabrication
from stud.solids import prism, round_member

RECIPES = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                            'examples/cadquery-foundations/foundations.py'))['RECIPES']


class SolidOperationTests(unittest.TestCase):
    def test_ring_and_openings_preserve_net_volume_under_rotation(self):
        frame=cq.Plane(origin=(10,20,30),xDir=(0,1,0),normal=(1,0,0))
        shape=prism([(0,0),(10,0),(10,8),(0,8)],3,
                    holes=[[(2,2),(8,2),(8,6),(2,6)]],frame=frame)
        self.assertAlmostEqual(shape.Volume(),(80-24)*3)
        box=shape.BoundingBox()
        self.assertAlmostEqual(box.xmin,10); self.assertAlmostEqual(box.xmax,13)
        self.assertAlmostEqual(box.ymin,20); self.assertAlmostEqual(box.ymax,30)
        self.assertAlmostEqual(box.zmin,30); self.assertAlmostEqual(box.zmax,38)

    def test_invalid_or_touching_openings_are_rejected_instead_of_clipped(self):
        outline=[(0,0),(10,0),(10,10),(0,10)]
        good=[(2,2),(4,2),(4,4),(2,4)]
        for holes in [
            [[(-1,2),(2,2),(2,4),(-1,4)]],
            [[(0,2),(2,2),(2,4),(0,4)]],
            [good,good],
            [good,[(4,2),(6,2),(6,4),(4,4)]],
            [[(20,20),(22,20),(22,22),(20,22)]],
        ]:
            with self.subTest(holes=holes),self.assertRaises(ValueError):prism(outline,2,holes=holes)
        for profile in ([(0,0),(1,0),(2,0)],[(0,0),(2,2),(0,2),(2,0)],[(0,0),(math.nan,0),(0,1)]):
            with self.assertRaises(ValueError):prism(profile,2)
        for depth in (0,-1,math.inf,'four'):
            with self.assertRaises(ValueError):prism(outline,depth)

    def test_round_pipe_on_diagonal_has_expected_material_and_end_faces(self):
        shape=round_member((10,20,30),(13,24,30),4,inner_diameter=2)
        self.assertAlmostEqual(shape.Volume(),math.pi*(4-1)*5)
        faces=[face for face in shape.Faces() if face.geomType()=='PLANE']
        self.assertEqual(len(faces),2)
        self.assertEqual(sorted(tuple(round(v,6) for v in f.Center().toTuple()) for f in faces),
                         [(10,20,30),(13,24,30)])
        for start,end,outer,inner in [((0,0,0),(0,0,0),4,0),((0,0,0),(0,0,4),4,4),
                                       ((0,0,0),(0,math.inf,4),4,0),((0,0,0),(0,0,4),-1,0)]:
            with self.assertRaises(ValueError):round_member(start,end,outer,inner_diameter=inner)


class BulkMaterialTests(unittest.TestCase):
    def test_native_volumes_convert_to_delivery_units_without_changing_geometry(self):
        for units,scale in [('in',1),('mm',25.4)]:
            model=Model('One cubic yard',units=units)
            shape=cq.Workplane('XY').box(36*scale,36*scale,36*scale)
            model.part('pour',shape,material='concrete')
            volume_demand(model,'pour.volume',product_id='concrete',specification={},object_ids=['pour'],
                          purchase_unit='yd3',purchase_increment='.25')
            plan=purchase_lines(list(model.demands.values()),{})[0]
            self.assertEqual(Decimal(plan['quantity']),1)
            self.assertAlmostEqual(float(plan['demand_quantity']),46656*scale**3)
            self.assertEqual(audit_fabrication(model.export()),[])

    def test_union_prevents_counting_thickened_edge_twice(self):
        model=Model('One pour',units='in')
        slab=cq.Workplane('XY').box(20,10,4,centered=(False,False,False)).val()
        thickening=cq.Workplane('XY').box(5,10,8,centered=(False,False,False)).val()
        model.part('pour',slab.fuse(thickening).clean(),material='concrete')
        volume_demand(model,'v',product_id='concrete',specification={},object_ids=['pour'],purchase_unit='ft3')
        self.assertAlmostEqual(float(model.demands['v']['quantity']),1000)
        self.assertEqual(Decimal(model.demands['v']['pack_size']),1728)
        with self.assertRaises(ValueError):
            volume_demand(model,'duplicate',product_id='concrete',specification={},object_ids=['pour','pour'],purchase_unit='ft3')

    def test_delivery_boundaries_survive_split_pours_and_cross_system_conversion(self):
        for separate in (True,False):
            model=Model('Quarter yard split across pours',units='in')
            for pid,volume in [('a',1234.567891234),('b',11664-1234.567891234)]:
                model.part(pid,cq.Workplane('XY').box(10,10,volume/100),material='concrete')
            groups=[['a'],['b']] if separate else [['a','b']]
            for ids in groups:
                volume_demand(model,ids[0],product_id='concrete',specification={},object_ids=ids,
                              purchase_unit='yd3',purchase_increment='.25')
            self.assertEqual(Decimal(purchase_lines(list(model.demands.values()),{})[0]['quantity']),Decimal('.25'))
        model=Model('Quarter cubic meter in inches',units='in')
        model.part('pour',cq.Workplane('XY').box(1000/25.4,1000/25.4,250/25.4),material='concrete')
        volume_demand(model,'v',product_id='concrete',specification={},object_ids=['pour'],
                      purchase_unit='m3',purchase_increment='.25')
        self.assertEqual(Decimal(purchase_lines(list(model.demands.values()),{})[0]['quantity']),Decimal('.25'))
        # A real excess still requires the next delivery increment.
        model.demands['v']['quantity']=str(Decimal(model.demands['v']['quantity'])+1)
        self.assertEqual(Decimal(purchase_lines(list(model.demands.values()),{})[0]['quantity']),Decimal('.50'))

    def test_volume_audit_detects_replaced_solid_and_wrong_cubic_units(self):
        model=Model('Stale volume',units='in')
        model.part('pour',cq.Workplane('XY').box(10,10,10),material='concrete')
        volume_demand(model,'v',product_id='concrete',specification={},object_ids=['pour'],purchase_unit='yd3')
        model.part('pour',cq.Workplane('XY').box(20,10,10),material='concrete',replace=True)
        self.assertIn('stale_material_volume',{f['category'] for f in audit_fabrication(model.export())})
        manifest=model.export();manifest['demands'][0]['unit']='mm3'
        self.assertIn('incompatible_material_units',{f['category'] for f in audit_fabrication(manifest)})

    def test_volume_audit_detects_part_counted_by_component_and_assembly_demands(self):
        model=Model('Duplicate takeoff',units='in')
        model.part('pad',cq.Workplane('XY').box(36,36,9),material='concrete')
        for key in ('pad.volume','foundation.volume'):
            volume_demand(model,key,product_id='concrete',specification={},object_ids=['pad'],
                          purchase_unit='yd3',purchase_increment='.25')
        findings=audit_fabrication(model.export())
        self.assertEqual([(f['category'],f['target']) for f in findings],[('duplicate_material_volume','pad')])


class FoundationRecipeTests(unittest.TestCase):
    def test_every_major_family_has_valid_geometry_and_explicit_design_gaps(self):
        self.assertEqual(len(RECIPES),13)
        for name,builder in RECIPES.items():
            with self.subTest(foundation=name):
                model=Model(name,units='in');result=builder(model)
                checks=check_model(model)
                self.assertTrue(checks['all_passed'],checks['findings'])
                self.assertEqual(set(result['parts']),set(model.objects))
                findings=audit_fabrication(model.export())
                if name=='frost_protected_slab':
                    self.assertTrue(all(f['category']=='missing_part_material' and 'insulation' in f['target'] for f in findings))
                else:self.assertEqual(findings,[])
                self.assertTrue(model.connections['foundation.design_basis']['unresolved'])
                self.assertTrue(all(d['unresolved'] for d in model.demands.values()))

    def test_stem_wall_and_floor_remain_independent_with_verified_bearing(self):
        model=Model('Independent floor',units='in');RECIPES['stem_wall_slab'](model)
        self.assertAlmostEqual(model.objects['foundation.floor_slab']['volume'],128*96*4)
        self.assertAlmostEqual(model.objects['foundation.stem_wall']['volume'],(144*112-128*96)*40)
        model.shapes['foundation.stem_wall']['world']=model.shapes['foundation.stem_wall']['world'].translate((0,0,1))
        self.assertTrue(any(f['kind']=='support' and f['status']=='failed' for f in check_model(model)['findings']))

    def test_nested_placement_moves_sections_dimensions_and_support_direction(self):
        model=Model('Placed foundations',units='in')
        model.assembly('building',location=cq.Location(cq.Vector(300,400,500),cq.Vector(1,0,0),25))
        RECIPES['stem_wall_slab'](model,parent='building',location=cq.Location(cq.Vector(20,30,40),cq.Vector(0,0,1),90))
        self.assertTrue(check_model(model)['all_passed'])
        a=resolve_point(model,'foundation.strip_footing:plan_origin')
        b=resolve_point(model,'foundation.strip_footing:plan_width')
        self.assertAlmostEqual((cq.Vector(*b)-cq.Vector(*a)).Length,144)
        self.assertNotEqual(model.drawings['foundation.section']['section']['normal'],[0,1,0])

    def test_parametric_plan_changes_preserve_part_identity_and_quantities(self):
        a=Model('Small',units='in');b=Model('Large',units='in')
        for model,width in [(a,144),(b,160)]:RECIPES['stem_wall_slab'](model,width=width)
        self.assertEqual(set(a.objects),set(b.objects))
        self.assertAlmostEqual(b.objects['foundation.floor_slab']['volume']-a.objects['foundation.floor_slab']['volume'],16*96*4)
        self.assertEqual(audit_fabrication(b.export()),[])
