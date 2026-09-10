"""Capture the declared source set without executing project Python."""
import importlib.metadata
import platform
import re
from pathlib import Path, PurePosixPath
import shutil
import tempfile

from .contracts import StudError, confined, digest, encoded, read_json, write_json, sync_directory

DEPENDENCIES = {'cadquery': '2.6.1', 'cadquery-ocp': '7.8.1.1.post1',
                'reportlab': '4.4.4', 'svglib': '1.5.1'}


def runtime_fingerprint():
    lock = Path(__file__).resolve().parents[1] / 'requirements.lock'
    locked = dict(re.findall(r'^([A-Za-z0-9_.-]+)==([^\s;]+)', lock.read_text(), re.MULTILINE)) if lock.is_file() else DEPENDENCIES
    versions = {}
    for name in locked:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    engine_root = Path(__file__).resolve().parent
    engine = {path.name: digest(path.read_bytes()) for path in engine_root.glob('*.py')}
    details = dict(python=platform.python_version(), implementation=platform.python_implementation(),
                   platform=platform.system(), machine=platform.machine(), packages=versions)
    details['engine_id'] = digest(engine)
    details['dependency_lock_id'] = digest(lock.read_bytes()) if lock.is_file() else None
    return dict(id=digest(details), **details)


def new_manifest(name, project_id):
    return dict(schema_version=1, project_id=project_id, name=name, engine='cadquery',
                entrypoint='design.py', source_files=['*.py', 'src/**/*.py', 'inputs/**/*'],
                units='mm', display_units='imperial', runtime={'packages': DEPENDENCIES},
                evaluation={'deterministic': False, 'linear_tolerance_mm': 0.1,
                            'angular_tolerance': 0.1, 'query_tolerance_mm': 0.01},
                print={'paper': 'letter', 'margin_mm': 12.7, 'template_version': 1})


def manifest_at(root):
    manifest = read_json(confined(root, 'stud.json'))
    if not isinstance(manifest, dict) or manifest.get('schema_version') != 1:
        raise StudError('migration_required', 'This folder needs an explicit stud project conversion.')
    if manifest.get('engine') != 'cadquery' or manifest.get('units') != 'mm':
        raise StudError('unsupported_project', 'Expected a CadQuery project with millimeter coordinates.')
    if not manifest.get('project_id') or not isinstance(manifest.get('source_files'), list):
        raise StudError('invalid_manifest', 'Project identity and declared source files are required.')
    confined(root, manifest['entrypoint'])
    return manifest


def source_files(root, manifest):
    root = Path(root)
    files = {'stud.json', manifest['entrypoint']}
    for pattern in manifest['source_files']:
        if not isinstance(pattern, str) or not pattern or Path(pattern).is_absolute() or '..' in Path(pattern).parts:
            raise StudError('invalid_manifest', f'Invalid source pattern: {pattern}')
        for file in root.glob(pattern):
            if file.is_file():
                files.add(file.relative_to(root).as_posix())
    reserved = {'.git', '.stud', 'records', 'checkpoints', 'exports', 'annotations'}
    for relative in files:
        if Path(relative).parts[0] in reserved or relative == 'estimating.json':
            raise StudError('invalid_manifest', f'Records and estimates are not modeling source: {relative}')
        if not confined(root, relative).is_file():
            raise StudError('missing_source', f'Declared source is missing: {relative}')
    return sorted(files)


def matches_source(name, manifest):
    """The same anchored, recursive-glob semantics used by Path.glob above."""
    return name in ('stud.json', manifest['entrypoint']) or any(
        PurePosixPath(name).full_match(pattern) for pattern in manifest['source_files'])


def read_source(root):
    manifest = manifest_at(root)
    return {name: confined(root, name).read_bytes() for name in source_files(root, manifest)}


def source_identity(files):
    return digest({name: digest(body) for name, body in sorted(files.items())})


def evaluated_identity(manifest):
    """Compare reproduced evidence without execution IDs, timings or cache paths."""
    objects=[{k:v for k,v in obj.items() if k not in ('shape_key','provenance')} for obj in manifest.get('objects',[])]
    assemblies=[{k:v for k,v in obj.items() if k!='provenance'} for obj in manifest.get('assemblies',[])]
    return digest(dict(objects=sorted(objects,key=lambda obj:obj['id']),assemblies=sorted(assemblies,key=lambda obj:obj['id']),
        **{key:manifest.get(key) for key in ('name','units','references','requirements','demands','dimensions','drawings','steps','connections','notes')},
        findings=manifest.get('checks',{}).get('findings'),coverage=manifest.get('checks',{}).get('coverage')))


def capture(root, destination, expected=None):
    """Two content inventories catch same-size writes and source-set changes."""
    for _ in range(3):
        try:
            first = read_source(root)
            second = read_source(root)
        except FileNotFoundError:
            continue
        if first == second:
            break
    else:
        raise StudError('source_changing', 'Source changed during capture; retry after saving.', retryable=True)
    source_id = source_identity(first)
    if expected is not None and expected != source_id:
        raise StudError('stale_source', 'The captured source differs from the expected source.',
                        expected=expected, current=source_id)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    final = destination / source_id
    inventory = dict(schema_version=1, source_id=source_id,
                     files={name: digest(body) for name, body in first.items()})
    if final.exists():
        verify_snapshot(final)
    else:
        temporary = Path(tempfile.mkdtemp(prefix='.capture-', dir=destination))
        try:
            for name, body in first.items():
                path = confined(temporary / 'files', name)
                path.parent.mkdir(parents=True, exist_ok=True)
                from .contracts import atomic_write
                atomic_write(path, body)
            write_json(temporary / 'source.json', inventory)
            try:
                temporary.rename(final)
                sync_directory(destination)
            except OSError:
                if not final.exists():
                    raise
                # Another capture of the identical source may have published
                # while this one was writing. Verify it before adopting it.
                verify_snapshot(final)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return dict(**inventory, path=str(final))


def verify_snapshot(path):
    path = Path(path)
    record = read_json(path / 'source.json')
    if not record:
        raise StudError('unavailable_artifact', 'The source snapshot has no manifest.')
    for name, expected in record['files'].items():
        file = confined(path / 'files', name)
        if not file.is_file() or digest(file.read_bytes()) != expected:
            raise StudError('unavailable_artifact', 'A frozen source artifact is missing or corrupt.',
                            references=[name])
    if digest(record['files']) != record['source_id']:
        raise StudError('unavailable_artifact', 'The source inventory is corrupt.')
    return record
