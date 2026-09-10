"""Copy and move entire projects without retargeting the original folder."""
import shutil
from pathlib import Path
from unittest.mock import patch

from test_session import ProjectFixture
from stud.client import Client
from stud.contracts import StudError, write_json
from stud.history import canonical_project_root
from stud.session import Session


class RelocationTests(ProjectFixture):
    def test_windows_paths_rebase_on_a_posix_host(self):
        from pathlib import PureWindowsPath
        from stud.contracts import read_json
        request = self.begin()
        source = self.edit(request)
        self.session.close()
        old = PureWindowsPath('C:/Users/Alice/Projects/Native test')
        record = read_json(self.session._request_path(request['id']))
        record['workspace'] = str(old / '.stud' / 'workspaces' / request['id'])
        write_json(self.session._request_path(request['id']), record)
        write_json(self.root / '.stud/location.json', {'root': str(old)})
        self.session = Session(self.root)
        self.assertEqual(self.session.source(request['id'])['source_id'], source)
        self.assertTrue(Path(self.session.snapshot()['request']['workspace']).is_relative_to(self.root.resolve()))

    def test_copy_reopens_draft_cached_geometry_history_and_export(self):
        request = self.begin()
        finished = self.finish(request, self.edit(request))
        packet = self.session.plans(key='packet', checkpoint=finished['checkpoint'])
        packet = self.session.wait(packet['id'])
        self.assertEqual(packet['status'], 'complete', packet)
        archived_pdf = Path(packet['result']['pdf']).read_bytes()
        historical = self.session.evaluate_checkpoint(finished['checkpoint'], key='history')
        self.assertEqual(self.session.wait(historical['id'])['status'], 'complete')
        draft = self.begin('draft')
        source = self.edit(draft)
        original_git = (Path(draft['workspace']) / '.git').read_bytes()
        original_job = self.session._job_path(finished['build_id']).read_bytes()
        copy = (self.root.parent / 'Moved project with café').resolve()
        shutil.copytree(self.root, copy)
        with Session(copy) as moved:
            snapshot = moved.snapshot()
            self.assertEqual(snapshot['project_id'], self.initial['project_id'])
            self.assertEqual(snapshot['project_root'], str(copy))
            self.assertEqual(moved.source(draft['id'])['source_id'], source)
            self.assertTrue(Path(snapshot['request']['workspace']).is_relative_to(copy))
            self.assertEqual(canonical_project_root(snapshot['request']['workspace']), copy)
            self.assertEqual(moved.history.head(), finished['checkpoint'])
            self.assertTrue(Path(moved.job(finished['build_id'])['artifact_path']).is_relative_to(copy))
            reopened = moved.plans(key='packet', checkpoint=finished['checkpoint'])
            self.assertEqual(Path(reopened['result']['pdf']).read_bytes(), archived_pdf)
            self.assertTrue(Path(reopened['result']['pdf']).is_relative_to(copy))
            self.assertEqual(moved.evaluate_checkpoint(finished['checkpoint'], key='history')['id'], historical['id'])
            modified = Path(snapshot['request']['workspace']) / 'design.py'
            modified.write_text(modified.read_text().replace('700', '750'))
            self.assertNotEqual(moved.source(draft['id'])['source_id'], source)
        self.assertEqual(self.session.source(draft['id'])['source_id'], source)
        self.assertEqual((Path(draft['workspace']) / '.git').read_bytes(), original_git)
        self.assertEqual(self.session._job_path(finished['build_id']).read_bytes(), original_job)

    def test_copied_endpoint_cannot_attach_to_original_coordinator(self):
        write_json(self.root / '.stud/endpoint.json', {'url': 'http://127.0.0.1:1'})
        with patch.object(Client, 'get', return_value={
                'project_id': self.initial['project_id'], 'project_root': str(self.root.parent / 'original')}):
            with self.assertRaises(StudError) as error:
                Client(self.root, start=False)
        self.assertEqual(error.exception.category, 'coordinator_unavailable')
