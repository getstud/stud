"""Read native geometry findings for a CadQuery project's evaluated source."""
import argparse
import json
from pathlib import Path
import sys


def validate_project(project_dir=None, *, strict=False, json_output=False):
    from build import evaluate_project
    result, manifest = evaluate_project(project_dir)
    if manifest is None:
        print(json.dumps(result))
        return 1
    checks = manifest.get('checks', {})
    if json_output:
        print(json.dumps(checks))
    else:
        for finding in checks.get('findings', []):
            if finding['status'] != 'passed':
                print(f"{finding['status']} {finding['requirement_id']}: {finding.get('explanation', '')}")
        print('; '.join(f'{count} {status}' for status, count in checks.get('counts', {}).items()))
    counts = checks.get('counts', {})
    if counts.get('failed') or counts.get('execution_failed'):
        return 1
    return 2 if strict and not checks.get('all_passed') else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path.cwd(), help='Initialized CadQuery project directory.')
    parser.add_argument('--json', action='store_true', help='Print machine-readable native findings.')
    parser.add_argument('--strict', action='store_true', help='Also exit nonzero for incomplete checks.')
    args = parser.parse_args()
    try:
        return validate_project(args.project, strict=args.strict, json_output=args.json)
    except (ValueError, OSError) as error:
        print(f'stud: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
