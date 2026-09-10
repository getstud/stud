"""Interface tests for the plan's version spine and real worker lifecycle."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stud.contracts import StudError, ProjectLock, read_json, write_json
from stud.history import History, initialize
from stud.session import Session
from stud.source import capture, runtime_fingerprint

DESIGN = '''import cadquery as cq
from stud.cad import Model
model = Model('Measured component')
model.assembly('frame')
model.part('beam', cq.Workplane('XY').box(600, 38, 89, centered=(False, False, False)),
           parent='frame', material='2x4', blank={'size': [600, 38, 89], 'cut_length':600,
               'operations':[{'kind':'square_cut','finished_length':600}]})
model.reference('beam', 'left', point=(0,0,0))
model.reference('beam', 'right', point=(600,0,0))
model.requirement('length', 'length', ['beam:left', 'beam:right'], threshold=600)
model.requirement('blank', 'stock_fit', ['beam'])
model.demand('lumber', product_id='2x4', specification={'material':'pine','section':[38,89]},
             object_ids=['beam'], unit='mm', purchase_unit='board',
             stock_lengths=[2400], cuts=[{'object_id':'beam','length':600}])
model.dimension('length', 'beam:left', 'beam:right', label='Length')
model.drawing('front', dimensions=['length'])
'''


class ProjectFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'project'
        self.root.mkdir()
        (self.root / 'design.py').write_text(DESIGN)
        self.initial = initialize(self.root)
        self.session = Session(self.root)
        self.addCleanup(lambda: self.session.close() if not self.session.closed else None)

    def begin(self, key='first'):
        return self.session.begin(expected_head=self.session.snapshot()['option']['head'], intent='Resize beam', key=key)

    def edit(self, request, source=DESIGN.replace('600', '700')):
        (Path(request['workspace']) / 'design.py').write_text(source)
        return self.session.source(request['id'])['source_id']

    def finish(self, request, source):
        job = self.session.finish(request['id'], expected_source=source, summary='Resize beam')
        result = self.session.wait(job['id'], timeout=60)
        self.assertEqual(result['status'], 'complete', result)
        return result


class SourceAndHistoryTests(ProjectFixture):
    def test_workspaces_preserve_committed_source_bytes_with_git_line_endings(self):
        history=self.session.history
        history.git('config','core.autocrlf','true')
        option=self.session.snapshot()['option']
        exact={
            'design.py':DESIGN.encode('utf-8'),
            'helper.py':b'VALUE = 7\r\n',
            '.gitattributes':b'*.py text eol=crlf\n*.json text eol=crlf\n',
        }
        head=history.commit(option['head'],exact,[],'Commit exact source bytes',history.author(),1700000000)
        history.advance(option['ref'],head,option['head'])
        request=self.begin()
        workspace=Path(request['workspace'])
        for name in ('design.py','helper.py','stud.json'):
            self.assertEqual((workspace/name).read_bytes(),history.read_file(head,name),name)
        result=self.finish(request,self.session.source(request['id'])['source_id'])
        self.assertTrue(result['no_change'],result)
        self.assertEqual(result['checkpoint'],head)

    def test_finish_retains_complete_geometry_when_native_checks_crash(self):
        request=self.begin()
        source=self.edit(request,DESIGN+"\nimport os, stud.checks\nstud.checks.measure_requirement=lambda *args: os._exit(7)\n")
        finished=self.finish(request,source)
        report=self.session.history.checkpoint_report(finished['checkpoint'])
        self.assertEqual(report['outcome'],'generation_failed')
        self.assertEqual(report['completion']['geometry'],'complete')
        self.assertEqual(report['completion']['checks'],'interrupted')
        self.assertEqual(report['evaluated_manifest']['objects'][0]['id'],'beam')
        self.assertIsNotNone(report['preview'])

    def test_identity_survives_reload_and_source_excludes_prices(self):
        first = capture(self.root, self.root / '.stud/sources')
        inputs = read_json(self.root / 'estimating.json')
        inputs['overrides']['2x4'] = '99'
        write_json(self.root / 'estimating.json', inputs)
        second = capture(self.root, self.root / '.stud/sources')
        self.assertEqual(first['source_id'], second['source_id'])
        self.session.close()
        self.session = Session(self.root)
        self.assertEqual(self.session.snapshot()['project_id'], self.initial['project_id'])

    def test_request_is_isolated_idempotent_and_stale_heads_fail(self):
        request = self.begin()
        self.assertEqual(self.begin()['id'], request['id'])
        with self.assertRaises(StudError) as error:
            self.session.begin(expected_head='0'*40, intent='Other', key='other')
        self.assertEqual(error.exception.category, 'changed_head')
        self.edit(request)
        self.assertEqual((self.root / 'design.py').read_text(), DESIGN)
        self.assertEqual(History(Path(request['workspace'])).head(), self.initial['checkpoint'])
        self.assertIsNone(self.session.snapshot()['displayed_build'])

    def test_one_coordinator_and_cancellation_retains_draft(self):
        with self.assertRaises(StudError) as error:
            Session(self.root)
        self.assertEqual(error.exception.category, 'coordinator_busy')
        request = self.begin()
        with self.assertRaises(StudError) as workspace_error:
            Session(request['workspace'])
        self.assertEqual(workspace_error.exception.category, 'coordinator_busy')
        self.edit(request)
        self.session.cancel(request['id'])
        next_request = self.begin('next')
        (Path(request['workspace'])/'design.py').write_text('late old write')
        self.assertEqual((Path(next_request['workspace'])/'design.py').read_text(), DESIGN)

    def test_recovery_repairs_begin_and_cancel_pointer_windows(self):
        request = self.begin()
        self.session.state['active_request'] = None
        self.session._save_state()
        self.session.close()
        self.session = Session(self.root)
        self.assertEqual(self.session.snapshot()['active_request'], request['id'])
        self.assertEqual(self.begin()['id'], request['id'])
        request['status'] = 'canceled'
        self.session._save_request(request)
        self.session.close()
        self.session = Session(self.root)
        self.assertIsNone(self.session.snapshot()['active_request'])
        self.begin('new-after-cancel')

    def test_capture_rejects_path_escape_and_preserves_exact_bytes(self):
        request = self.begin()
        workspace = Path(request['workspace'])
        (workspace / 'helper.py').write_bytes(b'VALUE = 7\r\n')
        source = self.session.source(request['id'])
        self.assertEqual((Path(source['path']) / 'files/helper.py').read_bytes(), b'VALUE = 7\r\n')
        manifest = read_json(workspace/'stud.json')
        manifest['source_files'].append('../*.py')
        write_json(workspace/'stud.json', manifest)
        with self.assertRaises(StudError):
            self.session.source(request['id'])

    def test_snapshot_replay_reset_has_a_consistent_boundary(self):
        before = self.session.snapshot()['sequence']
        request = self.begin()
        replay = self.session.events_after(before)
        self.assertFalse(replay['reset'])
        self.assertEqual(replay['events'][0]['request_id'], request['id'])
        with self.session.mutex:
            for index in range(260):
                self.session._emit('progress', index=index)
        reset = self.session.events_after(before)
        self.assertTrue(reset['reset'])
        after = reset['snapshot']['sequence']
        self.assertEqual(self.session.events_after(after)['events'], [])


@unittest.skipUnless(runtime_fingerprint()['packages']['cadquery'], 'Requires the pinned CadQuery runtime')
class EvaluationAndFinishTests(ProjectFixture):
    def test_nested_unrelated_python_and_ignored_collisions_are_preserved(self):
        (self.root/'tools').mkdir()
        (self.root/'tools/personal.py').write_text('unrelated = True\n')
        with (self.root/'.gitignore').open('a') as stream:
            stream.write('helper.py\n')
        self.session.history.git('add', 'tools/personal.py', '.gitignore')
        self.session.history.git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','User scripts')
        request = self.begin()
        (self.root/'helper.py').write_text('private ignored file')
        (Path(request['workspace'])/'helper.py').write_text('MODEL_INPUT = 1\n')
        source = self.edit(request)
        result = self.finish(request, source)
        self.assertEqual(self.session.history.read_file(result['checkpoint'],'tools/personal.py'), b'unrelated = True\n')
        self.assertEqual((self.root/'helper.py').read_text(), 'private ignored file')
        self.assertEqual(self.session._request(request['id'])['checkout_state'], 'local_edits_preserved')

    def test_real_builds_have_distinct_ids_and_independent_geometry_evidence(self):
        request = self.begin()
        source = self.edit(request)
        first = self.session.evaluate(request['id'], source, key='evaluate1')
        self.assertEqual(self.session.evaluate(request['id'], source, key='evaluate1')['id'], first['id'])
        result = self.session.wait(first['id'])
        self.assertEqual(result['status'], 'complete', result)
        manifest = read_json(result['manifest'])
        self.assertEqual(manifest['source_id'], source)
        self.assertAlmostEqual(manifest['objects'][0]['volume'], 700 * 38 * 89, places=6)
        self.assertTrue(manifest['checks']['all_passed'], manifest['checks'])
        mesh = Path(result['artifact_path']) / next(iter(manifest['assets'].values()))['mesh']
        self.assertEqual(mesh.read_bytes()[:8], b'STUDMESH')
        second = self.session.evaluate(request['id'], source)
        self.assertNotEqual(second['id'], first['id'])
        self.assertEqual(second['source_id'], first['source_id'])
        self.session.wait(second['id'])

    def test_finish_once_excludes_unrelated_edits_and_updates_checkout(self):
        request = self.begin()
        source = self.edit(request)
        (self.root / 'private.txt').write_text('Do not checkpoint me')
        (Path(request['workspace']) / 'notes.txt').write_text('Unrelated agent scratch')
        result = self.finish(request, source)
        again = self.session.finish(request['id'], expected_source=source, summary='Retry')
        self.assertEqual(result['id'], again['id'])
        self.assertEqual(result['checkpoint'], again['checkpoint'])
        history = self.session.history
        self.assertEqual(history.git('rev-list', '--count', result['checkpoint']).decode().strip(), '2')
        self.assertIsNone(history.read_file(result['checkpoint'], 'private.txt'))
        self.assertIsNone(history.read_file(result['checkpoint'], 'notes.txt'))
        self.assertEqual((self.root/'private.txt').read_text(), 'Do not checkpoint me')
        self.assertIn('700', (self.root/'design.py').read_text())
        report = json.loads(history.read_file(result['checkpoint'], f'checkpoints/{request["id"]}.json'))
        self.assertEqual(report['source_id'], source)
        self.assertEqual(report['original_estimate']['rows'][0]['quantity'], '1')
        self.assertIsNone(report['original_estimate']['total'])
        self.assertNotIn('checkpoint', report)

    def test_unrelated_tracked_changes_are_never_discarded_or_committed(self):
        (self.root/'personal.md').write_text('original')
        self.session.history.git('add', 'personal.md')
        self.session.history.git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','User file')
        request = self.begin()
        (self.root/'personal.md').write_text('user working edit')
        source = self.edit(request)
        result = self.finish(request, source)
        self.assertEqual((self.root/'personal.md').read_text(), 'user working edit')
        self.assertEqual(self.session.history.read_file(result['checkpoint'],'personal.md'), b'original')
        self.assertEqual(self.session._request(request['id'])['checkout_state'], 'local_edits_preserved')

    def test_no_change_does_not_create_an_empty_checkpoint(self):
        request = self.begin()
        source = self.session.source(request['id'])['source_id']
        result = self.finish(request, source)
        self.assertTrue(result['no_change'])
        self.assertEqual(result['checkpoint'], self.initial['checkpoint'])

    def test_failed_checks_preserve_complete_geometry_and_failed_generation_preserves_partial(self):
        request = self.begin()
        source = self.edit(request, DESIGN.replace('threshold=600', 'threshold=601'))
        job = self.session.evaluate(request['id'], source)
        result = self.session.wait(job['id'])
        self.assertEqual(result['status'], 'complete', result)
        manifest = read_json(result['manifest'])
        self.assertEqual(manifest['completion']['geometry'], 'complete')
        self.assertFalse(manifest['checks']['all_passed'])
        self.assertIsNone(self.session.snapshot()['last_valid_build'])
        source = self.edit(request, DESIGN + '\nraise RuntimeError("failure after publication")\n')
        job = self.session.evaluate(request['id'], source)
        result = self.session.wait(job['id'])
        self.assertEqual(result['status'], 'generation_failed')
        manifest = read_json(result['manifest'])
        self.assertEqual(manifest['completion']['geometry'], 'partial')
        self.assertEqual(len(manifest['objects']), 1)
        finished = self.finish(request, source)
        report = json.loads(self.session.history.read_file(finished['checkpoint'],f'checkpoints/{request["id"]}.json'))
        self.assertEqual(report['original_estimate']['status'], 'unavailable')

    def test_crash_between_commit_and_ref_publication_recovers_same_commit(self):
        request = self.begin()
        source = self.edit(request)
        with patch.object(self.session.history, 'advance', side_effect=StudError('simulated_crash', 'Crash before publication')):
            job = self.session.finish(request['id'], expected_source=source, summary='Resize beam')
            self.assertEqual(self.session.wait(job['id'])['status'], 'failed')
        recorded = self.session._request(request['id'])['finalization']['commit']
        self.session.close()
        self.session = Session(self.root)
        recovered = self.session.job(job['id'])
        self.assertEqual(recovered['status'], 'complete')
        self.assertEqual(recovered['checkpoint'], recorded)
        self.assertEqual(self.session.snapshot()['option']['head'], recorded)

    def test_recovery_finishes_local_cleanup_after_commit_was_saved(self):
        request = self.begin()
        source = self.edit(request)
        result = self.finish(request, source)
        saved = self.session._request(request['id'])
        saved.pop('cleanup_complete')
        self.session._save_request(saved)
        self.session.state['active_request'] = request['id']
        self.session._save_state()
        self.session.close()
        self.session = Session(self.root)
        self.assertIsNone(self.session.snapshot()['active_request'])
        self.assertEqual(self.session.job(result['id'])['checkpoint'], result['checkpoint'])
        self.begin('after-recovery')

    def test_finish_recovery_reconstructs_missing_job_and_runs_frozen_source(self):
        request = self.begin()
        source = self.edit(request)
        original_submit = self.session.executor.submit
        with patch.object(self.session.executor, 'submit'):
            job = self.session.finish(request['id'], expected_source=source, summary='Frozen source')
        self.session._job_path(job['id']).unlink()
        (Path(request['workspace'])/'design.py').write_text('late invalid edits')
        self.session.close()
        self.session = Session(self.root)
        recovered = self.session.wait(job['id'], timeout=60)
        self.assertEqual(recovered['status'], 'complete', recovered)
        self.assertIn(b'700', self.session.history.read_file(recovered['checkpoint'], 'design.py'))

    @unittest.skipIf(os.name == 'nt', 'POSIX signal behavior')
    def test_cancel_kills_a_worker_that_ignores_sigterm(self):
        import time
        request = self.begin()
        source = self.edit(request, DESIGN + '\nimport signal, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\nprint("ready", flush=True)\nwhile True: time.sleep(.1)\n')
        job = self.session.evaluate(request['id'], source)
        deadline = time.monotonic() + 15
        log = Path(job['artifact_path']) / 'stderr.log'
        while time.monotonic() < deadline and (not log.exists() or 'ready' not in log.read_text()):
            time.sleep(.05)
        self.assertIn('ready', log.read_text())
        process = self.session.processes[job['id']]
        started = time.monotonic()
        self.session.cancel(request['id'])
        result = self.session.wait(job['id'], timeout=6)
        self.assertEqual(result['status'], 'canceled')
        self.assertIsNotNone(process.poll())
        self.assertLess(time.monotonic()-started, 5)


if __name__ == '__main__':
    unittest.main()
