"""Behavior at the public flooring interface and native edge requirement."""
from dataclasses import replace
from pathlib import Path
import runpy
import tempfile
import unittest
import cadquery as cq
from stud.cad import Model
from stud.checks import check_model
from stud.fabrication import audit_fabrication
from stud.floors import (deck_floor, PanelSpec, FloorSurface, DeckRegion, BackingDetail,
    FloorInstallation, Opening)
from stud.framing import MemberProfile


def box(x,y,z,w,h,d):
    return cq.Workplane('XY').box(w,h,d,centered=(False,False,False)).translate((x,y,z)).val()


def fixture(edge='tongue_and_groove',location=None,opening=None,with_backing=True):
    m=Model('Panel joint test',units='in');location=location or cq.Location()
    m.assembly('frame',location=location)
    hosts=[]
    for pid,shape in [('west',box(0,0,-9.5,1.75,96,9.5)),('east',box(94.25,0,-9.5,1.75,96,9.5)),
                      ('south',box(1.75,0,-9.5,92.5,1.75,9.5)),('north',box(1.75,94.25,-9.5,92.5,1.75,9.5))]:
        m.part(pid,shape,parent='frame',material='lumber');hosts.append(pid)
    surface=FloorSurface(((0,0),(96,0),(96,96),(0,96)),tuple(hosts),0,openings=(opening,) if opening else (),location=location)
    deck=deck_floor(m,surface,object_id='deck',panel=PanelSpec('plywood',.703,edge=edge,actual_size=(47.5,95.875)),
        regions=(DeckRegion('field',stagger=0),),backing=BackingDetail(MemberProfile(3.5,1.5,'backing',(96,144)),
        'Fit to framing with specified end attachment.') if with_backing else None,installation=FloorInstallation('Specified nails','Specified glue',.125))
    return m,deck


class DeckingTests(unittest.TestCase):
    def assert_passed(self,m):
        c=check_model(m)
        self.assertTrue(c['all_passed'],[f for f in c['findings'] if f['status']!='passed'])
        return c

    def test_tg_removes_backing_but_square_edges_generate_it(self):
        tg,a=fixture();sq,b=fixture('square')
        self.assert_passed(tg);self.assert_passed(sq)
        self.assertEqual(len(a['panels']),2);self.assertEqual(a['backing'],[])
        self.assertGreater(len(b['backing']),0)
        self.assertAlmostEqual(sum(tg.objects[p]['volume'] for p in a['panels']),96*96*.703)
        findings=[f for f in check_model(tg)['findings'] if f['kind']=='panel_edge_system']
        self.assertTrue(all(sum(e['joint_supported'] for e in f['evidence']['edges'])>90 for f in findings))

    def test_rotated_surface_uses_local_stock_axes_and_world_contacts(self):
        m,d=fixture(location=cq.Location(cq.Vector(300,-50,15),cq.Vector(0,0,1),37))
        self.assert_passed(m)
        self.assertEqual(d['backing'],[])
        for p in d['panels']:
            self.assertEqual(m.objects[p]['parent'],'deck.panels')
            self.assertAlmostEqual(m.objects[p]['volume'],48*96*.703)

    def test_deleted_mate_and_support_produce_findings(self):
        for remove in ('mate','support'):
            m,d=fixture();key=d['panels'][1] if remove=='mate' else 'north'
            del m.objects[key];del m.shapes[key]
            c=check_model(m)
            self.assertTrue(any(f['kind']=='panel_edge_system' and f['status']=='unresolved' for f in c['findings']))

    def test_joint_metadata_and_moved_geometry_invalidate_cached_pass(self):
        for change in ('role','family','move','rip'):
            m,d=fixture();pid=d['panels'][1]
            with tempfile.TemporaryDirectory() as temp:
                cache=Path(temp)/'cache.json';self.assertTrue(check_model(m,cache_path=cache)['all_passed'])
                if change in ('role','family'):
                    for e in m.objects[pid]['blank']['factory_edges']:e[change]='tongue' if change=='role' else 'incompatible'
                else:
                    obj=m.objects[pid];entry=m.shapes[pid]
                    shape=entry['local'];loc=entry['location']
                    if change=='move':loc=loc*cq.Location(cq.Vector(0,0,.1))
                    else:shape=shape.cut(box(-1,-1,-1,3,98,3))
                    m.part(pid,shape,location=loc,blank=obj['blank'],material=obj['material'],replace=True)
                failures=[f for f in check_model(m,cache_path=cache)['findings'] if f['kind']=='panel_edge_system' and f['status']=='failed']
                self.assertTrue(failures,change)

    def test_missing_planar_underside_is_not_a_vacuous_pass(self):
        m,d=fixture();pid=d['panels'][1];entry=m.shapes[pid];obj=m.objects[pid]
        m.part(pid,entry['local'].rotate((0,0,0),(1,0,0),10),location=entry['location'],
               blank=obj['blank'],material=obj['material'],replace=True)
        finding=next(f for f in check_model(m)['findings'] if f['requirement_id']==pid+'.edges')
        self.assertEqual(finding['status'],'unsupported')

    def test_supported_flat_strip_cannot_hide_sloped_underside(self):
        m,d=fixture()
        for pid in d['panels']:
            entry=m.shapes[pid];obj=m.objects[pid]
            cutter=box(-1,1,-5,50,100,5).rotate((0,1,0),(1,1,0),.3)
            m.part(pid,entry['local'].cut(cutter),location=entry['location'],blank=obj['blank'],material=obj['material'],replace=True)
        findings=[f for f in check_model(m)['findings'] if f['kind']=='panel_edge_system']
        self.assertTrue(all(f['status']=='unsupported' for f in findings))

    def test_square_end_failure_is_not_hidden_by_valid_tg_joint(self):
        m,d=fixture();obj=m.objects['north']
        m.part('north',box(1.75,94.25,-9.5,92.5,1.75,8),material='lumber',replace=True)
        failures=[f for f in check_model(m)['findings'] if f['kind']=='panel_edge_system' and f['status']=='failed']
        self.assertEqual(len(failures),2)
        self.assertTrue(all(f['measured']>40 for f in failures))

    def test_nominal_layout_never_claims_actual_stock_cut_fit(self):
        m,d=fixture()
        demand=m.demands['deck.sheets']
        self.assertEqual(demand['specification']['sheet'],[48,96])
        self.assertEqual(demand['specification']['actual_sheet'],[47.5,95.875])
        findings=audit_fabrication(m.export())
        self.assertTrue(any(f['category']=='nominal_sheet_layout' for f in findings))
        self.assertFalse(any(f['category']=='incompatible_sheet_stock' for f in findings))
        self.assertEqual(m.connections['deck.installation']['detail']['joint_gap'],.125)

    def test_irregular_regions_and_moved_shared_opening(self):
        path=Path(__file__).resolve().parents[1]/'examples/cadquery-subfloor-system/design.py'
        old=None
        for x in (30,40):
            ns={};exec(compile(path.read_text().replace("Opening('stairs',30,35,25,30)",f"Opening('stairs',{x},35,25,30)"),str(path),'exec'),ns)
            m,d=ns['model'],ns['deck'];self.assert_passed(m)
            hole=box(x,35,-1,25,30,12)
            self.assertAlmostEqual(sum(m.shapes[p]['world'].intersect(hole).Volume() for p in d['panels']),0)
            self.assertAlmostEqual(sum(m.shapes[p]['world'].intersect(hole).Volume() for p in ns['frames'][0]['parts']),0)
            self.assertAlmostEqual(sum(m.objects[p]['volume'] for p in d['panels'])/.703,144*144+48*96-25*30)
            if old:
                self.assertEqual(set(old['panels']),set(d['panels']))
            old=d

    def test_enclosed_hole_retains_inner_wire_cut_and_edge_support(self):
        opening=Opening('hole',15,15,10,10)
        m,d=fixture('square',opening=opening)
        self.assert_passed(m)
        hole=box(15,15,-1,10,10,3)
        self.assertAlmostEqual(sum(m.shapes[p]['world'].intersect(hole).Volume() for p in d['panels']),0)
        self.assertTrue(any(op['kind']=='profile_cutout' for p in d['panels'] for op in m.objects[p]['blank']['operations']))
        self.assertTrue(any(c.get('geometry_unresolved') for c in m.connections.values()))

    def test_square_seam_without_backing_remains_an_inspectable_failure(self):
        m,d=fixture('square',with_backing=False)
        self.assertEqual(d['backing'],[])
        failures=[f for f in check_model(m)['findings'] if f['kind']=='panel_edge_system' and f['status']=='failed']
        self.assertEqual(len(failures),2)
        self.assertTrue(all(f['measured']>90 for f in failures))

    def test_invalid_inputs_and_incomplete_regions_are_rejected(self):
        for kwargs in ({'edge':'magic'},{'thickness':float('nan')},{'actual_size':(0,96)}):
            args=dict(product_id='panel',thickness=.703);args.update(kwargs)
            with self.assertRaises(ValueError):PanelSpec(**args)
        m,_=fixture()
        surface=FloorSurface(((0,0),(96,0),(96,96),(0,96)),('west','east','south','north'),0)
        for regions in ((DeckRegion('a',outline=((0,0),(48,0),(48,96),(0,96))),),
                        (DeckRegion('a'),DeckRegion('b'))):
            with self.assertRaises(ValueError):
                deck_floor(m,surface,object_id='invalid'+str(len(m.assemblies)),panel=PanelSpec('panel',.703),regions=regions)
