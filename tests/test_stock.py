"""Behavior at the generic construction-stock interface."""
import unittest

import cadquery as cq

from stud.cad import Model
from stud.fabrication import audit_fabrication


class PlanarPanelTests(unittest.TestCase):
    def test_one_profile_installs_on_horizontal_vertical_and_sloped_planes(self):
        from stud.stock import cut_panel

        profile=[(0,0),(8,0),(0,6)]
        frames=[
            cq.Plane(origin=(2,3,4),xDir=(1,0,0),normal=(0,0,1)),
            cq.Plane(origin=(2,3,4),xDir=(1,0,0),normal=(0,-1,0)),
            cq.Plane(origin=(2,3,4),xDir=(1,0,0),normal=(0,-1,1)),
        ]
        for frame in frames:
            with self.subTest(normal=frame.zDir.toTuple()):
                shape,placement,blank=cut_panel(frame,profile,.5)
                self.assertEqual(blank['size'],[8,6,.5])
                self.assertEqual(blank['panel_axes'],[0,1])
                self.assertEqual(blank['operations'],[{'kind':'profile_cut','profile':[[0,0],[8,0],[0,6]]}])
                self.assertAlmostEqual(shape.Volume(),12)
                world=shape.moved(placement);origin=frame.origin;normal=frame.zDir
                distances=[normal.dot(vertex.Center()-origin) for vertex in world.Vertices()]
                self.assertTrue(all(min(abs(value),abs(value-.5))<1e-7 for value in distances))

    def test_panel_profile_is_normalized_into_its_original_sheet_blank(self):
        from stud.stock import cut_panel

        frame=cq.Plane(origin=(10,20,30),xDir=(0,1,0),normal=(1,0,0))
        shape,placement,blank=cut_panel(frame,[(-3,5),(1,5),(1,7),(-3,7)],.75)
        self.assertEqual(blank['size'],[4,2,.75])
        self.assertEqual(blank['operations'][0]['profile'],[[0,0],[4,0],[4,2],[0,2]])
        box=shape.BoundingBox()
        self.assertEqual((box.xmin,box.ymin,box.zmin),(0,0,0))
        self.assertEqual((box.xmax,box.ymax,box.zmax),(4,2,.75))
        self.assertEqual(shape.moved(placement).BoundingBox().xmin,10)

    def test_panel_rejects_invalid_frames_profiles_and_thicknesses(self):
        from stud.stock import cut_panel

        frame=cq.Plane(origin=(0,0,0),normal=(0,0,1))
        for profile,thickness in [([(0,0),(1,0)],.5), ([(0,0),(1,0),(2,0)],.5),
                                  ([(0,0),(1,0),(0,1)],0)]:
            with self.assertRaises(ValueError):cut_panel(frame,profile,thickness)
        with self.assertRaises(ValueError):cut_panel(object(),[(0,0),(1,0),(0,1)],.5)


class StockPartsTests(unittest.TestCase):
    def test_parts_register_with_stock_evidence_and_group_into_purchases(self):
        from stud.stock import StockParts

        model=Model('Stock registration',units='in');model.assembly('frame')
        stock=StockParts(model,parent='frame',demand_prefix='fixture.')
        for object_id,length,section in [('rail',20,(1.5,3.5)),('stud',30,(1.5,3.5)),
                                         ('header',24,(1.5,5.5))]:
            width,depth=section
            result=(cq.Workplane('XY').box(width,length,depth,centered=(False,False,False)),
                    cq.Location(),{'size':[width,length,depth],'cut_length':length,
                                   'operations':[{'kind':'square_cut','finished_length':length}]})
            self.assertEqual(stock.add(object_id,result,section=section),object_id)
        self.assertEqual(stock.purchase(stock_lengths=[48,96],kerf=.125),
                         ['fixture.lumber.1.5x3.5','fixture.lumber.1.5x5.5'])
        self.assertEqual(set(model.objects),{'rail','stud','header'})
        self.assertEqual(set(model.requirements),{'rail.blank','stud.blank','header.blank'})
        self.assertEqual(model.objects['header']['material'],'lumber.1.5x5.5')
        demand=model.demands['fixture.lumber.1.5x3.5']
        self.assertEqual(demand['object_ids'],['rail','stud'])
        self.assertEqual(demand['cuts'],[{'object_id':'rail','length':20},{'object_id':'stud','length':30}])
        self.assertEqual(demand['stock_lengths'],[48,96])
        self.assertEqual(audit_fabrication(model.export()),[])

    def test_one_stock_family_can_keep_an_existing_demand_identity(self):
        from stud.stock import StockParts

        model=Model('Compatible demand identity',units='in')
        stock=StockParts(model,demand_prefix='unused.')
        result=(cq.Workplane('XY').box(2,12,4,centered=(False,False,False)),cq.Location(),
                {'size':[2,12,4],'cut_length':12,'operations':[{'kind':'square_cut','finished_length':12}]})
        stock.add('part',result,section=(2,4))
        self.assertEqual(stock.purchase(stock_lengths=[24],demand_id='legacy.lumber'),['legacy.lumber'])
        self.assertEqual(model.demands['legacy.lumber']['product_id'],'lumber.2x4')

    def test_registration_rejects_bad_results_and_ambiguous_demand_ids(self):
        from stud.stock import StockParts

        model=Model('Invalid stock registration',units='in');stock=StockParts(model)
        with self.assertRaises(ValueError):stock.add('bad',(cq.Workplane('XY').box(1,2,3),cq.Location(),{}),section=(1,3))
        with self.assertRaises(ValueError):stock.add('bad',(cq.Workplane('XY').box(1,2,3),cq.Location(),{'cut_length':'two'}),section=(1,3))
        for object_id,section in [('a',(1,3)),('b',(2,4))]:
            result=(cq.Workplane('XY').box(section[0],10,section[1]),cq.Location(),
                    {'size':[section[0],10,section[1]],'cut_length':10,'operations':[]})
            stock.add(object_id,result,section=section)
        with self.assertRaises(ValueError):stock.purchase(stock_lengths=[20],demand_id='one.id')


class StockGeometryTests(unittest.TestCase):
    def test_planes_cut_vertical_stock_without_roof_coordinates(self):
        from stud.stock import Plane, cut_member

        bottom=Plane((0,0,0),(0,0,-1));top=Plane((0,0,10),(0,0,1))
        shape,placement,blank=cut_member((0,0,0),(0,0,10),(2,4),
            start_plane=bottom,end_plane=top,up=(1,0,0))
        self.assertEqual(blank['size'],[2,10,4])
        self.assertAlmostEqual(shape.Volume(),80)
        world=shape.moved(placement)
        self.assertTrue(all(bottom.signed_distance(vertex.Center())<=1e-7 for vertex in world.Vertices()))
        self.assertTrue(all(top.signed_distance(vertex.Center())<=1e-7 for vertex in world.Vertices()))

    def test_roof_imports_preserve_the_generic_plane_and_member_behavior(self):
        from stud.stock import Plane, cut_member
        from stud.roof_geometry import Plane as RoofPlane, cut_member as cut_roof_member

        generic=cut_member((0,0,0),(20,0,10),(2,4))
        compatible=cut_roof_member((0,0,0),(20,0,10),(2,4))
        self.assertIs(RoofPlane,Plane)
        self.assertEqual(generic[2],compatible[2])
        self.assertAlmostEqual(generic[0].Volume(),compatible[0].Volume())
