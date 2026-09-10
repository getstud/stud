"""The single project coordinator: requests, jobs, display versions and recovery.

Geometry executes in disposable child processes. Git mutations and state changes
are short, serialized operations; reads never trigger a geometry build.
"""
from concurrent.futures import ThreadPoolExecutor
from collections import deque
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback

from .contracts import (ProjectLock, StudError, atomic_write, confined, digest, encoded,
                        identifier, read_json, write_json)
from .history import History, canonical_project_root
from .source import capture, manifest_at, matches_source, runtime_fingerprint, verify_snapshot

ENGINE_ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {'complete', 'generation_failed', 'canceled', 'superseded', 'interrupted', 'failed'}


class Session:
    def __init__(self, root):
        self.root = canonical_project_root(root)
        self.manifest = manifest_at(self.root)
        # An agent often invokes the CLI from its detached request worktree.
        # That workspace shares the owner's Git repository and must not become
        # an independent coordinator for the same project identity.
        self.local = confined(self.root,'.stud')
        self.process_lock = ProjectLock(self.local / 'coordinator.lock')
        self.mutex = threading.RLock()
        self.condition = threading.Condition(self.mutex)
        self.history = History(self.root)
        from .relocation import repair_local_paths
        repair_local_paths(self.root, self.history)
        self.events = deque(maxlen=256)
        self.processes = {}
        self.futures = {}
        self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='stud-job')
        self.workers = ThreadPoolExecutor(max_workers=1, thread_name_prefix='stud-geometry')
        self.history_workers = ThreadPoolExecutor(max_workers=1, thread_name_prefix='stud-history-geometry')
        self.closed = False
        self.watcher = None
        self.state = read_json(self.local / 'state.json')
        if not self.state:
            options = self.history.options()
            if not options:
                self.process_lock.close()
                self.executor.shutdown(wait=False)
                self.workers.shutdown(wait=False)
                self.history_workers.shutdown(wait=False)
                raise StudError('migration_required', 'Project history has no retained design options.')
            self.state = dict(schema_version=1, project_id=self.manifest['project_id'],
                              active_option=options[0]['id'], active_request=None, latest_build=None,
                              displayed_build=None, last_valid_build=None, sequence=0)
        from .records import Records
        from .versions import Versions
        from .operations import Operations
        self.records = Records(self)
        self.versions = Versions(self)
        self.operations = Operations(self)
        self._recover()
        self.versions.recover()
        with self.mutex:
            self.records.schedule_flush()

    def _save_state(self):
        write_json(self.local / 'state.json', self.state)

    def _request_path(self, request_id):
        return confined(self.local, f'requests/{request_id}.json')

    def _request(self, request_id):
        request = read_json(self._request_path(request_id))
        if not request:
            raise StudError('unknown_request', f'Unknown request: {request_id}')
        return request

    def _save_request(self, request):
        write_json(self._request_path(request['id']), request)

    def _job_path(self, job_id):
        return confined(self.local, f'jobs/{job_id}.json')

    def _save_job(self, job):
        write_json(self._job_path(job['id']), job)

    def _emit(self, kind, **payload):
        # Called with the mutation lock held. A snapshot has the exact same
        # sequence boundary as its state; reconnection never skips an update.
        self.state['sequence'] += 1
        event = dict(schema_version=1, project_id=self.manifest['project_id'],
                     sequence=self.state['sequence'], type=kind, **payload)
        self._save_state()
        self.events.append(event)
        self.condition.notify_all()
        return event

    def _recover(self):
        """No PID inference: jobs in this new lock owner's old session stopped."""
        with self.mutex:
            requests = [read_json(file) for file in (self.local / 'requests').glob('*.json')]
            live = [request for request in requests if request['status'] in ('editing', 'finishing')]
            active = next((request for request in live if request['id'] == self.state['active_request']), None)
            if not active:
                self.state['active_request'] = None
                if len(live) == 1:
                    self.state.update(active_request=live[0]['id'], active_option=live[0]['option_id'])
                elif len(live) > 1:
                    self.state['recovery_error'] = dict(category='draft_conflict',
                        message='Multiple unfinished request records require explicit recovery.',
                        requests=[request['id'] for request in live])
            for file in (self.local / 'jobs').glob('*.json'):
                job = read_json(file)
                if job['status'] not in TERMINAL:
                    job.update(status='interrupted', diagnostics='Coordinator stopped before this job completed.')
                    self._save_job(job)
            for request in requests:
                if request.get('finish_job') and not self._job_path(request['finish_job']).exists():
                    self._save_job(dict(schema_version=1, id=request['finish_job'], kind='finish',
                        project_id=self.manifest['project_id'], request_id=request['id'], status='interrupted',
                        source_id=request['final_source'], build_id=request['latest_build']))
                needs_cleanup = request['status'] == 'complete' and not request.get('cleanup_complete')
                if request.get('finalization') and (request['status'] != 'complete' or needs_cleanup):
                    try:
                        self._publish_finalization(request)
                    except StudError as error:
                        request['recovery_error'] = error.as_dict()
                        self._save_request(request)
                elif request['status'] == 'finishing' and not request.get('finalization'):
                    self.futures[request['finish_job']] = self.executor.submit(self._finish_job, request['id'])
            self._save_state()

    def close(self):
        if self.watcher:self.watcher.close()
        with self.mutex:
            self.closed = True
            for process in list(self.processes.values()):
                if process.poll() is None:
                    self._terminate_worker(process)
            self.condition.notify_all()
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.workers.shutdown(wait=True, cancel_futures=True)
        self.history_workers.shutdown(wait=True,cancel_futures=True)
        self.operations.executor.shutdown(wait=True,cancel_futures=True)
        self.process_lock.close()

    def watch(self):
        from .watching import SourceWatcher
        with self.mutex:
            if not self.watcher:self.watcher=SourceWatcher(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def snapshot(self):
        with self.mutex:
            active = self.state['active_request']
            return dict(schema_version=1, **{k: v for k, v in self.state.items() if k != 'schema_version'},
                        project_root=str(self.root),
                        option=next(option for option in self.versions.options() if option['id']==self.state['active_option']),
                        request=self._request(active) if active else None,
                        latest_job=self.job(self.state['latest_build']) if self.state['latest_build'] else None,
                        pending_records=self.pending_records(), runtime=runtime_fingerprint())

    def events_after(self, sequence, timeout=0):
        with self.condition:
            if self.state['sequence'] <= sequence and timeout:
                self.condition.wait_for(lambda: self.closed or self.state['sequence'] > sequence, timeout)
            if sequence > self.state['sequence'] or (sequence < self.state['sequence'] and
                    (not self.events or sequence < self.events[0]['sequence'] - 1)):
                return dict(reset=True, snapshot=self.snapshot(), events=[])
            return dict(reset=False, sequence=self.state['sequence'],
                        events=[e for e in self.events if e['sequence'] > sequence])

    def begin(self, *, option_id=None, expected_head, intent, key, seed_checkpoint=None, change_kind='design'):
        if not key or not isinstance(intent, str) or not intent.strip():
            raise StudError('invalid_request', 'A client key and user intent are required.')
        with self.mutex:
            option_id = option_id or self.state['active_option']
            for file in (self.local / 'requests').glob('*.json'):
                existing = read_json(file)
                if existing['key'] == key:
                    if (existing['option_id'], existing['expected_head'], existing['intent'], existing.get('seed_checkpoint'),existing.get('change_kind','design')) != (option_id, expected_head, intent, seed_checkpoint,change_kind):
                        raise StudError('idempotency_conflict', 'That client key was used for a different request.')
                    return existing
            option = self.history.option(option_id)
            if option['head'] != expected_head:
                raise StudError('changed_head', 'Begin against the current option head.',
                                expected=expected_head, current=option['head'])
            if self.state['active_request']:
                raise StudError('busy_request', 'Finish or cancel the active editing request first.',
                                current=self.state['active_request'])
            if option_id!=self.state['active_option'] and self.pending_records():
                raise StudError('pending_records','Checkpoint pending records before starting work on another option.',retryable=True)
            request_id = identifier('request')
            workspace = self.history.workspace(request_id, expected_head)
            if seed_checkpoint:
                seeded_names=self._historical_source_names(seed_checkpoint)
                for name in set(self._historical_source_names(expected_head))-set(seeded_names):
                    confined(workspace,name).unlink(missing_ok=True)
                for name in seeded_names+['estimating.json']:
                    body=self.history.read_file(seed_checkpoint,name)
                    if body is not None:atomic_write(confined(workspace,name),body)
                inputs=read_json(workspace/'estimating.json',{})
                current_inputs=self.records.inputs(expected_head,include_pending=True,option_id=option_id)
                inputs['quote_selection']=current_inputs.get('quote_selection',{})
                write_json(workspace/'estimating.json',inputs)
            request = dict(schema_version=1, project_id=self.manifest['project_id'], id=request_id,
                           key=key, option_id=option_id, expected_head=expected_head, intent=intent,
                           workspace=str(workspace), status='editing', latest_build=None,
                           created_at=time.time(), finalization=None, seed_checkpoint=seed_checkpoint,change_kind=change_kind)
            self._save_request(request)
            self.state.update(active_request=request_id, active_option=option_id)
            self._emit('request_started', request_id=request_id, option_id=option_id)
            return request

    def _editable(self, request_id):
        request = self._request(request_id)
        if request['status'] != 'editing' or self.state['active_request'] != request_id:
            raise StudError('stale_request', 'This request is no longer accepting source edits.',
                            expected=request_id, current=self.state['active_request'])
        return request

    def source(self, request_id, expected=None):
        with self.mutex:
            request = self._request(request_id)
            workspace = request['workspace']
        return capture(workspace, self.local / 'sources', expected)

    def evaluate(self, request_id, expected_source=None, key=None,full_checks=False):
        with self.mutex:
            request = self._editable(request_id)
            if key:
                for file in (self.local / 'jobs').glob('*.json'):
                    job = read_json(file)
                    if job.get('key') == key and job.get('request_id') == request_id and job['kind'] == 'evaluate':
                        if bool(job['settings'].get('full_checks'))!=bool(full_checks):
                            raise StudError('idempotency_conflict','Evaluation key has different check settings.')
                        if expected_source and expected_source != job['source_id']:
                            raise StudError('idempotency_conflict', 'Evaluation key has a different source.')
                        return job
        source = capture(request['workspace'], self.local / 'sources', expected_source)
        with self.mutex:
            request = self._editable(request_id)
            if key:
                for file in (self.local / 'jobs').glob('*.json'):
                    existing = read_json(file)
                    if existing.get('key') == key and existing.get('request_id') == request_id and existing['kind'] == 'evaluate':
                        if bool(existing['settings'].get('full_checks'))!=bool(full_checks):
                            raise StudError('idempotency_conflict','Evaluation key has different check settings.')
                        if expected_source and expected_source != existing['source_id']:
                            raise StudError('idempotency_conflict', 'Evaluation key has a different source.')
                        return existing
            return self._schedule_build(request, source, key,full_checks=full_checks)

    def _schedule_build(self, request, source, key=None,full_checks=False):
        previous = request.get('latest_build')
        if previous:
            old = self.job(previous)
            if old['status'] not in TERMINAL:
                self._stop_build(old, 'superseded')
        build_id = identifier('build')
        directory = self.local / 'builds' / build_id
        directory.mkdir(parents=True)
        job = dict(schema_version=1, id=build_id, build_id=build_id, kind='evaluate', key=key,
                   project_id=self.manifest['project_id'], request_id=request['id'],
                   option_id=request['option_id'], source_id=source['source_id'],
                   source_path=source['path'], runtime=runtime_fingerprint(), status='queued',
                   created_at=time.time(), artifact_path=str(directory),
                   settings={**manifest_at(Path(source['path']) / 'files')['evaluation'],'full_checks':bool(full_checks)})
        self._save_job(job)
        request['latest_build'] = build_id
        self._save_request(request)
        self.state['latest_build'] = build_id
        self._emit('build_started', request_id=request['id'], source_id=job['source_id'],
                   build_id=build_id, option_id=request['option_id'], predecessor=self.state['displayed_build'])
        self.futures[build_id] = self.workers.submit(self._run_build, job)
        return job

    def evaluate_checkpoint(self, checkpoint=None, *, display=False, key=None):
        """Read-only historical materialization never retargets an editing request."""
        with self.mutex:
            option = self.history.option(self.state['active_option'])
            checkpoint = self.history.head(checkpoint or option['head'])
            if display and self.state['active_request']:
                # History browsing is permitted; its result must not become the
                # latest edit or the agent's active source.
                display = False
            if key:
                for file in (self.local / 'jobs').glob('*.json'):
                    existing = read_json(file)
                    if existing.get('key') == key and existing['kind'] == 'historical_evaluate':
                        if existing.get('checkpoint') != checkpoint:
                            raise StudError('idempotency_conflict', 'Historical evaluation key has another checkpoint.')
                        return existing
        materialization = self.local / 'historical_sources' / checkpoint
        if not materialization.exists():
            import tempfile
            temporary = Path(tempfile.mkdtemp(prefix='stud-history-'))
            try:
                for name in self._historical_source_names(checkpoint):
                    atomic_write(confined(temporary, name), self.history.read_file(checkpoint, name))
                snapshot = capture(temporary, self.local / 'sources')
            finally:
                shutil.rmtree(temporary)
            write_json(materialization, snapshot)
        source = read_json(materialization)
        verify_snapshot(source['path'])
        with self.mutex:
            build_id = identifier('build')
            directory = self.local / 'builds' / build_id
            directory.mkdir(parents=True)
            report = self.history.checkpoint_report(checkpoint)
            required_runtime = report['runtime'] if report else runtime_fingerprint()
            job = dict(schema_version=1, id=build_id, build_id=build_id, kind='historical_evaluate', key=key,
                project_id=self.manifest['project_id'], request_id=None, option_id=option['id'],
                source_id=source['source_id'], source_path=source['path'], runtime=required_runtime,
                status='queued', checkpoint=checkpoint, display=display, created_at=time.time(),
                artifact_path=str(directory), settings=manifest_at(Path(source['path']) / 'files')['evaluation'])
            self._save_job(job)
            if display:
                self.state['latest_build'] = build_id
            self._emit('historical_build_started', build_id=build_id, checkpoint=checkpoint, source_id=source['source_id'])
            self.futures[build_id] = self.history_workers.submit(self._run_build, job)
            return job

    def _display_history(self,build_id,checkpoint):
        if self.state.get('view_mode')!='history':
            self.state['live_displayed_build']=self.state['displayed_build']
        self.state.update(view_mode='history',view_checkpoint=checkpoint,
                          displayed_build=build_id,history_pending=None)

    def _accepts(self, job):
        if job.get('request_id') is None:
            return not self.closed and self.job(job['id'])['status'] not in ('canceled', 'superseded')
        request = self._request(job['request_id'])
        return (not self.closed and self.state['active_request'] == request['id'] and
                request['status'] in ('editing', 'finishing') and request['latest_build'] == job['id'] and
                self.job(job['id'])['status'] not in ('canceled', 'superseded'))

    def _run_build(self, job):
        directory = Path(job['artifact_path'])
        process = None
        started = time.perf_counter()
        try:
            verify_snapshot(job['source_path'])
            execution = directory / 'execution'
            shutil.copytree(Path(job['source_path']) / 'files', execution)
            with self.mutex:
                if not self._accepts(job):
                    return
                job['status'] = 'running'
                self._save_job(job)
                with (directory / 'stderr.log').open('w') as diagnostics:
                    process = subprocess.Popen([sys.executable, '-B', '-E', '-s', str(ENGINE_ROOT / 'stud/worker.py'),
                                                '--job', str(self._job_path(job['id']))],
                                               cwd=execution, stdout=subprocess.PIPE,
                                               stderr=diagnostics, text=True,
                                               **({'start_new_session': True} if os.name != 'nt' else {}))
                self.processes[job['id']] = process
            for line in process.stdout:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                with self.mutex:
                    if not self._accepts(job):
                        continue
                    if event.get('type') in ('part_batch', 'progress', 'geometry_complete', 'checks_updated'):
                        if event['type']=='part_batch':
                            version=job.get('publication_sequence',0)+1;job['publication_sequence']=version
                            relative=f'partials/{version}.json'
                            job.setdefault('manifest_hashes',{})[relative]=digest((directory/relative).read_bytes())
                            self._save_job(job)
                        elif event['type']=='geometry_complete':
                            job.setdefault('manifest_hashes',{})['geometry.json']=digest((directory/'geometry.json').read_bytes())
                            self._save_job(job)
                        self._emit(event['type'], build_id=job['id'], source_id=job['source_id'],
                                   request_id=job['request_id'], data=event.get('data'))
            code = process.wait()
            result = read_json(directory / 'manifest.json')
            retained=result or read_json(directory/'geometry.json') or read_json(directory/'partial.json')
            with self.mutex:
                if not self._accepts(job):
                    return
                job.update(status='complete' if code == 0 and result and result['completion']['geometry'] == 'complete'
                           else 'generation_failed', elapsed_seconds=time.perf_counter() - started,
                           manifest=str(directory / 'manifest.json') if result else None)
                if code:
                    job['diagnostics'] = (directory / 'stderr.log').read_text()[-12000:]
                if result:job.setdefault('manifest_hashes',{})['manifest.json']=digest((directory/'manifest.json').read_bytes())
                if job['kind']=='historical_evaluate' and result and result['completion']['geometry']=='complete':
                    from .source import evaluated_identity
                    report=self.history.checkpoint_report(job['checkpoint'])
                    if report and report.get('evaluated_manifest'):
                        job['reproduction']='matches_saved_evidence' if evaluated_identity(result)==evaluated_identity(report['evaluated_manifest']) else 'differs_from_saved_evidence'
                self._save_job(job)
                show_result = (job.get('request_id') is not None or
                               (job.get('display') and self.state['latest_build'] == job['id'] and not self.state['active_request']))
                inspect_result=job.get('inspect') and self.state.get('history_pending')==job['id']
                if inspect_result:
                    self.state['history_pending']=None
                    self.state['history_reproduction']=job.get('reproduction')
                    if retained and (retained.get('objects') or retained['completion']['geometry']=='complete'):
                        self._display_history(job['id'],job['checkpoint'])
                if show_result and retained and (retained.get('objects') or retained['completion']['geometry']=='complete'):
                    self.state['live_displayed_build' if self.state.get('view_mode')=='history' else 'displayed_build'] = job['id']
                if show_result and result and all(result['completion'].get(k) == 'complete' for k in ('geometry', 'checks')) and result.get('checks', {}).get('all_passed'):
                    self.state['last_valid_build'] = job['id']
                self._emit('build_ended', build_id=job['id'], request_id=job['request_id'],
                           source_id=job['source_id'], status=job['status'], manifest=job.get('manifest'))
        except Exception as error:
            with self.mutex:
                if self._accepts(job):
                    job.update(status='generation_failed', diagnostics=str(error), traceback=traceback.format_exc())
                    self._save_job(job)
                    self._emit('build_ended', build_id=job['id'], request_id=job['request_id'],
                               source_id=job['source_id'], status=job['status'], diagnostics=str(error))
        finally:
            if process:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                process.stdout.close()
            with self.mutex:
                self.processes.pop(job['id'], None)

    def job(self, job_id):
        job = read_json(self._job_path(job_id))
        if not job:
            raise StudError('unknown_job', f'Unknown job: {job_id}')
        return job

    def wait(self, job_id, timeout=60):
        future = self.futures.get(job_id)
        if future:
            future.result(timeout=timeout)
        return self.job(job_id)

    def _stop_build(self, job, status):
        job['status'] = status
        self._save_job(job)
        process = self.processes.get(job['id'])
        if process and process.poll() is None:
            self._terminate_worker(process)
        self._emit('build_ended', build_id=job['id'], request_id=job['request_id'],
                   source_id=job['source_id'], status=status)

    def _terminate_worker(self, process):
        """Escalation cannot depend on a cooperative worker closing stdout."""
        if os.name == 'nt':
            # Kill descendants before the root exits, while its tree is still
            # identifiable. CAD scripts can spawn child processes themselves.
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
        def force():
            if os.name == 'nt':
                if process.poll() is None:
                    process.kill()
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        watchdog = threading.Timer(2, force)
        watchdog.daemon = True
        watchdog.start()

    def cancel(self, request_id):
        with self.mutex:
            request = self._request(request_id)
            if request['status'] == 'canceled':
                return request
            if request.get('finalization') or request['status'] == 'finishing':
                raise StudError('finalizing', 'Finalization has already frozen this request.')
            request = self._editable(request_id)
            if request['latest_build']:
                job = self.job(request['latest_build'])
                if job['status'] not in TERMINAL:
                    self._stop_build(job, 'canceled')
            request['status'] = 'canceled'
            self._save_request(request)
            self.state['active_request'] = None
            self._emit('request_canceled', request_id=request_id, workspace=request['workspace'])
            return request

    def pending_records(self):
        return sorted(self.records.pending_files())

    def _record_files(self):
        """Union retained option records; conflicting IDs need reconciliation."""
        records = {}
        for option in self.history.options():
            for name in self.history.files(option['head'], 'records'):
                body = self.history.read_file(option['head'], name)
                if name in records and records[name] != body:
                    raise StudError('record_conflict', 'Retained options contain conflicting immutable records.', references=[name])
                records[name] = body
        for name, body in self.records.pending_files().items():
            if name in records and records[name] != body:
                raise StudError('record_conflict', 'A pending record conflicts with saved history.', references=[name])
            records[name] = body
        return records

    def finish(self, request_id, *, expected_source, summary, addressed_prompt_ids=None):
        with self.mutex:
            request = self._request(request_id)
            if request.get('finish_job'):
                if request.get('final_source') != expected_source:
                    raise StudError('idempotency_conflict', 'Finish was already requested with another source.')
                existing = self.job(request['finish_job'])
                if existing['status'] in ('failed', 'interrupted'):
                    existing['status'] = 'queued'
                    self._save_job(existing)
                    self.futures[existing['id']] = self.executor.submit(self._finish_job, request_id)
                return existing
            request = self._editable(request_id)
        source = capture(request['workspace'], self.local / 'sources', expected_source)
        with self.mutex:
            request = self._request(request_id)
            if request.get('finish_job'):
                if request['final_source'] != expected_source:
                    raise StudError('idempotency_conflict', 'Finish already captured another source.')
                return self.job(request['finish_job'])
            request = self._editable(request_id)
            option = self.history.option(request['option_id'])
            if option['head'] != request['expected_head']:
                raise StudError('changed_head', 'The option changed before finalization.',
                                expected=request['expected_head'], current=option['head'])
            prompts={prompt['id']:prompt for prompt in self.records.prompts()}
            for prompt_id in addressed_prompt_ids or []:
                if prompt_id not in prompts:
                    raise StudError('unresolved_reference','Addressed prompt is missing.',references=[prompt_id])
                self.records.update_prompt(key=f'{request_id}:address:{prompt_id}',prompt_id=prompt_id,
                    expected_revision=prompts[prompt_id]['revision'],action='resolve',addressing_request=request_id)
            records = self._record_files()
            frozen = self.local / 'finalizing' / request_id
            frozen.mkdir(parents=True, exist_ok=True)
            for name, body in records.items():
                atomic_write(confined(frozen, name), body)
            estimating = encoded(self.records.inputs(request=request)) + b'\n'
            atomic_write(frozen / 'estimating.json', estimating)
            current = self.job(request['latest_build']) if request['latest_build'] else None
            if not current or current['source_id'] != expected_source or current['status'] in ('interrupted', 'canceled', 'superseded'):
                current = self._schedule_build(request, source)
                request = self._request(request_id)
            job_id = identifier('job')
            job = dict(schema_version=1, id=job_id, kind='finish', project_id=self.manifest['project_id'],
                       request_id=request_id, status='queued', source_id=expected_source, build_id=current['id'])
            request.update(status='finishing', final_source=expected_source, finish_job=job_id,
                           summary=summary, addressed_prompt_ids=addressed_prompt_ids or [],
                           frozen_records=sorted(records), frozen_pending=self.pending_records())
            self._save_job(job)
            self._save_request(request)
            self.futures[job_id] = self.executor.submit(self._finish_job, request_id)
            return job

    def _finish_job(self, request_id):
        request = self._request(request_id)
        job = self.job(request['finish_job'])
        try:
            if request.get('finalization'):
                with self.mutex:
                    self._publish_finalization(request)
                return
            if self.job(request['latest_build'])['status'] == 'interrupted':
                with self.mutex:
                    source = verify_snapshot(self.local / 'sources' / request['final_source'])
                    source['path'] = str(self.local / 'sources' / request['final_source'])
                    current = self._schedule_build(request, source)
                    request = self._request(request_id)
                    job['build_id'] = current['id']
                    self._save_job(job)
            # Geometry and estimating run outside the Git/state lock.
            result_job = self.wait(request['latest_build'], timeout=None)
            if self.closed:
                job['status'] = 'interrupted'
                self._save_job(job)
                return
            frozen = self.local / 'finalizing' / request_id
            source = verify_snapshot(self.local / 'sources' / request['final_source'])
            source_root = self.local / 'sources' / request['final_source'] / 'files'
            result = read_json(Path(result_job['artifact_path']) / 'manifest.json')
            if result is None:
                for retained in ('geometry.json','partial.json'):
                    result=read_json(Path(result_job['artifact_path']) / retained)
                    if result is not None:break
                if result is not None:
                    result['completion']={stage:('interrupted' if status=='pending' else status)
                                          for stage,status in result['completion'].items()}
                    result['diagnostics']=dict(type='WorkerInterrupted',message=result_job.get('diagnostics') or 'The worker stopped before publishing its final report.')
            estimate = self._original_estimate(result, read_json(frozen / 'estimating.json'), frozen)
            report = dict(schema_version=1, project_id=self.manifest['project_id'], request_id=request_id,
                          source_id=request['final_source'], build_id=request['latest_build'],
                          intent=request['intent'], summary=request['summary'],
                          addressed_prompt_ids=request['addressed_prompt_ids'], source_files=source['files'],
                          outcome=result_job['status'], runtime=result_job['runtime'],
                          completion=result.get('completion') if result else {'geometry': 'unavailable'},
                          checks=result.get('checks') if result else None,
                          diagnostics=result_job.get('diagnostics'), original_estimate=estimate,
                          preview=self._preview(result), estimating_inputs=read_json(frozen / 'estimating.json'))
            report['evaluated_manifest']=result
            report['change_kind']=request.get('change_kind','design')
            report['completion']['estimates']='complete' if estimate['status']=='complete' else 'unavailable' if estimate['status']=='unavailable' else 'incomplete'
            write_json(frozen / f'checkpoints/{request_id}.json', report)
            updates = {name: confined(source_root, name).read_bytes() for name in source['files']}
            updates.update({p.relative_to(frozen).as_posix(): p.read_bytes() for p in frozen.rglob('*') if p.is_file()})
            base_source_names = self._historical_source_names(request['expected_head'])
            changed = any(self.history.read_file(request['expected_head'], name) != body for name, body in updates.items()
                          if not name.startswith('checkpoints/')) or bool(set(base_source_names) - set(source['files']))
            with self.mutex:
                request = self._request(request_id)
                request['finalization'] = dict(timestamp=int(time.time()), author=self.history.author(),
                    base=request['expected_head'], ref=f"refs/heads/stud/{request['option_id']}",
                    files={name: digest(body) for name, body in updates.items()},
                    source_files=sorted(source['files']), deletions=sorted(set(base_source_names) - set(source['files'])),
                    no_change=not changed, commit=None)
                self._save_request(request)
                self._publish_finalization(request)
        except Exception as error:
            with self.mutex:
                job.update(status='failed', error=error.as_dict() if isinstance(error, StudError) else dict(category='finalization_failed', message=str(error)))
                self._save_job(job)
                self._emit('job_failed', job_id=job['id'], request_id=request_id, error=job['error'])

    def _historical_source_names(self, commit):
        raw = self.history.read_file(commit, 'stud.json')
        if not raw:
            return []
        manifest = json.loads(raw)
        return [name for name in self.history.files(commit) if matches_source(name, manifest)]

    def _original_estimate(self, result, inputs, frozen):
        if not result or result['completion']['geometry'] != 'complete':
            return dict(status='unavailable', reason='No complete geometric model for this source.')
        from .estimate import calculate, quotes_from_directory
        try:
            return calculate(result.get('demands', []), inputs, quotes_from_directory(frozen),
                             demand_findings=result.get('fabrication_findings'),
                             project_id=result['project_id'], source_id=result['source_id'], build_id=result['build_id'])
        except (StudError, KeyError, TypeError, ValueError) as error:
            # Invalid estimating inputs must not strand the source writer or
            # erase a complete geometric result. Preserve the exact inputs and
            # classify this stage independently in the saved checkpoint.
            return dict(status='unavailable', reason='Estimate calculation failed.',
                        error=error.as_dict() if isinstance(error, StudError) else {'message': str(error)},
                        estimating_inputs=inputs, project_id=result['project_id'],
                        source_id=result['source_id'], build_id=result['build_id'])

    @staticmethod
    def _preview(result):
        if not result:
            return None
        return dict(name=result.get('name'), objects=[{k: v for k, v in obj.items() if k in
                    ('id', 'label', 'mark', 'parent', 'shape_key', 'shape_digest', 'placement', 'bounds', 'color', 'lineage')}
                    for obj in result.get('objects', [])], assemblies=result.get('assemblies', []))

    def _publish_finalization(self, request):
        journal = request['finalization']
        if request['status'] == 'complete':
            commit = request['checkpoint']
        elif journal['no_change']:
            commit = journal['base']
        else:
            updates = {}
            for name, expected in journal['files'].items():
                base = self.local / 'sources' / request['final_source'] / 'files' if name in journal['source_files'] else self.local / 'finalizing' / request['id']
                path = confined(base, name)
                if not path.is_file() or digest(path.read_bytes()) != expected:
                    raise StudError('unavailable_artifact', 'Finalization input is missing or corrupt.', references=[name])
                updates[name] = path.read_bytes()
            # Persist journal inputs before commit-tree. Re-running it after a
            # crash yields the exact same object, including author and time.
            commit = journal.get('commit') or self.history.commit(journal['base'], updates, journal['deletions'],
                f"{request['summary']}\n\nStud-Request: {request['id']}\n", journal['author'], journal['timestamp'])
            journal['commit'] = commit
            self._save_request(request)
            self.history.advance(journal['ref'], commit, journal['base'])
        request.update(status='complete', checkpoint=commit,
                       checkout_state=self.history.synchronize(journal['ref'], journal['base'], commit))
        request.pop('recovery_error', None)
        self._save_request(request)
        job = self.job(request['finish_job'])
        job.update(status='complete', checkpoint=commit, no_change=journal['no_change'],
                   source_id=request['final_source'], build_id=request['latest_build'])
        self._save_job(job)
        build=self.job(request['latest_build'])
        if commit not in build.setdefault('checkpoints',[]):build['checkpoints'].append(commit)
        build.setdefault('checkpoint',commit)
        self._save_job(build)
        self.records.clear_pending(request.get('frozen_pending', []),journal['files'])
        if self.state['active_request'] == request['id']:
            self.state['active_request'] = None
        self._emit('checkpoint_created', request_id=request['id'], checkpoint=commit,
                   source_id=request['final_source'], build_id=request['latest_build'], no_change=journal['no_change'])
        request['cleanup_complete'] = True
        self._save_request(request)
        self.records.schedule_flush()

    def save_prompt(self,**arguments):
        return self.records.save_prompt(**arguments)

    def update_prompt(self,**arguments):
        return self.records.update_prompt(**arguments)

    def save_prices(self,**arguments):
        return self.records.save_prices(**arguments)

    def create_option(self,**arguments):
        return self.versions.create(**arguments)

    def rename_option(self,**arguments):
        return self.versions.rename(**arguments)

    def activate_option(self,**arguments):
        return self.versions.activate(**arguments)

    def restore(self,**arguments):
        return self.versions.restore(**arguments)

    def compare_versions(self,**arguments):
        return self.versions.compare(**arguments)

    def inspect_checkpoint(self,**arguments):
        return self.versions.inspect(**arguments)

    def return_live(self,**arguments):
        return self.versions.live(**arguments)

    def plans(self,**arguments):
        return self.operations.plans(**arguments)

    def measure(self,**arguments):
        return self.operations.measure(**arguments)

    def show(self,**arguments):
        return self.operations.show(**arguments)

    def acknowledge_show(self,**arguments):
        return self.operations.acknowledge_show(**arguments)
