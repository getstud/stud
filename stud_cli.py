"""Command-line entry point for the stud design workshop."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import sqlite3
from stud.projects import register, list_projects

ROOT = Path(__file__).resolve().parent


def init_legacy_project(destination, name=None):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError(f'Destination already exists: {destination}. Choose a new directory.')
    title = name or destination.name
    destination.mkdir(parents=True)
    (destination / 'design.py').write_text(f'''"""Edit this trusted local Python file; stud rebuilds the viewer automatically."""
from stud import Project

project = Project({title!r})
project.stock('2x4', 'Untreated 2x4', '#ddbd8b',
              section=(1.5, 3.5), lengths=(96, 120, 144))
project.box('frame.stud.01', 'Frame', '2x4',
            size=(1.5, 3.5, 80), origin=(0, 0, 0),
            note='Starter part. Replace with your own design.')
project.dimension('Height', (-4, 0, 0), (-4, 0, 80))
project.notes.append('Design study. Geometry and material quantities do not establish structural suitability.')
project.validation = {{'version': 1, 'automatic': ['solid_collision', 'stock_fit'], 'rules': []}}
''')
    (destination / '.gitignore').write_text('__pycache__/\n*.pyc\noutput/model/\n.DS_Store\n')
    (destination / 'README.md').write_text(f'''# {title}

Open this project with `stud serve .`; edit `design.py` to change the model.
Run `stud build .` for JSON and CSV exports, or `stud validate .` for checks.
Use the stud checkout's `python3 /path/to/stud_cli.py` if the command is not installed.

Saved comments and prices live in `annotations/`; keep them with this project.
Generated files live in `output/model/`. Units are inches, with Z up.
Only open trusted designs: design.py and its helpers are executable Python.
''')
    register(destination, title)
    return destination


def init_project(destination, name=None, example=None):
    """New projects use the CadQuery authoring and explicit request contract."""
    destination=Path(destination).resolve()
    if destination.exists():
        raise ValueError(f'Destination already exists: {destination}. Choose a new directory.')
    destination.mkdir(parents=True)
    title=name or destination.name
    (destination/'design.py').write_text(f'''"""Edit in the workspace returned by stud begin, then stud finish the request."""
import cadquery as cq
from stud.cad import Model

model = Model({title!r})
model.part('starter', cq.Workplane('XY').box(600, 38, 89, centered=(False,False,False)),
           label='Starter member', material='lumber.38x89', blank={{'size_mm':[600,38,89], 'cut_length_mm':600,
               'operations':[{{'kind':'square_cut','finished_length_mm':600}}]}})
model.reference('starter','left',point=(0,0,0))
model.reference('starter','right',point=(600,0,0))
model.requirement('starter.length','length',['starter:left','starter:right'],threshold=600)
model.requirement('starter.blank','stock_fit',['starter'])
model.demand('starter.lumber',product_id='lumber.38x89',specification={{'material':'softwood','section_mm':[38,89]}},
             object_ids=['starter'],purchase_unit='board',unit='mm',stock_lengths_mm=[2400],
             cuts_mm=[{{'object_id':'starter','length_mm':600}}])
model.dimension('starter.length','starter:left','starter:right',label='Length')
model.drawing('starter.front',dimensions=['starter.length'])
''')
    if example:
        import shutil
        for source in (ROOT/'examples'/('cadquery-'+example)).glob('*.py'):
            shutil.copyfile(source,destination/source.name)
    from stud.history import initialize
    initialize(destination,title)
    (destination/'README.md').write_text(f'''# {title}

Open with `stud serve .`. Geometry is ordinary Python and CadQuery in millimeters.

For a design change, inspect `stud status .`, begin a request with its expected
option head, edit the returned workspace, evaluate, and finish with its source ID.
The complete command protocol is documented in stud's CadQuery project guide.

Keep the entire folder: `records/` contains review/pricing history, `exports/`
contains immutable PDF packets, and `.stud/` contains recoverable local drafts.
Only open trusted projects: the design executes Python.
''')
    register(destination,title)
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description='stud — a local design workshop')
    version_file = ROOT / 'version.json'
    if not version_file.exists():
        version_file = ROOT / 'package.json'
    version = json.loads(version_file.read_text())['version']
    parser.add_argument('--version', action='version', version=f'stud {version}')
    commands = parser.add_subparsers(dest='command', required=True)
    catalog = commands.add_parser('projects', help='List remembered projects or register an existing folder')
    catalog.add_argument('--add', type=Path)
    catalog.add_argument('--json', action='store_true')
    init = commands.add_parser('init', help='Create a new project with a starter model')
    init.add_argument('directory', type=Path)
    init.add_argument('--name')
    init.add_argument('--example',choices=['workbench','opening','roof-joint','shed','mansion'])
    commands.add_parser('doctor', help='Check bundled Python, CadQuery, PDF and Git runtime')
    for operation in ('status','begin','source','evaluate','finish','cancel','job','plans',
                      'option-create','option-activate','option-rename','restore','compare','prompts','prices','measure',
                      'options','checkpoints','inspect','live','show','stop'):
        command=commands.add_parser(operation,help=f'Project session: {operation}')
        command.add_argument('directory',nargs='?',type=Path,default=Path.cwd())
        command.add_argument('--key')
        if operation in ('source','evaluate','finish','cancel'):
            command.add_argument('--request',required=True)
        if operation in ('evaluate','finish'):
            command.add_argument('--source',required=operation=='finish')
        if operation=='evaluate':command.add_argument('--full-checks',action='store_true',help='Bypass native query reuse for an independent full check')
        if operation=='begin':
            command.add_argument('--intent',required=True)
            command.add_argument('--expected-head',required=True)
            command.add_argument('--option')
        if operation=='finish':
            command.add_argument('--summary',required=True)
            command.add_argument('--addressed-prompt',action='append',default=[])
        if operation=='job':command.add_argument('--id',required=True)
        if operation in ('plans','restore','inspect'):command.add_argument('--checkpoint',required=True)
        if operation=='plans':
            command.add_argument('--build')
            command.add_argument('--paper',choices=['letter','a4'],default='letter')
            command.add_argument('--layout',choices=['compact','expanded'],default='compact')
            command.add_argument('--scale',type=float)
            command.add_argument('--view',action='append')
            command.add_argument('--drawings-only',action='store_true',help='Omit the companion fabrication-list pages')
        if operation=='option-create':
            command.add_argument('--name',required=True);command.add_argument('--base',required=True)
        if operation=='option-rename':
            command.add_argument('--name',required=True);command.add_argument('--option',required=True);command.add_argument('--expected-revision',type=int,required=True)
        if operation in ('option-activate','restore'):
            command.add_argument('--option',required=True);command.add_argument('--expected-head',required=True)
        if operation=='compare':
            command.add_argument('--left',required=True);command.add_argument('--right',required=True)
            command.add_argument('--mode',choices=['historical','common_price'],required=True)
        if operation in ('prices','measure','show'):command.add_argument('--input',type=Path,required=True)
        if operation in ('evaluate','finish','job','plans','restore','compare','measure','inspect','show'):
            command.add_argument('--wait',action='store_true')
    for name, help_text in [('serve', 'Open a project in the local 3D viewer'),
                            ('build', 'Validate and export a project'),
                            ('validate', 'Check declared model relationships')]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument('directory', nargs='?', type=Path, default=Path.cwd())
        if name == 'serve':
            command.add_argument('--port', type=int, default=8765)
            command.add_argument('--no-open', action='store_true', help='Print the viewer URL without opening a browser')
        if name == 'validate':
            command.add_argument('--json', action='store_true')
            command.add_argument('--strict', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'doctor':
            from stud.runtime import doctor
            result = doctor()
            print(json.dumps(result))
            return 0 if result['status'] == 'healthy' else 1
        if args.command == 'projects':
            if args.add:
                register(args.add)
            projects = list_projects()
            if args.json:
                print(json.dumps(projects))
            else:
                for project in projects:
                    suffix = '' if project['available'] else ' (missing)'
                    print(f"{project['name']}: {project['path']}{suffix}")
            return 0
        if args.command not in ('init','status','job'):
            register(args.directory)
        if args.command not in ('init','serve','build','validate'):
            from stud.client import Client
            if args.command == 'stop':
                from stud.contracts import StudError
                try:
                    client = Client(args.directory, start=False)
                    result = client.command('shutdown', key=args.key)
                except StudError as error:
                    if error.category != 'coordinator_unavailable':
                        raise
                    result = {'status': 'stopped'}
                print(json.dumps(result))
                return 0
            client=Client(args.directory)
            arguments={}
            operation=args.command.replace('-','_')
            if operation=='status':result=client.get('/api/v1/status')
            elif operation=='job':result=client.wait(args.id) if args.wait else client.get('/api/v1/jobs/'+args.id)
            elif operation=='prompts':result=client.get('/api/v1/prompts')
            elif operation in ('options','checkpoints'):result=client.get('/api/v1/'+operation)
            else:
                if operation=='begin':arguments=dict(intent=args.intent,expected_head=args.expected_head,option_id=args.option)
                elif operation=='source':arguments=dict(request_id=args.request)
                elif operation=='evaluate':arguments=dict(request_id=args.request,expected_source=args.source,full_checks=args.full_checks)
                elif operation=='finish':arguments=dict(request_id=args.request,expected_source=args.source,summary=args.summary,addressed_prompt_ids=args.addressed_prompt)
                elif operation=='cancel':arguments=dict(request_id=args.request)
                elif operation=='plans':arguments=dict(checkpoint=args.checkpoint,build_id=args.build,views=args.view,include_lists=not args.drawings_only,print_spec={'paper':args.paper,'layout':args.layout,**({'scale':args.scale} if args.scale else {})})
                elif operation=='option_create':operation='create_option';arguments=dict(name=args.name,base_checkpoint=args.base)
                elif operation=='option_activate':operation='activate_option';arguments=dict(option_id=args.option,expected_head=args.expected_head)
                elif operation=='option_rename':operation='rename_option';arguments=dict(option_id=args.option,name=args.name,expected_revision=args.expected_revision)
                elif operation=='restore':arguments=dict(checkpoint=args.checkpoint,option_id=args.option,expected_head=args.expected_head)
                elif operation=='compare':arguments=dict(left=args.left,right=args.right,mode=args.mode)
                elif operation=='prices':operation='save_prices';arguments=json.loads(args.input.read_text())
                elif operation in ('measure','show'):arguments=json.loads(args.input.read_text())
                elif operation=='inspect':operation='inspect_checkpoint';arguments=dict(checkpoint=args.checkpoint)
                elif operation=='live':operation='return_live'
                result=client.command(operation,arguments,args.key)
                if getattr(args,'wait',False) and result.get('id') and result.get('kind'):
                    result=client.wait(result['id'])
            print(json.dumps(result,allow_nan=False))
            return 1 if isinstance(result,dict) and result.get('status') in ('failed','generation_failed') else 0
        if args.command == 'init':
            destination = init_project(args.directory, args.name, args.example)
            print(f'Created stud project: {destination}')
            skill = ROOT / 'skills' / 'stud-design'
            if not skill.is_dir():
                skill = ROOT.parent / 'skills' / 'stud-design'
            print(f'Before starting a design, install the skill from {json.dumps(str(skill))} in Codex if needed, '
                  'then load and follow stud-design.')
            print(f'Open with: stud serve {json.dumps(str(destination))}')
        elif args.command == 'build':
            if (args.directory/'stud.json').is_file():
                from stud.client import Client
                client=Client(args.directory)
                active=client.get('/api/v1/status')['request']
                if active and Path(active['workspace']).resolve()==args.directory.resolve():
                    job=client.command('evaluate',{'request_id':active['id']})
                else:job=client.command('evaluate_checkpoint',{'display':True})
                result=client.wait(job['id']);print(json.dumps(result))
                return 0 if result['status']=='complete' else 1
            from build import build
            build(args.directory)
        elif args.command == 'serve':
            from serve import serve
            serve(args.directory, args.port, open_browser=not args.no_open)
        else:
            if (args.directory/'stud.json').is_file():
                from stud.client import Client
                client=Client(args.directory)
                state=client.get('/api/v1/status')
                if not state['latest_build']:
                    job=client.command('evaluate_checkpoint',{'display':True})
                else:job=state['latest_job']
                job=client.wait(job['id'])
                manifest=client.get('/api/v1/builds/'+job['id']+'/manifest.json')
                checks=manifest.get('checks',{})
                print(json.dumps(checks))
                return 1 if job['status']!='complete' or checks.get('counts',{}).get('failed') else 2 if args.strict and not checks.get('all_passed') else 0
            flags = [flag for flag in ('--json', '--strict') if getattr(args, flag[2:])]
            return subprocess.call([sys.executable, '-B', '-E', '-s', str(ROOT/'validate.py'),
                                    '--project', str(args.directory.resolve()), *flags])
    except (ValueError, OSError, KeyError, SyntaxError, sqlite3.Error) as error:
        print(f'stud: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
