"""Cached, informational release checks. Installation stays in the signed updater."""
import json
import os
import re
import threading
import time
from urllib.request import Request, urlopen


def stable_version(value):
    match = re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:\+[0-9A-Za-z.-]+)?', value or '')
    return tuple(map(int, match.groups())) if match else None


class UpdateNotice:
    def __init__(self, root):
        metadata = root / 'version.json'
        if not metadata.exists():
            metadata = root / 'package.json'
        settings = json.loads(metadata.read_text())
        self.version = settings['version']
        self.repository = settings.get('repository') or os.environ.get('STUD_RELEASE_REPOSITORY', '')
        if not isinstance(self.repository, str) or not re.fullmatch(r'[\w.-]+/[\w.-]+', self.repository):
            self.repository = ''
        self.lock = threading.Lock()
        self.next_check = 0
        self.result = {'available': False}

    def check(self):
        if not self.repository:
            return {'available': False}
        with self.lock:
            now = time.monotonic()
            if now < self.next_check:
                return self.result.copy()
            self.next_check = now + 15 * 60
            try:
                base = f'https://github.com/{self.repository}/releases/latest'
                request = Request(base + '/download/latest.json', headers={'User-Agent': 'stud/' + self.version})
                with urlopen(request, timeout=5) as response:
                    if not response.url.startswith('https://'):
                        raise ValueError('Expected HTTPS')
                    payload = response.read(1024 * 1024 + 1)
                    if len(payload) > 1024 * 1024:
                        raise ValueError('Release metadata too large')
                    release = json.loads(payload)
                latest = stable_version(release.get('version'))
                current = stable_version(self.version)
                if latest is None or current is None:
                    raise ValueError('Expected stable release versions')
                self.result = {'available': latest > current}
                if self.result['available']:
                    self.result.update(version=release['version'], url=base)
                self.next_check = now + 6 * 60 * 60
            except (OSError, ValueError, TypeError, AttributeError):
                pass  # Offline checks never interrupt a design or erase a known update.
            return self.result.copy()
