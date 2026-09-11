"""Evaluate a CadQuery project through its shared coordinator."""
import json
from pathlib import Path
import sys


def evaluate_project(project_dir=None):
    from stud.client import Client
    root = Path(project_dir or Path.cwd()).resolve()
    client = Client(root)
    active = client.get('/api/v1/status')['request']
    if active and Path(active['workspace']).resolve() == root:
        job = client.command('evaluate', {'request_id': active['id']})
    else:
        job = client.command('evaluate_checkpoint', {'display': True})
    result = client.wait(job['id'])
    manifest = client.get('/api/v1/builds/' + job['id'] + '/manifest.json') if result['status'] == 'complete' else None
    return result, manifest


def build(project_dir=None):
    result, manifest = evaluate_project(project_dir)
    print(json.dumps(result))
    if result['status'] != 'complete':
        raise SystemExit(1)
    return manifest


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path.cwd())
    try:
        build(parser.parse_args().project)
    except (ValueError, OSError) as error:
        print(f'stud: {error}', file=sys.stderr)
        raise SystemExit(1)
