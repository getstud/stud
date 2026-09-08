import copy
import unittest
from stud import WallFrame, wall_frame, wall_enclosure, door_unit, window_unit
from test_construction_assemblies import project, failures


def trimmed(angle=0,inward=1):
    p=project()
    p.stock('casing','Casing','#ddd',section=(.75,5.5),lengths=(96,120,144))
    for key in ('door','window'):p.stock(key,key,'#aaa',product=True)
    walls=wall_frame(p,'w',width=144,depth=192,height=96,stud_stock='stud',header_stock='joist',spacer_stock='sheet',
        frame=WallFrame((11,-17,9),angle,inward),openings=[
            dict(id='entry',wall='front',start=50,width=38,bottom=0,height=82),
            dict(id='view',wall='west',start=48,width=36,bottom=40,height=36)])
    args=dict(walls=walls,sheathing_stock='sheet',siding_stock='sheet',trim_stock='trim',opening_trim_stock='casing')
    skin=wall_enclosure(p,'skin',**args)
    for key,builder in [('entry',door_unit),('view',window_unit)]:
        builder(p,key,opening=walls.interfaces['openings'][key]['opening'],product_stock='door' if key=='entry' else 'window',
                inset=-1.125,frame_depth=5.125,obstacle_ids=walls.part_ids+skin.part_ids)
    return p,walls,skin,args


class OpeningTrimTests(unittest.TestCase):
    def test_actual_four_inch_faces_and_unit_clearance_in_transforms(self):
        for angle,inward in [(0,1),(37,-1)]:
            p,w,skin,args=trimmed(angle,inward)
            self.assertEqual(failures(p),[])
            casing=[p for p in p.parts if p['stock']=='casing']
            self.assertEqual(len(casing),7)
            for part in casing:
                axis=2 if part['role'].endswith(('head','sill')) else 0
                self.assertEqual(part['size'][axis],4)
                self.assertEqual(part['blank_size'][axis],5.5)
            materials={r['stock']:r for r in p.export()['materials']}
            self.assertEqual(sum(len(bin['cuts']) for bin in materials['casing']['bins']),7)
            self.assertEqual(materials['door']['quantity'],1)
            self.assertEqual(materials['window']['quantity'],1)

    def test_door_head_trim_extends_into_gable_siding(self):
        from test_enclosure_roof import enclosed_project
        p,w,r,skin=enclosed_project(37,-1)
        p.parts[:]=[part for part in p.parts if not part['id'].startswith('skin.')]
        for key in ('rules','requirements','unverified'):
            p.validation[key]=[item for item in p.validation[key] if not item.get('id',item.get('rule','')).startswith('skin.')]
        p.stock('casing','Casing','#ddd',section=(.75,5.5),lengths=(96,120,144))
        skin=wall_enclosure(p,'skin',walls=w,roof=r,exterior_bottom=-8,
            sheathing_stock='sheet',siding_stock='sheet',trim_stock='trim',liner_stock='sheet',opening_trim_stock='casing')
        self.assertEqual(failures(p),[])
        head=next(part for part in p.parts if part['id']=='skin.front.opening_trim.entry.head')
        self.assertGreater(head['origin'][2]+head['size'][2],r.interfaces['soffit_bottom'])
        backing=next(rule for rule in p.validation['rules'] if rule['id']==head['id']+'.backing')
        self.assertTrue(any('.upper.sheathing.' in pid for pid in backing['parts']))

    def test_missing_floating_and_narrow_trim_fail(self):
        p,w,skin,args=trimmed()
        pid='skin.front.opening_trim.entry.left'
        changed=copy.deepcopy(p);changed.parts[:]=[part for part in changed.parts if part['id']!=pid]
        self.assertIn('skin.front.members',{f.get('rule_id') for f in failures(changed)})
        changed=copy.deepcopy(p);part=next(part for part in changed.parts if part['id']==pid)
        part['origin'][1]-=.25
        self.assertIn(pid+'.backing',{f.get('rule_id') for f in failures(changed)})
        changed=copy.deepcopy(p);part=next(part for part in changed.parts if part['id']==pid)
        part['size'][0]=3.5
        self.assertIn(pid+'.width',{f.get('rule_id') for f in failures(changed)})

    def test_bad_width_and_corner_conflicts_are_atomic(self):
        p,w,skin,args=trimmed();before=copy.deepcopy(p.export())
        for changes in [dict(opening_trim_width=6),dict(opening_trim_overlap=4),dict(opening_trim_width=-1)]:
            with self.assertRaises(ValueError):wall_enclosure(p,'invalid',**(args|changes))
            self.assertEqual(p.export(),before)
        args['walls'].interfaces['openings']['entry']['spec']['start']=3
        with self.assertRaises(ValueError):wall_enclosure(p,'invalid',**args)
        self.assertEqual(p.export(),before)
