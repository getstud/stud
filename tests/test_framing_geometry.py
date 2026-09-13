import math
import unittest
import cadquery as cq
from stud.cad import Model
from stud.checks import check_model
from stud.framing import MemberProfile, AnchorDetail
from stud.floors import HangerDetail
from stud.framing_geometry import (offset_polygon,perimeter_stock,polygon_intervals,
    clipped_member,drill_anchor_pattern,member_end_interfaces)
from stud.solids import prism


class IrregularFramingTests(unittest.TestCase):
    def test_perimeter_preserves_stock_and_partitions_miters_and_pockets(self):
        outline=[(0,0),(80,0),(100,20),(100,80),(0,80)]
        stock=MemberProfile(4,2,'rim',(48,96))
        void=cq.Workplane('XY').box(8,12,4,centered=(False,False,False)).translate((40,-2,-1)).val()
        cuts=list(perimeter_stock(outline,stock,bottom=0,max_length=48,voids=[void]))
        expected=prism(outline,2,holes=[offset_polygon(outline,4)]).cut(void)
        model=Model('Generic mitered band',units='in');ids=[]
        for edge,piece,(shape,location,blank) in cuts:
            pid=f'edge{edge}.piece{piece}';ids.append(pid)
            model.part(pid,shape,location=location,blank=blank)
            model.requirement(pid+'.stock','stock_fit',[pid])
            self.assertLessEqual(blank['cut_length'],48)
            for operation in blank['operations']:
                for x,y in operation['profile']:
                    self.assertTrue(-1e-6<=x<=blank['size'][0]+1e-6)
                    self.assertTrue(-1e-6<=y<=blank['size'][1]+1e-6)
        model.requirement('clear','collision_free',ids)
        self.assertTrue(check_model(model)['all_passed'])
        self.assertAlmostEqual(sum(p['volume'] for p in model.objects.values()),expected.Volume())

    def test_clipped_i_member_retains_factory_section_and_finished_outline(self):
        profile=MemberProfile(2,10,'joist',(120,),flange=1,web=.375)
        boundary=prism([(0,-5),(100,-5),(100,5),(10,5)],10)
        cut=clipped_member(profile,(0,0,10),(100,0,10),boundary=boundary)
        shape,location,blank=cut
        self.assertEqual(blank['size'],[2,100,10])
        self.assertGreaterEqual(len(blank['operations'][-1]['profile']),3)
        self.assertAlmostEqual(shape.moved(location).cut(boundary).Volume(),0)
        self.assertAlmostEqual(shape.moved(location).cut(profile.cut((0,0,10),(100,0,10))[0].moved(location)).Volume(),0)

    def test_anchor_pattern_keeps_station_keys_and_actual_containment(self):
        detail=AnchorDetail('anchor',.5,.5625,7,.75,2,.125,.4375,())
        plate=cq.Workplane('XY').box(100,5.5,1.5,centered=(False,False,False)).val()
        drilled,points=drill_anchor_pattern(plate,cq.Location(),width=5.5,depth=1.5,length=100,
            detail=detail,max_spacing=36,end_distance=12,min_end=2,shifts=(0,2,-2),
            accept=lambda p:not 35<p[0]<39)
        self.assertEqual([p[0] for p in points],[0,1,2,3])
        self.assertAlmostEqual(plate.Volume()-drilled.Volume(),len(points)*math.pi*(.5625/2)**2*1.5)
        self.assertTrue(detail.shape(sill_depth=1.5,hook_length=2,nut_diameter=.875).isValid())
        self.assertGreater(HangerDetail('hanger',2,7,.0625,()).shape(2,face_flange=1.5).Volume(),0)

    def test_end_candidates_cannot_borrow_from_opposite_support(self):
        profile=MemberProfile(2,10,'joist',(120,));shape,loc,_=profile.cut((0,0,10),(100,0,10));world=shape.moved(loc)
        support=cq.Workplane('XY').box(4,10,10,centered=(True,True,False)).translate((0,0,-10)).val()
        ends=list(member_end_interfaces(world,(0,0,0),(100,0,0),2,{'west':support},{'joist':world},member_id='joist'))
        self.assertEqual(ends[0]['supports'],['west']);self.assertIn('unresolved',ends[1])
        self.assertEqual(polygon_intervals([(0,0),(80,0),(80,40),(30,40),(30,80),(0,80)],60),[(0,30)])
