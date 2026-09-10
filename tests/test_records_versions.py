"""Branch, record and retry tests through the coordinator interface."""
from pathlib import Path
import time
from unittest.mock import patch

from test_session import ProjectFixture, DESIGN
from test_estimate_contract import quote
from stud.contracts import StudError, read_json, write_json
from stud.estimate import purchase_lines


class RecordsAndVersionsTests(ProjectFixture):
    def test_loading_history_keeps_actual_display_identity_until_ready(self):
        from stud.display import model_for_viewer
        request=self.begin();source=self.edit(request);finished=self.finish(request,source)
        with patch.object(self.session.history_workers,'submit'):
            self.session.inspect_checkpoint(key='load-initial',checkpoint=self.initial['checkpoint'])
            visible=model_for_viewer(self.session)
            self.assertEqual(visible['cad']['build_id'],finished['build_id'])
            self.assertEqual(visible['cad']['presentation'],'live')
            self.assertNotEqual(visible['cad']['checkpoint'],self.initial['checkpoint'])

    def test_historical_prompts_use_the_viewed_ancestry(self):
        from stud.display import displayed_prompts
        request=self.begin();source=self.edit(request);first=self.finish(request,source)
        request=self.begin('resolve');source=self.edit(request,DESIGN.replace('600','800'))
        build=self.session.wait(self.session.evaluate(request['id'],source)['id'])
        self.session.save_prompt(key='history-prompt',prompt_id='history_prompt',text='Review this beam',build_id=build['id'],source_id=source,object_id='beam')
        self.session.update_prompt(key='history-resolve',prompt_id='history_prompt',expected_revision=0,action='resolve',addressing_request=request['id'])
        self.finish(request,source)
        self.session.inspect_checkpoint(key='older-view',checkpoint=first['checkpoint'])
        self.assertFalse(displayed_prompts(self.session)[0]['addressing_requests'][0]['in_viewed_history'])

    def test_hard_crash_checkpoint_reuses_its_retained_geometry_for_inspection(self):
        from stud.display import model_for_viewer
        request=self.begin();source=self.edit(request,DESIGN+"\nimport os, stud.checks\nstud.checks.measure_requirement=lambda *args: os._exit(7)\n")
        failed=self.finish(request,source)
        request=self.begin('later');source=self.edit(request,DESIGN.replace('600','800'));self.finish(request,source)
        with patch.object(self.session.history_workers,'submit',side_effect=AssertionError('Retained geometry needs no worker')):
            inspected=self.session.inspect_checkpoint(key='crashed-view',checkpoint=failed['checkpoint'])
        self.assertEqual(inspected['status'],'complete')
        visible=model_for_viewer(self.session)
        self.assertEqual(visible['cad']['checkpoint'],failed['checkpoint'])
        self.assertEqual(visible['cad']['build_id'],failed['build_id'])

    def test_durable_quote_and_prompt_action_retry_after_receipt_crash(self):
        request=self.begin();source=self.edit(request)
        job=self.session.evaluate(request['id'],source);self.session.wait(job['id'])
        manifest=read_json(Path(job['artifact_path'])/'manifest.json')
        saved_quote=quote(purchase_lines(manifest['demands'],{})[0])
        original_write=write_json
        def crash(path,data):
            if 'record_receipts' in str(path):raise OSError('Crash after durable rename')
            return original_write(path,data)
        with patch('stud.records.write_json',side_effect=crash):
            with self.assertRaises(OSError):self.session.save_prices(key='price-retry',quotes=[saved_quote])
        sequence=self.session.state['save_sequence']
        first=self.session.save_prices(key='price-retry',quotes=[saved_quote])
        self.assertEqual(first,self.session.save_prices(key='price-retry',quotes=[saved_quote]))
        self.assertEqual(self.session.state['save_sequence'],sequence)
        self.session.save_prompt(key='p',prompt_id='prompt_a',text='Widen the beam',build_id=job['id'],source_id=source,object_id='beam')
        with patch('stud.records.write_json',side_effect=crash):
            with self.assertRaises(OSError):self.session.update_prompt(key='resolve',prompt_id='prompt_a',expected_revision=0,action='resolve')
        self.session.update_prompt(key='resolve',prompt_id='prompt_a',expected_revision=0,action='resolve')
        self.assertEqual(self.session.records.prompts()[0]['revision'],1)
        with self.assertRaises(StudError):self.session.save_prices(key='price-retry',quotes=[])

    def test_options_comparison_restore_retain_source_and_project_records(self):
        request=self.begin();source=self.edit(request);first=self.finish(request,source)
        main=self.session.snapshot()['active_option']
        option=self.session.create_option(key='alternative',name='Wider option',base_checkpoint=first['checkpoint'])
        self.assertEqual(self.session.create_option(key='alternative',name='Wider option',base_checkpoint=first['checkpoint']),option)
        self.session.activate_option(key='activate',option_id=option['id'],expected_head=option['head'])
        request=self.begin('wide');source=self.edit(request,DESIGN.replace('600','900'))
        build=self.session.evaluate(request['id'],source);self.session.wait(build['id'])
        manifest=read_json(Path(build['artifact_path'])/'manifest.json')
        q=quote(purchase_lines(manifest['demands'],{})[0],price='18.25')
        self.session.save_prices(key='wide-price',quotes=[q])
        self.session.save_prompt(key='wide-prompt',prompt_id='review_beam',text='Review the new width',build_id=build['id'],source_id=source,object_id='beam')
        second=self.finish(request,source)
        active=self.begin('compare-while-editing');self.edit(active,DESIGN.replace('600','950'))
        compare_job=self.session.compare_versions(key='common',left=first['checkpoint'],right=second['checkpoint'],mode='common_price')
        comparison=self.session.wait(compare_job['id'])
        self.assertEqual(comparison['status'],'complete',comparison)
        self.assertIn('reshaped',comparison['result']['objects'][0]['changes'])
        self.assertEqual(len(comparison['result']['views']),2)
        self.assertEqual(comparison['result']['views'][0]['cad']['checkpoint'],first['checkpoint'])
        self.assertEqual(comparison['result']['views'][1]['cad']['checkpoint'],second['checkpoint'])
        self.assertEqual(comparison['result']['geometry_status'],'available')
        self.assertEqual(comparison['result']['estimates']['left_total'],'18.25')
        self.assertEqual(self.session.snapshot()['active_request'],active['id'])
        with self.assertRaises(StudError):self.session.restore(key='too-early',checkpoint=first['checkpoint'],expected_head=second['checkpoint'])
        self.session.cancel(active['id'])
        restore=self.session.restore(key='restore',checkpoint=first['checkpoint'],expected_head=second['checkpoint'])
        self.assertIn('700',(Path(restore['workspace'])/'design.py').read_text())
        restored=self.finish(restore,self.session.source(restore['id'])['source_id'])
        self.assertNotEqual(restored['checkpoint'],first['checkpoint'])
        self.assertEqual(self.session.history.git('rev-parse',restored['checkpoint']+'^').decode().strip(),second['checkpoint'])
        report=self.session.history.checkpoint_report(restored['checkpoint'])
        self.assertEqual(report['original_estimate']['total'],'18.25')
        self.assertEqual(len(self.session.records.values('quotes')),1)
        self.assertEqual(len(self.session.records.prompts()),1)
        self.assertEqual(self.session.history.option(main)['head'],first['checkpoint'])

    def test_idle_price_checkpoint_reuses_geometry_and_original_totals(self):
        request=self.begin();source=self.edit(request);first=self.finish(request,source)
        report=self.session.history.checkpoint_report(first['checkpoint']);q=quote(purchase_lines(report['evaluated_manifest']['demands'],{})[0])
        builds=len(list((self.session.local/'builds').glob('*')))
        with patch.object(self.session,'_schedule_build',side_effect=AssertionError('Price changes must not execute CAD')):
            self.session.save_prices(key='idle',quotes=[q],overrides={'2x4':'2'},expected_build=first['build_id'])
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                state=self.session.snapshot()
                if not state['pending_records'] and not state['active_request']:break
                time.sleep(.03)
        self.assertFalse(self.session.pending_records(),self.session.snapshot())
        self.assertEqual(len(list((self.session.local/'builds').glob('*'))),builds)
        saved=self.session.history.checkpoint_report(self.session.snapshot()['option']['head'])
        self.assertEqual(saved['original_estimate']['total'],'24.70')
        self.assertIsNone(self.session.history.checkpoint_report(first['checkpoint'])['original_estimate']['total'])

    def test_estimate_failure_is_saved_without_stranding_the_writer(self):
        request=self.begin();source=self.edit(request)
        write_json(Path(request['workspace'])/'estimating.json',{'tax_rate':'not a number'})
        result=self.finish(request,source)
        report=self.session.history.checkpoint_report(result['checkpoint'])
        self.assertEqual(report['original_estimate']['status'],'unavailable')
        self.assertEqual(report['completion']['geometry'],'complete')
        self.assertIsNone(self.session.snapshot()['active_request'])

    def test_internal_record_request_resumes_after_crash_before_finish(self):
        request=self.begin();source=self.edit(request);first=self.finish(request,source)
        manifest=self.session.history.checkpoint_report(first['checkpoint'])['evaluated_manifest']
        q=quote(purchase_lines(manifest['demands'],{})[0])
        with patch.object(self.session.executor,'submit'):
            self.session.save_prices(key='crash-flush',quotes=[q])
        with patch.object(self.session,'source',side_effect=SystemExit('Crash before freeze')):
            with self.assertRaises(SystemExit):self.session.records.flush()
        self.assertEqual(self.session.snapshot()['request']['change_kind'],'records')
        self.session.close()
        from stud.session import Session
        self.session=Session(self.root)
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if not self.session.snapshot()['active_request'] and not self.session.pending_records():break
            time.sleep(.05)
        self.assertIsNone(self.session.snapshot()['active_request'],self.session.snapshot())
        self.assertFalse(self.session.pending_records())
        self.begin('after-record-recovery')

    def test_invalid_manual_clear_never_becomes_an_immutable_record(self):
        self.begin()
        with self.assertRaises(StudError):
            self.session.save_prices(key='bad-clear',quotes=[dict(action='clear_manual',product_id='2x4',specification={},purchase_unit='board',pack_size='bad')])
        self.assertEqual(self.session.records.values('quotes'),[])

    def test_option_rename_is_revisioned_and_does_not_change_option_identity(self):
        request=self.begin();option=self.session.snapshot()['option']
        first=self.session.rename_option(key='rename',option_id=option['id'],name='Workshop',expected_revision=0)
        current=self.session.snapshot()['option']
        self.assertEqual(current['id'],option['id']);self.assertEqual(current['head'],option['head'])
        self.assertEqual(current['label'],'Workshop');self.assertEqual(current['revision'],1)
        self.assertEqual(self.session.rename_option(key='rename',option_id=option['id'],name='Workshop',expected_revision=0),first)
        with self.assertRaises(StudError) as error:self.session.rename_option(key='stale-name',option_id=option['id'],name='Older name',expected_revision=0)
        self.assertEqual(error.exception.category,'stale_revision')
        self.finish(request,self.session.source(request['id'])['source_id'])
        self.session.close();from stud.session import Session
        self.session=Session(self.root)
        self.assertEqual(self.session.snapshot()['option']['label'],'Workshop')
