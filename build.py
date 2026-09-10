"""Build a project using its declared engine and shared session interface."""
import csv, hashlib, io, json, os, tempfile
from pathlib import Path
from runpy import run_path


def compile_project(project_dir=None):
    import sys
    root = Path(project_dir or Path.cwd()).resolve()
    # Resolve project assets consistently and never reuse stale helper bytecode.
    previous_cwd = Path.cwd()
    previous_path = sys.path[:]
    previous_cache = sys.pycache_prefix
    previous_bytecode = sys.dont_write_bytecode
    previous_modules = set(sys.modules)
    with tempfile.TemporaryDirectory(prefix='stud-cache-') as cache:
        sys.path.insert(0, str(root))
        sys.pycache_prefix = cache
        sys.dont_write_bytecode = True
        try:
            os.chdir(root)
            project = run_path(str(root / 'design.py'))['project']
            data = project.export()
        finally:
            os.chdir(previous_cwd)
            sys.path[:] = previous_path
            sys.pycache_prefix = previous_cache
            sys.dont_write_bytecode = previous_bytecode
            for name in set(sys.modules) - previous_modules:
                file = getattr(sys.modules[name], '__file__', None)
                if file and Path(file).resolve().is_relative_to(root):
                    sys.modules.pop(name, None)
    from stud.environment import snapshot_environment
    data['environment'] = snapshot_environment(root, data.get('environment', []))
    serialized=json.dumps(data,sort_keys=True,allow_nan=False)
    data['revision']=hashlib.sha256(serialized.encode()).hexdigest()[:12]
    return data

def parts_csv(data):
    stream=io.StringIO(); w=csv.writer(stream)
    w.writerow(['part_id','assembly','material','x_in','y_in','z_in','status','note','blank_size_in','profile_heights_in','wall_seats_in','outline_yz_in','profile_bands_in'])
    for p in data['parts']: w.writerow([p['id'],p['assembly'],data['stocks'][p['stock']]['name'],*p['size'],p['status'],p['note'],json.dumps(p.get('blank_size')),json.dumps(p.get('profile')),json.dumps(p.get('seats')),json.dumps(p.get('outline')),json.dumps(p.get('profile',{}).get('bands'))])
    return stream.getvalue()

def build(project_dir=None):
    root = Path(project_dir or Path.cwd()).resolve()
    if (root / 'stud.json').is_file():
        from stud.client import Client
        client = Client(root)
        active = client.get('/api/v1/status')['request']
        job = client.command('evaluate', {'request_id': active['id']}) if active and Path(active['workspace']).resolve() == root else client.command('evaluate_checkpoint', {'display': True})
        result = client.wait(job['id'])
        print(json.dumps(result))
        if result['status'] != 'complete':
            raise SystemExit(1)
        return client.get('/api/v1/builds/' + job['id'] + '/manifest.json')
    data=compile_project(root)
    out=root/'output/model';out.mkdir(parents=True,exist_ok=True)
    from validate import validate
    from validation_rules import coverage
    findings=validate(data)
    data['validation_results'] = dict(findings=findings, coverage=coverage(data, findings))
    report=out/'validation.json'
    temp=report.with_suffix('.tmp')
    temp.write_text(json.dumps(dict(revision=data['revision'],**data['validation_results']),indent=2), encoding='utf-8')
    os.replace(temp,report)
    failures=[f for f in findings if f['status']=='FAIL']
    if failures:
        for f in failures: print(f"FAIL {f['rule']} {f['parts']}: {f['message']}")
        raise SystemExit(1)
    print(f"Validation: {sum(f['status']=='PASS' for f in findings)} passed, {sum(f['status']=='WARNING' for f in findings)} warnings, {sum(f['status']=='UNVERIFIED' for f in findings)} unverified. Report: {report}")
    for name,body in [('model.json',json.dumps(data,indent=2)),('parts.csv',parts_csv(data))]:
        path=out/name; temp=path.with_suffix('.tmp');temp.write_text(body, encoding='utf-8');os.replace(temp,path)
    print(f"Built {len(data['parts'])} parts / revision {data['revision']}")

    return data

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path.cwd())
    build(parser.parse_args().project)
