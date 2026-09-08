import copy
import math
import unittest
from stud import asphalt_roof, Project
from test_enclosure_roof import enclosed_project
from test_construction_assemblies import failures


def finished(angle=0,inward=1):
    p,w,r,skin=enclosed_project(angle,inward)
    p.stock('deck','Deck','#ba9',sheet=(48,96),sheet_thickness=.625)
    for key in ('membrane','shingle'):
        p.stock(key,key,'#333',coverage_sq_ft=32.8,waste_factor=.1)
    for key,yield_ft in [('metal',10),('starter',120),('cap',20)]:
        p.stock(key,key,'#444',coverage_linear_ft=yield_ft,waste_factor=.1)
    args=dict(roof=r,deck_stock='deck',membrane_stock='membrane',shingle_stock='shingle',flashing_stock='metal',starter_stock='starter',cap_stock='cap')
    finish=asphalt_roof(p,'finish',**args)
    return p,r,finish,args


class AsphaltRoofTests(unittest.TestCase):
    def test_rotated_mirrored_finish_and_quantities(self):
        for angle,inward in [(0,1),(37,-1)]:
            with self.subTest(angle=angle,inward=inward):
                p,r,f,args=finished(angle,inward)
                self.assertEqual(failures(p),[])
                rows={r['stock']:r for r in p.export()['materials']}
                self.assertAlmostEqual(rows['shingle']['square_ft'],f.interfaces['net_field_sq_ft'],places=2)
                self.assertAlmostEqual(rows['cap']['linear_ft'],f.interfaces['ridge_length']/12,places=2)
                expected=2*217.5/12+4*84.75*math.sqrt(1.25)/12
                self.assertAlmostEqual(rows['metal']['linear_ft'],expected,places=2)
                self.assertEqual(rows['metal']['quantity'],math.ceil(expected*1.1/10))
                self.assertEqual(rows['shingle']['quantity'],math.ceil(f.interfaces['net_field_sq_ft']*1.1/32.8))
                self.assertFalse(any(x['rule']=='r.enclosure' for x in p.validation['unverified']))
                self.assertTrue(any(x['rule']=='finish.deck_installation' for x in p.validation['unverified']))

    def test_missing_layers_and_displaced_deck_fail(self):
        p,r,f,args=finished()
        for pid,rule in [('finish.membrane.0','finish.field_bearing.0.2.2.0.0'),('finish.cap.0.0','finish.members')]:
            changed=copy.deepcopy(p);changed.parts[:]=[x for x in changed.parts if x['id']!=pid]
            self.assertIn(rule,{x.get('rule_id') for x in failures(changed)})
        changed=copy.deepcopy(p)
        starter='finish.starter.eave.0'
        carried={starter}
        for rule in changed.validation['rules']:
            if starter in rule.get('parts',[]) and rule['id'].startswith('finish.field_bearing'):
                carried.add(rule['parts'][0])
        for part in changed.parts:
            if part['id'] in carried:part['origin'][2]+=1
        self.assertIn('finish.starter_bearing.eave.0',{x.get('rule_id') for x in failures(changed)})
        changed=copy.deepcopy(p)
        part=next(x for x in changed.parts if x['id']=='finish.deck.0.0.0');part['origin'][2]-=.25
        self.assertIn('finish.deck_bearing.0.0.0',{x.get('rule_id') for x in failures(changed)})

    def test_invalid_inputs_are_atomic(self):
        p,r,f,args=finished();before=copy.deepcopy(p.export())
        for changes in [dict(exposure=0),dict(overhang=1),dict(deck_thickness=.25),dict(deck_stock='shingle')]:
            with self.assertRaises(ValueError):asphalt_roof(p,'invalid',**(args|changes))
            self.assertEqual(p.export(),before)
        r.interfaces['pitch']=3
        with self.assertRaises(ValueError):asphalt_roof(p,'invalid',**args)
        self.assertEqual(p.export(),before)

    def test_plumb_cut_allowance_fits_each_deck_blank(self):
        from dataclasses import replace
        from stud.model import sheet_blank_candidates
        p,r,f,args=finished()
        p.parts[:]=[part for part in p.parts if part.get('component')!='finish']
        for key in ('rules','requirements','unverified'):
            p.validation[key]=[item for item in p.validation[key] if not str(item.get('id',item.get('rule',''))).startswith('finish.')]
        p.stocks['deck']=replace(p.stocks['deck'],sheet=(47.65,96))
        f=asphalt_roof(p,'finish',**args)
        for part in p.parts:
            if part['stock']=='deck':
                options=sheet_blank_candidates(part.get('blank_size',part['size']),.625)
                self.assertTrue(any(a<=47.65+.001 and b<=96+.001 for a,b in options))

    def test_shared_accessory_stock_keeps_role_lengths(self):
        p,r,f,args=finished()
        before=sum(row['linear_ft'] for row in p.export()['materials'] if row['stock'] in ('cap','starter'))
        # Rebuild on a fresh roof with the same package stock in both roles.
        base,w,roof,skin=enclosed_project()
        base.stocks.update({key:value for key,value in p.stocks.items() if key not in base.stocks})
        asphalt_roof(base,'other',**(args|dict(roof=roof,starter_stock='cap')))
        row=next(row for row in base.export()['materials'] if row['stock']=='cap')
        self.assertAlmostEqual(row['linear_ft'],before,places=1)

    def test_linear_coverage_rejects_invalid_metadata_and_stock(self):
        p=Project('lengths')
        for kw in [dict(coverage_linear_ft=0),dict(coverage_linear_ft=10,coverage_sq_ft=5),dict(coverage_linear_ft=10,waste_factor=float('inf'))]:
            with self.assertRaises(ValueError):p.stock('bad','bad','#aaa',**kw)
        p.stock('edge','edge','#aaa',coverage_linear_ft=10)
        p.box('edge','Edge','edge',(1,1,1),(0,0,0))
        with self.assertRaises(ValueError):p.export()
        p.parts[-1]['coverage_length_in']=120
        self.assertEqual(p.export()['materials'][0]['quantity'],1)
        p.parts[-1]['coverage_length_in']=-1
        with self.assertRaises(ValueError):p.export()
