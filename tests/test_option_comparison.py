"""Comparison display uses real saved evidence without touching source writers."""
from pathlib import Path
from test_session import ProjectFixture, DESIGN
from stud.contracts import StudError
from stud.display import model_for_viewer
from stud.session_http import ProjectAPI


class OptionComparisonTests(ProjectFixture):
    def test_three_tabs_reuse_immutable_views_and_keep_open_writer(self):
        request=self.begin();source=self.edit(request);first=self.finish(request,source)
        main=self.session.snapshot()['option']
        options=[main]
        for index in range(2):
            option=self.session.create_option(key=f'option{index}',name=f'Dormered {index}',base_checkpoint=first['checkpoint'])
            self.session.activate_option(key=f'active{index}',option_id=option['id'],expected_head=option['head'])
            request=self.begin(f'edit{index}');source=self.edit(request,DESIGN.replace('600',str(900+index*100)))
            self.finish(request,source)
            options.append(self.session.history.option(option['id']))
        writer=self.begin('writer');self.edit(writer,DESIGN.replace('600','1200'))
        before=self.session.snapshot()
        source_before=(Path(writer['workspace'])/'design.py').read_bytes()
        branches_before=self.session.history.git('show-ref','--heads')
        checkout_before=(self.root/'design.py').read_bytes()
        api=ProjectAPI(self.session)
        def command(operation,key,**arguments):
            return api.command(dict(operation=operation,key=key,arguments=arguments))
        prepared=[]
        for index,option in enumerate(options):
            job=command('prepare_option',f'prepare{index}',option_id=option['id'],expected_head=option['head'])
            ready=self.session.wait(job['id'])
            self.assertEqual(ready['status'],'complete',ready)
            self.assertEqual(ready['result']['geometry_status'],'available')
            prepared.append(ready)
            self.assertEqual(self.session.state.get('view_mode'),before.get('view_mode'))
        for index in [0,1,2,0]:
            option=options[index]
            command('inspect_option',f'switch{index}-{self.session.state["sequence"]}',option_id=option['id'],expected_head=option['head'],comparison_id=prepared[index]['id'])
            visible=model_for_viewer(self.session)
            self.assertEqual(visible['cad']['option_id'],option['id'])
            self.assertEqual(visible['cad']['checkpoint'],option['head'])
            self.assertEqual(visible['cad']['build_id'],prepared[index]['result']['views'][0]['cad']['build_id'])
            self.assertEqual(self.session.snapshot()['active_request'],writer['id'])
            self.assertEqual(self.session.snapshot()['active_option'],before['active_option'])
        self.assertEqual((Path(writer['workspace'])/'design.py').read_bytes(),source_before)
        self.assertEqual(self.session.history.git('show-ref','--heads'),branches_before)
        self.assertEqual((self.root/'design.py').read_bytes(),checkout_before)
        command('return_live','live')
        self.assertEqual(self.session.state['view_mode'],'live')
        self.assertIsNone(self.session.state.get('view_option'))

    def test_stale_and_wrong_evidence_are_rejected_before_selecting(self):
        request=self.begin();source=self.edit(request);first=self.finish(request,source)
        option=self.session.snapshot()['option']
        job=self.session.versions.prepare_option(key='prepared',option_id=option['id'],expected_head=option['head'])
        job=self.session.wait(job['id'])
        with self.assertRaises(StudError) as failure:
            self.session.versions.inspect_option(key='stale',option_id=option['id'],expected_head=self.initial['checkpoint'],comparison_id=job['id'])
        self.assertEqual(failure.exception.category,'changed_head')
        with self.assertRaises(StudError) as failure:
            self.session.versions.inspect_option(key='wrong',option_id=option['id'],expected_head=option['head'],comparison_id=first['build_id'])
        self.assertEqual(failure.exception.category,'unavailable_artifact')
        self.assertNotEqual(self.session.state.get('view_mode'),'history')

    def test_retry_does_not_undo_return_to_live(self):
        request=self.begin();source=self.edit(request);self.finish(request,source)
        option=self.session.snapshot()['option']
        job=self.session.wait(self.session.versions.prepare_option(key='prepared',option_id=option['id'],expected_head=option['head'])['id'])
        args=dict(key='select',option_id=option['id'],expected_head=option['head'],comparison_id=job['id'])
        self.session.versions.inspect_option(**args)
        self.session.return_live(key='live')
        self.session.versions.inspect_option(**args)
        self.assertEqual(self.session.state['view_mode'],'live')
