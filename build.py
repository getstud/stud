"""Compile once: python3 build.py. No third-party Python dependencies."""
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
    w.writerow(['part_id','assembly','material','x_in','y_in','z_in','status','note','blank_size_in','profile_heights_in','wall_seats_in'])
    for p in data['parts']: w.writerow([p['id'],p['assembly'],data['stocks'][p['stock']]['name'],*p['size'],p['status'],p['note'],json.dumps(p.get('blank_size')),json.dumps(p.get('profile')),json.dumps(p.get('seats'))])
    return stream.getvalue()

def build(project_dir=None):
    root = Path(project_dir or Path.cwd()).resolve()
    data=compile_project(root)
    out=root/'output/model';out.mkdir(parents=True,exist_ok=True)
    from validate import validate
    from validation_rules import coverage
    findings=validate(data)
    data['validation_results'] = dict(findings=findings, coverage=coverage(data, findings))
    report=out/'validation.json'
    temp=report.with_suffix('.tmp')
    temp.write_text(json.dumps(dict(revision=data['revision'],**data['validation_results']),indent=2))
    os.replace(temp,report)
    failures=[f for f in findings if f['status']=='FAIL']
    if failures:
        for f in failures: print(f"FAIL {f['rule']} {f['parts']}: {f['message']}")
        raise SystemExit(1)
    print(f"Validation: {sum(f['status']=='PASS' for f in findings)} passed, {sum(f['status']=='WARNING' for f in findings)} warnings, {sum(f['status']=='UNVERIFIED' for f in findings)} unverified. Report: {report}")
    for name,body in [('model.json',json.dumps(data,indent=2)),('parts.csv',parts_csv(data))]:
        path=out/name; temp=path.with_suffix('.tmp');temp.write_text(body);os.replace(temp,path)
    print(f"Built {len(data['parts'])} parts / revision {data['revision']}")

    return data

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path.cwd())
    build(parser.parse_args().project)
