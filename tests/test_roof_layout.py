import math
import unittest

from stud.cad import Model
from stud.framing import MemberProfile
from stud.roof_geometry import Plane
from stud.roof_layout import RoofFace, hip_roof_faces, gable_roof_faces, layout_roofs, roof_stations, roof_edges, roof_boundary_edges, _area
from stud.roof_framing import RafterField, plan_roof_members, roof_wall_limit, truss_profile_envelope, frame_sloping_wall, frame_roof
from stud.wall_layout import WallLine, WallRun, WallOpening


class RoofLayoutTests(unittest.TestCase):
    def test_gable_orientation_profile_and_parameter_edit(self):
        for end in ((0,160),(96,128)):
            length=math.hypot(*end);n=(-end[1]/length,end[0]/length)
            for pitch in (.5,.8):
                faces=gable_roof_faces('gable',(0,0),end,half_span=60,eave_top=100,pitch=pitch)
                roof=layout_roofs(faces)
                self.assertEqual([f.id for f in faces],['gable.left','gable.right'])
                self.assertAlmostEqual(sum(_area(f.outline) for f in roof.patches),120*length)
                profile=roof.section(tuple(-60*v for v in n),tuple(60*v for v in n))
                self.assertEqual(len(profile),2)
                self.assertAlmostEqual(profile[0].start[2],100)
                self.assertAlmostEqual(profile[0].end[2],100+60*pitch)
                self.assertAlmostEqual(profile[-1].end[2],100)
                boundary=roof_boundary_edges(roof)
                self.assertEqual(sum(e.kind=='rake' for e in boundary),4)
                self.assertEqual(sum(e.kind=='eave' for e in boundary),2)
                self.assertEqual([e.kind for e in roof_edges(roof)],['ridge'])
        for args in (dict(half_span=0),dict(pitch=float('nan')),dict(end=(0,0))):
            kw=dict(start=(0,0),end=(0,100),half_span=60,eave_top=100,pitch=.5);kw.update(args)
            with self.assertRaises(ValueError):gable_roof_faces('g',**kw)

    def test_mixed_pitch_gable_preserves_visible_peak(self):
        main=hip_roof_faces('main',((0,0),(240,0),(240,200),(0,200)),eave_top=100,pitch=.5)
        gable=gable_roof_faces('front',(120,-24),(120,100),half_span=48,eave_top=100,pitch=.8)
        roof=layout_roofs((*main,*gable))
        self.assertEqual(roof,layout_roofs((*gable,*main)))
        self.assertAlmostEqual(roof.section((72,-24),(168,-24))[0].end[2],138.4)
        self.assertAlmostEqual(roof.height_at(120,100),150)
        self.assertTrue(any(e.kind=='valley' for e in roof_edges(roof)))
        self.assertFalse(any(e.kind=='step' for e in roof_boundary_edges(roof)))

    def test_boundary_splits_partial_step_without_inventing_joint(self):
        high=RoofFace('high',Plane.roof(origin=(0,0,100)),((0,0),(100,0),(100,100),(0,100)))
        low=RoofFace('low',Plane.roof(origin=(0,0,80)),((100,20),(140,20),(140,80),(100,80)))
        roof=layout_roofs((high,low));edges=roof_boundary_edges(roof)
        steps=[e for e in edges if e.kind=='step']
        self.assertEqual(len(steps),1)
        self.assertAlmostEqual(math.dist(steps[0].start,steps[0].end),60)
        self.assertEqual(steps[0].faces,('high',))
        self.assertFalse(roof_edges(roof))
        self.assertFalse(any(e.faces==('low',) and abs(e.start[0]-100)<1e-7 and abs(e.end[0]-100)<1e-7 for e in edges))

    def test_forward_gable_coplanar_extension_removes_covered_rake(self):
        main=gable_roof_faces('main',(120,0),(120,120),half_span=120,eave_top=100,pitch=.75)
        forward=gable_roof_faces('forward',(180,-16),(180,16),half_span=60,eave_top=100,pitch=.75)
        roof=layout_roofs((*main,*forward));edges=roof_boundary_edges(roof)
        # The right slopes are coplanar. Their former shared line at y=0
        # must not acquire a fly rafter/lookout or a roof-to-wall step.
        self.assertFalse(any(abs(e.start[1])<1e-7 and abs(e.end[1])<1e-7 and
                             min(e.start[0],e.end[0])>=180-1e-7 for e in edges))
        front=[e for e in edges if abs(e.start[1]+16)<1e-7 and abs(e.end[1]+16)<1e-7]
        self.assertEqual(len(front),2)
        self.assertTrue(all(e.kind=='rake' for e in front))

    def test_hip_area_ridge_and_pitch_edit(self):
        outline=((0,0),(240,0),(240,144),(0,144))
        for pitch in (.5,.75):
            roof=layout_roofs(hip_roof_faces('main',outline,eave_top=100,pitch=pitch))
            self.assertAlmostEqual(sum(_area(p.outline) for p in roof.patches),240*144)
            self.assertAlmostEqual(roof.height_at(100,72),100+72*pitch)
            profile=roof.section((100,0),(100,144))
            self.assertEqual(len(profile),2)
            self.assertAlmostEqual(profile[0].end[2],100+72*pitch)
            self.assertEqual(profile[0].end,profile[1].start)
            edges=roof_edges(roof)
            self.assertEqual(sum(e.kind=='ridge' for e in edges),1)
            self.assertEqual(sum(e.kind=='hip' for e in edges),4)
            ridge=next(e for e in edges if e.kind=='ridge')
            self.assertAlmostEqual(math.dist(ridge.start,ridge.end),96)

    def test_overlap_clips_before_framing_and_is_order_independent(self):
        a=RoofFace('low',Plane.roof(slope=(.5,0)),((0,0),(100,0),(100,100),(0,100)))
        b=RoofFace('high',Plane.roof(origin=(0,0,20),slope=(-.5,0)),((0,0),(100,0),(100,100),(0,100)))
        roof=layout_roofs((a,b))
        self.assertEqual(roof,layout_roofs((b,a)))
        self.assertAlmostEqual(sum(_area(f.outline) for f in roof.patches),10000)
        p=roof.section((0,50),(100,50))
        self.assertEqual(len(p),2);self.assertAlmostEqual(p[0].end[0],20)
        self.assertAlmostEqual(p[0].end[2],10)
        self.assertEqual([e.kind for e in roof_edges(roof)],['valley'])
        duplicate=RoofFace('z',a.plane,a.outline)
        self.assertAlmostEqual(sum(_area(f.outline) for f in layout_roofs((a,duplicate)).patches),10000)

    def test_holes_remain_gaps_and_bad_domains_fail(self):
        a=RoofFace('a',Plane.roof(),((0,0),(10,0),(10,10),(0,10)))
        b=RoofFace('b',Plane.roof(),((20,0),(30,0),(30,10),(20,10)))
        roof=layout_roofs((a,b));self.assertIsNone(roof.height_at(15,5))
        p=roof.section((0,5),(30,5));self.assertEqual(len(p),2)
        with self.assertRaises(ValueError):truss_profile_envelope(Model('test',units='in'),p,object_id='t',bottom=-10,diagram_diameter=.5)
        with self.assertRaises(ValueError):roof_wall_limit(roof,WallLine('w',(0,5),(30,5),-20),depth=2,clearance=2)
        with self.assertRaises(ValueError):RoofFace('bad',a.plane,((0,0),(10,0),(2,2),(0,10)))

    def test_rafter_cuts_fit_blank_and_domain(self):
        face=RoofFace('slope',Plane.roof(origin=(0,0,100),slope=(0,.5)),((0,0),(96,0),(48,96),(0,96)))
        roof=layout_roofs((face,))
        stock=MemberProfile(1.5,7.25,'2x8',(192,))
        plan=plan_roof_members(roof,(RafterField('slope',stock,16,origin=(8,0)),))
        self.assertTrue(plan)
        for m in plan:
            shape,loc,blank=m.cut();self.assertTrue(shape.isValid());self.assertEqual(len(shape.Solids()),1)
            self.assertLessEqual(shape.Volume(),math.prod(blank['size'])+1e-6)
            for v in shape.moved(loc).Vertices():
                p=v.Center();self.assertTrue(face.contains(p.x,p.y))
                self.assertLessEqual(face.plane.signed_distance(p.toTuple()),1e-6)

    def test_truss_is_factory_outline_not_lumber(self):
        roof=layout_roofs(hip_roof_faces('h',((0,0),(100,0),(100,80),(0,80)),eave_top=100,pitch=.5))
        p=roof.section((50,0),(50,80));m=Model('test',units='in')
        truss_profile_envelope(m,p,object_id='t',bottom=95,diagram_diameter=.5)
        self.assertFalse(m.objects['t'].get('blank'))
        self.assertEqual(m.objects['t']['lineage']['representation'],'coordination_outline')
        self.assertEqual(m.demands['t.factory']['purchase_unit'],'truss')
        self.assertTrue(m.connections['t.shop_design']['geometry_unresolved'])
        self.assertFalse(m.demands['t.factory'].get('cuts'))

    def test_wall_cap_responds_to_full_width_and_plane_change(self):
        for pitch in (.5,1):
            roof=layout_roofs((RoofFace('s',Plane.roof(origin=(0,0,100),slope=(pitch,0)),((0,0),(100,0),(100,100),(0,100))),))
            cap=roof_wall_limit(roof,WallLine('w',(10,10),(10,90),0),depth=4,clearance=10)
            self.assertAlmostEqual(cap,90+8*pitch)
        with self.assertRaises(ValueError):roof_stations(roof,direction=(0,0),spacing=16)

    def test_gable_wall_keeps_opening_and_full_stud_to_cap_contact(self):
        from stud.walls import OpeningDetail, HeaderDetail
        from stud.checks import check_model
        opening=WallOpening('window',49,22,38,36,detail=OpeningDetail(HeaderDetail(7.25,cap=1.5)))
        run=WallRun('gable',WallLine('g',(0,0),(120,0),0),120,5.5,alignment='center',openings=(opening,))
        caps=(Plane.roof(origin=(0,0,80),slope=(.5,0)),Plane.roof(origin=(120,0,80),slope=(-.5,0)))
        m=Model('gable probe',units='in');result=frame_sloping_wall(m,run,caps,object_id='g')
        report=check_model(m)
        self.assertTrue(report['all_passed'],[f for f in report['findings'] if f['status']!='passed'])
        self.assertTrue(result['parts'])
        for pid in result['parts']:
            for v in m.shapes[pid]['world'].Vertices():
                self.assertLessEqual(max(p.signed_distance(v.Center().toTuple()) for p in caps),1e-6)
        # A roof edit that cuts into the header fails before touching the model.
        bad=Model('bad opening',units='in')
        with self.assertRaises(ValueError):frame_sloping_wall(bad,run,tuple(p.offset(-25) for p in caps),object_id='g')
        self.assertFalse(bad.objects)

    def test_named_bearing_cuts_real_seat_and_retains_original_blank(self):
        import cadquery as cq
        from stud.checks import check_model
        m=Model('seat probe',units='in')
        m.part('plate',cq.Workplane('XY').box(96,5.5,1.5,centered=False).translate((0,0,98.5)))
        m.requirement('plate.valid','solid_valid',['plate'])
        roof=layout_roofs((RoofFace('slope',Plane.roof(origin=(0,0,107),slope=(0,.5)),
                                    ((0,-12),(96,-12),(96,100),(0,100))),))
        stock=MemberProfile(1.5,7.25,'fixture.2x8',(192,))
        fields=(RafterField('slope',stock,16,origin=(8,0)),)
        result=frame_roof(m,roof,fields,bearings=('plate',),bearing_length=1.5)
        report=check_model(m)
        self.assertTrue(report['all_passed'],[f for f in report['findings'] if f['status']!='passed'])
        for pid in result['parts']:
            self.assertLess(m.shapes[pid]['world'].intersect(m.shapes['plate']['world']).Volume(),1e-6)
            self.assertTrue(any(op['kind']=='bearing_seat' for op in m.objects[pid]['blank']['operations']))


if __name__=='__main__':unittest.main()
