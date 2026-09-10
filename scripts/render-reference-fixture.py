"""Start an isolated HD rendering appearance fixture for manual or browser QA."""
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from stud.history import initialize
from stud.session import Session
from stud.session_http import serve_project

root=Path(tempfile.mkdtemp(prefix='stud-hd-render-'))
(root/'design.py').write_bytes((ROOT/'tests/fixtures/hd-shed.py').read_bytes())
initialize(root,'HD rendering appearance fixture',units='in')
with Session(root) as session:
    baseline=session.wait(session.evaluate_checkpoint(display=True,key='initial')['id'])
    if baseline['status']!='complete':raise RuntimeError(baseline)
serve_project(root,ready=lambda endpoint:print('READY '+json.dumps(dict(**endpoint,root=str(root),baseline=baseline['id'])),flush=True))
