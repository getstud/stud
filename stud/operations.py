"""Version-bound native measurements, immutable exports, and viewer focus jobs."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import subprocess
import sys
import time

from .contracts import StudError, confined, digest, identifier, read_json, write_json, sync_directory


class Operations:
    def __init__(self, session):
        self.session=session
        # Background drawing/query work cannot occupy the current-build slots.
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='stud-native-query')

    def submit(self,kind,key,arguments,freeze=None):
        session=self.session;job_id=f'{kind}_'+digest(key.encode())[:32]
        with session.mutex:
            existing=read_json(session._job_path(job_id))
            if existing:
                if existing['payload_id']!=digest(arguments):raise StudError('idempotency_conflict','The operation key has different versioned inputs.')
                if existing['status']!='interrupted':return existing
                job=existing;job['status']='queued'
            else:
                job=dict(schema_version=1,id=job_id,kind=kind,status='queued',project_id=session.manifest['project_id'],
                    payload_id=digest(arguments),arguments=arguments,created_at=time.time(),**(freeze() if freeze else {}))
            session._save_job(job)
            session.futures[job_id]=self.executor.submit(self.run,job)
            return job

    def plans(self, *, key, checkpoint, build_id=None, print_spec=None, views=None, diagnostic=False, estimate_mode='historical',include_lists=True):
        checkpoint=self.session.history.head(checkpoint)
        if estimate_mode not in ('historical','current'):raise StudError('invalid_estimate_mode','Use historical or current saved prices.')
        # Capture prices/inputs before enqueueing so a long job has a fixed basis.
        with self.session.mutex:
            from .estimate import select_quotes
            return self.submit('plans',key,dict(checkpoint=checkpoint,build_id=build_id,print_spec=print_spec,
                views=views,diagnostic=diagnostic,estimate_mode=estimate_mode,include_lists=bool(include_lists)),
                freeze=lambda:dict(price_basis=select_quotes(self.session.records.values('quotes')) if estimate_mode=='current' else None))

    def measure(self, *, key, build_id, targets, kind='point_distance', source_id=None, tolerance=None, expected_display=None, manifest_version=None):
        session=self.session
        with session.mutex:
            job=session.job(build_id)
            tolerance=job['settings']['query_tolerance'] if tolerance is None else tolerance
            if source_id and job['source_id']!=source_id:raise StudError('stale_target','Measurement source and build do not match.',expected=source_id,current=job['source_id'])
            if expected_display and session.state['displayed_build']!=expected_display:raise StudError('stale_target','The displayed model changed before the measurement request.',expected=expected_display,current=session.state['displayed_build'])
            return self.submit('measure',key,dict(build_id=build_id,source_id=job['source_id'],targets=targets,
                kind=kind,tolerance=tolerance,manifest_version=manifest_version))

    def _plan_build(self,job):
        session=self.session;args=job['arguments'];report=session.history.checkpoint_report(args['checkpoint'])
        build_id=args['build_id']
        if build_id:
            build=session.job(build_id)
            # Resolve checkpoint source independently of whether it has a report.
            from .source import source_identity
            files={name:session.history.read_file(args['checkpoint'],name) for name in session._historical_source_names(args['checkpoint'])}
            expected=source_identity(files)
            if build['source_id']!=expected:raise StudError('stale_target','The export build does not belong to the requested checkpoint.',expected=expected,current=build['source_id'])
            if report and build['runtime']['id']!=report['runtime']['id']:
                raise StudError('unavailable_runtime','A different runtime cannot be labeled as the original checkpoint output.',expected=report['runtime']['id'],current=build['runtime']['id'])
            if build['status'] not in ('complete','generation_failed'):build=session.wait(build_id,timeout=None)
        else:
            expected=(report or {}).get('source_id')
            candidates=[]
            if report:
                for path in (session.local/'jobs').glob('*.json'):
                    candidate=read_json(path)
                    if (candidate['id']==report['build_id'] and candidate.get('source_id')==expected and candidate.get('runtime',{}).get('id')==report['runtime']['id']
                            and candidate['status'] in ('complete','generation_failed') and candidate.get('artifact_path')):
                        manifest=read_json(Path(candidate['artifact_path'])/'manifest.json')
                        if manifest and manifest.get('assets') and all(confined(candidate['artifact_path'],asset['native']).is_file() for asset in manifest['assets'].values()):
                            candidates.append(candidate)
            if candidates:build=candidates[-1]
            else:
                with session.mutex:
                    attempt=job.get('geometry_attempt',0)+1;job['geometry_attempt']=attempt
                    session._save_job(job)
                build=session.evaluate_checkpoint(args['checkpoint'],key=f'{job["id"]}:geometry:{attempt}')
                job['geometry_job']=build['id'];session._save_job(job)
                build=session.wait(build['id'],timeout=None)
        manifest=read_json(Path(build['artifact_path'])/'manifest.json')
        if not manifest or not manifest.get('assets'):
            raise StudError('unavailable_artifact','The requested checkpoint has no usable geometric archive.',references=[build['id']])
        if build.get('diagnostics') and manifest['completion']['geometry']=='unavailable':
            raise StudError('unavailable_runtime',build['diagnostics'])
        estimate=(report or {}).get('original_estimate')
        if report and report.get('evaluated_manifest') and build['id']!=report['build_id']:
            from .source import evaluated_identity
            if evaluated_identity(manifest)!=evaluated_identity(report['evaluated_manifest']):
                raise StudError('non_reproducible_checkpoint','This execution differs from the saved checkpoint evidence. Save the changed result as a new design checkpoint before exporting it.',references=[report['build_id'],build['id']])
            job['reproduced_from_build']=report['build_id'];session._save_job(job)
            if estimate and estimate.get('price_basis'):
                from .estimate import calculate
                estimate=calculate(manifest['demands'],report['estimating_inputs'],basis=estimate['price_basis'],
                    demand_findings=manifest.get('fabrication_findings'),
                    project_id=job['project_id'],source_id=build['source_id'],build_id=build['id'])
        if args['estimate_mode']=='current' and manifest['completion']['geometry']=='complete':
            from .estimate import calculate
            inputs=session.records.inputs(args['checkpoint'])
            estimate=calculate(manifest['demands'],inputs,basis=job['price_basis'],project_id=job['project_id'],source_id=build['source_id'],build_id=build['id'],demand_findings=manifest.get('fabrication_findings'))
        return build,estimate

    def run(self,job):
        session=self.session;started=time.perf_counter();process=None
        try:
            output=confined(session.root,f'exports/{job["id"]}') if job['kind']=='plans' else None
            if job['kind']=='plans' and (output/'manifest.json').is_file():
                result=read_json(output/'manifest.json')
                if result['checkpoint']!=job['arguments']['checkpoint']:raise StudError('artifact_conflict','The retained export has another checkpoint.')
                for name,expected in result['files'].items():
                    if digest(confined(output,name).read_bytes())!=expected:raise StudError('unavailable_artifact','A retained export is corrupt.',references=[name])
                return self.complete(job,dict(**result,directory=str(output),pdf=str(output/'plans.pdf')),started)
            if job['kind']=='plans':build,estimate=self._plan_build(job)
            else:build=session.job(job['arguments']['build_id']);estimate=None
            if session.closed:return
            directory=confined(session.root,f'.stud/operations/{job["id"]}/{identifier("attempt")}')
            directory.mkdir(parents=True)
            native=dict(kind=job['kind'],arguments=job['arguments'],build=build,estimate=estimate,output=str(directory/'packet'),result_path=str(directory/'result.json'))
            native['reproduced_from_build']=job.get('reproduced_from_build')
            write_json(directory/'request.json',native)
            with session.mutex:
                if session.closed:return
                job.update(status='running',source_id=build['source_id'],build_id=build['id'],artifact_path=str(directory))
                session._save_job(job)
                engine=Path(__file__).resolve().parents[1]
                with (directory/'stderr.log').open('w') as diagnostics:
                    process=subprocess.Popen([sys.executable,'-X','utf8','-B','-E','-s',str(engine/'stud/native_worker.py'),'--request',str(directory/'request.json')],
                        stdout=diagnostics,stderr=diagnostics,**({'start_new_session':True} if os.name!='nt' else {}))
                session.processes[job['id']]=process
                session._emit('job_started',job_id=job['id'],operation=job['kind'],build_id=build['id'])
            code=process.wait()
            if session.closed:return
            result=read_json(directory/'result.json')
            if not result:raise StudError('native_operation_failed',(directory/'stderr.log').read_text(encoding='utf-8',errors='replace')[-12000:])
            if code or result.get('error'):
                error=result.get('error',{})
                raise StudError(error.get('category','native_operation_failed'),error.get('message','Native operation failed.'),references=error.get('references'))
            if job['kind']=='plans':
                output.parent.mkdir(parents=True,exist_ok=True)
                if output.exists():raise StudError('artifact_conflict','An immutable export already occupies this destination.')
                (directory/'packet').rename(output);sync_directory(output.parent)
                result.update(directory=str(output),pdf=str(output/'plans.pdf'))
                result['reproduced_from_build']=job.get('reproduced_from_build')
            self.complete(job,result,started)
        except Exception as error:
            with session.mutex:
                job.update(status='failed',error=error.as_dict() if isinstance(error,StudError) else {'category':'operation_failed','message':str(error)})
                session._save_job(job);session._emit('job_failed',job_id=job['id'],error=job['error'])
        finally:
            if process:
                if process.poll() is None:session._terminate_worker(process)
                with session.mutex:session.processes.pop(job['id'],None)
            if session.closed:
                job['status']='interrupted';session._save_job(job)

    def complete(self,job,result,started):
        with self.session.mutex:
            job.update(status='complete',result=result,elapsed_seconds=time.perf_counter()-started)
            self.session._save_job(job)
            self.session._emit('job_complete',job_id=job['id'],operation=job['kind'],build_id=job.get('build_id'))

    def show(self, *, key, expected_build, objects=None, region=None, checkpoint=None):
        session=self.session;arguments=dict(expected_build=expected_build,objects=objects,region=region,checkpoint=checkpoint)
        job_id='show_'+digest(key.encode())[:32]
        with session.mutex:
            existing=read_json(session._job_path(job_id))
            if existing:
                if existing['payload_id']!=digest(arguments):raise StudError('idempotency_conflict','Show key has another target.')
                if existing['status']!='interrupted':return existing
            from .display import displayed_manifest
            manifest,build=displayed_manifest(session)
            if manifest['build_id']!=expected_build:raise StudError('stale_target','The displayed build changed.',expected=expected_build,current=manifest['build_id'])
            if checkpoint:
                checkpoint=session.history.head(checkpoint)
                report=session.history.checkpoint_report(checkpoint)
                if not report or report['source_id']!=manifest['source_id']:raise StudError('stale_target','The displayed model does not match the requested checkpoint.')
            ids=manifest_scope(manifest,objects)
            if region is not None:
                import math
                if not isinstance(region,dict) or any(not isinstance(region.get(k),list) or len(region[k])!=3 or not all(isinstance(n,(int,float)) and math.isfinite(n) for n in region[k]) for k in ('min','max')):
                    raise StudError('invalid_region','A focus region requires finite min/max model coordinates in project units.')
                if any(b<=a for a,b in zip(region['min'],region['max'])):raise StudError('invalid_region','Each focus maximum must exceed its minimum.')
            job=dict(id=job_id,kind='show',status='waiting_viewer',payload_id=digest(arguments),arguments=arguments,
                project_id=session.manifest['project_id'],source_id=manifest['source_id'],build_id=expected_build,objects=ids,region=region)
            previous=session.state.get('focus_job')
            if previous:
                old=session.job(previous)
                if old['status']=='waiting_viewer':
                    old.update(status='superseded',superseded_by=job_id);session._save_job(old)
                    session._emit('show_superseded',job_id=previous,superseded_by=job_id)
            session._save_job(job);session.state['focus_job']=job_id
            session._emit('show_requested',job_id=job_id,build_id=expected_build,objects=ids,region=region)
            return job

    def acknowledge_show(self, *, key, job_id, build_id, camera):
        session=self.session
        with session.mutex:
            job=session.job(job_id)
            if job['kind']!='show' or job['build_id']!=build_id:raise StudError('stale_target','Viewer focus acknowledgement has another model.')
            if job['status']=='complete':return job
            if session.state.get('focus_job')!=job_id:raise StudError('stale_target','A newer focus request superseded this one.')
            from .display import displayed_manifest
            manifest,_=displayed_manifest(session)
            if manifest['build_id']!=build_id:raise StudError('stale_target','The displayed model changed before focus was applied.',expected=build_id,current=manifest['build_id'])
            import math
            if not isinstance(camera,dict) or any(not isinstance(camera.get(field),list) or len(camera[field])!=count or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in camera[field]) for field,count in [('position',3),('quaternion',4)]):
                raise StudError('invalid_viewer_ack','Focus acknowledgement requires finite camera position and orientation.')
            job.update(status='complete',result=dict(build_id=build_id,objects=job['objects'],region=job['region'],camera=camera))
            session._save_job(job);session._emit('show_complete',job_id=job_id,build_id=build_id)
            return job


def manifest_scope(manifest,scope):
    objects={p['id']:p for p in manifest['objects']};assemblies={a['id']:a for a in manifest['assemblies']}
    if scope is None:return sorted(objects)
    result=set()
    for target in scope:
        if target in objects:result.add(target)
        elif target in assemblies:
            for obj in objects.values():
                parent=obj['parent']
                while parent:
                    if parent==target:result.add(obj['id']);break
                    parent=assemblies[parent]['parent']
        else:raise StudError('unresolved_reference','A focus target is missing.',references=[target])
    return sorted(result)
