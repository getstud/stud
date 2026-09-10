"""Shared project protocol primitives, independent of HTTP and CadQuery."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

SCHEMA_VERSION = 1


class StudError(ValueError):
    def __init__(self, category, message, *, expected=None, current=None,
                 references=None, retryable=False):
        super().__init__(message)
        self.category = category
        self.expected = expected
        self.current = current
        self.references = references or []
        self.retryable = retryable

    def as_dict(self):
        return dict(category=self.category, message=str(self), expected=self.expected,
                    current=self.current, references=self.references, retryable=self.retryable)


def identifier(kind):
    return f'{kind}_{uuid.uuid4().hex}'


def manifest_name(version=None):
    if version is None or version=='final':return 'manifest.json'
    if version=='geometry':return 'geometry.json'
    if isinstance(version,bool) or not str(version).isdigit() or int(version)<1:
        raise StudError('invalid_manifest_version','Use a positive publication sequence, geometry, or final.')
    return f'partials/{int(version)}.json'


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else encoded(value)).hexdigest()


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_bytes()) if path.exists() else default


def sync_directory(path):
    if os.name == 'nt':
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path, data):
    """Acknowledge only after contents and directory entry are durable."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_json(path, value):
    atomic_write(path, encoded(value) + b'\n')


def confined(root, relative):
    """Project inputs and artifact paths must be regular paths inside their root."""
    root = Path(root).resolve()
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
        raise StudError('invalid_path', f'Expected a project-relative path: {relative}')
    candidate = root / relative
    if not candidate.resolve().is_relative_to(root):
        raise StudError('invalid_path', f'Path escapes its project: {relative}')
    for part in [candidate, *candidate.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise StudError('invalid_path', f'Symlink inputs are not supported: {relative}')
    return candidate


class ProjectLock:
    """An OS-held lock, released by the OS on process death (not a stale PID file)."""
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.stream.seek(0)
                if not self.stream.read(1):
                    self.stream.write(b'\0')
                    self.stream.flush()
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.stream.close()
            raise StudError('coordinator_busy', 'This project already has a coordinator.',
                            retryable=True) from error

    def close(self):
        if self.stream.closed:
            return
        if os.name == 'nt':
            import msvcrt
            self.stream.seek(0)
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        self.stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
