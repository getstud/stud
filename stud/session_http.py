"""Versioned local HTTP/SSE adapter for the shared project coordinator."""
import json
import mimetypes
import os
from pathlib import Path
import secrets
import socket
import sys
from urllib.parse import parse_qs, unquote, urlsplit

from .contracts import StudError, confined, digest, read_json, write_json
from .session import ENGINE_ROOT, Session


class ProjectAPI:
    def __init__(self, session):
        self.session = session

    def command(self, payload):
        operation = payload.get('operation')
        key = payload.get('key')
        if not isinstance(key, str) or not key:
            raise StudError('invalid_request', 'Each mutation requires an idempotency key.')
        arguments = payload.get('arguments', {})
        if not isinstance(arguments, dict):
            raise StudError('invalid_request', 'Command arguments must be an object.')
        session = self.session
        if operation == 'begin':
            return session.begin(key=key, **arguments)
        if operation == 'evaluate':
            return session.evaluate(key=key, **arguments)
        if operation == 'evaluate_checkpoint':
            return session.evaluate_checkpoint(key=key, **arguments)
        if operation == 'finish':
            return session.finish(**arguments)
        if operation == 'cancel':
            return session.cancel(**arguments)
        if operation == 'source':
            return session.source(**arguments)
        if operation == 'shutdown':
            import threading
            if not getattr(session, 'shutdown_server', None):
                raise StudError('unsupported_operation', 'This session is not running an HTTP coordinator.')
            threading.Timer(.1, session.shutdown_server).start()
            return dict(status='stopping', project_id=session.manifest['project_id'],
                        message='Draft workspaces and saved results are retained.')
        # Further operations share this adapter and their same Session methods.
        methods = {'create_option': 'create_option', 'activate_option': 'activate_option', 'rename_option':'rename_option',
                   'restore': 'restore', 'compare': 'compare_versions', 'save_prompt': 'save_prompt',
                   'update_prompt': 'update_prompt', 'save_prices': 'save_prices',
                   'plans': 'plans', 'measure': 'measure', 'show': 'show', 'acknowledge_show':'acknowledge_show',
                   'inspect_checkpoint':'inspect_checkpoint','return_live':'return_live'}
        method = methods.get(operation)
        if method and hasattr(session, method):
            return getattr(session, method)(key=key, **arguments)
        raise StudError('unsupported_operation', f'Unknown project operation: {operation}')


def make_handler(session):
    # Reuse the existing appearance, static viewer, and update routes. All model
    # and project mutations are intercepted here, so legacy rebuild-on-read code
    # cannot execute for a CadQuery project.
    from serve import Handler
    api = ProjectAPI(session)

    class SessionHandler(Handler):
        def do_GET(self):
            if self.headers.get('Host','') not in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}:
                return self.send(b'Forbidden','text/plain',status=403)
            parsed = urlsplit(self.path)
            path = parsed.path
            try:
                if path == '/api/v1/status':
                    return self.json(session.snapshot())
                if path == '/api/v1/events':
                    return self.events(parsed)
                if path == '/api/v1/options':
                    return self.json(session.versions.options())
                if path == '/api/v1/exports':
                    return self.json([job for file in (session.local/'jobs').glob('*.json')
                        if (job:=read_json(file)).get('kind')=='plans'])
                if path.startswith('/api/v1/exports/'):
                    pieces=unquote(path.removeprefix('/api/v1/exports/')).split('/',1)
                    if len(pieces)!=2:raise StudError('invalid_path','An exported file name is required.')
                    job=session.job(pieces[0]);result=job.get('result',{});name=pieces[1]
                    if job.get('kind')!='plans' or job['status']!='complete' or name not in {*result.get('files',{}),'manifest.json'}:
                        raise StudError('unavailable_artifact','The requested packet file is unavailable.')
                    file=confined(session.root,f'exports/{job["id"]}/{name}')
                    if not file.is_file() or (name!='manifest.json' and digest(file.read_bytes())!=result['files'][name]):
                        raise StudError('unavailable_artifact','The saved packet is missing or corrupt.')
                    return self.send(file.read_bytes(),mimetypes.guess_type(str(file))[0] or 'application/octet-stream',name)
                if path == '/api/v1/checkpoints':
                    return self.json(session.versions.checkpoints())
                if path == '/api/v1/prompts':
                    from .display import displayed_prompts
                    return self.json(displayed_prompts(session))
                if path.startswith('/api/v1/jobs/'):
                    return self.json(session.job(unquote(path.removeprefix('/api/v1/jobs/'))))
                if path.startswith('/api/v1/builds/'):
                    pieces = unquote(path.removeprefix('/api/v1/builds/')).split('/', 1)
                    if len(pieces) != 2:
                        raise StudError('invalid_path', 'Build artifact path is missing.')
                    job = session.job(pieces[0])
                    relative = pieces[1]
                    base = Path(job['artifact_path'])
                    file = confined(base, relative)
                    if relative.startswith('execution/') or not file.is_file():
                        raise StudError('unavailable_artifact', 'Requested build artifact is unavailable.')
                    kind = mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
                    return self.send(file.read_bytes(), kind)
                if path == '/api/model':
                    from .display import model_for_viewer
                    return self.json(model_for_viewer(session))
                if path == '/api/validation':
                    from .display import model_for_viewer
                    model = model_for_viewer(session)
                    return self.json(dict(revision=model['revision'], **model['validation_results']))
                if path == '/api/pricing':
                    from .display import prices_for_viewer
                    return self.json(prices_for_viewer(session))
                if path in ('/api/parts.csv', '/api/materials.csv', '/api/costs.csv'):
                    from .display import csv_for_viewer
                    return self.send(csv_for_viewer(session, path).encode(), 'text/csv', path.rsplit('/', 1)[-1])
                if path == '/api/comments':
                    from .display import prompts_for_viewer
                    return self.json(dict(comments=prompts_for_viewer(session)))
                if path.startswith('/api/comment-images/'):
                    image_id = unquote(path.removeprefix('/api/comment-images/'))
                    body = session._record_files().get(f'records/captures/{image_id}.png')
                    if body is None:
                        raise StudError('unavailable_artifact', 'Saved screenshot is unavailable.')
                    return self.send(body, 'image/png')
                if path == '/api/update':
                    return super().do_GET()
                if path.startswith('/api/'):
                    raise StudError('unsupported_operation', 'Unknown API route.')
                if path in ('/cad-scene.js', '/project-events.js'):
                    file = ENGINE_ROOT / 'web' / path.lstrip('/')
                    return self.send(file.read_bytes(), 'text/javascript')
                return super().do_GET()
            except (BrokenPipeError, ConnectionResetError):
                return
            except StudError as error:
                return self.problem(error)
            except Exception as error:
                return self.problem(StudError('internal_error', str(error)))

        def json(self, value, status=200):
            return self.send(json.dumps(value, allow_nan=False).encode(), 'application/json', status=status)

        def problem(self, error):
            conflict = {'changed_head', 'stale_source', 'stale_request', 'stale_target', 'busy_request',
                        'idempotency_conflict', 'stale_revision', 'finalizing'}
            missing = {'unknown_job', 'unknown_request', 'unknown_checkpoint', 'unavailable_artifact'}
            status = 409 if error.category in conflict else 404 if error.category in missing else 422
            if error.category == 'internal_error':
                status = 500
            return self.json(dict(schema_version=1, project_id=session.manifest['project_id'], error=error.as_dict()), status)

        def events(self, parsed):
            after = self.headers.get('Last-Event-ID') or parse_qs(parsed.query).get('after', ['0'])[0]
            try:
                sequence = int(after)
            except ValueError:
                raise StudError('invalid_sequence', 'Expected an integer stream sequence.')
            if sequence < 0:
                raise StudError('invalid_sequence', 'Stream sequences cannot be negative.')
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.connection.settimeout(15)
            try:
                while not session.closed:
                    batch = session.events_after(sequence, timeout=10)
                    if batch['reset']:
                        snapshot = batch['snapshot']
                        sequence = snapshot['sequence']
                        self.wfile.write(f'id: {sequence}\nevent: reset\ndata: {json.dumps(snapshot)}\n\n'.encode())
                    elif batch['events']:
                        for event in batch['events']:
                            sequence = event['sequence']
                            self.wfile.write(f'id: {sequence}\nevent: project\ndata: {json.dumps(event)}\n\n'.encode())
                    else:
                        self.wfile.write(b': keepalive\n\n')
                    self.wfile.flush()
            except (OSError, TimeoutError):
                pass

        def do_POST(self):
            allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            host = self.headers.get('Host', '')
            if host not in allowed or self.headers.get('Origin') not in (None, f'http://{host}'):
                return self.send(b'Forbidden', 'text/plain', status=403)
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.send(b'Expected JSON', 'text/plain', status=415)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 8 * 1024 * 1024:
                    raise StudError('invalid_request', 'Invalid request size.')
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise StudError('invalid_request', 'Expected a JSON object.')
                path = urlsplit(self.path).path
                if path == '/api/v1/command':
                    return self.json(api.command(payload))
                if path == '/api/comments':
                    from .display import save_viewer_prompt
                    return self.json(save_viewer_prompt(session, payload))
                if path == '/api/pricing':
                    from .display import save_viewer_prices
                    return self.json(save_viewer_prices(session, payload))
                raise StudError('unsupported_operation', 'Unknown mutation route.')
            except StudError as error:
                return self.problem(error)
            except (ValueError, TypeError, KeyError) as error:
                return self.problem(StudError('invalid_request', str(error)))
            except Exception as error:
                return self.problem(StudError('internal_error', str(error)))

    return SessionHandler


def serve_project(root, port=0, *, open_browser=False, ready=None):
    from serve import ViewerServer
    import webbrowser
    try:
        session = Session(root)
    except StudError as error:
        if error.category != 'coordinator_busy':
            raise
        from .client import Client
        import time
        client = Client(root, start=False)
        print(f"stud · {client.root.name}: {client.url}", flush=True)
        if ready:
            ready(dict(url=client.url, project_id=client.project_id))
        if open_browser:
            webbrowser.open(client.url)
        try:
            while True:
                time.sleep(1)
                client.get('/api/v1/status')
        except (KeyboardInterrupt, StudError):
            return
    try:
        server = ViewerServer(('127.0.0.1', port), make_handler(session))
        session.shutdown_server = server.shutdown
        endpoint = dict(schema_version=1, url=f'http://127.0.0.1:{server.server_port}',
                        project_id=session.manifest['project_id'], project_root=str(session.root), pid=os.getpid())
        write_json(session.local / 'endpoint.json', endpoint)
        print(f"stud · {session.manifest['name']}: {endpoint['url']}", flush=True)
        if ready:
            ready(endpoint)
        if open_browser:
            webbrowser.open(endpoint['url'])
        if not session.state['displayed_build'] and not session.state['active_request']:
            session.evaluate_checkpoint(display=True, key=f'initial:{secrets.token_hex(12)}')
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        session.close()
        endpoint_path = session.local / 'endpoint.json'
        if read_json(endpoint_path, {}).get('pid') == os.getpid():
            endpoint_path.unlink(missing_ok=True)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    serve_project(args.project, args.port)
