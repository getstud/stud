import copy
import unittest
from stud import WallFrame, floor_frame, wall_frame, door_unit, window_unit, Project
from test_construction_assemblies import project, failures
from test_opening_units import unit_project
from test_roof_assemblies import roof_project


class AuditFixTests(unittest.TestCase):
    def test_floor_separation_fails_for_every_wall_in_transformed_frames(self):
        for angle,inward in ((0,1),(90,-1),(37,1)):
            p=project(); frame=WallFrame((17,-23,4),angle,inward)
            floor=floor_frame(p,'floor',width=96,depth=96,joist_stock='joist',panel_stock='sheet',frame=frame)
            panels=[pid for role,pid in floor.roles.items() if role.startswith('panel.')]
            walls=wall_frame(p,'walls',width=96,depth=96,height=96,stud_stock='stud',
                frame=WallFrame(frame.point(0,0,8),angle,inward),support_ids=panels)
            self.assertFalse(failures(p),failures(p))
            for part in p.parts:
                if part['id'] in floor.part_ids: part['origin'][2]-=.25
            failed={f.get('rule_id') for f in failures(p)}
            for side in ('front','back','west','east'):
                self.assertIn(f'walls.{side}.floor_bearing.0',failed)

    def test_door_and_window_packers_bear_and_count_separately(self):
        for angle,inward in ((0,1),(37,-1),(90,1)):
            for make in (door_unit,window_unit):
                p,o=unit_project(angle,inward)
                p.stock('packer','Half inch packer','#abc',sheet=(48,96),sheet_thickness=.5)
                p.stock('base','Fixture support','#aaa',sheet=(48,96),sheet_thickness=.75)
                p.box('base','Fixture','base',**o.frame.box((24,0,-.75),(38,3.5,.75)))
                unit=make(p,'unit',opening=o,product_stock='unit',frame_depth=4.5,inset=-.5,
                    sill_support_stock='packer',sill_support_ids=['base'])
                self.assertFalse(failures(p),failures(p))
                rows={r['stock']:r for r in p.export()['materials']}
                self.assertEqual(rows['unit']['quantity'],1)
                self.assertEqual(rows['packer']['parts'],1)
                packer=next(part for part in p.parts if part['id']==unit.roles['sill_support'])
                packer['origin'][2]+=.125
                self.assertIn('unit.sill_support.bearing',{f.get('rule_id') for f in failures(p)})
                p.parts.remove(packer)
                self.assertIn('unit.members',{f.get('rule_id') for f in failures(p)})

    def test_invalid_support_inputs_are_atomic(self):
        p,o=unit_project();before=copy.deepcopy(p.__dict__)
        with self.assertRaises(ValueError):
            door_unit(p,'bad',opening=o,product_stock='unit',frame_depth=3.5,sill_support_stock='missing',sill_support_ids=['missing'])
        self.assertEqual(before,p.__dict__)
        p=project();before=copy.deepcopy(p.__dict__)
        with self.assertRaises(ValueError):
            wall_frame(p,'bad',width=96,depth=96,height=96,stud_stock='stud',support_ids=['missing'])
        self.assertEqual(before,p.__dict__)

    def test_bird_box_stocks_are_separate_and_wrong_thickness_fails(self):
        # Use a dedicated closure sheet already registered by this fixture stock alias.
        p,r=roof_project(rake_overhang=12,fascia_stock='fascia',soffit_stock='sheet',soffit_support_stock='nailer')
        p.stock('closure','Three quarter closure','#abc',sheet=(48,96),sheet_thickness=.75)
        p.stock('thin','Three eighth soffit','#abc',sheet=(48,96),sheet_thickness=.375)
        # Rebuild through the public builder with the separate stock inputs.
        from stud import gable_roof
        p.parts[:]=[part for part in p.parts if part['id'].startswith(('plate.','wall.stud.'))];p.validation={}
        r=gable_roof(p,'roof',length=192,span=144,pitch=6,plate_depth=3.5,frame=r.frame,
            rafter_stock='rafter',ridge_stock='ridge',tie_stock='plate',system='ridge_board_ties',
            maximum_notch=2,minimum_remaining=5,notch_basis='Test',rake_overhang=12,fascia_stock='fascia',
            soffit_stock='thin',bird_box_stock='closure',soffit_support_stock='nailer',
            soffit_wall_ids=([f'wall.stud.0.{i}' for i in (0,1)],[f'wall.stud.1.{i}' for i in (0,1)]))
        self.assertFalse(failures(p),failures(p))
        rows={row['stock']:row for row in p.export()['materials']}
        self.assertEqual(rows['thin']['parts'],12);self.assertEqual(rows['closure']['parts'],8)
        part=next(part for part in p.parts if part['id']==r.roles['bird_box.0.0.face'])
        part['stock']='thin'
        self.assertTrue(any(f['rule']=='stock_fit' and part['id'] in f['parts'] for f in failures(p)))

    def test_narrow_sheet_strip_keeps_declared_thickness_axis(self):
        p=Project('Narrow strip');p.stock('s','sheet','#abc',sheet=(48,96),sheet_thickness=.75)
        p.box('s','test','s',(.25,48,.75),(0,0,0));p.validation={'version':1,'automatic':['stock_fit']}
        self.assertFalse(failures(p),failures(p))
        self.assertEqual(p.export()['materials'][0]['square_ft'],.08)
        p.parts[0]['size'][2]=.7505
        self.assertFalse(failures(p),failures(p))
        self.assertEqual(p.export()['materials'][0]['square_ft'],.08)
