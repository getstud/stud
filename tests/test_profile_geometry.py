import unittest
from stud import Project
from profile_geometry import triangulate_outline
from solid_geometry import solids,volume,collision


class ProfileTests(unittest.TestCase):
    def test_concave_notch_has_correct_volume_and_no_solid_in_void(self):
        p=Project('profile');p.stock('wood','wood','#aaa',section=(1.5,7.25),lengths=(96,))
        outline=[(0,0),(10,0),(10,2),(14,2),(14,0),(40,0),(40,7.25),(0,7.25)]
        p.polygon_prism('rafter','Roof','wood',(1.5,40,7.25),(0,0,0),outline)
        cut=p.parts[0]
        self.assertAlmostEqual(sum(volume(s) for s in solids(cut)),1.5*(40*7.25-4*2))
        void=dict(size=(1,3,1),origin=(.25,10.5,.5))
        self.assertIsNone(collision(solids(cut),solids(void)))
        self.assertEqual(len(p.export()['materials'][0]['bins'][0]['cuts']),1)

    def test_invalid_profiles_are_rejected_before_mutation(self):
        p=Project('p');p.stock('s','s','#aaa',section=(1.5,7.25),lengths=(96,))
        for outline in ([[0,0],[10,7],[0,7],[10,0]],[[0,0],[10,0],[20,0]],
                        [[0,0],[10,0],[10,8],[0,8]],[[0,0],[10,0],[10,float('nan')]]):
            with self.assertRaises(ValueError):p.polygon_prism('p','Roof','s',(1.5,40,7.25),(0,0,0),outline)
            self.assertEqual(p.parts,[])

    def test_reversed_and_collinear_outline_has_same_area(self):
        a=[(0,0),(10,0),(20,0),(20,5),(0,5)]
        def area(tris):return sum(abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2 for a,b,c in tris)
        self.assertEqual(area(triangulate_outline(a)),100)
        self.assertEqual(area(triangulate_outline(a[::-1])),100)

    def test_depth_bands_preserve_notch_voids_and_one_stock_cut(self):
        p=Project('bands');p.stock('s','2x4','#aaa',section=(1.5,3.5),lengths=(96,))
        bands=[dict(x=[0,1.5],bottom=[0,0],top=[4,5]),dict(x=[1.5,3],bottom=[3.5,3.5],top=[10,11]),dict(x=[3,3.5],bottom=[0,0],top=[10,11])]
        p.banded_prism('p','Gable','s',(3.5,1.5,11),(0,0,0),bands)
        self.assertAlmostEqual(sum(volume(s) for s in solids(p.parts[0])),33.75)
        for origin in ((.1,.1,6),(1.6,.1,.1)):
            self.assertIsNone(collision(solids(p.parts[0]),solids(dict(size=(.5,.5,.5),origin=origin))))
        self.assertEqual(len(p.export()['materials'][0]['bins'][0]['cuts']),1)
        bad=[dict(x=[0,1.5],bottom=[0,0],top=[3,3]),dict(x=[1.5,3.5],bottom=[3.5,3.5],top=[10,10])]
        with self.assertRaises(ValueError):p.banded_prism('bad','Gable','s',(3.5,1.5,11),(0,0,0),bad)
        self.assertEqual(len(p.parts),1)


    def test_layered_scribe_has_connected_volume_and_one_blank(self):
        p=Project('scribe');p.stock('s','1x4','#aaa',section=(.75,3.5),lengths=(96,))
        outer=[(0,0),(3.5,0),(3.5,4),(1.25,4),(1.25,8),(3.5,8),(3.5,12),(0,12)]
        lower=[(0,0),(3.5,0),(3.5,4),(0,4)];upper=[(1.25,8),(3.5,8),(3.5,12),(1.25,12)]
        layers=[dict(x=[0,.5],outlines=[outer]),dict(x=[.5,.75],outlines=[lower,upper])]
        p.layered_prism('trim','Corners','s',(.75,3.5,12),(0,0,0),layers)
        self.assertAlmostEqual(sum(volume(s) for s in solids(p.parts[0])),22.25)
        for box in (dict(size=(.1,.5,1),origin=(.6,.25,6)),dict(size=(.5,.5,1),origin=(.1,2,5))):
            self.assertIsNone(collision(solids(p.parts[0]),solids(box)))
        self.assertEqual(sum(len(bin['cuts']) for bin in p.export()['materials'][0]['bins']),1)
        import copy
        before=copy.deepcopy(p.__dict__)
        bad=copy.deepcopy(layers);bad[1]['x'][0]=.6
        overlap=copy.deepcopy(layers);overlap[0]['outlines'].append(outer)
        detached=[dict(x=[0,.5],outlines=[lower]),dict(x=[.5,.75],outlines=[upper])]
        for value in (bad,overlap,detached):
            with self.assertRaises(ValueError):p.layered_prism('bad','Corners','s',(.75,3.5,12),(0,0,0),value)
            self.assertEqual(p.__dict__,before)
