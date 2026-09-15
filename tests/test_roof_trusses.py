import unittest
import cadquery as cq
from stud.cad import Model
from stud.checks import check_model
from stud.roof_layout import RoofSegment, RoofFace, layout_roofs
from stud.roof_framing import RafterField, plan_roof_members
from stud.framing import MemberProfile
from stud.stock import cut_member, Plane
from stud.trusses import frame_profile_truss, incident_miters


class TrussCompositionTests(unittest.TestCase):
    def build(self, points):
        model=Model('explicit assumed factory truss',units='in')
        profile=tuple(RoofSegment(str(i),a,b) for i,(a,b) in enumerate(zip(points,points[1:])))
        result=frame_profile_truss(model,profile,object_id='truss',bottom=96,chord_section=(1.5,5.5),
            web_section=(1.5,3.5),panel_length=72,bearing_insets=(12,12),plate_size=(6,8,.04))
        return model,result

    def test_gable_has_joined_members_and_single_factory_purchase(self):
        model,result=self.build(((0,0,96),(144,0,210),(288,0,96)))
        checks=check_model(model)
        self.assertTrue(all(f['status']=='passed' for f in checks['findings']),checks['findings'])
        self.assertTrue(any('.plate.' in p for p in result['parts']))
        self.assertTrue(any('.diagonal.' in p for p in result['parts']))
        self.assertTrue(all(len(model.shapes[p]['world'].Solids())==1 for p in result['timber']))
        self.assertEqual(len(model.demands),1)
        demand=next(iter(model.demands.values()))
        self.assertEqual((demand['quantity'],demand['purchase_unit']),(1,'truss'))
        self.assertIsNone(demand['cuts'])
        self.assertEqual(demand['specification']['status'],'unengineered model')

    def test_hip_profile_and_pitch_change(self):
        for peak in (152,176):
            model,result=self.build(((0,0,96),(80,0,peak),(208,0,peak),(288,0,96)))
            checks=check_model(model)
            self.assertTrue(all(f['status']=='passed' for f in checks['findings']),checks['findings'])
            tops=[model.shapes[p]['world'].BoundingBox().zmax for p in result['timber'] if '.top.' in p]
            self.assertAlmostEqual(max(tops),peak,places=5)

    def test_missing_profile_is_rejected_before_registration(self):
        model=Model('gap',units='in')
        with self.assertRaisesRegex(ValueError,'missing profile'):
            frame_profile_truss(model,(RoofSegment('a',(0,0,96),(100,0,150)),RoofSegment('b',(102,0,150),(288,0,96))),
                object_id='truss',bottom=96,chord_section=(1.5,5.5),web_section=(1.5,3.5),panel_length=72,
                bearing_insets=(12,12),plate_size=(6,8,.04))
        self.assertFalse(model.objects)

    def test_common_rafter_bounds_preserve_the_spacing_grid(self):
        roof=layout_roofs((RoofFace('shed',Plane.roof(origin=(0,0,96),slope=(.5,0)),((0,0),(96,0),(96,96),(0,96))),))
        stock=MemberProfile(1.5,7.25,'fixture.rafter',(144,))
        full=plan_roof_members(roof,(RafterField('shed',stock,16),))
        bounded=plan_roof_members(roof,(RafterField('shed',stock,16,station_bounds=(16,64)),))
        self.assertEqual([m.id for m in bounded],[m.id for m in full if 16<=m.start[1]<=64])
        self.assertEqual([m.start[1] for m in bounded],[16,32,48,64])

    def test_three_way_miter_partitions_joint(self):
        segments=(((0,0,20),(40,0,20)),((0,0,20),(-30,30,20)),((0,0,20),(-30,-30,20)))
        shapes=[]
        for (a,b),planes in zip(segments,incident_miters(segments)):
            shape,loc,blank=cut_member(a,b,(1.5,9.25),start_plane=planes[0],top_planes=planes)
            shapes.append(shape.moved(loc))
        for i,a in enumerate(shapes):
            for b in shapes[i+1:]:
                self.assertLess(a.intersect(b).Volume(),1e-6)
                self.assertLess(a.distance(b),1e-6)

if __name__=='__main__':unittest.main()
