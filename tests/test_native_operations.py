"""Fixed-version measurements and immutable PDF jobs through Session."""
from pathlib import Path
from unittest.mock import patch

from test_session import ProjectFixture
from stud.contracts import StudError, read_json


class NativeOperationsTests(ProjectFixture):
    def test_cropped_detail_keeps_scale_and_saved_quote_evidence(self):
        from test_session import DESIGN
        from pypdf import PdfReader
        source_text=DESIGN+"""
model.reference('beam','detail_end',point=(100,0,0))
model.dimension('detail_length','beam:left','beam:detail_end',label='End region')
model.drawing('end_detail',label='End detail',detail_of='front',crop_mm=[-10,-10,110,100],dimensions=['detail_length'],scale=2)
"""
        request=self.begin();source=self.edit(request,source_text)
        self.session.save_prices(key='quote',quotes=[dict(id='test_quote',product_id='2x4',specification={'material':'pine','section_mm':[38,89],'stock_length_mm':'2.4E+3'},
            purchase_unit='board',pack_size=1,price='17.25',currency='USD',supplier='Synthetic supplier',source='Explicit test fixture',quote_date='2026-09-09',kind='manual')])
        finished=self.finish(request,source)
        result=self.session.wait(self.session.plans(key='detail',checkpoint=finished['checkpoint'],build_id=finished['build_id'])['id'])
        self.assertEqual(result['status'],'complete',result)
        detail=result['result']['sheets'][1]
        self.assertEqual(detail['projection']['crop_mm'],[-10,-10,110,100])
        import math
        self.assertAlmostEqual(math.dist(detail['dimensions'][0]['start'],detail['dimensions'][0]['end']),100*72/25.4/2)
        pdf=PdfReader(result['result']['pdf'])
        self.assertIn(b'W',pdf.pages[1].get_contents().get_data())
        text='\n'.join(page.extract_text() for page in pdf.pages)
        for expected in ('USD 17.25','Synthetic supplier','Explicit test fixture','2026-09-09','detail of sheet 1'):
            self.assertIn(expected,text)

    def test_native_measurement_names_picks_and_stale_sources(self):
        request=self.begin();source=self.edit(request);finished=self.finish(request,source)
        args=dict(build_id=finished['build_id'],source_id=source,targets=['beam:left','beam:right'])
        job=self.session.measure(key='named',**args);result=self.session.wait(job['id'])
        self.assertEqual(result['status'],'complete',result)
        self.assertAlmostEqual(result['result']['value'],700)
        self.assertEqual(self.session.measure(key='named',**args)['id'],job['id'])
        picked=self.session.measure(key='picked',build_id=finished['build_id'],targets=[
            {'object_id':'beam','point_mm':[0,19,44.501]}, {'object_id':'beam','point_mm':[700,19,44.501]}])
        result=self.session.wait(picked['id'])
        self.assertEqual(result['status'],'complete',result)
        self.assertAlmostEqual(result['result']['value'],700)
        self.assertEqual(len(result['result']['picks']),2)
        with self.assertRaises(StudError):self.session.measure(key='stale',**{**args,'source_id':'wrong'})
        missing=self.session.measure(key='missing',build_id=finished['build_id'],targets=['beam:deleted','beam:right'])
        self.assertEqual(self.session.wait(missing['id'])['error']['category'],'unresolved_reference')

    def test_pdf_scale_immutable_export_retry_and_source_mismatch(self):
        request=self.begin();source=self.edit(request);finished=self.finish(request,source)
        args=dict(checkpoint=finished['checkpoint'],build_id=finished['build_id'],print_spec={'scale':5})
        job=self.session.plans(key='packet',**args);result=self.session.wait(job['id'])
        self.assertEqual(result['status'],'complete',result)
        from pypdf import PdfReader
        pdf=Path(result['result']['pdf']);original=pdf.read_bytes();reader=PdfReader(pdf)
        self.assertGreaterEqual(len(reader.pages),3)
        self.assertEqual(tuple(float(v) for v in reader.pages[0].mediabox),(0,0,612,792))
        sheet=result['result']['sheets'][0];start,end=sheet['dimensions'][0]['start'],sheet['dimensions'][0]['end']
        import math
        self.assertAlmostEqual(math.dist(start,end),700*72/25.4/5,places=6)
        self.assertIn('100 mm',reader.pages[0].extract_text())
        self.assertEqual(self.session.plans(key='packet',**args)['id'],job['id'])
        # Simulate stopping after export publication, before the job completion write.
        interrupted=self.session.job(job['id']);interrupted['status']='interrupted';self.session._save_job(interrupted)
        with patch.object(self.session.operations,'_plan_build',side_effect=AssertionError('Must reopen retained output')):
            self.session.plans(key='packet',**args)
            self.assertEqual(self.session.wait(job['id'])['status'],'complete')
        self.assertEqual(pdf.read_bytes(),original)
        wrong=self.session.plans(key='wrong-checkpoint',checkpoint=self.initial['checkpoint'],build_id=finished['build_id'])
        self.assertEqual(self.session.wait(wrong['id'])['error']['category'],'stale_target')
        self.assertEqual(pdf.read_bytes(),original)

    def test_show_requires_matching_version_and_actual_viewer_ack(self):
        request=self.begin();source=self.edit(request);finished=self.finish(request,source)
        job=self.session.show(key='focus',expected_build=finished['build_id'],objects=['beam'])
        self.assertEqual(job['status'],'waiting_viewer')
        self.assertEqual(job['objects'],['beam'])
        with self.assertRaises(StudError):self.session.show(key='badfocus',expected_build='old',objects=['beam'])
        result=self.session.acknowledge_show(key='ack',job_id=job['id'],build_id=finished['build_id'],camera={'position':[1,2,3],'quaternion':[0,0,0,1]})
        self.assertEqual(result['status'],'complete')

    def test_export_symlink_and_altered_manifest_are_rejected(self):
        from stud.contracts import write_json
        request=self.begin();source=self.edit(request);finished=self.finish(request,source)
        outside=self.root.parent/'outside';outside.mkdir()
        (self.root/'exports').symlink_to(outside,target_is_directory=True)
        job=self.session.plans(key='outside',checkpoint=finished['checkpoint'],build_id=finished['build_id'])
        self.assertEqual(self.session.wait(job['id'])['error']['category'],'invalid_path')
        self.assertFalse(list(outside.iterdir()))
        build=self.session.job(finished['build_id']);path=Path(build['artifact_path'])/'manifest.json';manifest=read_json(path)
        manifest['source_id']='altered';write_json(path,manifest)
        job=self.session.measure(key='altered',build_id=build['id'],source_id=source,targets=['beam:left','beam:right'])
        self.assertEqual(self.session.wait(job['id'])['error']['category'],'artifact_identity_mismatch')

    def test_late_viewer_acknowledgement_cannot_claim_the_new_model(self):
        request=self.begin();source=self.edit(request);first=self.finish(request,source)
        show=self.session.show(key='focus-old',expected_build=first['build_id'],objects=['beam'])
        request=self.begin('new');source=self.edit(request,__import__('test_session').DESIGN.replace('600','800'));self.finish(request,source)
        with self.assertRaises(StudError) as error:
            self.session.acknowledge_show(key='late',job_id=show['id'],build_id=first['build_id'],camera={'position':[1,2,3],'quaternion':[0,0,0,1]})
        self.assertEqual(error.exception.category,'stale_target')
