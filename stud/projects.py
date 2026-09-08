"""Per-user project catalog shared by the desktop app and CLI.

Listing and registering projects never imports executable design files.
"""
import os
from pathlib import Path
import sqlite3
import sys
from datetime import datetime, timezone


def catalog_path():
    override = os.environ.get('STUD_DATA_DIR')
    if override:
        return Path(override) / 'projects.sqlite3'
    if sys.platform == 'darwin':
        root = Path.home() / 'Library' / 'Application Support'
    elif sys.platform == 'win32':
        root = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    else:
        root = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return root / 'stud' / 'projects.sqlite3'


def connect():
    path = catalog_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.execute('CREATE TABLE IF NOT EXISTS projects (path TEXT PRIMARY KEY, name TEXT NOT NULL, last_used TEXT NOT NULL)')
    return connection


def register(directory, name=None):
    path = Path(directory).expanduser().resolve()
    if not (path / 'design.py').is_file():
        raise ValueError(f'No design.py found in {path}')
    key = os.path.normcase(str(path))
    connection = connect()
    try:
        with connection:
            connection.execute('''INSERT INTO projects VALUES (?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                name=COALESCE(?, projects.name), last_used=excluded.last_used''',
                (key, name or path.name, datetime.now(timezone.utc).isoformat(), name))
    finally:
        connection.close()
    return path


def list_projects():
    if not catalog_path().exists():
        return []
    connection = connect()
    try:
        return [dict(path=path, name=name, lastUsed=last_used,
                     available=(Path(path) / 'design.py').is_file())
                for path, name, last_used in connection.execute(
                    'SELECT path, name, last_used FROM projects ORDER BY last_used DESC, path')]
    finally:
        connection.close()
