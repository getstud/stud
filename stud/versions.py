"""Branch alternatives and comparisons, independent of the active source writer."""
import json
from pathlib import Path
import time

from .contracts import StudError, digest, encoded, identifier, read_json, write_json
from .estimate import calculate, compare, select_quotes


class Versions:
    def __init__(self, session):
        self.session=session

    def options(self):
        options=self.session.history.options()
        actions=self.session.records.values('option_actions')
        for option in options:
            option['revision']=0
            for action in sorted((a for a in actions if a['option_id']==option['id']),key=lambda a:a['revision']):
                if action['revision']!=option['revision']+1:
                    raise StudError('record_conflict','Option name revisions conflict; retain both actions for reconciliation.',references=[option['id']])
                option.update(label=action['label'],revision=action['revision'])
        return options

    def rename(self, *, key, option_id, name, expected_revision):
        session=self.session;payload=dict(option_id=option_id,name=name,expected_revision=expected_revision)
        with session.mutex:
            receipt=session.records.receipt(key,payload)
            if receipt:return receipt
            if not isinstance(name,str) or not 1<=len(name.strip())<=120:
                raise StudError('invalid_option','Option names must have 1-120 characters.')
            option=next((o for o in self.options() if o['id']==option_id),None)
            if option is None:raise StudError('unknown_option','The option is missing.')
            if option['revision']!=expected_revision:
                raise StudError('stale_revision','The option name changed; reload it before renaming.',expected=expected_revision,current=option['revision'])
            action_id='option_action_'+digest(key.encode())[:32]
            action=dict(id=action_id,option_id=option_id,label=name.strip(),revision=expected_revision+1,
                        save_sequence=session.records._sequence())
            return session.records.save_batch(key=key,payload=payload,kind='option_name',
                files={f'records/option_actions/{action_id}.json':encoded(action)})

    def create(self, *, key, name, base_checkpoint=None):
        session=self.session
        payload=dict(name=name,base_checkpoint=base_checkpoint)
        with session.mutex:
            path=session.local/'option_journal'/f'{digest(key.encode())}.json'
            journal=read_json(path)
            if journal:
                if journal['payload_id']!=digest(payload):raise StudError('idempotency_conflict','Option key has different inputs.')
            else:
                if not isinstance(name,str) or not 1<=len(name.strip())<=120:
                    raise StudError('invalid_option','Option names must have 1-120 characters.')
                base=session.history.head(base_checkpoint or session.history.option(session.state['active_option'])['head'])
                raw=session.history.read_file(base,'stud.json')
                if not raw or json.loads(raw)['project_id']!=session.manifest['project_id']:
                    raise StudError('invalid_checkpoint','The option must start from this project.')
                option_id=identifier('option')
                record=dict(id=option_id,label=name.strip(),created_from=base)
                files=session._record_files()
                files[f'records/options/{option_id}.json']=encoded(record)
                journal=dict(payload_id=digest(payload),base=base,record=record,files={name:body.decode() for name,body in files.items() if not name.startswith('records/captures/')},
                    binary_files={name:__import__('base64').b64encode(body).decode() for name,body in files.items() if name.startswith('records/captures/')},
                    author=session.history.author(),timestamp=int(time.time()))
                write_json(path,journal)
            return self._publish_option(path,journal)

    def _publish_option(self,path,journal):
        session=self.session;record=journal['record'];ref=f'refs/heads/stud/{record["id"]}'
        if journal.get('complete'):return dict(**record,ref=ref,head=journal['commit'])
        files={name:body.encode() for name,body in journal['files'].items()}
        files.update({name:__import__('base64').b64decode(body) for name,body in journal['binary_files'].items()})
        commit=journal.get('commit') or session.history.commit(journal['base'],files,[],f'Create option {record["label"]}\n',journal['author'],journal['timestamp'])
        journal['commit']=commit;write_json(path,journal)
        session.history.advance(ref,commit,'0'*len(commit))
        journal['complete']=True;write_json(path,journal)
        session._emit('option_created',option_id=record['id'],checkpoint=commit)
        return dict(**record,ref=ref,head=commit)

    def recover(self):
        with self.session.mutex:
            for path in (self.session.local/'option_journal').glob('*.json'):
                journal=read_json(path)
                if not journal.get('complete'):
                    try:self._publish_option(path,journal)
                    except StudError as error:
                        self.session.state['option_recovery_error']=error.as_dict()
            for path in (self.session.local/'activation_receipts').glob('*.json'):
                journal=read_json(path)
                if not journal.get('result') and self.session.state.get('activation_key')==journal.get('key'):
                    try:self.activate(key=journal['key'],**journal['arguments'])
                    except StudError as error:self.session.state['option_recovery_error']=error.as_dict()

    def activate(self, *, key, option_id, expected_head):
        session=self.session;payload=dict(option_id=option_id,expected_head=expected_head)
        with session.mutex:
            receipt=session.local/'activation_receipts'/f'{digest(key.encode())}.json'
            saved=read_json(receipt)
            if saved:
                if saved['payload_id']!=digest(payload):raise StudError('idempotency_conflict','Activation key has different inputs.')
                if saved.get('result'):return saved['result']
                if session.state.get('activation_key') not in (None,key):
                    raise StudError('superseded','A newer option activation replaced this interrupted attempt.')
            option=session.history.option(option_id)
            if option['head']!=expected_head:raise StudError('changed_head','The selected option changed.',expected=expected_head,current=option['head'])
            if session.state['active_request']:raise StudError('busy_request','Finish or cancel the editing request before activating an option.')
            if session.pending_records():raise StudError('pending_records','Saved record batches are being checkpointed; retry activation after they finish.',retryable=True)
            write_json(receipt,dict(payload_id=digest(payload),key=key,arguments=payload))
            session.state['activation_key']=key
            session._save_state()
            # Git refuses tracked changes and ignored-file collisions. A dirty
            # checkout is left intact; subsequent requests use the option ref.
            checkout='local_edits_preserved'
            if not session.history.git('diff','--name-only','HEAD').strip() and not session.history.git('diff','--cached','--name-only').strip():
                changed=session.history.git('switch','--no-overwrite-ignore',option['ref'].removeprefix('refs/heads/'),check=False)
                if changed.returncode==0:checkout='synchronized'
            observed=session.history.option(option_id)['head']
            if observed!=expected_head:
                raise StudError('changed_head','The selected option changed during activation; reload its current head.',expected=expected_head,current=observed)
            session.state.update(active_option=option_id,latest_build=None,displayed_build=None,last_valid_build=None)
            session.state.update(view_mode='live',live_displayed_build=None,history_pending=None,view_checkpoint=None)
            session._emit('option_activated',option_id=option_id,checkpoint=expected_head)
            result=dict(**option,checkout_state=checkout)
            # This explicit display action may reopen cached or recorded evidence.
            session.evaluate_checkpoint(expected_head,display=True,key=f'{key}:display')
            write_json(receipt,dict(payload_id=digest(payload),result=result))
            return result

    def restore(self, *, key, checkpoint, option_id=None, expected_head):
        session=self.session
        checkpoint=session.history.head(checkpoint)
        raw=session.history.read_file(checkpoint,'stud.json')
        if not raw or json.loads(raw)['project_id']!=session.manifest['project_id']:
            raise StudError('invalid_checkpoint','Restore requires a checkpoint from this project.')
        return session.begin(key=key,option_id=option_id,expected_head=expected_head,
            intent=f'Restore design from {checkpoint}',seed_checkpoint=checkpoint)

    def checkpoints(self,option_id=None):
        session=self.session;options=[session.history.option(option_id)] if option_id else session.history.options()
        rows={}
        for option in options:
            commits=session.history.git('log','--format=%H%x00%s%x00%ct',option['head']).decode().splitlines()
            for line in commits:
                commit,summary,stamp=line.split('\0',2)
                if commit not in rows:
                    report=session.history.checkpoint_report(commit)
                    rows[commit]=dict(checkpoint=commit,summary=summary,created_at=int(stamp),options=[],
                        source_id=(report or {}).get('source_id'),build_id=(report or {}).get('build_id'),
                        outcome=(report or {}).get('outcome','unevaluated'),original_estimate=(report or {}).get('original_estimate'),
                        request_id=(report or {}).get('request_id'))
                rows[commit]['options'].append(option['id'])
        return sorted(rows.values(),key=lambda row:(row['created_at'],row['checkpoint']),reverse=True)

    def inspect(self, *, key, checkpoint):
        session=self.session;checkpoint=session.history.head(checkpoint)
        with session.mutex:
            receipt=session.local/'inspection_receipts'/f'{digest(key.encode())}.json'
            saved=read_json(receipt)
            if saved:
                if saved['checkpoint']!=checkpoint:raise StudError('idempotency_conflict','Inspection key has another checkpoint.')
                return session.job(saved['job_id']) if saved.get('job_id') else saved
            report=session.history.checkpoint_report(checkpoint)
            if report:
                for path in (session.local/'jobs').glob('*.json'):
                    job=read_json(path)
                    if job['id']!=report['build_id'] or job.get('source_id')!=report['source_id'] or job.get('runtime',{}).get('id')!=report['runtime']['id'] or not job.get('artifact_path'):continue
                    base=Path(job['artifact_path'])
                    manifest=read_json(base/'manifest.json') or read_json(base/'geometry.json') or read_json(base/'partial.json')
                    if not manifest or not manifest.get('assets'):continue
                    from .contracts import confined
                    if not all(confined(job['artifact_path'],asset['mesh']).is_file() for asset in manifest['assets'].values()):continue
                    session._display_history(job['id'],checkpoint)
                    session._emit('history_displayed',checkpoint=checkpoint,build_id=job['id'])
                    result=dict(status='complete',checkpoint=checkpoint,build_id=job['id'],report=report)
                    write_json(receipt,result);return result
            job=session.evaluate_checkpoint(checkpoint,key=f'{key}:inspection')
            job['inspect']=True;session._save_job(job)
            session.state['history_pending']=job['id'];session._save_state()
            write_json(receipt,dict(checkpoint=checkpoint,job_id=job['id']))
            session._emit('history_loading',checkpoint=checkpoint,build_id=job['id'],archived_report=report)
            return job

    def live(self, *, key):
        session=self.session
        with session.mutex:
            receipt=session.local/'live_receipts'/f'{digest(key.encode())}.json'
            saved=read_json(receipt)
            if saved:return saved
            if session.state.get('view_mode')=='history':session.state['displayed_build']=session.state.get('live_displayed_build')
            session.state.update(view_mode='live',history_pending=None,view_checkpoint=None)
            session._emit('live_displayed',build_id=session.state['displayed_build'])
            result=dict(status='complete',build_id=session.state['displayed_build'])
            write_json(receipt,result);return result

    def compare(self, *, key, left, right, mode='historical', quote_selection=None):
        session=self.session
        if mode not in ('historical','common_price'):raise StudError('invalid_comparison','Choose historical or common_price.')
        left,right=session.history.head(left),session.history.head(right)
        payload=dict(left=left,right=right,mode=mode,quote_selection=quote_selection)
        with session.mutex:
            job_id='comparison_'+digest(key.encode())[:32]
            existing=read_json(session._job_path(job_id))
            if existing:
                if existing['payload_id']!=digest(payload):raise StudError('idempotency_conflict','Comparison key has different inputs.')
                if existing['status']!='interrupted':return existing
                job=existing
            else:
                basis=select_quotes(session.records.values('quotes'),quote_selection) if mode=='common_price' else None
                job=dict(id=job_id,kind='compare',status='queued',project_id=session.manifest['project_id'],
                    payload_id=digest(payload),arguments=payload,price_basis=basis,created_at=time.time())
            session._save_job(job)
            session.futures[job_id]=session.executor.submit(self._compare_job,job)
            return job

    def _compare_job(self,job):
        session=self.session;started=time.perf_counter()
        try:
            args=job['arguments']
            reports=[session.history.checkpoint_report(args[side]) for side in ('left','right')]
            manifests=[(report or {}).get('evaluated_manifest') for report in reports]
            views=[];view_errors=[]
            for index,side in enumerate(('left','right')):
                manifest=manifests[index];report=reports[index];checkpoint=args[side]
                candidate=None
                if report:
                    candidate=read_json(session._job_path(report['build_id']))
                from .contracts import confined
                def has_assets(build,model):
                    return bool(build and model and build.get('artifact_path') and all(
                        confined(build['artifact_path'],asset['mesh']).is_file() for asset in model.get('assets',{}).values()))
                if not has_assets(candidate,manifest):
                    attempt=session.evaluate_checkpoint(checkpoint,key=f'{job["id"]}:{side}:{identifier("view")}')
                    candidate=session.wait(attempt['id'],timeout=300)
                    if candidate['status']=='complete' and candidate.get('reproduction')!='differs_from_saved_evidence':
                        manifest=read_json(Path(candidate['artifact_path'])/'manifest.json')
                        if manifests[index] is None:
                            manifests[index]=manifest
                            reports[index]=dict(source_id=manifest['source_id'],build_id=manifest['build_id'],
                                estimating_inputs=session.records.inputs(checkpoint,include_pending=False),evaluated_manifest=manifest)
                    else:
                        view_errors.append(dict(side=side,checkpoint=checkpoint,category='non_reproducible_checkpoint' if candidate.get('reproduction')=='differs_from_saved_evidence' else 'unavailable_runtime',
                                                message=candidate.get('diagnostics') or 'The saved geometry cannot be regenerated by this runtime.'))
                        views.append(None);continue
                if has_assets(candidate,manifest):
                    from .display import model_from_manifest
                    views.append(model_from_manifest(session,manifest,candidate,
                        inputs=session.records.inputs(checkpoint,include_pending=False),presentation='comparison',checkpoint=checkpoint))
                else:
                    views.append(None);view_errors.append(dict(side=side,checkpoint=checkpoint,category='unavailable_artifact',message='The saved display meshes are unavailable.'))
            estimates=[(report or {}).get('original_estimate',{'status':'unavailable'}) for report in reports]
            if args['mode']=='common_price':
                estimates=[calculate(manifest['demands'],report['estimating_inputs'],basis=job['price_basis'],
                    demand_findings=manifest.get('fabrication_findings'),
                    project_id=job['project_id'],source_id=manifest['source_id'],build_id=manifest['build_id'])
                    if manifest and manifest['completion']['geometry']=='complete' else {'status':'unavailable'}
                    for manifest,report in zip(manifests,reports)]
            estimate_difference=compare(*estimates,mode=args['mode']) if all('id' in e for e in estimates) else dict(status='unavailable',left=estimates[0],right=estimates[1])
            result=dict(project_id=job['project_id'],left_checkpoint=args['left'],right_checkpoint=args['right'],
                left_source_id=(reports[0] or {}).get('source_id'),right_source_id=(reports[1] or {}).get('source_id'),
                left_build_id=(reports[0] or {}).get('build_id'),right_build_id=(reports[1] or {}).get('build_id'),
                units=[(manifest or {}).get('units') for manifest in manifests],objects=object_changes(*manifests),requirements=record_changes(*[m.get('requirements',[]) if m else [] for m in manifests]),
                findings=record_changes(*[[dict(**finding,id=finding['requirement_id']) for finding in (m or {}).get('checks',{}).get('findings',[])] for m in manifests]),
                materials=record_changes(*[m.get('demands',[]) if m else [] for m in manifests]),
                estimates=estimate_difference,views=views,view_errors=view_errors,
                geometry_status='available' if all(views) else 'partial' if any(views) else 'unavailable',elapsed_seconds=time.perf_counter()-started)
            output=session.local/'comparisons'/job['id']/'result.json';write_json(output,result)
            with session.mutex:
                job.update(status='complete',result=result,result_path=str(output));session._save_job(job)
                session._emit('comparison_complete',job_id=job['id'],left=args['left'],right=args['right'])
        except Exception as error:
            with session.mutex:
                job.update(status='failed',error=error.as_dict() if isinstance(error,StudError) else {'message':str(error)})
                session._save_job(job);session._emit('job_failed',job_id=job['id'],error=job['error'])


def record_changes(left,right):
    a,b=[{row['id']:row for row in rows} for rows in (left,right)]
    return [dict(id=key,left=a.get(key),right=b.get(key),status='added' if key not in a else 'removed' if key not in b else 'changed' if a[key]!=b[key] else 'unchanged')
            for key in sorted(set(a)|set(b))]


def object_changes(left,right):
    changes=record_changes((left or {}).get('objects',[]),(right or {}).get('objects',[]))
    for row in changes:
        old,new=row['left'],row['right'];flags=[]
        if old and new:
            if old['placement']!=new['placement']:flags.append('moved')
            if old['shape_digest']!=new['shape_digest']:flags.append('reshaped')
            if old.get('lineage')!=new.get('lineage'):flags.append('replaced')
            if any(old.get(k)!=new.get(k) for k in ('label','parent','material','blank')):flags.append('metadata')
            row['status']='changed' if flags else 'unchanged'
        row['changes']=flags or [row['status']]
    return changes
