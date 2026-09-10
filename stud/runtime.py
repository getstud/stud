"""Read-only diagnostics for installed and source-checkout runtimes."""
from pathlib import Path
import re
import subprocess
import sys

from .history import git_executable
from .source import runtime_fingerprint


def doctor():
    runtime = runtime_fingerprint()
    lock = Path(__file__).resolve().parents[1] / 'requirements.lock'
    expected = dict(re.findall(r'^([A-Za-z0-9_.-]+)==([^\s;]+)', lock.read_text(), re.MULTILINE))
    issues = [{'package': name, 'expected': version, 'installed': runtime['packages'].get(name)}
              for name, version in expected.items() if runtime['packages'].get(name) != version]
    try:
        git = subprocess.run([git_executable(), '--version'], capture_output=True, text=True, timeout=10)
        git_result = git.stdout.strip()
        if git.returncode:
            issues.append({'git': git.stderr.strip()})
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        git_result = None
        issues.append({'git': str(error)})
    try:
        native = subprocess.run([sys.executable, '-B', '-E', '-s', '-c',
            'import cadquery as cq; from reportlab.pdfgen.canvas import Canvas; from svglib.svglib import svg2rlg; '
            'assert abs(cq.Workplane("XY").box(10,20,30).val().Volume()-6000)<1e-6'],
            capture_output=True, text=True, timeout=60)
        if native.returncode:
            issues.append({'native': native.stderr[-4000:]})
    except (OSError, subprocess.TimeoutExpired) as error:
        issues.append({'native': str(error)})
    return dict(status='healthy' if not issues else 'unavailable', runtime=runtime, git=git_result, issues=issues,
                recovery='Reinstall the desktop app to restore its pinned runtime. Projects are stored separately. '
                'For a source checkout, install requirements.lock with Python 3.13 and pip --require-hashes.')
