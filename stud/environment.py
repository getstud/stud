"""Snapshot project-owned environment resources for revision-safe browser imports."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile


def asset_path(source):
    if not isinstance(source, str) or '\\' in source:
        raise ValueError('Environment source must be a path under assets/')
    path = PurePosixPath(source)
    if path.is_absolute() or '..' in path.parts or len(path.parts) < 2 or path.parts[0] != 'assets' or path.suffix not in ('.js', '.mjs'):
        raise ValueError('Environment source must be a .js or .mjs file under assets/')
    return path.as_posix()


def _snapshot_environment(root, assets):
    """Keep missing/broken resources separate from construction build failures."""
    if not assets:
        return []
    base = root / 'assets'
    files = {}
    for path in sorted(base.rglob('*')):
        if path.is_file() and path.resolve().is_relative_to(base.resolve()) and base.resolve().is_relative_to(root):
            files[path.relative_to(root).as_posix()] = path.read_bytes()
    digest = hashlib.sha256()
    for name, content in files.items():
        digest.update(json.dumps([name, len(content)]).encode())
        digest.update(content)
    revision = digest.hexdigest()[:20]
    destination = root / 'output/environment' / revision
    if files and not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
            staging = Path(temp) / 'snapshot'
            staging.mkdir()
            for name, content in files.items():
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            try:
                staging.rename(destination)
            except OSError:
                if not destination.is_dir():
                    raise
    result = []
    for asset in assets:
        entry = dict(asset, revision=revision)
        if asset['source'] not in files:
            entry['error'] = f"Environment module not found: {asset['source']}"
        result.append(entry)
    return result


def snapshot_environment(root, assets):
    try:
        return _snapshot_environment(root.resolve(), assets)
    except (OSError, RuntimeError) as error:
        # An unavailable resource must not prevent a construction revision.
        return [dict(asset, revision='unavailable', error=f'Environment resources unavailable: {error}') for asset in assets]


def environment_stamp(root):
    """Asset save/delete races and permission changes must not stop the watcher."""
    result = []
    try:
        for path in sorted((root / 'assets').rglob('*')):
            try:
                stat = path.stat()
                result.append((str(path), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size))
            except OSError as error:
                result.append((str(path), str(error)))
    except OSError as error:
        result.append(('assets', str(error)))
    return tuple(result)
