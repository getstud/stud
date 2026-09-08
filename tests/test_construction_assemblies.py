import copy
import unittest
from stud import Project, WallFrame, floor_frame, wall_frame, wall_enclosure, plate_junction
from validate import validate
from validation_rules import coverage


def project():
    p=Project('Construction fixture')
    for key,sec in [('stud',(1.5,3.5)),('joist',(1.5,7.25)),('header',(1.5,7.25)),('trim',(.75,3.5))]:
        p.stock(key,key,'#aaa',section=sec,lengths=(96,120,144,192,240))
    p.stock('sheet','sheet','#bbb',sheet=(48,96))
    return p


def failures(p):
    return [f for f in validate(p.export()) if f['status']=='FAIL']


def remove(p,pid):
    p.parts[:]=[part for part in p.parts if part['id']!=pid]


class FloorTests(unittest.TestCase):
    def test_short_span_and_transformed_floor_with_blocked_panel_edges(self):
        for w,d in ((144,192),(192,144)):
            for angle in (0,90,180,270,37):
                for inward in (-1,1):
                    with self.subTest(w=w,angle=angle,inward=inward):
                        p=project()
                        floor=floor_frame(p,'floor',width=w,depth=d,joist_stock='joist',
                            panel_stock='sheet',frame=WallFrame((21,-32,10),angle,inward))
                        self.assertEqual(floor.interfaces['joist_axis'],0 if w<d else 1)
                        self.assertEqual(floor.interfaces['joist_span'],141)
                        self.assertEqual(floor.interfaces['blocking_rows'],[48,96])
                        self.assertFalse(failures(p),failures(p))

    def test_removed_block_fails_contact_and_inventory(self):
        p=project();f=floor_frame(p,'f',width=96,depth=96,joist_stock='joist',panel_stock='sheet')
        remove(p,f.roles['blocking.0.0'])
        fs=failures(p)
        self.assertTrue(any(x.get('rule_id')=='f.members' for x in fs))
        self.assertTrue(any(x.get('rule_id','').startswith('f.block.') for x in fs))
        self.assertTrue(any(x.get('rule_id','').startswith('f.panel_support.') for x in fs))

    def test_tongue_and_groove_does_not_invent_intermediate_blocking(self):
        for angle in (0,90,180,37):
            p=project();f=floor_frame(p,'f',width=144,depth=192,joist_stock='joist',panel_stock='sheet',
                panel_edges='tongue_and_groove',panel_joint_basis='Fixture panel manufacturer T&G detail',frame=WallFrame(angle=angle))
            self.assertEqual(f.interfaces['blocking_rows'],[])
            self.assertFalse(failures(p),failures(p))
            joint=next(r for r in p.validation['rules'] if r['kind']=='panel_joint')
            panel=next(part for part in p.parts if part['id']==joint['parts'][1]);panel['origin'][2]+=.25
            self.assertTrue(any(x.get('rule_id')==joint['id'] for x in failures(p)))

    def test_interval_is_explicit_and_blocking_changes_with_span(self):
        p=project();f=floor_frame(p,'f',width=144,depth=192,joist_stock='joist',maximum_block_spacing=96,
                                 blocking_basis='Fixture local design interval')
        rows=[.75,*f.interfaces['blocking_rows'],143.25]
        self.assertLessEqual(max(b-a for a,b in zip(rows,rows[1:])),96)
        self.assertFalse(failures(p))
        p=project();before=copy.deepcopy(p.__dict__)
        with self.assertRaises(ValueError):floor_frame(p,'f',width=144,depth=192,joist_stock='joist',maximum_block_spacing=96)
        self.assertEqual(p.__dict__,before)

    def test_end_restraint_and_alternative_axis_reason(self):
        p=project()
        with self.assertRaises(ValueError):floor_frame(p,'f',width=96,depth=144,joist_stock='joist',joist_axis=1)
        f=floor_frame(p,'f',width=96,depth=144,joist_stock='joist',joist_axis=1,direction_reason='Intermediate beam support layout')
        self.assertFalse(failures(p))
        remove(p,f.roles['rim.0'])
        self.assertTrue(any(x.get('rule_id','').startswith('f.end.') for x in failures(p)))

    def test_missing_check_remains_unverified(self):
        p=project();floor_frame(p,'f',width=96,depth=96,joist_stock='joist',blocking_rows=(48,))
        rid='f.block.0.0.0'
        p.validation['rules']=[r for r in p.validation['rules'] if r['id']!=rid]
        findings=validate(p.export())
        self.assertEqual(next(r for r in coverage(p.export(),findings)['requirements'] if r['id']==rid)['status'],'UNVERIFIED')


class WallTests(unittest.TestCase):
    def make(self,angle=0,inward=1,finish=True,openings=()):
        p=project();w=wall_frame(p,'walls',width=144,depth=192,height=96,stud_stock='stud',
            frame=WallFrame((13,-7,10),angle,inward),interior_finish=finish,
            openings=openings,header_stock='header',spacer_stock='sheet')
        return p,w

    def test_rotated_and_mirrored_finished_corners_and_openings(self):
        ops=[dict(id='door',wall='front',start=50,width=38,bottom=0,height=82),
             dict(id='window',wall='west',start=40,width=36,bottom=40,height=36)]
        for angle in (0,90,180,37):
            for inward in (-1,1):
                with self.subTest(angle=angle,inward=inward):
                    p,w=self.make(angle,inward,openings=ops)
                    wall_enclosure(p,'skin',walls=w,sheathing_stock='sheet',siding_stock='sheet',trim_stock='trim',liner_stock='sheet')
                    self.assertFalse(failures(p),[(f.get('rule_id'),f['message']) for f in failures(p)])

    def test_cap_lap_detects_shortened_member(self):
        p,w=self.make()
        cap=next(p for p in p.parts if p['id']==w.interfaces['caps']['west'][1][0])
        cap['origin'][1]+=3.5;cap['size'][0]-=3.5;cap['cut_length']-=3.5
        self.assertTrue(any(f.get('rule_id')=='walls.lap.west.front' for f in failures(p)))

    def test_long_wall_splices_stagger_and_moved_splice_fails(self):
        p=project();p.stock('short','short','#ccc',section=(1.5,3.5),lengths=(96,))
        w=wall_frame(p,'w',width=240,depth=144,height=96,stud_stock='short')
        self.assertFalse(failures(p),failures(p))
        rule=next(r for r in p.validation['rules'] if r['id']=='w.front.splices')
        rule['minimum_offset']=25
        self.assertTrue(any(f.get('rule_id')==rule['id'] for f in failures(p)))

    def test_removing_corner_backer_fails_finish_support(self):
        p,w=self.make();wall_enclosure(p,'skin',walls=w,sheathing_stock='sheet',siding_stock='sheet',trim_stock='trim',liner_stock='sheet')
        pid=next(pid for role,pid in w.roles.items() if role=='front.stud.1')
        remove(p,pid)
        self.assertTrue(any(f.get('rule_id','').startswith('skin.front.backing') for f in failures(p)))

    def test_unfinished_corner_and_finish_without_backing_plan(self):
        p,w=self.make(finish=False)
        self.assertFalse(failures(p))
        before=copy.deepcopy(p.export())
        with self.assertRaises(ValueError):wall_enclosure(p,'skin',walls=w,sheathing_stock='sheet',siding_stock='sheet',trim_stock='trim',liner_stock='sheet')
        self.assertEqual(p.export(),before)

    def test_trim_gap_is_preserved_and_unintended_gap_fails(self):
        p,w=self.make();wall_enclosure(p,'skin',walls=w,sheathing_stock='sheet',siding_stock='sheet',trim_stock='trim',trim_gap=.125)
        self.assertFalse(failures(p))
        rule=next(r for r in p.validation['rules'] if r['kind']=='surface_gap')
        panel=next(part for part in p.parts if part['id']==rule['parts'][1]);panel['origin'][0]+=.25
        self.assertTrue(any(f.get('rule_id')==rule['id'] for f in failures(p)))

    def test_l_and_t_plate_junctions(self):
        for at in (0,36):
            for angle in (0,37,90):
                p=project();j=plate_junction(p,'j',main_length=96,branch_length=48,branch_at=at,
                    stock='stud',frame=WallFrame(angle=angle))
                self.assertFalse(failures(p),failures(p))
                remove(p,j.roles['upper.branch'])
                self.assertTrue(any(f.get('rule_id')=='j.lap' for f in failures(p)))

    def test_invalid_opening_does_not_partially_commit_walls(self):
        p=project();before=copy.deepcopy(p.__dict__)
        with self.assertRaises(ValueError):wall_frame(p,'w',width=144,depth=192,height=96,stud_stock='stud',
            header_stock='header',spacer_stock='sheet',openings=[dict(id='bad',wall='back',start=2,width=40,bottom=0,height=82)])
        self.assertEqual(p.__dict__,before)

class ReviewRegressionTests(unittest.TestCase):
    def test_moved_complete_blocking_row_exceeds_interval(self):
        p=project();f=floor_frame(p,'f',width=144,depth=192,joist_stock='joist',maximum_block_spacing=96,blocking_basis='Fixture interval')
        for part in p.parts:
            if part['id'].startswith('f.blocking.0.'):
                part['origin'][0]-=48
        self.assertTrue(any(x.get('rule_id')=='f.blocking_interval' for x in failures(p)))

    def test_detached_siding_plane_fails_backing(self):
        p=project();w=wall_frame(p,'w',width=144,depth=192,height=96,stud_stock='stud')
        wall_enclosure(p,'s',walls=w,sheathing_stock='sheet',siding_stock='sheet',trim_stock='trim')
        for part in p.parts:
            if part['id'].startswith('s.front.siding.'):
                part['origin'][1]-=12
        self.assertTrue(any('siding_backing' in x.get('rule_id','') for x in failures(p)))

    def test_shortened_stud_fails_top_bearing(self):
        p=project();w=wall_frame(p,'w',width=144,depth=192,height=96,stud_stock='stud')
        part=next(p for p in p.parts if p['id']==w.roles['front.stud.3'])
        part['size'][2]-=12;part['cut_length']-=12
        self.assertTrue(any(x.get('rule_id')=='w.front.head.3' for x in failures(p)))
