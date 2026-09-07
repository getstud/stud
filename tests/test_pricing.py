import unittest,tempfile
from pathlib import Path
from pricing import PriceStore,lines
from stud import Project


def pricing_model():
    project = Project('Pricing test')
    project.stock('pt2x4', 'Test lumber', '#fff', section=(1.5, 3.5), lengths=(96, 144))
    for i in range(10):
        project.box(f'board.{i}', 'Test', 'pt2x4', (1.5, 3.5, 96), (i*4, 0, 0))
    project.box('long', 'Test', 'pt2x4', (1.5, 3.5, 144), (44, 0, 0))
    project.stock('skin', 'Test coverage', '#fff', coverage_sq_ft=1, purchase_unit='6-board pack')
    project.box('panel', 'Test', 'skin', (12, .5, 120), (0, 10, 0))
    project.stock('fees', 'Test fee', '#fff')
    project.allowances.append(dict(stock='fees', name='Test fee', kind='coverage',
                                  quantity=1, unit='fee', basis='Test', url='', taxable=False))
    project.budget = dict(target='2000', sales_tax_rate='0.0625', contingency_rate='0.10')
    return dict(project.export(), revision='pricing-test')

class PricingTests(unittest.TestCase):
    def test_categories_are_project_metadata_not_stock_names(self):
        project = Project('Furniture')
        project.stock('2x4', 'Frame', '#fff', section=(1.5, 3.5), lengths=(96,),
                      category='Furniture')
        project.stock('roofing', 'Cover', '#fff', coverage_sq_ft=10)
        project.box('frame', 'Seat', '2x4', (1.5, 3.5, 48), (0, 0, 0))
        project.box('cover', 'Seat', 'roofing', (48, 24, .25), (0, 0, 0))
        model = project.export()
        rows = {row['key']: row for row in lines(model)}
        self.assertEqual(rows['2x4:board:96']['category'], 'Furniture')
        self.assertEqual(rows['roofing:pack']['category'], 'Other')
        model['materials'][0]['category'] = 'Custom override'
        self.assertEqual(lines(model)[0]['category'], 'Custom override')

    def test_shiplap_uses_pack_coverage_and_dynamic_quantity(self):
        import copy
        m=pricing_model()
        row=next(r for r in lines(m) if r['key']=='skin:pack')
        self.assertEqual(row['unit'],'6-board pack')
        self.assertEqual(row['model_quantity'],10)
        with tempfile.TemporaryDirectory() as d:
            store=PriceStore(Path(d)/'prices.json')
            store.update(dict(key='skin:pack',kind='source',unit_price='105.63',source='Home Depot',observed_on='2026-09-07',url='https://www.homedepot.com/p/322913023'),m)
            self.assertEqual(store.estimate(m)['subtotal'],'1056.30')
            changed=copy.deepcopy(m)
            next(r for r in changed['materials'] if r['stock']=='skin')['quantity']=11
            self.assertEqual(store.estimate(changed)['subtotal'],'1161.93')

    def test_quotes_totals_precedence_and_persistence(self):
        m=pricing_model()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'prices.json';s=PriceStore(path);key='pt2x4:board:96'
            base=dict(key=key,unit_price='10.25',source='Supplier',observed_on='2026-09-07',url='https://www.homedepot.com/p/206968441')
            s.update(dict(base,kind='source'),m)
            e=s.estimate(m);self.assertEqual(e['subtotal'],'102.50');self.assertEqual(e['priced_lines'],1)
            s.update(dict(base,kind='manual',unit_price='9.99',quantity=30),m)
            s.update(dict(base,kind='source',unit_price='12.00'),m)
            self.assertEqual(PriceStore(path).estimate(m)['subtotal'],'299.70')
            e=s.update(dict(key=key,action='clear_manual'),m);self.assertEqual(e['subtotal'],'120.00')
    def test_units_missing_prices_and_validation(self):
        m=pricing_model();keys={r['key'] for r in lines(m)}
        self.assertIn('pt2x4:board:96',keys);self.assertIn('pt2x4:board:144',keys)
        with tempfile.TemporaryDirectory() as d:
            s=PriceStore(Path(d)/'p.json');self.assertEqual(s.estimate(m)['priced_lines'],0)
            base=dict(key='pt2x4:board:96',source='Yard',observed_on='2026-09-07')
            for value in ('NaN','Infinity','-1','no'):
                with self.assertRaises(ValueError):s.update(dict(base,unit_price=value),m)
            with self.assertRaises(ValueError):s.update(dict(base,unit_price='10',kind='source'),m)
            e=s.update(dict(base,unit_price='0'),m);self.assertEqual(e['priced_lines'],1);self.assertEqual(e['subtotal'],'0.00')

    def test_estimate_fallback_and_budget_math(self):
        from decimal import Decimal
        m=pricing_model()
        with tempfile.TemporaryDirectory() as d:
            s=PriceStore(Path(d)/'p.json')
            q=dict(key='pt2x4:board:96',unit_price='5',source='Estimate',observed_on='2026-09-07')
            e=s.update(dict(q,kind='estimate'),m)
            self.assertEqual(e['price_kinds']['estimate']['subtotal'],'50.00')
            self.assertEqual(e['budget']['sales_tax'],'3.13')
            self.assertEqual(e['budget']['contingency'],'5.31')
            self.assertEqual(e['budget']['grand_total'],'58.44')
            self.assertFalse(e['budget']['complete'])
            e=s.update(dict(q,kind='source',unit_price='6',url='https://example.com/quote'),m)
            self.assertEqual(e['subtotal'],'60.00')
            e=s.update(dict(q,kind='manual',unit_price='4'),m)
            self.assertEqual(e['subtotal'],'40.00')
            e=s.update(dict(q,action='clear_manual'),m)
            self.assertEqual(e['subtotal'],'60.00')
            self.assertEqual(Decimal(e['budget']['grand_total']),Decimal(e['subtotal'])+Decimal(e['budget']['sales_tax'])+Decimal(e['budget']['contingency']))

    def test_budget_fees_not_taxed(self):
        m=pricing_model()
        with tempfile.TemporaryDirectory() as d:
            s=PriceStore(Path(d)/'p.json')
            e=s.update(dict(key='fees:pack',kind='estimate',unit_price='100',source='Reserve',observed_on='2026-09-07'),m)
            self.assertEqual(e['budget']['sales_tax'],'0.00')
            self.assertEqual(e['budget']['grand_total'],'110.00')
