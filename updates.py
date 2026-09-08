"""Cached, informational release checks. Installation stays in the signed updater."""
import json
import os
import re
import threading
import time
from urllib.request import Request, urlopen


def release_version(value):
    match = re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-preview\.(0|[1-9]\d*))?', value or '')
    if not match:
        return None
    major, minor, patch, preview = match.groups()
    return (int(major), int(minor), int(patch), preview is None, int(preview or 0))


def stable_version(value):
    version = release_version(value)
    return version[:3] if version and version[3] else None


class UpdateNotice:
    def __init__(self, root):
        metadata = root / 'version.json'
        if not metadata.exists():
            metadata = root / 'package.json'
        settings = json.loads(metadata.read_text())
        self.version = settings['version']
        self.channel = settings.get('channel') or os.environ.get('STUD_RELEASE_CHANNEL', 'stable')
        self.repository = settings.get('repository') or os.environ.get('STUD_RELEASE_REPOSITORY', '')
        if self.channel not in ('stable', 'preview') or not isinstance(self.repository, str) or not re.fullmatch(r'[\w.-]+/[\w.-]+', self.repository):
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
                base = f'https://github.com/{self.repository}/releases'
                feed = base + ('/latest/download/latest.json' if self.channel == 'stable' else '/download/channel-preview/latest.json')
                request = Request(feed, headers={'User-Agent': 'stud/' + self.version})
                with urlopen(request, timeout=5) as response:
                    if not response.url.startswith('https://'):
                        raise ValueError('Expected HTTPS')
                    payload = response.read(1024 * 1024 + 1)
                    if len(payload) > 1024 * 1024:
                        raise ValueError('Release metadata too large')
                    release = json.loads(payload)
                parse = stable_version if self.channel == 'stable' else release_version
                latest = parse(release.get('version'))
                current = parse(self.version)
                if latest is None or current is None:
                    raise ValueError('Expected supported release versions')
                self.result = {'available': latest > current}
                if self.result['available']:
                    self.result.update(version=release['version'], url=base + '/tag/v' + release['version'].removeprefix('v'))
                self.next_check = now + 6 * 60 * 60
            except (OSError, ValueError, TypeError, AttributeError):
                pass  # Offline checks never interrupt a design or erase a known update.
            return self.result.copy()
