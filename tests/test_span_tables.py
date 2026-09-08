import copy
import unittest
from stud import Project, gable_roof, select_rafter_size

CONDITIONS = dict(species='Southern Pine', grade='No.2', roof_snow_psf=40,
                  dead_load_psf=15, deflection_limit=240, service='dry',
                  top_edge_braced=True, uniform_load=True,
                  load_basis='Regression inputs only; no site load claim')


class SpanTableTests(unittest.TestCase):
    def test_published_rows_and_boundaries(self):
        for spacing,limits in ((12,(132,168,199,234)),(16,(114,145,172,203)),
                               (19.2,(104,132,157,185)),(24,(93,118,141,165))):
            for nominal,limit in zip(('2x6','2x8','2x10','2x12'),limits):
                with self.subTest(spacing=spacing,size=nominal):
                    result=select_rafter_size(span=limit,spacing=spacing,**CONDITIONS)
                    self.assertEqual(result['nominal'],nominal)
                    self.assertEqual(result['allowable_span'],limit)
            with self.assertRaises(ValueError):select_rafter_size(span=limits[-1]+.001,spacing=spacing,**CONDITIONS)
        self.assertEqual(select_rafter_size(span=72,spacing=16,**CONDITIONS)['nominal'],'2x6')
        self.assertEqual(select_rafter_size(span=114.001,spacing=16,**CONDITIONS)['nominal'],'2x8')

    def test_unsupported_conditions_are_not_silently_substituted(self):
        changes=dict(species='SPF',grade='No.1',roof_snow_psf=30,dead_load_psf=20,
                     deflection_limit=360,service='wet',top_edge_braced=False,
                     uniform_load=False,load_basis='',span=float('nan'),spacing=20)
        for key,value in changes.items():
            args=dict(CONDITIONS,span=72,spacing=16);args[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):select_rafter_size(**args)
        for value in (True,0,-1,float('inf')):
            with self.assertRaises(ValueError):select_rafter_size(span=value,spacing=16,**CONDITIONS)

    def project_and_roof(self,stock='rafter',**changes):
        p=Project('Span lookup fixture')
        for key,sec in [('rafter',(1.5,5.5)),('large',(1.5,7.25)),('ridge',(1.5,9.25)),('tie',(1.5,3.5))]:
            p.stock(key,key,'#aaa',section=sec,lengths=(96,192,240))
        args=dict(length=192,span=144,pitch=6,plate_depth=3.5,
                  rafter_stock=stock,ridge_stock='ridge',tie_stock='tie',
                  system='ridge_board_ties',maximum_notch=2,minimum_remaining=3.5,
                  notch_basis='Geometry test inputs, not an approved notch detail',span_table=CONDITIONS)
        args.update(changes)
        return p,args

    def test_roof_uses_actual_span_and_persists_lookup(self):
        p,args=self.project_and_roof();r=gable_roof(p,'r',**args)
        result=r.interfaces['rafter_sizing']
        self.assertEqual(result['required_span'],67.75)
        self.assertEqual(result['nominal'],'2x6')
        exported=p.export()
        part=next(p for p in exported['parts'] if p['id']==r.roles['rafter.0.0'])
        self.assertEqual(part['span_table']['source'],result['source'])
        self.assertIn('SFPA',part['note'])

    def test_mismatch_and_notch_failure_leave_project_unchanged(self):
        for stock,changes in (('large',{}),('rafter',{'span':300}),
                              ('rafter',{'spacing':20}),('rafter',{'maximum_notch':1}),
                              ('rafter',{'length':97})):
            p,args=self.project_and_roof(stock,**changes);before=copy.deepcopy((p.parts,p.validation))
            with self.assertRaises(ValueError):gable_roof(p,'r',**args)
            self.assertEqual((p.parts,p.validation),before)

    def test_unsized_roof_is_explicitly_provisional(self):
        p,args=self.project_and_roof(span_table=None);gable_roof(p,'r',**args)
        self.assertTrue(any(row['rule']=='r.rafter_sizing' for row in p.validation['unverified']))
