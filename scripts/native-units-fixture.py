"""Serve one independently authored native-unit board for browser acceptance."""
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from stud.history import initialize
from stud.session import Session
from stud.session_http import serve_project

units=sys.argv[1]
assert units in ('in','mm')
w,d,h,x,y=(1.5,3.5,24,10,20) if units=='in' else (38.1,88.9,609.6,254,508)
root=Path(tempfile.mkdtemp(prefix='stud-browser-'+units+'-'))
(root/'design.py').write_text(f'''import cadquery as cq
from stud.cad import Model
model=Model('Exact stock — {units}',units={units!r})
model.assembly('frame','Frame')
model.part('board',cq.Workplane('XY').box({w},{d},{h},centered=(False,False,False)),
    parent='frame',location=cq.Location(cq.Vector({x},{y},0)),material='lumber',
    blank={{'size':[{w},{d},{h}],'cut_length':{h}}})
model.reference('board','a',point=(0,0,0))
model.reference('board','b',point=({w},0,0))
model.requirement('width','length',['board:a','board:b'],threshold={w})
model.dimension('width','board:a','board:b',label='Board thickness')
''',encoding='utf-8')
initial=initialize(root,units=units)
with Session(root) as session:
    request=session.begin(key='board',expected_head=initial['checkpoint'],intent='Inspect native stock')
    source=session.source(request['id'])['source_id']
    session.wait(session.evaluate(request['id'],source)['id'],timeout=600)
    result=session.wait(session.finish(request['id'],expected_source=source,summary='Exact native stock')['id'])
    if result['status']!='complete':raise RuntimeError(result)
serve_project(root,ready=lambda endpoint:print('READY '+json.dumps(dict(root=str(root),units=units,**endpoint)),flush=True))
