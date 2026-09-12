"""Regression checks for finite ridge joints and plumb eave framing."""
import importlib.util
from pathlib import Path
import unittest
import cadquery as cq
from stud.cad import Model
from stud.checks import contact_area


class HipJunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=Path(__file__).resolve().parents[1]/'examples/cadquery-hip-roof/hip_roof.py'
        spec=importlib.util.spec_from_file_location('hip_recipe',path)
        recipe=importlib.util.module_from_spec(spec);spec.loader.exec_module(recipe)
        cls.recipe=staticmethod(recipe.hip_roof)
        cls.model=Model('Hip junction test',units='in');cls.recipe(cls.model)

    def test_ridge_end_corner_wedges_are_filled(self):
        # These patches lie inside the rafter, beyond the former infinite hip
        # offset cut, and before the finite ridge side face.
        z0=100+5.5*(1+.5**2)**.5-3.5*.5
        for side,y in [('front',47.1),('back',48.9)]:
            for station,x in [(48,48.4),(96,95.6)]:
                if side=='back':x=144-x
                with self.subTest(side=side,station=station):
                    patch=cq.Workplane('XY').box(.1,.1,.1).translate((x,y,z0+.5*47.1-.15)).val()
                    rafter=self.model.shapes[f'hip.rafter.{side}.at_{station}']['world']
                    self.assertAlmostEqual(rafter.intersect(patch).Volume(),patch.Volume(),places=7)

    def test_continuous_plumb_subfascia_covers_whole_rafter_tails(self):
        expected=1.5*5.5*(1+.5**2)**.5
        for side in ('front','back','left','right'):
            fascia=self.model.shapes['hip.subfascia.'+side]['world']
            bbox=fascia.BoundingBox()
            self.assertAlmostEqual(bbox.ylen if side in ('front','back') else bbox.xlen,1.5,places=6)
            for pid,data in self.model.shapes.items():
                if pid.startswith('hip.rafter.'+side+'.'):
                    self.assertAlmostEqual(contact_area(data['world'],fascia,.0004),expected,places=5,msg=pid)
        self.assertFalse(any('eave_block' in pid for pid in self.model.shapes))

    def test_subfascia_detail_rejects_insufficient_overhang_before_registration(self):
        for overhang in (0,1.49):
            model=Model('Invalid eave',units='in')
            with self.assertRaisesRegex(ValueError,'at least 1.5'):
                self.recipe(model,overhang=overhang)
            self.assertFalse(model.objects)

    def test_end_common_retains_full_width_at_ridge_end(self):
        for side,x in [('left',47.05),('right',96.95)]:
            common=self.model.shapes[f'hip.rafter.{side}.at_48']['world']
            for y in (47.5,48.5):
                patch=cq.Workplane('XY').box(.1,.1,.1).translate((x,y,125)).val()
                self.assertAlmostEqual(common.intersect(patch).Volume(),patch.Volume(),places=7)
            ridge=self.model.shapes['hip.ridge']['world']
            self.assertGreater(contact_area(common,ridge,.0004),8)

    def test_nearby_grid_station_is_replaced_by_required_common(self):
        model=Model('Off-grid ridge',units='in');self.recipe(model,depth=98)
        for side in ('front','back','left','right'):
            stations=sorted(float(pid.rsplit('_',1)[1]) for pid in model.shapes if pid.startswith('hip.rafter.'+side+'.'))
            self.assertIn(49,stations)
            self.assertNotIn(48,stations)
            self.assertTrue(all(b-a>=1.5 for a,b in zip(stations,stations[1:])))

    def test_low_ties_replace_posts_and_meet_both_rafter_sides(self):
        self.assertFalse(any(pid.startswith('hip.ridge_post.') for pid in self.model.shapes))
        ties=[pid for pid in self.model.shapes if pid.startswith('hip.tie.cross.')]
        self.assertEqual(len(ties),8)
        for pid in ties:
            at=float(pid.rsplit('_',1)[1]);tie=self.model.shapes[pid]['world']
            for side,station in [('front',at),('back',144-at)]:
                rafter=self.model.shapes[f'hip.rafter.{side}.at_{station:g}']['world']
                self.assertGreater(contact_area(tie,rafter,.0004),.5)

    def test_end_commons_stop_at_ridge_end_even_above_ridge_top(self):
        for side,x in [('left',47.6),('right',96.4)]:
            common=self.model.shapes[f'hip.rafter.{side}.at_48']['world']
            patch=cq.Workplane('XY').box(.05,.05,.05).translate((x,48,128.1)).val()
            self.assertAlmostEqual(common.intersect(patch).Volume(),0,places=9)

    def test_intermediate_commons_have_no_lips_over_ridge(self):
        for side,y in [('front',47.6),('back',48.4)]:
            for station in (64,80):
                x=station if side=='front' else 144-station
                common=self.model.shapes[f'hip.rafter.{side}.at_{station}']['world']
                patch=cq.Workplane('XY').box(.05,.05,.05).translate((x,y,128.1)).val()
                self.assertAlmostEqual(common.intersect(patch).Volume(),0,places=9)

    def test_jack_top_does_not_overhang_hip_side(self):
        for side,x,y in [('front',32,31.5),('back',112,64.5),('left',31.5,64),('right',112.5,32)]:
            jack=self.model.shapes[f'hip.rafter.{side}.at_32']['world']
            patch=cq.Workplane('XY').box(.05,.05,.05).translate((x,y,120.1)).val()
            self.assertAlmostEqual(jack.intersect(patch).Volume(),0,places=9)

    def test_ridge_is_rectangular_extended_stock_and_hips_have_one_square_top(self):
        ridge=self.model.shapes['hip.ridge']['world']
        self.assertEqual(len(ridge.Faces()),6)
        self.assertAlmostEqual(ridge.Volume(),49.5*1.5*7.25,places=6)
        self.assertAlmostEqual(ridge.BoundingBox().xmin,47.25,places=6)
        self.assertAlmostEqual(ridge.BoundingBox().xmax,96.75,places=6)
        for pid,data in self.model.shapes.items():
            if pid.startswith('hip.hip.'):
                tops=[face for face in data['world'].Faces() if face.normalAt().z>.85]
                self.assertEqual(len(tops),1,pid)
                self.assertAlmostEqual(tops[0].normalAt().z,1/(1+.5**2/2)**.5,places=6)
        for side in ('front','back','left','right'):
            fascia=self.model.shapes['hip.subfascia.'+side]['world']
            self.assertAlmostEqual(fascia.BoundingBox().zlen,5.5*(1+.5**2)**.5+.125,places=6)
