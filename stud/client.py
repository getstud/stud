"""CLI client for the same coordinator the viewer uses."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .contracts import StudError, identifier, read_json
from .source import manifest_at
from .history import canonical_project_root

ENGINE_ROOT = Path(__file__).resolve().parents[1]


class Client:
    def __init__(self, root, *, start=True):
        self.root = canonical_project_root(root)
        self.project_id = manifest_at(root)['project_id']
        self.url = None
        endpoint = read_json(self.root / '.stud/endpoint.json')
        if endpoint:
            self.url = endpoint['url']
            try:
                state = self.get('/api/v1/status')
                if state['project_id'] == self.project_id and state.get('project_root') == str(self.root):
                    return
            except (OSError, ValueError, StudError):
                pass
        if not start:
            raise StudError('coordinator_unavailable', 'Start the project viewer or retry with coordinator startup enabled.')
        log = self.root / '.stud/coordinator.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        flags = {'start_new_session': True} if os.name != 'nt' else {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS}
        resources = ENGINE_ROOT.parent
        launcher = resources / ('stud.exe' if os.name == 'nt' else '../MacOS/stud')
        command = [str(launcher), 'serve', str(self.root), '--port', '0', '--no-open'] if (resources / 'runtime-info.json').is_file() and launcher.is_file() else [sys.executable, '-B', '-E', '-s', '-m', 'stud.session_http', '--project', str(self.root)]
        with log.open('ab') as output:
            process = subprocess.Popen(command,
                cwd=ENGINE_ROOT, stdin=subprocess.DEVNULL, stdout=output, stderr=output, **flags)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            endpoint = read_json(self.root / '.stud/endpoint.json')
            if endpoint:
                self.url = endpoint['url']
                try:
                    state = self.get('/api/v1/status')
                    if state['project_id'] == self.project_id and state.get('project_root') == str(self.root):
                        return
                except (OSError, ValueError, StudError):
                    pass
            if process.poll() is not None:
                # Another CLI may have won the lock; give its endpoint a chance.
                if process.returncode != 0 and time.monotonic() > deadline - 10:
                    break
            time.sleep(0.05)
        raise StudError('coordinator_unavailable', f'The project coordinator did not become ready. See {log}.')

    def get(self, path):
        return self._request(path)

    def _request(self, path, body=None):
        request = Request(self.url + path, data=json.dumps(body).encode() if body is not None else None,
                          headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as response:
            try:
                error = json.load(response)['error']
                if isinstance(error, dict):
                    raise StudError(error['category'], error['message'], expected=error.get('expected'),
                                    current=error.get('current'), references=error.get('references'),
                                    retryable=error.get('retryable', False))
            except (ValueError, KeyError):
                pass
            raise StudError('transport_error', f'Project server returned HTTP {response.code}.')
        except (URLError, TimeoutError) as error:
            raise StudError('transport_error', f'Cannot contact the project coordinator: {error}', retryable=True) from error

    def command(self, operation, arguments=None, key=None):
        return self._request('/api/v1/command', dict(operation=operation, key=key or identifier('client'), arguments=arguments or {}))

    def wait(self, job_id, timeout=300):
        from .session import TERMINAL
        deadline = time.monotonic() + timeout
        while True:
            job = self.get('/api/v1/jobs/' + job_id)
            if job['status'] in TERMINAL:
                return job
            if time.monotonic() >= deadline:
                return job
            time.sleep(0.1)
