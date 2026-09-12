"""Analytic checks for reusable roof planes and stock-preserving cuts."""
import math
from pathlib import Path
import runpy
import unittest

import cadquery as cq

from stud.roof_geometry import Plane, cut_member, cut_panel
from stud.cad import Model


class RoofGeometryTests(unittest.TestCase):
    def assert_on_plane(self, point, plane):
        self.assertAlmostEqual(cq.Vector(*plane.normal).dot(cq.Vector(*point)-cq.Vector(*plane.point)),0,places=7)

    def test_plane_intersection_and_normal_offset(self):
        a=Plane.roof(origin=(0,0,10),slope=(.5,0))
        b=Plane.roof(origin=(0,0,10),slope=(0,.5))
        point,direction=a.intersection(b)
        self.assertAlmostEqual(cq.Vector(*direction).Length,1)
        for distance in (-100,0,20):
            at=(cq.Vector(*point)+cq.Vector(*direction)*distance).toTuple()
            self.assert_on_plane(at,a);self.assert_on_plane(at,b)
        self.assertAlmostEqual(a.offset(2).height_at(8,0),14+2*math.sqrt(1.25))
        with self.assertRaises(ValueError):a.intersection(a.offset(1))
        with self.assertRaises(ValueError):Plane((0,0,0),(1,0,0)).height_at(0,0)

    def test_compound_end_cuts_extend_original_stock(self):
        # A jack whose far cut is oblique across the stock and plumb in elevation.
        first=Plane((0,0,0),(0,-1,0));last=Plane((0,20,10),(1,1,0))
        shape,place,blank=cut_member((0,0,0),(0,20,10),(2,4),start_plane=first,end_plane=last)
        self.assertGreater(blank['cut_length'],math.sqrt(500))
        stock=cq.Workplane('XY').box(*blank['size'],centered=(False,False,False)).val()
        self.assertLess(shape.cut(stock).Volume(),1e-7)
        self.assertTrue(shape.isValid());self.assertEqual(len(shape.Solids()),1)
        world=shape.moved(place)
        for cap in (first,last):
            distances=[cq.Vector(*cap.normal).dot(vertex.Center()-cq.Vector(*cap.point)) for vertex in world.Vertices()]
            self.assertLessEqual(max(distances),1e-7)
            self.assertGreaterEqual(sum(abs(d)<1e-7 for d in distances),3)
        # The archived cut planes describe the same cuts in the original blank.
        for world_plane,local_plane in zip((first,last),blank['operations'][0]['planes']):
            for vertex in shape.Vertices():
                local_distance=cq.Vector(*local_plane['normal']).dot(vertex.Center()-cq.Vector(*local_plane['point']))
                world_vertex=cq.Vertex.makeVertex(*vertex.Center().toTuple()).moved(place).Center()
                world_distance=cq.Vector(*world_plane.normal).dot(world_vertex-cq.Vector(*world_plane.point))
                self.assertAlmostEqual(local_distance,world_distance,places=7)

    def test_backed_hip_is_translation_invariant(self):
        planes=(Plane.roof(slope=(.5,0)),Plane.roof(slope=(0,.5)))
        shape,place,blank=cut_member((0,0,0),(20,20,10),(2,4),top_planes=planes)
        delta=cq.Vector(10000,-20000,5000)
        translated=tuple(Plane((cq.Vector(*p.point)+delta).toTuple(),p.normal) for p in planes)
        moved,moved_place,moved_blank=cut_member(delta.toTuple(),(delta+cq.Vector(20,20,10)).toTuple(),(2,4),top_planes=translated)
        self.assertAlmostEqual(shape.Volume(),moved.Volume(),places=6)
        for a,b in zip(blank['size'],moved_blank['size']):self.assertAlmostEqual(a,b,places=7)
        world=shape.moved(place)
        for plane in planes:
            self.assertLessEqual(max(cq.Vector(*plane.normal).dot(v.Center()) for v in world.Vertices()),1e-7)
        self.assertLess(shape.Volume(),math.prod(blank['size']))

    def test_panel_footprint_area_normal_thickness_and_stock_fit(self):
        plane=Plane.roof(origin=(0,0,10),slope=(0,.5))
        shape,place,blank=cut_panel(plane,[(0,0),(8,0),(0,10)],.5)
        self.assertAlmostEqual(shape.Volume(),40*math.sqrt(1.25)*.5,places=7)
        self.assertAlmostEqual(blank['size'][0],8)
        self.assertAlmostEqual(blank['size'][1],10*math.sqrt(1.25))
        for vertex in shape.moved(place).Vertices():
            distance=cq.Vector(*plane.normal).dot(vertex.Center()-cq.Vector(*plane.point))
            self.assertLess(min(abs(distance),abs(distance-.5)),1e-7)
        stock=cq.Workplane('XY').box(*blank['size'],centered=(False,False,False)).val()
        self.assertLess(shape.cut(stock).Volume(),1e-7)

    def test_invalid_stock_and_cuts_are_rejected(self):
        for kwargs in ({'section':(0,4)}, {'start_plane':Plane((0,0,0),(0,1,0))},
                       {'top_planes':(Plane((0,0,-100),(0,0,1)),)}):
            args={'section':(2,4),**kwargs}
            with self.assertRaises(ValueError):cut_member((0,0,0),(0,20,10),**args)
        with self.assertRaises(ValueError):cut_panel(Plane.roof(),[(0,0),(1,0),(2,0)],.5)
        with self.assertRaises(ValueError):Plane((0,0,0),(0,0,0))

    def test_hip_recipe_support_limits_and_eave_perimeter(self):
        recipe=Path(__file__).resolve().parents[1]/'examples/cadquery-hip-roof/hip_roof.py'
        hip_roof=runpy.run_path(str(recipe))['hip_roof']
        for options in ({'slope':.01},{'length':100,'depth':96}):
            model=Model('Invalid hip supports',units='in')
            with self.assertRaises(ValueError):hip_roof(model,**options)
            self.assertFalse(model.objects)
        model=Model('Hip tail limits',units='in');roof=hip_roof(model)
        for part in roof['hips']:
            box=model.shapes[part]['world'].BoundingBox()
            self.assertGreater(min(box.xmin+8,box.ymin+8,152-box.xmax,104-box.ymax),-1e-5,part)
