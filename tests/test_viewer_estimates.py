"""Conversation and cells share version-bound estimate writes and evidence."""
from pathlib import Path
import csv
import io
from unittest.mock import patch
from test_session import ProjectFixture
from test_estimate_contract import quote
from stud.contracts import StudError, read_json
from stud.display import prices_for_viewer, save_viewer_prices, csv_for_viewer
from stud.estimate import purchase_lines


class ViewerEstimateTests(ProjectFixture):
    def prepared(self):
        draft=self.begin();source=self.edit(draft)
        build=self.session.wait(self.session.evaluate(draft['id'],source)['id'])
        manifest=read_json(Path(build['artifact_path'])/'manifest.json')
        line=purchase_lines(manifest['demands'],{})[0]
        self.session.save_prices(key='source-price',quotes=[quote(line,price='12',kind='sourced')])
        return draft,source,build

    def test_price_and_quantity_overrides_are_independent_and_clear_survives_checkpoint(self):
        draft,source,build=self.prepared()
        initial=prices_for_viewer(self.session);line=initial['rows'][0]
        self.assertEqual(line['model_quantity'],'1')
        changed=save_viewer_prices(self.session,dict(key=line['key'],unit_price=8,quantity=3,source='Voice correction',observed_on='2026-09-10',expected_estimate=initial['estimate_id']))
        self.assertEqual(changed['subtotal'],'24.00')
        self.assertEqual(changed['rows'][0]['model_quantity'],'1')
        self.assertEqual(changed['rows'][0]['quantity_override'],'3')
        clear_price=save_viewer_prices(self.session,dict(key=line['key'],action='clear_manual'))
        self.assertEqual(clear_price['subtotal'],'36.00')
        self.assertEqual(clear_price['rows'][0]['quote_kind'],'source')
        clear_quantity=save_viewer_prices(self.session,dict(key=line['key'],action='clear_quantity'))
        self.assertEqual(clear_quantity['subtotal'],'12.00')
        self.assertIsNone(clear_quantity['rows'][0]['quantity_override'])
        result=self.finish(draft,source)
        self.assertNotIn(line['key'],self.session.records.inputs(result['checkpoint'])['overrides'])

    def test_stale_or_historical_prices_do_not_write_and_missing_evidence_is_returned(self):
        draft,source,build=self.prepared();before=prices_for_viewer(self.session);row=before['rows'][0]
        self.assertTrue(row['stock']);self.assertEqual(row['object_ids'],['beam'])
        self.assertEqual(before['units'],'mm');self.assertIn('missing',before)
        with self.assertRaises(StudError):save_viewer_prices(self.session,dict(key=row['key'],action='clear_manual',expected_estimate='stale'))
        self.assertEqual(prices_for_viewer(self.session)['subtotal'],before['subtotal'])
        result=self.finish(draft,source)
        changed=save_viewer_prices(self.session,dict(key=row['key'],unit_price=20,source='Later correction',observed_on='2026-09-10'))
        self.assertEqual(changed['subtotal'],'20.00')
        job=self.session.inspect_checkpoint(key='history',checkpoint=result['checkpoint'])
        if job.get('id'):self.session.wait(job['id'])
        for action in ('clear_manual','clear_quantity'):
            with self.assertRaises(StudError):save_viewer_prices(self.session,dict(key=row['key'],action=action))
        self.assertEqual(prices_for_viewer(self.session)['subtotal'],before['subtotal'])
        for path in ('/api/costs.csv','/api/materials.csv'):
            exported=list(csv.DictReader(io.StringIO(csv_for_viewer(self.session,path))))
            self.assertEqual(exported[0]['amount'],'12.00')
            self.assertEqual(exported[0]['checkpoint'],result['checkpoint'])

    def test_clearing_legacy_product_override_removes_the_correct_scope(self):
        draft,source,build=self.prepared()
        self.session.save_prices(key='quantity',quotes=[],overrides={'2x4':5},expected_build=build['id'])
        before=prices_for_viewer(self.session);self.assertEqual(before['rows'][0]['quantity'],'5')
        after=save_viewer_prices(self.session,dict(key=before['rows'][0]['key'],action='clear_quantity'))
        self.assertEqual(after['rows'][0]['quantity'],'1')
        self.assertNotIn('2x4',self.session.records.inputs(request=draft)['overrides'])
