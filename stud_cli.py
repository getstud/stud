"""Command-line entry point for the stud design workshop."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def init_project(destination, name=None):
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
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description='stud — a local design workshop')
    version_file = ROOT / 'version.json'
    if not version_file.exists():
        version_file = ROOT / 'package.json'
    version = json.loads(version_file.read_text())['version']
    parser.add_argument('--version', action='version', version=f'stud {version}')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='Create a new project with a starter model')
    init.add_argument('directory', type=Path)
    init.add_argument('--name')
    for name, help_text in [('serve', 'Open a project in the local 3D viewer'),
                            ('build', 'Validate and export a project'),
                            ('validate', 'Check declared model relationships')]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument('directory', nargs='?', type=Path, default=Path.cwd())
        if name == 'serve':
            command.add_argument('--port', type=int, default=8765)
        if name == 'validate':
            command.add_argument('--json', action='store_true')
            command.add_argument('--strict', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            destination = init_project(args.directory, args.name)
            print(f'Created stud project: {destination}')
            print(f'Open with: stud serve {json.dumps(str(destination))}')
        elif args.command == 'build':
            from build import build
            build(args.directory)
        elif args.command == 'serve':
            from serve import serve
            serve(args.directory, args.port)
        else:
            flags = [flag for flag in ('--json', '--strict') if getattr(args, flag[2:])]
            return subprocess.call([sys.executable, '-B', '-E', '-s', str(ROOT/'validate.py'),
                                    '--project', str(args.directory.resolve()), *flags])
    except (ValueError, OSError, KeyError, SyntaxError) as error:
        print(f'stud: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
