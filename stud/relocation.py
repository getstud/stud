"""Repair rebuildable coordination paths when an entire project folder moves."""
from pathlib import Path, PurePosixPath, PureWindowsPath

from .contracts import StudError, read_json, write_json


def stored_path(value):
    return PureWindowsPath(value) if PureWindowsPath(value).drive else PurePosixPath(value)


def repair_local_paths(root, history):
    root = Path(root).resolve()
    local = root / '.stud'
    location = read_json(local / 'location.json')
    old = location.get('root') if location else None
    if not old:
        # Upgrade pre-location sessions from a generated request workspace path.
        for file in (local / 'requests').glob('*.json'):
            workspace = read_json(file).get('workspace')
            if workspace and stored_path(workspace).parent.name == 'workspaces' and stored_path(workspace).parent.parent.name == '.stud':
                old = str(stored_path(workspace).parent.parent.parent)
                break
    if old and old != str(root):
        old_path = stored_path(old)
        path_keys = {'workspace', 'source_path', 'artifact_path', 'manifest',
                     'result_path', 'path', 'directory', 'pdf'}

        def relocate(value, key=None):
            if isinstance(value, dict):
                return {k: relocate(v, k) for k, v in value.items()}
            if isinstance(value, list):
                return [relocate(v, key) for v in value]
            if key in path_keys and isinstance(value, str):
                try:
                    relative = stored_path(value).relative_to(old_path)
                except ValueError:
                    return value
                if relative.parts and relative.parts[0] in ('.stud', 'exports'):
                    return str(root.joinpath(*relative.parts))
            return value

        # Never rewrite saved source, immutable manifests, or Git records.
        for directory in ('requests', 'jobs', 'historical_sources', 'comparisons', 'inspection_receipts', 'live_receipts'):
            for file in (local / directory).rglob('*'):
                if not file.is_file():
                    continue
                value = read_json(file)
                updated = relocate(value)
                if updated != value:
                    write_json(file, updated)
        workspaces = [path for path in (local / 'workspaces').iterdir() if path.is_dir()] if (local / 'workspaces').exists() else []
        if workspaces:
            result = history.git('worktree', 'repair', *map(str, workspaces), check=False)
            if result.returncode:
                raise StudError('relocation_failed', result.stderr.decode(errors='replace'))
        # A copied endpoint belongs to the original coordinator process.
        (local / 'endpoint.json').unlink(missing_ok=True)
    write_json(local / 'location.json', {'root': str(root)})
