"""Immutable, project-wide quotes and anchored review records in normal files."""
from datetime import datetime, timezone
import base64
import json
from pathlib import Path
import shutil
import tempfile

from .contracts import StudError, atomic_write, confined, digest, encoded, identifier, read_json, write_json, sync_directory, manifest_name
from .estimate import calculate, decimal, validate_quote, validate_clear


class Records:
    def __init__(self, session):
        self.session=session
        self.flush_scheduled=False

    def pending_files(self):
        root=self.session.local/'pending'
        result={}
        for batch in sorted(root.glob('*/files')):
            for path in batch.rglob('*'):
                if path.is_file():
                    key=path.relative_to(batch).as_posix();body=path.read_bytes()
                    if key in result and result[key]!=body:
                        raise StudError('record_conflict','Pending batches contain conflicting immutable records.',references=[key])
                    result[key]=body
        return result

    def clear_pending(self, names, hashes):
        for batch in (self.session.local/'pending').glob('*'):
            for name in names:
                path=confined(batch/'files',name)
                if path.is_file() and digest(path.read_bytes())==hashes.get(name):path.unlink()

    def values(self,kind):
        return [json.loads(body) for name,body in self.session._record_files().items()
                if name.startswith(f'records/{kind}/') and name.endswith('.json')]

    def _sequence(self):
        session=self.session
        maximum=session.state.get('save_sequence',0)
        for body in session._record_files().values():
            try:record=json.loads(body)
            except (ValueError,UnicodeDecodeError):continue
            if isinstance(record,dict):maximum=max(maximum,record.get('save_sequence',0))
        session.state['save_sequence']=maximum+1
        session._save_state()
        return maximum+1

    def receipt(self, key, payload):
        """A renamed batch is durable even if its separate receipt was not saved."""
        batch_id=digest(key.encode())
        path=self.session.local/'record_receipts'/f'{batch_id}.json'
        existing=read_json(path) or read_json(self.session.local/'pending'/batch_id/'receipt.json')
        if existing:
            if existing['payload_id']!=digest(payload):
                raise StudError('idempotency_conflict','This record key was used for different contents.')
            write_json(path,existing)
            self.schedule_flush()
        return existing

    def save_batch(self, *, key, payload, files, kind):
        session=self.session
        with session.mutex:
            batch_id=digest(key.encode())
            destination=session.local/'pending'/batch_id
            receipt=session.local/'record_receipts'/f'{batch_id}.json'
            existing=self.receipt(key,payload)
            if existing:
                if existing['payload_id']!=digest(payload):raise StudError('idempotency_conflict','This record key was used for different contents.')
                return existing
            all_records=session._record_files()
            for name,body in files.items():
                if not name.startswith('records/'):
                    raise StudError('invalid_record','Record batches may contain only project records.')
                confined(session.root,name)
                if name in all_records and all_records[name]!=body:
                    raise StudError('record_conflict','A record identity already has immutable contents.',references=[name])
            receipt_data=dict(id=batch_id,kind=kind,status='saved',payload_id=digest(payload),files={name:digest(body) for name,body in files.items()})
            if destination.exists():
                archived=read_json(destination/'receipt.json')
                if archived['payload_id']!=receipt_data['payload_id']:
                    raise StudError('idempotency_conflict','This batch key has different durable contents.')
                receipt_data=archived
            else:
                stage=Path(tempfile.mkdtemp(prefix='stud-record-',dir=session.local))
                try:
                    for name,body in files.items():atomic_write(confined(stage/'files',name),body)
                    write_json(stage/'receipt.json',receipt_data)
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    stage.rename(destination);sync_directory(destination.parent)
                finally:
                    if stage.exists():shutil.rmtree(stage)
            write_json(receipt,receipt_data)
            session._emit('records_saved',batch_id=batch_id,record_kind=kind)
            self.schedule_flush()
            return receipt_data

    def schedule_flush(self):
        session=self.session
        if self.flush_scheduled or session.closed:return
        active=session._request(session.state['active_request']) if session.state['active_request'] else None
        recoverable=active and active.get('change_kind')=='records' and (active['status']=='editing' or
            (active['status']=='finishing' and session.job(active['finish_job'])['status'] in ('interrupted','failed')))
        if recoverable or (not active and self.pending_files()):
            self.flush_scheduled=True
            session.executor.submit(self.flush,active['id'] if recoverable else None)

    def inputs(self, checkpoint=None, request=None, *, option_id=None, include_pending=None):
        session=self.session
        if include_pending is None:include_pending=checkpoint is None or request is not None
        if request:
            values=read_json(confined(request['workspace'],'estimating.json'),{})
            option_id=request['option_id']
        else:
            option_id=option_id or session.state['active_option']
            checkpoint=checkpoint or session.history.option(option_id)['head']
            raw=session.history.read_file(checkpoint,'estimating.json')
            values=json.loads(raw) if raw else {'currency':'USD'}
        # Only pending edits overlay a design. Saved historical inputs stay exact.
        actions=[json.loads(body) for name,body in self.pending_files().items() if name.startswith('records/input_changes/')] if include_pending else []
        for action in sorted(actions,key=lambda action:action['save_sequence']):
            if action['option_id']!=option_id:continue
            values.setdefault('overrides',{}).update(action.get('overrides',{}))
        return values

    def save_prices(self, *, key, quotes, overrides=None, expected_build=None, option_id=None):
        session=self.session
        original=dict(quotes=quotes,overrides=overrides,expected_build=expected_build,option_id=option_id)
        with session.mutex:
            receipt=self.receipt(key,original)
            if receipt:
                if receipt['payload_id']!=digest(original):raise StudError('idempotency_conflict','This pricing key has different contents.')
                return receipt
            option_id=option_id or session.state['active_option']
            session.history.option(option_id)
            if expected_build:
                job=session.job(expected_build)
                if job['project_id']!=session.manifest['project_id']:raise StudError('stale_target','The price target belongs to another project.')
            if overrides:
                if session.state.get('view_mode')=='history':
                    raise StudError('stale_target','Return to the current design to edit purchase quantities for its option.')
                if option_id!=session.state['active_option']:
                    raise StudError('stale_target','Quantity changes require the active option; saved quotes remain project-wide.')
                if expected_build and session.state['latest_build']!=expected_build:
                    raise StudError('stale_target','Reload the current design before changing its purchase quantities.',expected=expected_build,current=session.state['latest_build'])
            files={}
            for index,quote in enumerate(quotes):
                quote=dict(quote)
                record_id=quote.get('id') or 'quote_'+digest(f'{key}:{index}'.encode())[:32]
                quote.update(id=record_id,save_sequence=self._sequence(),project_id=session.manifest['project_id'])
                if quote.get('action')=='clear_manual':
                    validate_clear(quote)
                else:validate_quote(quote)
                files[f'records/quotes/{record_id}.json']=encoded(quote)
            if overrides:
                for value in overrides.values():decimal(value)
                change=dict(id=identifier('input'),option_id=option_id,save_sequence=self._sequence(),
                            overrides={k:str(decimal(v)) for k,v in overrides.items()},build_id=expected_build)
                files[f'records/input_changes/{change["id"]}.json']=encoded(change)
            return self.save_batch(key=key,payload=original,files=files,kind='pricing')

    def _build_context(self,build_id,source_id,manifest_version=None):
        session=self.session;job=session.job(build_id)
        if job['source_id']!=source_id:raise StudError('stale_target','The review source does not match its displayed build.',expected=source_id,current=job['source_id'])
        base=Path(job['artifact_path'])
        relative=manifest_name(manifest_version)
        manifest=read_json(confined(base,relative))
        if not manifest:raise StudError('unavailable_artifact','The original displayed context is unavailable.')
        if any(manifest.get(field)!=expected for field,expected in [('project_id',session.manifest['project_id']),('build_id',build_id),('source_id',source_id)]):
            raise StudError('artifact_identity_mismatch','The original displayed context does not match its recorded build.')
        expected_hash=job.get('manifest_hashes',{}).get(relative)
        if expected_hash and digest(confined(base,relative).read_bytes())!=expected_hash:
            raise StudError('unavailable_artifact','The saved display manifest has changed.')
        return job,manifest

    def save_prompt(self, *, key, prompt_id, text, build_id, source_id, object_id=None,
                    region=None,camera=None,screenshot=None,manifest_version=None):
        session=self.session
        original=dict(prompt_id=prompt_id,text=text,build_id=build_id,source_id=source_id,object_id=object_id,
                      region=region,camera=camera,screenshot=screenshot,manifest_version=manifest_version)
        with session.mutex:
            self.receipt(key,original)
            existing=next((p for p in self.values('prompts') if p['id']==prompt_id),None)
            if existing:
                if existing['request_digest']!=digest(original):raise StudError('idempotency_conflict','This prompt identity already contains different original context.')
                return existing
            if not isinstance(text,str) or not 1<=len(text.strip())<=5000:
                raise StudError('invalid_prompt','Enter a prompt of 1-5000 characters.')
            job,manifest=self._build_context(build_id,source_id,manifest_version)
            target=next((p for p in manifest['objects'] if p['id']==object_id),None)
            if object_id and target is None:raise StudError('unresolved_reference','The selected object does not exist in the displayed version.',references=[object_id])
            prompt=dict(id=prompt_id,text=text.strip(),request_digest=digest(original),build_id=build_id,
                source_id=source_id,project_id=session.manifest['project_id'],object_id=object_id,region=region,
                camera=camera,original_target=target,manifest_version=manifest_version,revision=0,
                created_at=datetime.now(timezone.utc).isoformat(),save_sequence=self._sequence(),
                checkpoint=job.get('checkpoint'),source_context=f'records/contexts/{prompt_id}.json')
            source=Path(job['source_path'])/'files'
            inventory=read_json(Path(job['source_path'])/'source.json')
            context=dict(manifest=manifest,source_id=source_id,files={name:base64.b64encode(confined(source,name).read_bytes()).decode()
                                                                        for name in inventory['files']})
            files={prompt['source_context']:encoded(context)}
            if screenshot:
                from comments import decode_screenshot
                image,width,height=decode_screenshot(screenshot)
                prompt['image']=dict(path=f'records/captures/{prompt_id}.png',width=width,height=height,mime_type='image/png')
                files[prompt['image']['path']]=image
            files[f'records/prompts/{prompt_id}.json']=encoded(prompt)
            self.save_batch(key=key,payload=original,files=files,kind='review')
            return prompt

    def prompts(self, *, build_id=None, checkpoint=None, manifest=None):
        session=self.session
        with session.mutex:
            actions=self.values('prompt_actions');requests={r['id']:r for r in [read_json(p) for p in (session.local/'requests').glob('*.json')]}
            if manifest is None and build_id:
                job=session.job(build_id);base=Path(job['artifact_path'])
                manifest=read_json(base/'manifest.json') or read_json(base/'geometry.json') or read_json(base/'partial.json')
            object_ids={p['id'] for p in manifest['objects']} if manifest else None
            rows=[]
            for prompt in self.values('prompts'):
                row={**prompt,'resolved':False,'deleted':False,'actions':[],'addressing_requests':[]}
                selected=sorted([action for action in actions if action['prompt_id']==prompt['id']],key=lambda action:action['revision'])
                expected=1
                for action in selected:
                    if action['revision']!=expected:raise StudError('record_conflict','Prompt revisions conflict across retained options.',references=[prompt['id']])
                    expected+=1;row['revision']=action['revision'];row['actions'].append(action)
                    if action['action']=='edit':row['text']=action['text']
                    if action['action']=='delete':row['deleted']=True
                    if action['action'] in ('resolve','reopen'):row['resolved']=action['action']=='resolve'
                    if action.get('addressing_request'):
                        request_id=action['addressing_request'];request=requests.get(request_id)
                        commit=request.get('checkpoint') if request else None
                        if commit is None:
                            for option in session.history.options():
                                data=session.history.read_file(option['head'],f'checkpoints/{request_id}.json')
                                if data:
                                    commits=session.history.git('log','--format=%H','-1',option['head'],'--',f'checkpoints/{request_id}.json').decode().strip()
                                    commit=commits or None;break
                        in_view=False
                        if commit:
                            viewed=checkpoint or session.history.option(session.state['active_option'])['head']
                            in_view=session.history.git('merge-base','--is-ancestor',commit,viewed,check=False).returncode==0
                        row['addressing_requests'].append(dict(request_id=request_id,checkpoint=commit,in_viewed_history=in_view))
                row['target_resolution']='region_snapshot' if not row.get('object_id') else 'unresolved' if object_ids is not None and row['object_id'] not in object_ids else 'identified'
                rows.append(row)
            return rows

    def update_prompt(self, *, key,prompt_id,expected_revision,action,text=None,addressing_request=None):
        session=self.session
        original=dict(prompt_id=prompt_id,expected_revision=expected_revision,action=action,text=text,addressing_request=addressing_request)
        with session.mutex:
            existing=self.receipt(key,original)
            if existing:
                if existing['payload_id']!=digest(original):raise StudError('idempotency_conflict','This prompt-action key has different contents.')
                return existing
            row=next((r for r in self.prompts() if r['id']==prompt_id),None)
            if row is None:raise StudError('unresolved_reference','Prompt does not exist.',references=[prompt_id])
            if row['revision']!=expected_revision:raise StudError('stale_revision','The prompt changed; reload before applying this action.',expected=expected_revision,current=row['revision'])
            if action not in ('resolve','reopen','edit','delete'):raise StudError('invalid_prompt','Unknown prompt action.')
            if action=='edit' and (not isinstance(text,str) or not 1<=len(text.strip())<=5000):raise StudError('invalid_prompt','Enter 1-5000 characters.')
            record=dict(id='action_'+digest(key.encode())[:32],prompt_id=prompt_id,revision=expected_revision+1,
                        action=action,text=text,addressing_request=addressing_request,save_sequence=self._sequence())
            return self.save_batch(key=key,payload=original,files={f'records/prompt_actions/{record["id"]}.json':encoded(record)},kind='review')

    def flush(self, request_id=None):
        """Idle batches use the same request finalization, reusing geometric evidence."""
        session=self.session
        try:
            with session.mutex:
                if session.closed:return
                if request_id:
                    request=session._request(request_id)
                    if session.state['active_request']!=request_id or request.get('change_kind')!='records':return
                    if request['status']=='finishing':
                        session.finish(request_id,expected_source=request['final_source'],summary=request['summary'])
                        return
                elif session.state['active_request'] or not self.pending_files():return
                option=session.history.option(request['option_id'] if request_id else session.state['active_option'])
                record_inputs=self.inputs(option['head'],include_pending=True)
                if not request_id:
                    request=session.begin(expected_head=option['head'],intent='Save project review and pricing records',key=identifier('records'),change_kind='records')
            source=session.source(request['id'])
            existing=[]
            for file in (session.local/'jobs').glob('*.json'):
                job=read_json(file)
                if job.get('source_id')==source['source_id'] and job['status']=='complete' and job.get('artifact_path'):
                    manifest=read_json(Path(job['artifact_path'])/'manifest.json')
                    if manifest and manifest['completion']['geometry']=='complete':existing.append(job)
            if not existing:
                report=session.history.checkpoint_report(option['head'])
                if report and report.get('evaluated_manifest') and report['evaluated_manifest']['source_id']==source['source_id']:
                    manifest=report['evaluated_manifest'];build_id=manifest['build_id']
                    directory=session.local/'archived_evidence'/build_id
                    write_json(directory/'manifest.json',manifest)
                    job=dict(id=build_id,kind='archived_evidence',status='complete',artifact_path=str(directory),
                             source_id=source['source_id'],source_path=source['path'],runtime=manifest['runtime'],project_id=session.manifest['project_id'])
                    session._save_job(job);existing.append(job)
            with session.mutex:
                request=session._request(request['id'])
                if existing:
                    request['latest_build']=existing[-1]['id'];session._save_request(request)
                # With no previously evaluated geometry, save a classified
                # unavailable estimate without executing CAD for a record edit.
                else:
                    build_id=identifier('build');directory=session.local/'archived_evidence'/build_id
                    directory.mkdir(parents=True)
                    from .source import runtime_fingerprint
                    job=dict(id=build_id,kind='archived_evidence',status='generation_failed',source_id=source['source_id'],
                             artifact_path=str(directory),runtime=runtime_fingerprint(),project_id=session.manifest['project_id'],
                             diagnostics='No evaluated geometry was available for this record-only checkpoint.')
                    session._save_job(job);request['latest_build']=build_id;session._save_request(request)
                write_json(Path(request['workspace'])/'estimating.json',record_inputs)
                session.finish(request['id'],expected_source=source['source_id'],summary='Save review and pricing records')
        except Exception as error:
            with session.mutex:
                session.state['record_save_error']=error.as_dict() if isinstance(error,StudError) else {'message':str(error)}
                session._save_state()
        finally:
            with session.mutex:self.flush_scheduled=False
