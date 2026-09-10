"""Independent geometric oracles for CadQuery output and reusable framing."""
import math
import unittest
import runpy
from pathlib import Path

import cadquery as cq

from stud.cad import Model
from stud.checks import check_model, measure_requirement, resolve_point
EXAMPLES=Path(__file__).resolve().parents[1]/'examples'
workbench=runpy.run_path(str(EXAMPLES/'cadquery-workbench/workbench.py'))['workbench']
rotated_opening=runpy.run_path(str(EXAMPLES/'cadquery-opening/opening.py'))['rotated_opening']
roof_joint=runpy.run_path(str(EXAMPLES/'cadquery-roof-joint/roof_joint.py'))['roof_joint']
from stud.buildings import floor_frame, framed_wall
from stud.contracts import StudError
from stud.fabrication import audit_fabrication


class NativeGeometryTests(unittest.TestCase):
    def test_rotated_workbench_drawings_follow_its_placement_and_section_plane(self):
        from stud.plans import project_vector,view_basis
        model=Model('Rotated bench',units='in')
        workbench(model,dog_hole=None,location=cq.Location(cq.Vector(10,20,0),cq.Vector(0,0,1),90))
        self.assertTrue(check_model(model)['all_passed'])
        section=model.drawings['bench.section']['section']
        for actual,expected in zip(section['origin'],[10,20+36,0]):self.assertAlmostEqual(actual,expected)
        for view in model.drawings.values():
            right,up,_=view_basis(view)
            for key in view['dimensions']:
                dimension=model.dimensions[key]
                delta=cq.Vector(*resolve_point(model,dimension['end']))-cq.Vector(*resolve_point(model,dimension['start']))
                self.assertAlmostEqual(math.hypot(delta.dot(right),delta.dot(up)),delta.Length)
        _,projection=project_vector(model,model.drawings['bench.section'],10)
        self.assertEqual(set(projection['section_objects']),{'bench.top','bench.shelf','bench.rail.upper.front',
            'bench.rail.upper.back','bench.rail.lower.front','bench.rail.lower.back'})

    def test_support_projects_contact_in_the_declared_bearing_direction(self):
        model=Model('Bearing direction',units='in');box=cq.Workplane('XY').box(10,10,10,centered=(False,False,False))
        model.part('load',box);model.part('side',box,location=cq.Location(cq.Vector(10,0,0)))
        model.part('below',box,location=cq.Location(cq.Vector(0,0,-10)))
        model.requirement('false_bearing','support',['load','side'],threshold=99,direction=[0,0,-1])
        model.requirement('downward','support',['load','below'],threshold=99)
        model.requirement('sideways','support',['load','side'],threshold=99,direction=[1,0,0])
        results={f['requirement_id']:f for f in check_model(model)['findings']}
        self.assertEqual(results['false_bearing']['measured'],0)
        self.assertAlmostEqual(results['downward']['measured'],100)
        self.assertAlmostEqual(results['sideways']['measured'],100)

    def test_end_members_do_not_overlap_and_sheet_seams_follow_custom_spacing(self):
        for builder in (framed_wall,floor_frame):
            model=Model('End boundary',units='in');part=builder(model,object_id='component',length=98,spacing=24)
            model.requirement('independent_interference','collision_free',part['parts'])
            self.assertTrue(check_model(model)['all_passed'])
            positions=sorted(set(round(model.objects[p]['placement'][0][3],4) for p in part['panels']))
            self.assertEqual(positions,[0,48,72])
        model=Model('Actual missing backing',units='in');part=framed_wall(model,object_id='wall',length=120,spacing=24)
        model.shapes['wall.stud.at_96']['world']=model.shapes['wall.stud.at_96']['world'].moved(cq.Location(cq.Vector(2,0,0)))
        findings=check_model(model)['findings']
        self.assertTrue(any(f['kind']=='panel_edge_support' and f['status']=='failed' and f['measured']>80 for f in findings))

    def test_purchase_audit_detects_missing_material_stale_cut_and_hardware(self):
        from copy import deepcopy
        model=Model('Purchases',units='in');workbench(model);manifest=model.export()
        self.assertEqual(audit_fabrication(manifest),[])
        wrong=deepcopy(manifest);wrong['demands'][0]['cuts'][0]['length']=10
        self.assertIn('stale_cut_length',{f['category'] for f in audit_fabrication(wrong)})
        wrong=deepcopy(manifest);wrong['demands']=[d for d in wrong['demands'] if d['product_id']!='panel.plywood']
        self.assertEqual({f['target'] for f in audit_fabrication(wrong) if f['category']=='missing_part_material'},{'bench.top','bench.shelf'})
        wrong=deepcopy(manifest);wrong['connections'][0]['hardware']['count']=10000
        self.assertIn('missing_hardware_quantity',{f['category'] for f in audit_fabrication(wrong)})
        wrong=deepcopy(manifest);wrong['demands'][0]['specification']['section']=[1,1]
        self.assertIn('incompatible_stock_section',{f['category'] for f in audit_fabrication(wrong)})
        corner=Model('Counted plate',units='in');rotated_opening(corner);wrong=corner.export()
        next(d for d in wrong['demands'] if d['product_id']=='steel.plate.3x3x0.25')['quantity']=0
        self.assertIn('missing_part_quantity',{f['category'] for f in audit_fabrication(wrong)})

    def test_panel_bearing_requirement_must_resolve_and_custom_opening_stays_supported(self):
        from stud.plans import preflight
        model=Model('Custom spacing',units='in');framed_wall(model,object_id='wall',length=120,spacing=24,
            openings=[dict(id='window',x=48,width=34,sill=36,height=36)])
        checks=check_model(model);self.assertTrue(checks['all_passed'],checks)
        model.requirements.pop('wall.panel.1.0.edge_backing')
        manifest=model.export();manifest['checks']=check_model(model)
        manifest['completion']=dict(geometry='complete',checks='complete',quantities='complete')
        result=preflight(model,manifest)
        self.assertTrue(any(f['category']=='unresolved_sheet_support' and f['target']=='wall.panel.1.0' for f in result['findings']))

    def test_corner_profile_bore_and_birdsmouth_use_reproducible_local_coordinates(self):
        model=Model('Mirror',units='in');rotated_opening(model,mirrored_detail=True)
        self.assertEqual(audit_fabrication(model.export()),[])
        operations=model.objects['opening.corner_detail']['blank']['operations']
        self.assertEqual(operations[1]['center'],[2.375,.625])
        self.assertIn((0,1),operations[0]['profile'])
        from stud.plans import project_vector,operation_text
        drawing,_=project_vector(model,model.drawings['opening.corner_plan'],1)
        self.assertAlmostEqual(drawing.width,3*72,places=5)
        roof=Model('Stock datum',units='in');roof_joint(roof)
        cut=roof.objects['roof_joint.rafter']['blank']['operations'][1]
        self.assertAlmostEqual(cut['stock_seat_endpoints'][0][2],1.75/math.sqrt(1.25))
        self.assertAlmostEqual(cut['stock_seat_endpoints'][1][2],0)
        self.assertIn('rectangular blank Y-Z face',operation_text(cut))
    def test_nested_rigid_placements_and_unchanged_instance_identity(self):
        model=Model('Nested',units='in')
        model.assembly('outer',location=cq.Location(cq.Vector(10,20,30),cq.Vector(0,0,1),90))
        model.assembly('inner',parent='outer',location=cq.Location(cq.Vector(5,0,0),cq.Vector(1,0,0),90))
        model.part('part',cq.Workplane('XY').box(3,4,5,centered=(False,False,False)),parent='inner',location=cq.Location(cq.Vector(2,3,4)))
        point=model.reference('part','corner',point=(3,4,5))
        # Local (5,7,9) -> inner rotation (5,-9,7), translation (10,-9,7)
        # -> outer rotation (9,10,7), translation (19,30,37).
        self.assertEqual([round(v,7) for v in resolve_point(model,point)],[19,30,37])
        self.assertAlmostEqual(model.shapes['part']['world'].Volume(),60)

    def test_stock_frame_for_sloped_rafter_is_rectangular_and_measured(self):
        model=Model('Sloped',units='in');roof_joint(model,slope=.5,run=20,seat=3.5)
        result=check_model(model)
        self.assertTrue(result['all_passed'],result)
        blank=model.objects['roof_joint.rafter']['blank']['size']
        self.assertEqual(blank[0],1.5);self.assertEqual(blank[2],5.5)
        self.assertAlmostEqual(blank[1],(20+5.5*math.sin(math.atan(.5)))/math.cos(math.atan(.5)))
        expected=1.5*(20*5.5/math.cos(math.atan(.5))-.5*.5*3.5**2)
        self.assertAlmostEqual(model.shapes['roof_joint.rafter']['local'].Volume(),expected,places=5)
        bearing=next(f for f in result['findings'] if f['requirement_id']=='roof_joint.bearing')
        self.assertAlmostEqual(bearing['measured'],1.5*3.5,places=5)

    def test_bored_solid_distance_uses_hole_not_bounds(self):
        model=Model('Hole',units='in')
        bored=cq.Workplane('XY').box(100,100,20,centered=(False,False,False)).cut(cq.Workplane('XY').circle(10).extrude(20).translate((50,50,0)))
        model.part('plate',bored)
        model.part('pin',cq.Workplane('XY').circle(4).extrude(20),location=cq.Location(cq.Vector(50,50,0)))
        model.requirement('clear','clearance',['plate','pin'],threshold=6)
        value,passed,_=measure_requirement(model,model.requirements['clear'])
        self.assertAlmostEqual(value,6,places=6);self.assertTrue(passed)
        self.assertAlmostEqual(model.objects['plate']['volume'],200000-math.pi*100*20,places=5)

    def test_near_faces_are_not_bearing_and_unsupported_is_visible(self):
        model=Model('Contact',units='in')
        box=cq.Workplane('XY').box(10,20,30,centered=(False,False,False))
        model.part('a',box);model.part('b',box,location=cq.Location(cq.Vector(10.005,0,0)))
        model.requirement('bearing','contact',['a','b'],threshold=1,tolerance=.001)
        model.requirement('unsupported','curved_bearing',['a','b'])
        result=check_model(model)
        self.assertEqual(result['counts']['failed'],1)
        self.assertEqual(result['counts']['unsupported'],1)
        self.assertFalse(result['coverage']['complete'])

    def test_batch_rollback_reference_replacement_and_frozen_blank(self):
        model=Model('Rollback',units='in');blank={'size':[10,20,30],'operations':[{'kind':'square_cut'}]}
        shape=cq.Workplane('XY').box(10,20,30,centered=(False,False,False))
        model.part('a',shape,blank=blank)
        blank['size'][0]=1
        self.assertEqual(model.objects['a']['blank']['size'][0],10)
        model.reference('a','old',point=(0,0,0))
        before=model.export()
        with self.assertRaisesRegex(RuntimeError,'abort'):
            with model.batch():
                model.part('b',shape);model.assembly('new')
                model.requirement('new','stock_fit',['b'])
                model.demand('new',product_id='new',specification={},object_ids=['b'])
                model.dimension('new','a:old',[0,0,0]);model.drawing('new')
                model.connection('new',parts=['b'],description='new');model.step('new','new',parts=['b'])
                model.notes.append('unpublished')
                raise RuntimeError('abort')
        after=model.export()
        for key in ('objects','assemblies','references','requirements','demands','dimensions','drawings','connections','steps','notes'):
            self.assertEqual(after[key],before[key],key)
        model.part('a',shape,replace=True)
        with self.assertRaises(StudError):resolve_point(model,'a:old')
        with self.assertRaises(StudError):model.part('face',cq.Workplane('XY').rect(10,10))

    def test_wall_opening_removes_framing_and_panels_with_independent_quantities(self):
        model=Model('Door wall',units='in')
        wall=framed_wall(model,object_id='wall',length=120,openings=[dict(id='door',x=42,width=36,height=80)])
        self.assertEqual(len(wall['parts']),17)
        self.assertEqual(len(wall['panels']),3)
        opening=cq.Workplane('XY').box(36,4.5,80,centered=(False,False,False)).translate((42,-.6,0)).val()
        overlap=sum(model.shapes[part]['world'].intersect(opening).Volume() for part in wall['parts']+wall['panels'])
        self.assertAlmostEqual(overlap,0,places=5)
        panel_volume=sum(model.objects[part]['volume'] for part in wall['panels'])
        self.assertAlmostEqual(panel_volume,((120-.25)*96-(36-.125)*80)*.5,places=4)
        result=check_model(model)
        self.assertTrue(result['all_passed'],result)

    def test_shared_wall_regeneration_preserves_unrelated_bore_exception(self):
        def make(width):
            model=Model('Window',units='in')
            wall=framed_wall(model,object_id='wall',length=120,openings=[dict(id='window',x=48,width=width,sill=36,height=36)],
                exceptions={'stud.at_16':{'bore':{'x':.75,'z':20,'diameter':.5}}})
            return model,wall
        first,a=make(26);second,b=make(34)
        key='wall.stud.at_16'
        self.assertEqual(first.objects[key]['shape_digest'],second.objects[key]['shape_digest'])
        self.assertEqual(first.objects[key]['placement'],second.objects[key]['placement'])
        self.assertNotEqual(first.objects[a['openings']['window']['header']]['shape_digest'],second.objects[b['openings']['window']['header']]['shape_digest'])
        expected=1.5*3.5*(96-4.5)-math.pi*.25**2*3.5
        self.assertAlmostEqual(second.objects[key]['volume'],expected,places=4)
        self.assertTrue(check_model(second)['all_passed'])

    def test_platform_actual_panels_and_stair_cut(self):
        model=Model('Floor',units='in');floor=floor_frame(model,object_id='floor',length=120,depth=96)
        self.assertEqual(len(floor['parts']),11);self.assertEqual(len(floor['panels']),3)
        self.assertAlmostEqual(sum(model.objects[p]['volume'] for p in floor['panels']),(120-.25)*96*.75,places=4)
        self.assertTrue(check_model(model)['all_passed'])
        cut_model=Model('Stair',units='in')
        floor=floor_frame(cut_model,object_id='floor',length=120,depth=96,stair_opening=dict(x=34,y=26,width=36,depth=56))
        void=cq.Workplane('XY').box(36,56,6.5,centered=(False,False,False)).translate((34,26,0)).val()
        self.assertAlmostEqual(sum(cut_model.shapes[p]['world'].intersect(void).Volume() for p in floor['parts']+floor['panels']),0,places=4)
