"""Short-lived, trusted-project CadQuery execution process. JSON lines are IPC."""
import argparse
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import runpy
import sys
import time
import traceback

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stud.contracts import confined, read_json, write_json
from stud.source import manifest_at, runtime_fingerprint
from stud.publication import GeometryPreview, PreviewPublisher


def run(job):
    started = time.perf_counter()
    directory = Path(job['artifact_path'])
    source = directory / 'execution'
    manifest = manifest_at(source)
    output = sys.stdout
    model = None
    publication_sequence = 0

    def write_preview(snapshot,data):
        nonlocal publication_sequence
        publication_sequence += 1
        partial = {**identity, **snapshot, 'publication_sequence':publication_sequence,
                    'artifact_stage':'partial',
                    'completion': {'geometry': 'partial', 'checks': 'pending', 'quantities': 'pending',
                                   'estimates': 'pending', 'plans': 'pending'}}
        write_json(directory / f'partials/{publication_sequence}.json', partial)
        write_json(directory / 'partial.json', partial)
        output.write(json.dumps(dict(type='part_batch',data=data),allow_nan=False)+'\n')
        output.flush()

    previews=PreviewPublisher(write_preview)
    preview_geometry=GeometryPreview()

    def publish(kind, data):
        nonlocal model
        if kind == 'model_created':
            if model is not None:
                raise ValueError('One published Model per design entrypoint is supported.')
            model = data
            return
        if kind == 'part_batch':
            # Assets are already fsynced before their ordered notification.
            frozen_started=time.perf_counter()
            snapshot=preview_geometry.freeze(model,data)
            previews.timings['snapshot_seconds']+=time.perf_counter()-frozen_started
            previews.submit(snapshot,data,frozen=True)
            return
        output.write(json.dumps(dict(type=kind, data=data), allow_nan=False) + '\n')
        output.flush()

    identity = {key: job[key] for key in ('project_id', 'request_id', 'source_id', 'build_id')}
    identity.update(schema_version=1, runtime=job['runtime'], settings=job['settings'])
    if job.get('checkpoint'):
        identity['checkpoint'] = job['checkpoint']
    completion = dict(geometry='unavailable', checks='pending', quantities='pending', estimates='pending', plans='pending')
    result = dict(**identity, objects=[], completion=completion)
    status = 0
    try:
        current_runtime = runtime_fingerprint()
        required = manifest['runtime']['packages']
        mismatch = {name: {'expected': version, 'current': current_runtime['packages'].get(name)}
                    for name, version in required.items() if current_runtime['packages'].get(name) != version}
        if mismatch:
            raise RuntimeError(f'Historical/project runtime unavailable: {mismatch}')
        if current_runtime['id'] != job['runtime']['id']:
            raise RuntimeError('Worker runtime differs from the scheduled runtime.')
        from stud.cad import Model, publication_context
        from stud.checks import check_model
        from stud.fabrication import audit_fabrication
        sys.path.insert(0, str(source))
        os.chdir(source)
        execution_started = time.perf_counter()
        with redirect_stdout(sys.stderr), publication_context(publish, directory, job['runtime'], job['settings']):
            try:
                namespace = runpy.run_path(str(source / manifest['entrypoint']), run_name='__stud_design__')
            finally:
                previews.close()
        if model is None or not isinstance(namespace.get('model', namespace.get('project')), Model):
            raise ValueError('The entrypoint must publish a stud.cad.Model named model or project.')
        model.timings['execution_seconds'] = time.perf_counter() - execution_started
        model.timings['preview_publication'] = previews.timings
        completion['geometry'] = 'complete'
        result.update(model.export())
        write_json(directory / 'geometry.json', {**result,'artifact_stage':'geometry'})
        publish('geometry_complete', dict(objects=list(model.objects), manifest='geometry.json'))
        publish('progress', dict(stage='checks', completed=0, total=len(model.requirements)))
        checks = check_model(model,cache_path=confined(directory.parent.parent,'query_cache/'+job['runtime']['id']+'.json'),
                             reuse=not job['settings'].get('full_checks',False))
        model.timings['solid_queries_seconds'] = checks['elapsed_seconds']
        result['checks'] = checks
        completion['checks'] = 'complete' if checks['coverage']['complete'] else 'incomplete'
        fabrication_started = time.perf_counter()
        result['fabrication_findings']=audit_fabrication(result)
        model.timings['fabrication_audit_seconds'] = time.perf_counter() - fabrication_started
        completion['quantities'] = 'complete' if model.demands and not result['fabrication_findings'] and all(not d.get('unresolved') for d in model.demands.values()) else 'incomplete'
        publish('checks_updated', checks)
    except BaseException as error:
        status = 1
        traceback.print_exc(file=sys.stderr)
        if model is not None:
            result.update(model.export())
            if completion['geometry'] != 'complete':
                completion['geometry'] = 'partial' if model.objects else 'unavailable'
        result['diagnostics'] = dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())
    result['completion'] = completion
    result['artifact_stage']='final'
    result['elapsed_seconds'] = time.perf_counter() - started
    try:
        import resource
        result['peak_memory_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
    except ImportError:
        result['peak_memory_bytes'] = None
    # Full bundles become visible through this final atomic pointer only.
    write_json(directory / 'manifest.json', result)
    return status


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(read_json(args.job)))
