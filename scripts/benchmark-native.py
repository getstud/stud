"""Measure real project jobs and compare edited results with fresh evaluation.

Each project is isolated in a new temporary directory. No source execution or
geometry cache is substituted for the full worker. Scene reuse is checked by
the companion browser workload against these saved full results.
"""
import argparse
import json
from pathlib import Path
import platform
import sys
import tempfile
import time

ENGINE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ENGINE))
from stud.contracts import read_json,write_json
from stud.history import initialize
from stud.session import Session
from native_evidence import compare_native_evidence


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('cases',nargs='*',default=['workbench','shed','framing','mansion'])
    parser.add_argument('--output',type=Path)
    parser.add_argument('--edits',action='store_true')
    parser.add_argument('--plans',action='store_true')
    args=parser.parse_args()
    base=args.output or Path(tempfile.mkdtemp(prefix='stud-performance-'))
    base.mkdir(parents=True,exist_ok=True)
    evidence=dict(platform=platform.platform(),python=platform.python_version(),root=str(base),cases=[])
    def save():write_json(base/'performance.json',evidence)
    print('EVIDENCE '+str(base/'performance.json'),flush=True)
    for name in args.cases:
        root=base/name;root.mkdir()
        (root/'design.py').write_text("from stud.cad import Model\nmodel=Model('Initial',units='in')\n")
        initial=initialize(root,name,units="in")
        case=dict(name=name,project=str(root),runs=[]);evidence['cases'].append(case)
        with Session(root) as session:
            def run(label,source_text=None,parameters=None,repeat=False):
                started=time.perf_counter()
                request=session.begin(key=label,expected_head=session.snapshot()['option']['head'],intent=label)
                workspace=Path(request['workspace'])
                if name=='framing':
                    (workspace/'design.py').write_text("import cadquery as cq\nfrom stud.cad import Model\nfrom stud.buildings import framed_wall\nmodel=Model('Repeated framing',units='in')\nfor i in range(24):\n    framed_wall(model,object_id=f'wall.{i}',length=168,location=cq.Location(cq.Vector(0,i*40,0)),sheathing=False)\n")
                else:
                    for path in (ENGINE/'examples'/('cadquery-'+name)).glob('*.py'):
                        (workspace/path.name).write_bytes(path.read_bytes())
                if parameters is not None:
                    (workspace/'design.py').write_text("from stud.cad import Model\nfrom mansion import residence\nmodel=Model('Courtyard residence framing study',units='in')\nresidence(model,**"+repr(parameters)+")\n")
                if source_text:(workspace/'design.py').write_text(source_text)
                capture_started=time.perf_counter();source=session.source(request['id'])['source_id'];capture_seconds=time.perf_counter()-capture_started
                build=session.wait(session.evaluate(request['id'],source)['id'],timeout=1800)
                if build['status']!='complete':raise RuntimeError(build)
                manifest=read_json(Path(build['artifact_path'])/'manifest.json')
                row=dict(label=label,source_id=source,build_id=build['id'],artifact_path=build['artifact_path'],
                    source_capture_seconds=capture_seconds,evaluate_seconds=time.perf_counter()-capture_started,
                    worker_seconds=manifest['elapsed_seconds'],stages=manifest['timings'],peak_memory_bytes=manifest.get('peak_memory_bytes'),
                    query_types=manifest['checks'].get('timings'),
                    parts=len(manifest['objects']),assets=len(manifest['assets']),checks=manifest['checks']['coverage'],
                    failed_requirements=[finding for finding in manifest['checks']['findings'] if finding['status']!='passed'],
                    fabrication_findings=manifest['fabrication_findings'],
                    mesh_bytes=sum((Path(build['artifact_path'])/asset['mesh']).stat().st_size for asset in manifest['assets'].values()),
                    manifest_bytes=(Path(build['artifact_path'])/'manifest.json').stat().st_size)
                row['preview_bytes']=sum(path.stat().st_size for path in (Path(build['artifact_path'])/'partials').glob('*.json'))
                row['preview_count']=len(list((Path(build['artifact_path'])/'partials').glob('*.json')))
                if repeat:
                    full=session.wait(session.evaluate(request['id'],source,full_checks=True)['id'],timeout=1800)
                    if full['status']!='complete':raise RuntimeError(full)
                    full_manifest=read_json(Path(full['artifact_path'])/'manifest.json')
                    row['full_evaluation_comparison']=compare_native_evidence(build['artifact_path'],full['artifact_path'])
                    row['independent_full_evaluation_agrees']=row['full_evaluation_comparison']['equivalent']
                finish_started=time.perf_counter()
                finished=session.wait(session.finish(request['id'],expected_source=source,summary=label)['id'],timeout=1800)
                if finished['status']!='complete':raise RuntimeError(finished)
                row['finish_seconds']=time.perf_counter()-finish_started;row['checkpoint']=finished['checkpoint']
                history_started=time.perf_counter();report=session.history.checkpoint_report(finished['checkpoint']);row['historical_read_seconds']=time.perf_counter()-history_started
                row['estimate_seconds']=report['original_estimate'].get('elapsed_seconds')
                row['estimate_id']=report['original_estimate'].get('id')
                if args.plans and label=='baseline':
                    plan_started=time.perf_counter()
                    # House-scale drawing cost uses authored overview/detail
                    # sheets. Small DIY cases include their complete cut packet.
                    options=dict(views=['house.floor_overview','house.west.level1.kitchen.front.elevation','house.west.level2.kitchen.roof.bearing_detail'],include_lists=False) if name=='mansion' else {}
                    packet=session.wait(session.plans(key='performance-plan',checkpoint=finished['checkpoint'],build_id=finished['build_id'],**options)['id'],timeout=1800)
                    if packet['status']!='complete':raise RuntimeError(packet)
                    row['plan_seconds']=time.perf_counter()-plan_started;row['plan_pdf']=packet['result']['pdf'];row['plan_pages']=len(packet['result']['sheets']);row['plan_scope']=options or 'full packet'
                row['total_seconds']=time.perf_counter()-started;case['runs'].append(row);save()
                print(json.dumps(dict(case=name,**{k:row[k] for k in ('label','parts','worker_seconds','peak_memory_bytes','checkpoint')})),flush=True)
                return row
            baseline=run('baseline',parameters={} if name=='mansion' else None)
            if args.edits and name=='mansion':
                for label,parameters in [
                    ('local_opening',dict(local_window_width=58)),
                    ('shared_windows',dict(local_window_width=58,window_width=44)),
                    ('whole_building_rotation',dict(local_window_width=58,window_width=44,rotation=23)),
                    ('remove_module_and_change_roof',dict(include_guest=False,slope=.5,bore_diameter=.625)),
                    ('restore_defaults',{}),
                ]:
                    changed=run(label,parameters=parameters,repeat=True)
                    comparison_started=time.perf_counter()
                    job=session.wait(session.compare_versions(key=label+'-comparison',left=baseline['checkpoint'],right=changed['checkpoint'],mode='common_price')['id'],timeout=1800)
                    if job['status']!='complete':raise RuntimeError(job)
                    changed['comparison_seconds']=time.perf_counter()-comparison_started;changed['comparison_job']=job['id'];save()
        save()


if __name__=='__main__':main()
