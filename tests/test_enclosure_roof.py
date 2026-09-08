import copy
import math
import unittest
from stud import WallFrame, floor_frame, wall_frame, wall_enclosure, gable_roof, gable_end_frame
from solid_geometry import solids, vertices, dot, normal
from validation_rules import polygon_union_area
from test_construction_assemblies import project, failures


def enclosed_project(angle=0,inward=1,**roof_changes):
    p=project()
    for key,sec in [('ridge',(1.5,9.25)),('fascia',(.75,13.25)),('rake',(.75,9.25)),('nailer',(1.5,3.5))]:
        p.stock(key,key,'#aaa',section=sec,lengths=(96,120,144,192,240))
    base=WallFrame((11,-24,9),angle,inward)
    floor=floor_frame(p,'f',width=144,depth=192,joist_stock='joist',panel_stock='sheet',frame=base)
    wall_base=WallFrame(base.point(0,0,8),angle,inward)
    walls=wall_frame(p,'w',width=144,depth=192,height=96,stud_stock='stud',header_stock='joist',spacer_stock='sheet',
        frame=wall_base,interior_finish=True,support_ids=[pid for role,pid in floor.roles.items() if role.startswith('panel.')],
        openings=[dict(id='entry',wall='front',start=50,width=38,bottom=0,height=82)])
    roof=gable_roof(p,'r',length=192,span=144,pitch=6,plate_depth=3.5,
        frame=WallFrame(wall_base.point(144,0,96),angle+90*inward,inward),
        rafter_stock='joist',ridge_stock='ridge',tie_stock='stud',system='ridge_board_ties',
        plate_ids=(walls.interfaces['caps']['east'][1],walls.interfaces['caps']['west'][1]),maximum_notch=2,
        minimum_remaining=5,notch_basis='Regression input',rake_overhang=12,fascia_stock='fascia',rake_fascia_stock='rake',
        soffit_stock='sheet',soffit_support_stock='nailer',corner_trim_clearance={'projection':1.25,'side_run':2.25},
        soffit_wall_ids=(walls.interfaces['walls']['east'].part_ids,walls.interfaces['walls']['west'].part_ids),**roof_changes)
    gable_end_frame(p,'g',roof=roof,stud_stock='stud',plate_ids=(walls.interfaces['caps']['front'][1],walls.interfaces['caps']['back'][1]))
    skin=wall_enclosure(p,'skin',walls=walls,roof=roof,exterior_bottom=-8,
        sheathing_stock='sheet',siding_stock='sheet',trim_stock='trim',liner_stock='sheet')
    return p,walls,roof,skin


class RoofEnclosureTests(unittest.TestCase):
    def test_complete_exterior_and_rake_width_in_transformed_frames(self):
        for angle,inward in ((0,1),(90,1),(180,-1),(37,-1)):
            with self.subTest(angle=angle,inward=inward):
                p,w,r,skin=enclosed_project(angle,inward)
                self.assertFalse(failures(p),failures(p))
                # Independently integrate the requested siding silhouette, minus the door and ridge notch.
                wf=w.interfaces['walls']['front'].frame
                base=wf.point(0,0,0)
                along=[a-b for a,b in zip(wf.point(1,0,0),base)]
                outward=[a-b for a,b in zip(wf.point(0,-1,0),base)]
                footprints=[]
                for part in p.parts:
                    if part['id'].startswith('skin.front.') and 'siding' in part['id']:
                        for solid in solids(part):
                            for face in solid:
                                if dot(normal(face),outward)>1-1e-6:
                                    footprints.append([(dot([a-b for a,b in zip(v,base)],along),v[2]-base[2]) for v in face])
                c=1/math.sqrt(1.25);s=.5;a=3.125;width=144;ridge_width=1.5
                corner=96-3.5*s-.375/c
                ridge_bottom=r.interfaces['ridge_top']-9.25-w.frame.origin[2]
                notch=0 if r.interfaces.get('ridge_termination')=='wall' else ridge_width*(corner+s*width/2-ridge_bottom)-s*ridge_width**2/4
                expected=(width-2*a)*(corner+8)+s*(width**2/4-a*a)-notch-38*82
                self.assertAlmostEqual(polygon_union_area(footprints),expected,places=5)
                for end in (0,1):
                    for side in (0,1):
                        part=next(part for part in p.parts if part['id']==r.roles[f'fascia.rake.{end}.{side}'])
                        self.assertAlmostEqual(max(z for y,z in part['outline'])-min(z for y,z in part['outline']),7.625)
                        self.assertEqual(part['blank_size'][2],9.25)
                # Unopened walls have equal, usable sheet widths at both ends.
                for wall in ('back','west','east'):
                    panels=[part for part in p.parts if part['id'].startswith(f'skin.{wall}.siding.')]
                    self.assertAlmostEqual(panels[0]['size'][1],panels[-1]['size'][1])
                    self.assertGreaterEqual(min(part['size'][1] for part in panels),24)
                back_gable=[part for part in p.parts if part['id'].startswith('skin.back.upper.siding.')]
                self.assertEqual(len(back_gable),3)
                self.assertAlmostEqual(back_gable[0]['size'][1],back_gable[-1]['size'][1])
                # Extended corner trim stays a single purchase cut per board.
                row=next(row for row in p.export()['materials'] if row['stock']=='trim')
                self.assertEqual(sum(len(bin['cuts']) for bin in row['bins']),8)
                for side in ('front','back','west','east'):
                    for end in ('start','end'):
                        part=next(part for part in p.parts if part['id']==skin.roles[f'{side}.trim.{end}'])
                        top=max(v[2] for solid in solids(part) for v in vertices(solid))
                        self.assertGreater(top,r.interfaces['soffit_bottom']+10)

    def test_triangular_return_shallow_fascia_and_independent_fascia_assembly(self):
        overlap=.375*math.sqrt(1.25)
        for angle,inward in ((0,1),(37,-1)):
            with self.subTest(angle=angle,inward=inward):
                p,w,r,skin=enclosed_project(angle,inward,eave_fascia_overlap=overlap,
                                            bird_box_return=7,fascia_assembly='Fascia')
                self.assertFalse(failures(p),failures(p))
                parts={part['id']:part for part in p.parts}
                fascia_parts=[part for part in p.parts if part['assembly']=='Fascia']
                self.assertEqual(len(fascia_parts),6)
                self.assertTrue(all('.fascia.' in part['id'] for part in fascia_parts))
                for end in (0,1):
                    for side in (0,1):
                        face=parts[r.roles[f'bird_box.{end}.{side}.face']]
                        self.assertEqual(len(face['outline']),3)
                        self.assertAlmostEqual(face['size'][1],12+7)
                        # The return is 4 inches past the 3-inch inside edge of the gable trim.
                        self.assertAlmostEqual(face['size'][1]-12-3,4)
                for side in (0,1):
                    fascia=parts[r.roles[f'fascia.eave.{side}']]
                    self.assertAlmostEqual(fascia['size'][2],7.25*math.sqrt(1.25)+overlap)
                    self.assertGreater(fascia['blank_size'][2],fascia['size'][2])
                if angle==0:
                    changed=copy.deepcopy(p)
                    cleat=next(part for part in changed.parts if part['id']==r.roles['soffit.block.0.0.0'])
                    cleat['origin'][2]-=.25
                    self.assertIn('r.soffit.block.0.0.0.rafter.0',{f.get('rule_id') for f in failures(changed)})

    def test_return_with_legacy_fascia_and_large_overlap_retains_support(self):
        for params in (dict(bird_box_return=7),dict(bird_box_return=7,eave_fascia_overlap=4)):
            with self.subTest(params=params):
                p,*_=enclosed_project(**params)
                self.assertFalse(failures(p),failures(p))
        with self.assertRaisesRegex(ValueError,'stop before the ridge'):
            enclosed_project(bird_box_return=73)

    def test_sheet_opening_cuts_keep_connected_panels_and_separate_offcuts(self):
        from stud.walls import _sheet_cut_regions, _outline_area, _centered_sheet_cuts
        hole=_sheet_cut_regions(0,48,0,96,[(8,32,20,40)])
        self.assertEqual(len(hole),1)
        self.assertAlmostEqual(sum(_outline_area(poly) for poly in hole[0]),48*96-32*40)
        split=_sheet_cut_regions(0,48,0,96,[(8,32,0,96)])
        self.assertEqual(len(split),2)
        self.assertAlmostEqual(sum(_outline_area(poly) for group in split for poly in group),16*96)
        self.assertEqual(_centered_sheet_cuts(0,47,48),[])
        self.assertEqual(_centered_sheet_cuts(0,96,48),[48])
        self.assertEqual(_centered_sheet_cuts(0,137.75,48),[44.875,92.875])

    def test_missing_cladding_backing_and_short_trim_fail(self):
        p,w,r,skin=enclosed_project()
        tests=[('skin.front.upper.siding.0.0','skin.front.members'),
               ('r.soffit.trim_backing.0.0.0','r.soffit.support.0.0'),
               ('r.bird_box.0.0.block.sister','r.bird_box.0.0.support')]
        for pid,rule in tests:
            changed=copy.deepcopy(p);changed.parts[:]=[part for part in changed.parts if part['id']!=pid]
            self.assertIn(rule,{f.get('rule_id') for f in failures(changed)})
        changed=copy.deepcopy(p)
        part=next(part for part in changed.parts if part['id']=='skin.front.trim.start')
        part['origin'][2]-=.25
        self.assertIn('skin.front.trim_upper.start',{f.get('rule_id') for f in failures(changed)})
        changed=copy.deepcopy(p)
        part=next(part for part in changed.parts if part['id']==r.roles['fascia.rake.0.0'])
        for point in part['outline']:
            if point[1]>7:point[1]+=.25
        self.assertIn('r.fascia_depth.0.0.top',{f.get('rule_id') for f in failures(changed)})

    def test_filled_scribe_or_soffit_notch_collides(self):
        p,w,r,skin=enclosed_project()
        for pid,field in (('skin.west.trim.start','profile'),('r.soffit.panel.1.0','outline')):
            changed=copy.deepcopy(p)
            next(part for part in changed.parts if part['id']==pid).pop(field)
            self.assertTrue(any(f['rule']=='solid_collision' and pid in f['parts'] for f in failures(changed)))

    def test_conflicting_soffit_height_is_rejected_atomically(self):
        p,w,r,skin=enclosed_project();before=copy.deepcopy(p.__dict__)
        with self.assertRaisesRegex(ValueError,'soffit datum'):
            wall_enclosure(p,'bad',walls=w,roof=r,exterior_height=r.interfaces['soffit_bottom']-w.frame.origin[2]-.5,
                sheathing_stock='sheet',siding_stock='sheet',trim_stock='trim')
        self.assertEqual(p.__dict__,before)
