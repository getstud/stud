"""Floor inputs, actual native interfaces and independent change regressions."""
import copy
from dataclasses import replace
import math
import runpy
from pathlib import Path
import tempfile
import unittest

import cadquery as cq

from stud.bulk import volume_demand
from stud.cad import Model
from stud.checks import check_model
from stud.design_review import design_review
from stud.fabrication import audit_fabrication
from stud.floors import Bearing, Opening, HangerDetail, frame_floor, layout_floor, deck_floor
from stud.framing import MemberProfile, AnchorDetail, anchor_layout, anchored_sill

SOLID=MemberProfile(1.5,9.5,'joist',(96,144,192,240),unresolved=('Specify species, grade and loads.',))
IJOIST=MemberProfile(2,9.5,'ijoist',(96,144,192,240),flange=1.125,web=.375,
                     unresolved=('Select exact engineered product and verify its load case.',))
RIM=MemberProfile(1.125,9.5,'rim',(96,144,192,240),unresolved=('Specify engineered rim product.',))
HEADER=MemberProfile(3.5,9.5,'header',(96,144,192,240),unresolved=('Size opening members for reactions.',))
HANGER=HangerDetail('hanger',2,7,.0625,('Select rated hardware and fasteners.',))


def fixture(*,opening=Opening('stairs',30,33,30,30),height=10,joist=IJOIST,placement=None,hanger=HANGER):
    model=Model('Generic floor region',units='in')
    model.assembly('building',location=placement)
    bearings=[]
    for pid,x,w in [('west',0,8),('middle',96,4),('east',192,8)]:
        model.part(pid,cq.Workplane('XY').box(w,120,height,centered=(True,False,False)).translate((x,0,0)),
                   parent='building',material='concrete')
        model.requirement(pid+'.valid','solid_valid',[pid]);bearings.append(Bearing(pid,x,w,height))
    volume_demand(model,'concrete',product_id='concrete',specification={},object_ids=[b.part_id for b in bearings],purchase_unit='ft3')
    floor=frame_floor(model,object_id='floor',length=192,width=120,joist=joist,rim=RIM,bearings=bearings,
        spacing=16,min_bearing=1.5,openings=[opening] if opening else [],opening_stock=HEADER,hanger=hanger,parent='building',
        unresolved=['Verify building loads and support reactions.'])
    return model,floor


class FloorTests(unittest.TestCase):
    def assert_checked(self,model):
        checks=check_model(model)
        self.assertTrue(checks['all_passed'],[f for f in checks['findings'] if f['status']!='passed'])
        self.assertEqual(audit_fabrication(model.export()),[])
        return checks

    def test_solid_and_engineered_members_share_layout_with_real_sections(self):
        for profile in (SOLID,IJOIST):
            with self.subTest(profile=profile.product_id):
                model,floor=fixture(joist=profile);self.assert_checked(model)
                joist=next(m for m in floor['layout'].members if m.role=='joist')
                length=math.dist(joist.start,joist.end)
                area=profile.width*profile.depth
                if profile.flange:area=2*profile.width*profile.flange+profile.web*(profile.depth-2*profile.flange)
                self.assertAlmostEqual(model.objects[floor['members'][joist.id]]['volume'],area*length)
                self.assertFalse(any('deck' in pid for pid in model.objects))

    def test_moving_opening_keeps_field_grid_and_rebuilds_clearance_and_takeoff(self):
        a,fa=fixture();b,fb=fixture(opening=Opening('stairs',40,38,35,30))
        self.assert_checked(b)
        key='floor.opening.stairs.header.west'
        self.assertEqual(a.objects[key]['mark'],b.objects[key]['mark'])
        self.assertNotEqual(a.objects[key]['placement'],b.objects[key]['placement'])
        unchanged=[pid for pid in a.objects.keys() & b.objects.keys() if '.joist.grid.' in pid and
                   a.objects[pid]['bounds']['min'][0]>=96]
        self.assertTrue(unchanged)
        self.assertTrue(all(a.objects[p]['shape_digest']==b.objects[p]['shape_digest'] and
                            a.objects[p]['placement']==b.objects[p]['placement'] for p in unchanged))
        hole=cq.Workplane('XY').box(35,30,9.5,centered=(False,False,False)).translate((40,38,10)).val()
        self.assertAlmostEqual(sum(b.shapes[p]['world'].intersect(hole).Volume() for p in fb['parts']),0)
        self.assertNotEqual(sum(o['volume'] for o in a.objects.values()),sum(o['volume'] for o in b.objects.values()))

    def test_changed_support_datum_and_rotated_wing_regenerate_bearing(self):
        placement=cq.Location(cq.Vector(200,-100,30),cq.Vector(0,0,1),90)
        a,fa=fixture(height=10,placement=placement);b,fb=fixture(height=14,placement=placement)
        self.assert_checked(a);self.assert_checked(b)
        self.assertEqual(set(a.objects),set(b.objects))
        self.assertEqual(fb['top']-fa['top'],4)
        for pid in fa['parts']:self.assertAlmostEqual(b.objects[pid]['bounds']['min'][2]-a.objects[pid]['bounds']['min'][2],4)

    def test_one_supported_end_cannot_mask_the_other_end(self):
        model,floor=fixture(opening=None)
        self.assert_checked(model)
        # Keep IDs and all other supports, but remove the middle seat physically.
        model.part('middle',cq.Workplane('XY').box(4,120,5,centered=(True,False,False)).translate((96,0,0)),
                   parent='building',material='concrete',replace=True)
        failures=[f for f in check_model(model)['findings'] if f['status']=='failed']
        self.assertTrue(any(f['kind']=='support' and f['targets'][1]=='middle' for f in failures))

    def test_expected_inventory_survives_deleted_output_and_deleted_check(self):
        model,floor=fixture();self.assert_checked(model)
        pid=next(p for p in floor['parts'] if '.joist.' in p)
        del model.objects[pid];del model.shapes[pid]
        for key in [k for k,v in model.requirements.items() if pid in v['targets']]:del model.requirements[key]
        report=design_review(model.export())
        self.assertTrue(any(f['category']=='missing_parts' and pid in f['message'] for f in report['findings']))
        self.assertTrue(any(f['category']=='missing_requirements' for f in report['findings']))

    def test_geometric_pass_is_separate_from_unresolved_design_details(self):
        model,_=fixture();manifest=model.export();manifest['checks']=self.assert_checked(model)
        review=design_review(manifest)
        self.assertEqual(review['geometry'],'verified');self.assertEqual(review['details'],'unresolved')
        self.assertTrue(any('rated hardware' in f['message'] for f in review['findings']))
        self.assertTrue(any('restraint' in f['message'] for f in review['findings']))

    def test_missing_expected_check_invalidates_geometry_status(self):
        model,_=fixture(opening=None)
        del model.requirements[next(k for k,v in model.requirements.items() if v['kind']=='support')]
        manifest=model.export();manifest['checks']=check_model(model)
        self.assertEqual(design_review(manifest)['geometry'],'not_verified')

    def test_unselected_physical_support_is_a_geometry_gap(self):
        model,_=fixture(hanger=None)
        manifest=model.export();manifest['checks']=check_model(model)
        self.assertTrue(manifest['checks']['all_passed'])
        self.assertEqual(design_review(manifest)['geometry'],'not_verified')

    def test_hanger_must_contact_its_named_host(self):
        model,_=fixture()
        pid='floor.opening.stairs.trimmer.south';entry=model.shapes[pid];obj=model.objects[pid]
        void=cq.Workplane('XY').box(7,5,12,centered=(False,False,False)).translate((25,28,9)).val()
        shape=entry['world'].cut(void).moved(entry['location'].inverse)
        model.part(pid,shape,location=entry['location'],blank=obj['blank'],material=obj['material'],replace=True)
        failures=[f for f in check_model(model)['findings'] if f['status']=='failed']
        self.assertTrue(any(f['requirement_id'].endswith('.hanger.host') for f in failures))

    def test_final_row_does_not_overlap_grid_and_shared_trimmers_are_explicit(self):
        args=dict(length=192,width=118,joist=IJOIST,rim=RIM,bearings=[Bearing('west',0,8,10),Bearing('east',192,8,10)],
                  spacing=16,min_bearing=1.5,opening_stock=HEADER)
        layout=layout_floor(**args)
        rows=sorted(m.start[1] for m in layout.members if m.role=='joist')
        self.assertTrue(all(b-a>=IJOIST.width for a,b in zip(rows,rows[1:])))
        with self.assertRaisesRegex(ValueError,'framing extents'):
            layout_floor(**args,openings=[Opening('a',30,33,20,30),Opening('b',90,33,20,30)])
        nested=[Opening('wide',30,20,20,60),Opening('narrow',90,35,20,30)]
        for openings in (nested,list(reversed(nested))):
            with self.assertRaisesRegex(ValueError,'framing extents'):layout_floor(**args,openings=openings)

    def test_multiple_openings_and_impossible_support_design(self):
        bearings=[Bearing('west',0,8,10),Bearing('middle',96,4,10),Bearing('east',192,8,10)]
        args=dict(length=192,width=160,joist=IJOIST,rim=RIM,bearings=bearings,spacing=16,min_bearing=1.5,opening_stock=HEADER)
        layout=layout_floor(**args,openings=[Opening('one',30,30,25,30),Opening('two',125,90,25,30)])
        self.assertEqual(sum(m.role=='header' for m in layout.members),4)
        with self.assertRaisesRegex(ValueError,'bearing line'):layout_floor(**args,openings=[Opening('cuts_beam',85,30,30,30)])
        with self.assertRaisesRegex(ValueError,'unique'):layout_floor(**args,openings=[Opening('same',30,30,20,20)]*2)

    def test_each_side_of_trimmer_keeps_spacing_without_removing_other_bays(self):
        _,floor=fixture()
        layout=floor['layout']
        for x in (15,80,150):
            rows=sorted({m.start[1] for m in layout.members if m.role in ('joist','trimmer') and m.start[0]<=x<=m.end[0]})
            self.assertLessEqual(max(b-a for a,b in zip(rows,rows[1:])),16+1e-8)

    def test_hanger_row_suppression_cannot_hide_excessive_joist_spacing(self):
        model,floor=fixture(opening=Opening('o',30,8,30,30))
        self.assertTrue(floor['layout'].unresolved)
        self.assertTrue(any('16.75 exceeds 16' in gap for gap in floor['layout'].unresolved))
        manifest=model.export();manifest['checks']=check_model(model)
        review=design_review(manifest)
        self.assertEqual(review['geometry'],'not_verified')
        self.assertTrue(any(f['target']=='floor.spacing' for f in review['findings']))

    def test_changed_bearing_region_invalidates_cached_native_evidence(self):
        model,_=fixture(opening=None)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'cache.json';self.assertTrue(check_model(model,cache_path=path)['all_passed'])
            key=next(k for k,v in model.requirements.items() if v['kind']=='support' and '.joist.' in k)
            rule=model.requirements[key];rule['policy']['region_local']['min'][1]+=10;rule['policy']['region_local']['max'][1]+=10
            finding=next(f for f in check_model(model,cache_path=path)['findings'] if f['requirement_id']==key)
            self.assertEqual(finding['status'],'failed')

    def test_deck_is_separate_and_uses_the_same_moved_opening_and_backed_edges(self):
        for opening in (Opening('stairs',30,33,30,30),Opening('stairs',40,38,35,30)):
            model,floor=fixture(opening=opening)
            original={p:(model.objects[p]['shape_digest'],model.objects[p]['placement']) for p in floor['parts']}
            deck=deck_floor(model,floor,product_id='floor.panel',thickness=.75,sheet_size=(48,96),gap=.125,
                            unresolved=['Select panel rating and fastening.'])
            self.assert_checked(model)
            self.assertEqual(original,{p:(model.objects[p]['shape_digest'],model.objects[p]['placement']) for p in floor['parts']})
            hole=cq.Workplane('XY').box(opening.length,opening.width,2,centered=(False,False,False)).translate((opening.x,opening.y,floor['top'])).val()
            self.assertAlmostEqual(sum(model.shapes[p]['world'].intersect(hole).Volume() for p in deck['panels']),0)
            self.assertTrue(deck['backing']);self.assertEqual(deck['top'],floor['top']+.75)

    def test_cross_operation_collisions_and_deck_aware_anchor_layout(self):
        path=Path(__file__).resolve().parents[1]/'examples/cadquery-floor-system/design.py'
        scope=runpy.run_path(str(path));model=scope['model']
        deck_floor(model,scope['floor'],product_id='panel',thickness=.75,sheet_size=(48,96),gap=.125)
        failures=[f for f in check_model(model)['findings'] if f['status']=='failed']
        self.assertTrue(any('.interfaces.' in f['requirement_id'] and any('anchor' in p for p in f['targets']) for f in failures))
        scope={};exec(compile(path.read_text().replace('INCLUDE_DECK = False','INCLUDE_DECK = True'),str(path),'exec'),scope)
        self.assert_checked(scope['model'])
        self.assertFalse(any(c.get('geometry_unresolved') for c in scope['model'].connections.values()))


class AnchorTests(unittest.TestCase):
    def test_short_return_does_not_crowd_anchor_hardware(self):
        result=anchor_layout(7,max_spacing=48,end_distance=12,min_end=3,min_spacing=2)
        self.assertTrue(result.unresolved)
        self.assertLessEqual(len(result.positions),1)
        feasible=anchor_layout(10,max_spacing=48,end_distance=6,min_end=3,min_spacing=4)
        self.assertEqual(feasible.positions,(3,7));self.assertFalse(feasible.unresolved)
        end_zone=anchor_layout(55,max_spacing=48,end_distance=3,min_end=3,min_spacing=2)
        self.assertFalse(end_zone.unresolved);self.assertEqual(end_zone.positions[0],3);self.assertEqual(end_zone.positions[-1],52)
        self.assertTrue(all(2<=b-a<=48 for a,b in zip(end_zone.positions,end_zone.positions[1:])))

    def test_layout_respects_pockets_spacing_and_end_zones(self):
        result=anchor_layout(192,max_spacing=48,end_distance=12,min_end=3,exclusions=[(8,24),(80,100)])
        self.assertFalse(result.unresolved,result)
        self.assertLessEqual(result.positions[0],12);self.assertGreaterEqual(result.positions[-1],180)
        self.assertLessEqual(max(b-a for a,b in zip(result.positions,result.positions[1:])),48+1e-7)
        self.assertTrue(all(not(8<=p<=24 or 80<=p<=100) for p in result.positions))

    def test_impossible_return_and_blocked_path_are_explicit(self):
        for length,exclusions in [(12,[(0,12)]),(192,[(50,160)])]:
            self.assertTrue(anchor_layout(length,max_spacing=48,end_distance=12,min_end=3,exclusions=exclusions).unresolved)
        self.assertEqual(len(anchor_layout(20,max_spacing=48,end_distance=12,min_end=3).positions),2)

    def test_sill_bores_hardware_and_neighbor_clearance_follow_one_layout(self):
        model=Model('Anchor fixture',units='in')
        model.part('wall',cq.Workplane('XY').box(120,8,12,centered=(False,True,False)).translate((0,0,-12)),material='concrete')
        model.part('obstacle',cq.Workplane('XY').box(8,8,8,centered=(False,True,False)).translate((40,0,1.5)),material='concrete')
        volume_demand(model,'concrete',product_id='concrete',specification={},object_ids=['wall','obstacle'],purchase_unit='ft3')
        model.requirement('obstacle.valid','solid_valid',['obstacle'])
        sill=anchored_sill(model,object_id='sill',start=(0,0,1.5),end=(120,0,1.5),
            stock=MemberProfile(5.5,1.5,'treated',(120,144)),anchor=AnchorDetail('anchor',.5,.5625,7,1,2,.125,.4375,('Select anchorage product.',)),
            support='wall',max_spacing=48,end_distance=12,min_end=3,avoid=['obstacle'])
        checks=check_model(model)
        self.assertTrue(checks['all_passed'],[f for f in checks['findings'] if f['status']!='passed'])
        self.assertFalse(sill['layout'].unresolved)
        self.assertEqual(audit_fabrication(model.export()),[])
        self.assertAlmostEqual(model.objects['sill']['volume'],120*5.5*1.5-len(sill['anchors'])*math.pi*(.5625/2)**2*1.5)
