"""Generate inspectable, fixed-checkpoint packets for the construction fixtures."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ENGINE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ENGINE))
from stud.contracts import read_json,write_json
from stud.history import initialize
from stud.session import Session

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('examples',nargs='*',default=['workbench','opening','roof-joint','shed'])
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    base=args.output or Path(tempfile.mkdtemp(prefix='stud-packets-'))
    base.mkdir(exist_ok=True,parents=True)
    evidence=[]
    for name in args.examples:
        root=base/name;root.mkdir()
        (root/'design.py').write_text("from stud.cad import Model\nmodel=Model('Initial')\n")
        initial=initialize(root,name)
        with Session(root) as session:
            request=session.begin(key='packet-fixture',expected_head=initial['checkpoint'],intent='Build the '+name+' packet fixture')
            (Path(request['workspace'])/'design.py').write_bytes((ENGINE/'examples'/('cadquery-'+name)/'design.py').read_bytes())
            source=session.source(request['id'])['source_id']
            finished=session.wait(session.finish(request['id'],expected_source=source,summary='Generate '+name+' fabrication evidence')['id'],timeout=600)
            if finished['status']!='complete':raise RuntimeError(finished)
            build=session.job(finished['build_id']);manifest=read_json(Path(build['artifact_path'])/'manifest.json')
            packet=session.wait(session.plans(key='packet',checkpoint=finished['checkpoint'],build_id=finished['build_id'])['id'],timeout=600)
            if packet['status']!='complete':raise RuntimeError(packet)
            row=dict(example=name,project=str(root),checkpoint=finished['checkpoint'],build_id=finished['build_id'],
                parts=len(manifest['objects']),checks=manifest['checks']['coverage'],fabrication=manifest['fabrication_findings'],
                pdf=packet['result']['pdf'],sheets=packet['result']['sheets'],completeness=packet['result']['completeness'])
            evidence.append(row);write_json(base/'evidence.json',evidence)
            print(json.dumps(dict(example=name,pdf=row['pdf'],pages=len(row['sheets']),parts=row['parts'],review=row['completeness']['findings'])),flush=True)
    print('EVIDENCE '+str(base/'evidence.json'),flush=True)

if __name__=='__main__':main()
