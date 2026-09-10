"""Isolated real coordinator fixture for the interactive viewer acceptance run."""
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from stud.contracts import read_json
from stud.history import initialize
from stud.session import Session
from stud.session_http import serve_project
from stud.estimate import purchase_lines

root=Path(tempfile.mkdtemp(prefix='stud-browser-'))
(root/'workbench.py').write_bytes((Path(__file__).resolve().parents[1]/'examples/cadquery-workbench/workbench.py').read_bytes())
(root/'design.py').write_text("from stud.cad import Model\nmodel=Model('Initial',units='in')\n")
initialize(root,'Browser acceptance workbench',units='in')
def design(width):
    return "from stud.cad import Model\nfrom workbench import workbench\nmodel=Model('Workbench',units='in')\nworkbench(model,width="+str(width)+")\n"
with Session(root) as session:
    first=session.begin(key='first',expected_head=session.snapshot()['option']['head'],intent='Create the workbench')
    (Path(first['workspace'])/'design.py').write_text(design(72))
    source=session.source(first['id'])['source_id']
    build=session.wait(session.evaluate(first['id'],source)['id'])
    manifest=read_json(Path(build['artifact_path'])/'manifest.json')
    quotes=[]
    for index,line in enumerate(purchase_lines(manifest['demands'],{})):
        quotes.append(dict(id=f'fixture_quote_{index}',product_id=line['product_id'],specification=line['specification'],
            purchase_unit=line['purchase_unit'],pack_size=line['pack_size'],price=str([12,55,9.5,8][index%4]),currency='USD',
            supplier='Synthetic acceptance fixture',source='Locally authored test values',quote_date='2026-09-09',kind='manual'))
    session.save_prices(key='fixture-quotes',quotes=quotes)
    baseline=session.wait(session.finish(first['id'],expected_source=source,summary='Six foot workbench')['id'])
    if baseline['status']!='complete':raise RuntimeError(baseline)
    alternative=session.create_option(key='wide',name='Wider workbench',base_checkpoint=baseline['checkpoint'])
    session.activate_option(key='activate',option_id=alternative['id'],expected_head=alternative['head'])
    draft=session.begin(key='wide-design',expected_head=alternative['head'],intent='Widen the workbench')
    (Path(draft['workspace'])/'design.py').write_text(design(84))
    source=session.source(draft['id'])['source_id']
    wider=session.wait(session.finish(draft['id'],expected_source=source,summary='Seven foot workbench')['id'])
    if wider['status']!='complete':raise RuntimeError(wider)
    active=session.begin(key='interactive-edit',expected_head=wider['checkpoint'],intent='Add two loose setup blocks')
info=dict(root=str(root),baseline=baseline,wider=wider,active=active)
serve_project(root,ready=lambda endpoint:print('READY '+json.dumps(dict(**info,**endpoint)),flush=True))
