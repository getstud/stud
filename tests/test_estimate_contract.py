"""Independent purchase and money examples; no CAD imports or workers."""
from copy import deepcopy
import unittest

from stud.contracts import StudError
from stud.estimate import calculate, compare, purchase_lines, select_quotes


def demand(key='screws',quantity=10):
    return dict(id=key,product_id='fastener',specification={'size':'M6'},object_ids=[key],unit='each',purchase_unit='pack',pack_size=20,quantity=quantity)


def quote(plan,price='12.35',sequence=1,kind='sourced',key='q1',currency='USD'):
    return dict(id=key,product_id=plan['product_id'],specification=plan['specification'],purchase_unit=plan['purchase_unit'],pack_size=plan.get('pack_size',1),
        price=price,currency=currency,supplier='Fixture supplier',source='Saved receipt',quote_date='2026-09-09',save_sequence=sequence,kind=kind)


class EstimateContractTests(unittest.TestCase):
    def test_pooling_before_pack_rounding_and_override_applies_once(self):
        demands=[demand('a',10),demand('b',10)]
        result=calculate(demands,{'overrides':{'fastener':'3'},'allowances':{'fastener':'1'}},[quote(demand())])
        self.assertEqual(len(result['rows']),1)
        self.assertEqual(result['rows'][0]['demand_quantity'],'20')
        self.assertEqual(result['rows'][0]['quantity'],'3')
        self.assertEqual(result['total'],'37.05')
        self.assertEqual(calculate(demands,{},[quote(demand())])['total'],'12.35')

    def test_mixed_board_lengths_are_separate_purchases_and_quotes(self):
        lumber=dict(id='framing',product_id='2x4',specification={'section_mm':[38,89]},object_ids=['long','short'],unit='mm',purchase_unit='board',
            stock_lengths_mm=[2400,3600],cuts_mm=[dict(object_id='long',length_mm=3000),dict(object_id='short',length_mm=2000)])
        plans=purchase_lines([lumber],{})
        self.assertEqual(len(plans),2)
        prices=[quote(p,'30' if p['stock'][0]['length_mm']=='3600' else '20',key=str(i)) for i,p in enumerate(plans)]
        result=calculate([lumber],{},prices)
        self.assertEqual(result['total'],'50.00')
        self.assertEqual(sorted(p['stock'][0]['remaining_mm'] for p in plans),['397','597'])
        with self.assertRaises(StudError):calculate([lumber],{'overrides':{'2x4':5}},prices)
        changed=calculate([lumber],{'overrides':{plans[0]['line_id']:2}},prices)
        self.assertIn(changed['total'],('70.00','80.00'))

    def test_reusable_offcut_accounts_for_last_saw_cut_and_exact_fit(self):
        lumber=dict(id='framing',product_id='2x4',specification={'section_mm':[38,89]},object_ids=['a','b'],unit='mm',purchase_unit='board',
            stock_lengths_mm=[1000],kerf_mm=3,cuts_mm=[dict(object_id='a',length_mm=600),dict(object_id='b',length_mm=200)])
        board=purchase_lines([lumber],{})[0]['stock'][0]
        self.assertEqual(board['remaining_mm'],'194')
        self.assertEqual(board['trailing_kerf_mm'],'3')
        self.assertEqual([c['kerf_before_mm'] for c in board['cuts']],['0','3'])
        lumber['cuts_mm']=[dict(object_id='a',length_mm=1000)]
        board=purchase_lines([lumber],{})[0]['stock'][0]
        self.assertEqual((board['remaining_mm'],board['trailing_kerf_mm']),('0','0'))
        lumber['cuts_mm']=[dict(object_id='a',length_mm=998)]
        board=purchase_lines([lumber],{})[0]['stock'][0]
        self.assertEqual((board['remaining_mm'],board['trailing_kerf_mm']),('0','2'))

    def test_precedence_clear_manual_and_latest_save_are_explicit(self):
        base=demand();sourced=quote(base,sequence=3);manual=quote(base,'15',sequence=2,kind='manual',key='manual')
        self.assertEqual(calculate([base],{},[manual,sourced])['total'],'15.00')
        clear={k:v for k,v in manual.items() if k in ('product_id','specification','purchase_unit','pack_size')}
        clear.update(id='clear',action='clear_manual',save_sequence=4)
        self.assertEqual(calculate([base],{},[manual,sourced,clear])['total'],'12.35')
        newer=quote(base,'11',sequence=5,key='new',kind='sourced')
        self.assertEqual(calculate([base],{},[manual,sourced,clear,newer])['total'],'11.00')
        with self.assertRaises(StudError):select_quotes([sourced,quote(base,sequence=3,key='conflict')])

    def test_decimal_rounding_missing_and_currency_are_not_zero(self):
        base=demand(quantity=60)
        result=calculate([base],{'tax_rate':'.075','contingency_rate':'.10'},[quote(base,'0.335')])
        # 3 * .335 = 1.005 -> 1.01, tax .08, contingency .11.
        self.assertEqual((result['known_subtotal'],result['tax'],result['contingency'],result['total']),('1.01','0.08','0.11','1.20'))
        for quotes in ([],[quote(base,currency='CAD')]):
            missing=calculate([base],{},quotes)
            self.assertIsNone(missing['total']);self.assertIsNone(missing['rows'][0]['line_total'])
        for price in ('NaN','-1','Infinity'):
            with self.assertRaises(StudError):calculate([base],{},[quote(base,price)])

    def test_common_price_preserves_changed_assumptions_and_historical_totals(self):
        base=demand();basis=select_quotes([quote(base)])
        left=calculate([base],{},basis=basis);right=calculate([base],{'overrides':{'fastener':2}},basis=basis)
        original=deepcopy(left);result=compare(left,right,mode='common_price')
        self.assertTrue(result['assumptions_changed'])
        self.assertIn('quantity_override',result['lines'][0]['changes'])
        self.assertEqual(left,original)
        legacy=deepcopy(left);legacy['rows']=[{**left['rows'][0],'line_id':None,'demand_id':'a'},{**left['rows'][0],'line_id':None,'demand_id':'b'}]
        self.assertEqual(len(compare(legacy,legacy)['lines']),2)
