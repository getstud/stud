import copy
import unittest
from stud import Project, WallFrame, gable_roof, sawn_rafter
from validate import validate
from solid_geometry import solids, volume, collision


def roof_project(angle=0,inward=1,**changes):
    p=Project('Roof fixture')
    for key,sec in [('rafter',(1.5,7.25)),('plate',(1.5,3.5)),('ridge',(1.5,9.25)),
                    ('fascia',(.75,13.25)),('nailer',(1.5,3.5))]:
        p.stock(key,key,'#aaa',section=sec,lengths=(96,144,192,240))
    p.stock('sheet','sheet','#bbb',sheet=(48,96))
    frame=WallFrame((17,-22,96),angle,inward)
    for i,y in enumerate((0,140.5)):
        p.box(f'plate.{i}','Wall plates','plate',**frame.box((0,y,-1.5),(192,3.5,1.5)))
    params=dict(length=192,span=144,pitch=6,plate_depth=3.5,rafter_stock='rafter',ridge_stock='ridge',
        maximum_notch=2,minimum_remaining=5,notch_basis='Fixture limits only',system='ridge_board_ties',
        tie_stock='plate',plate_ids=(['plate.0'],['plate.1']),frame=frame)
    params.update(changes)
    if params.get('soffit_stock') and 'soffit_wall_ids' not in params:
        supports=[[],[]]
        for side,y in enumerate((0,140.5)):
            for i,x in enumerate((0,190.5)):
                pid=f'wall.stud.{side}.{i}'
                p.box(pid,'Wall framing','plate',**frame.box((x,y,-96),(1.5,3.5,94.5)))
                supports[side].append(pid)
        params['soffit_wall_ids']=supports
    return p,gable_roof(p,'roof',**params)


def failures(p):return [(f.get('rule_id'),f['message']) for f in validate(p.export()) if f['status']=='FAIL']


class RoofTests(unittest.TestCase):
    def test_transformed_actual_seats_and_ridge_contacts(self):
        for angle in (0,90,180,37):
            for inward in (-1,1):
                with self.subTest(angle=angle,inward=inward):
                    p,r=roof_project(angle,inward)
                    self.assertFalse(failures(p),failures(p))
                    part=next(p for p in p.parts if p['id']==r.roles['rafter.0.0'])
                    self.assertIn('outline',part)
                    self.assertLess(sum(volume(s) for s in solids(part)),part['size'][0]*part['size'][1]*part['size'][2])
                    row=next(row for row in p.export()['materials'] if row['stock']=='rafter')
                    cuts=[cut for bin in row['bins'] for cut in bin['cuts']]
                    self.assertEqual(len(cuts),26)

    def test_supported_eave_soffits_and_rake_ladder(self):
        for rake in (0,12):
            p,r=roof_project(fascia_stock='fascia',soffit_stock='sheet',soffit_support_stock='nailer',rake_overhang=rake)
            self.assertFalse(failures(p),failures(p))
            remove_id=r.roles['soffit.block.0.0.0']
            p.parts[:]=[part for part in p.parts if part['id']!=remove_id]
            self.assertTrue(any(rid=='roof.soffit.support.0.0' for rid,msg in failures(p)))

    def test_removed_seat_and_moved_rafter_are_detected(self):
        for change in ('outline','position'):
            p,r=roof_project()
            part=next(part for part in p.parts if part['id']==r.roles['rafter.0.0'])
            if change=='outline':part.pop('outline')
            else:part['origin'][2]+=.5
            fs=failures(p)
            self.assertTrue(any(rid=='roof.rafter.0.0.bearing' for rid,msg in fs))
            if change=='outline':self.assertTrue(any(rid=='roof.rafter.0.0.section' for rid,msg in fs))

    def test_ridge_system_is_explicit_and_structural_support_is_unverified(self):
        with self.assertRaises(ValueError):roof_project(system='hip')
        with self.assertRaises(ValueError):roof_project(tie_stock=None)
        p,r=roof_project(system='structural_ridge',tie_stock=None)
        self.assertFalse(failures(p))
        self.assertFalse(any(role.startswith('tie.') for role in r.roles))
        self.assertTrue(any(f['rule']=='roof.ridge_support' and f['status']=='UNVERIFIED' for f in validate(p.export())))

    def test_notch_limits_and_bad_inputs_leave_project_unchanged(self):
        p=Project('r');p.stock('r','r','#aaa',section=(1.5,7.25),lengths=(144,))
        before=copy.deepcopy(p.__dict__)
        for params in ({'maximum_notch':.25},{'minimum_remaining':7},{'notch_basis':''}):
            args=dict(run=72,plate_depth=3.5,pitch=6,overhang=12,stock='r',maximum_notch=2,
                      minimum_remaining=5,notch_basis='Fixture')
            args.update(params)
            with self.subTest(params=params),self.assertRaises(ValueError):sawn_rafter(p,'r',**args)
            self.assertEqual(p.__dict__,before)

    def test_removed_tie_fails_connection_requirement(self):
        p,r=roof_project();pid=r.roles['tie.2'];p.parts[:]=[part for part in p.parts if part['id']!=pid]
        self.assertTrue(any(rid=='roof.tie_contact.2.0' for rid,msg in failures(p)))

    def test_zero_tail_and_soffit_input_boundaries(self):
        for fascia in (None,'fascia'):
            p,r=roof_project(eave_overhang=0,fascia_stock=fascia)
            self.assertFalse(failures(p),failures(p))
        with self.assertRaisesRegex(ValueError,'fascia'):roof_project(soffit_stock='sheet',soffit_support_stock='nailer')
        p,r=roof_project(length=193,plate_ids=((),()),fascia_stock='fascia',soffit_stock='sheet',soffit_support_stock='nailer')
        self.assertFalse(failures(p),failures(p))

    def test_gable_overhang_has_rafter_stock_framing_behind_fascia(self):
        for angle,inward in ((0,1),(90,1),(37,-1)):
            p,r=roof_project(angle,inward,rake_overhang=12,fascia_stock='fascia')
            self.assertFalse(failures(p),failures(p))
            parts={part['id']:part for part in p.parts}
            fly=r.roles['rafter.fly.0.0']
            lookout=r.roles['lookout.0.0.1']
            self.assertEqual(parts[fly]['stock'],'rafter')
            self.assertEqual(parts[lookout]['stock'],'rafter')
            self.assertEqual(parts[lookout]['size'],[9,1.5,7.25])
            p.parts[:]=[part for part in p.parts if part['id']!=fly]
            self.assertTrue(any(rid=='roof.lookout_edge.0.0.1' for rid,msg in failures(p)))

    def test_soffit_ledger_requires_real_framing_contact(self):
        for angle,inward in ((0,1),(90,1),(37,-1)):
            p,r=roof_project(angle,inward,fascia_stock='fascia',soffit_stock='sheet',soffit_support_stock='nailer')
            self.assertFalse(failures(p),failures(p))
            # Move the entire soffit support group outward, retaining its
            # internal relationships. The host wall requirement must still fail.
            frame=r.frame
            a=frame.point(0,0,0);b=frame.point(0,-1.125,0)
            for part in p.parts:
                if part['id'].startswith(('roof.soffit.nailer.0','roof.soffit.panel.0','roof.soffit.block.0')):
                    part['origin']=[v+y-x for v,x,y in zip(part['origin'],a,b)]
            self.assertTrue(any(rid=='roof.soffit.ledger_host.0' for rid,msg in failures(p)))

    def test_ledger_host_scope_and_missing_requirement(self):
        with self.assertRaisesRegex(ValueError,'framing part IDs'):
            roof_project(fascia_stock='fascia',soffit_stock='sheet',soffit_support_stock='nailer',soffit_wall_ids=((),()))
        p,r=roof_project(fascia_stock='fascia',soffit_stock='sheet',soffit_support_stock='nailer')
        p.parts[:]=[part for part in p.parts if part['id']!='wall.stud.0.0']
        self.assertTrue(any(rid=='roof.soffit.ledger_host.0' for rid,msg in failures(p)))
        p,r=roof_project(fascia_stock='fascia',soffit_stock='sheet',soffit_support_stock='nailer')
        rid='roof.soffit.ledger_host.0'
        p.validation['rules']=[rule for rule in p.validation['rules'] if rule['id']!=rid]
        from validation_rules import coverage
        model=p.export()
        requirement=next(q for q in coverage(model,validate(model))['requirements'] if q['id']==rid)
        self.assertEqual(requirement['status'],'UNVERIFIED')

    def test_soffit_framing_is_2x_on_edge_and_cannot_be_flattened(self):
        for role,rid,thin_axis in (('soffit.nailer.0','roof.soffit.ledger_section.0',1),
                                  ('soffit.block.0.0.0','roof.soffit.joist_section.0.0.0',0)):
            p,r=roof_project(37,-1,fascia_stock='fascia',soffit_stock='sheet',soffit_support_stock='nailer')
            part=next(part for part in p.parts if part['id']==r.roles[role])
            self.assertEqual((part['size'][thin_axis],part['size'][2]),(1.5,3.5))
            # Same stock still fits when laid flat; the construction requirement
            # must detect the incorrect orientation independently of stock_fit.
            part['size'][thin_axis],part['size'][2]=part['size'][2],part['size'][thin_axis]
            self.assertTrue(any(rule==rid for rule,msg in failures(p)))
            part['size'][thin_axis],part['size'][2]=part['size'][2],part['size'][thin_axis]
            part['rotation'][0]+=90
            self.assertTrue(any(rule==rid for rule,msg in failures(p)))
        with self.assertRaisesRegex(ValueError,'2x dimensional lumber'):
            roof_project(fascia_stock='fascia',soffit_stock='sheet',soffit_support_stock='fascia')

    def test_2x_soffit_framing_rejects_shallow_fascia(self):
        with self.assertRaisesRegex(ValueError,'Fascia must drop'):
            roof_project(fascia_stock='ridge',soffit_stock='sheet',soffit_support_stock='nailer')
