import unittest
import copy
from test_roof_assemblies import roof_project, failures
from solid_geometry import solids, volume


class BirdBoxTests(unittest.TestCase):
    def roof(self,angle=0,inward=1,**changes):
        return roof_project(angle,inward,rake_overhang=12,fascia_stock='fascia',
                            soffit_stock='sheet',soffit_support_stock='nailer',**changes)

    def test_single_outer_rail_and_doubled_attachment_in_transformed_frames(self):
        for angle,inward in ((0,1),(90,1),(180,-1),(37,-1)):
            with self.subTest(angle=angle,inward=inward):
                p,r=self.roof(angle,inward)
                self.assertFalse(failures(p),failures(p))
                for end in (0,1):
                    for side in (0,1):
                        self.assertNotIn(f'rafter.fly.{end}.{side}.sister',r.roles)
                        for role in (f'rafter.fly.{end}.{side}',f'rafter.rake_backing.{end}.{side}',
                                     f'soffit.rake.{end}.{side}.0',f'bird_box.{end}.{side}.face',
                                     f'bird_box.{end}.{side}.back',f'bird_box.{end}.{side}.soffit'):
                            self.assertIn(role,r.roles)
                self.assertFalse(any(row['rule']=='roof.rake_soffit' for row in p.validation['unverified']))

    def test_closed_peak_has_no_extended_ridge_or_soffit_gap(self):
        p,r=self.roof()
        self.assertEqual(r.interfaces['ridge_termination'],'wall')
        ridge=next(part for part in p.parts if part['id']==r.roles['ridge'])
        self.assertEqual(ridge['size'][0],r.interfaces['length'])
        changed=copy.deepcopy(p)
        ridge=next(part for part in changed.parts if part['id']==r.roles['ridge'])
        ridge['size'][0]+=24;ridge['origin'][0]-=12
        self.assertIn('roof.ridge_termination',{rid for rid,msg in failures(changed)})
        for role,rule in [('soffit.rake.0.0.0','roof.soffit_peak.0'),('rafter.fly.1.1','roof.fly_peak.1')]:
            changed=copy.deepcopy(p)
            part=next(part for part in changed.parts if part['id']==r.roles[role])
            part['origin'][2]+=.25
            self.assertIn(rule,{rid for rid,msg in failures(changed)})
        legacy,rr=self.roof(ridge_termination='extended')
        self.assertTrue(any(row['rule']=='roof.ridge_enclosure' for row in legacy.validation['unverified']))
        self.assertFalse(failures(legacy))

    def test_missing_backing_and_detached_fascia_fail_named_requirements(self):
        cases=(('rafter.fly.0.0','roof.lookout_edge.0.0.0'),
               ('rafter.rake_backing.0.0','roof.rake_backing_host.0.0'),
               ('bird_box.0.0.block','roof.bird_box.0.0.support'),
               ('bird_box.0.0.face','roof.bird_box.0.0.support'),
               ('lookout.0.0.0','roof.rake_soffit.block.0.0.0.0'))
        for role,rule in cases:
            with self.subTest(role=role):
                p,r=self.roof();p.parts[:]=[part for part in p.parts if part['id']!=r.roles[role]]
                self.assertTrue(any(rid==rule for rid,msg in failures(p)),failures(p))
        p,r=self.roof()
        part=next(part for part in p.parts if part['id']==r.roles['fascia.rake.0.0'])
        part['origin'][0]-=.25
        self.assertTrue(any(rid=='roof.fascia_corner.0.0' for rid,msg in failures(p)))

    def test_fascia_is_cut_and_meets_at_corners_and_peak(self):
        p,r=self.roof()
        parts={part['id']:part for part in p.parts}
        for end in (0,1):
            for side in (0,1):
                fascia=parts[r.roles[f'fascia.rake.{end}.{side}']]
                self.assertAlmostEqual(max(z for y,z in fascia['outline'])-min(z for y,z in fascia['outline']),7.625)
                self.assertLess(sum(volume(s) for s in solids(fascia)),
                                fascia['size'][0]*fascia['size'][1]*fascia['size'][2])
        self.assertFalse(failures(p),failures(p))

    def test_multiple_rake_panels_have_seam_backing(self):
        # Small sheets exercise rake seams without changing the roof span/load path.
        from stud import gable_roof
        p,old=self.roof();p.parts[:]=[part for part in p.parts if part['id'].startswith(('plate.','wall.stud.'))];p.validation={}
        p.stock('small','Small soffit sheet','#aaa',sheet=(48,48))
        r=gable_roof(p,'roof',length=192,span=144,pitch=6,plate_depth=3.5,
                    frame=old.frame,rafter_stock='rafter',ridge_stock='ridge',tie_stock='plate',
                    system='ridge_board_ties',maximum_notch=2,minimum_remaining=5,notch_basis='Test',
                    rake_overhang=12,fascia_stock='fascia',soffit_stock='small',soffit_support_stock='nailer',
                    soffit_wall_ids=([f'wall.stud.0.{i}' for i in (0,1)],[f'wall.stud.1.{i}' for i in (0,1)]))
        self.assertIn('soffit.rake.0.0.1',r.roles)
        self.assertIn('lookout.0.0.5',r.roles)
        self.assertFalse(failures(p),failures(p))

    def test_projecting_eave_fascia_fails_flush_check(self):
        for angle,inward in ((0,1),(37,-1)):
            p,r=self.roof(angle,inward)
            part=next(part for part in p.parts if part['id']==r.roles['fascia.eave.0'])
            # Extend both ends while retaining the same center/contact with rake boards.
            part['origin'][0]-=.25;part['size'][0]+=.5
            self.assertTrue(any(rid=='roof.fascia_flush.0.0' for rid,msg in failures(p)))

    def test_small_open_rake_has_single_outer_and_inner_attachment_rails(self):
        p,r=roof_project(rake_overhang=4,fascia_stock='fascia')
        self.assertFalse(failures(p),failures(p))
        part=next(part for part in p.parts if part['id']==r.roles['lookout.0.0.0'])
        self.assertEqual(part['size'][0],1)
