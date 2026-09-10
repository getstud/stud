"""Git-backed project history. Never stage the user's checkout or reset its files."""
import os
from pathlib import Path
import subprocess
import tempfile
import time

from .contracts import StudError, atomic_write, confined, identifier, read_json, write_json
from .source import manifest_at, new_manifest, source_files


def git_executable():
    resources = Path(__file__).resolve().parents[2]
    bundled = resources / ('git/cmd/git.exe' if os.name == 'nt' else 'git/bin/git')
    if bundled.is_file():
        return str(bundled)
    import shutil
    executable = shutil.which('git')
    if not executable:
        raise StudError('unavailable_runtime', 'Git is missing. Reinstall the stud desktop runtime, or install Git for a source checkout.')
    return executable


def canonical_project_root(root):
    root=Path(root).resolve()
    manifest=manifest_at(root)
    # A copied worktree's .git file may still point to the original folder.
    # Resolve the owning project lexically before asking Git about that file.
    if root.parent.name == 'workspaces' and root.parent.parent.name == '.stud':
        owner = root.parent.parent.parent
        record = read_json(owner / 'stud.json')
        if record and record.get('project_id') == manifest['project_id']:
            return owner
    common=History(root).git('rev-parse','--path-format=absolute','--git-common-dir').decode().strip()
    owner=Path(common).parent
    record=read_json(owner/'stud.json')
    return owner.resolve() if record and record.get('project_id')==manifest['project_id'] else root


class History:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def git(self, *args, input=None, env=None, check=True):
        result = subprocess.run([git_executable(), '-C', str(self.root), *args], input=input,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', **(env or {})})
        if check and result.returncode:
            raise StudError('git_error', result.stderr.decode(errors='replace').strip())
        return result.stdout if check else result

    def head(self, ref='HEAD'):
        result = self.git('rev-parse', '--verify', f'{ref}^{{commit}}', check=False)
        if result.returncode:
            raise StudError('unknown_checkpoint', f'Cannot find checkpoint: {ref}')
        return result.stdout.decode().strip()

    def read_file(self, commit, relative):
        confined(self.root, relative)
        commit = self.head(commit)
        result = self.git('show', f'{commit}:{relative}', check=False)
        return result.stdout if result.returncode == 0 else None

    def files(self, commit, prefix=''):
        commit = self.head(commit)
        scope = ['--', prefix] if prefix else []
        return [p.decode() for p in self.git('ls-tree', '-r', '--name-only', '-z', commit, *scope).split(b'\0') if p]

    def author(self):
        def config(key, default):
            result = self.git('config', '--get', key, check=False)
            return result.stdout.decode().strip() or default
        return dict(name=config('user.name', 'stud'), email=config('user.email', 'stud@localhost'))

    def commit(self, base, updates, deletions, message, author, timestamp):
        """Build a tree with a private index; identical journal inputs yield one SHA."""
        self.root.joinpath('.stud').mkdir(exist_ok=True)
        fd, index = tempfile.mkstemp(prefix='index-', dir=self.root / '.stud')
        os.close(fd)
        Path(index).unlink()
        env = {'GIT_INDEX_FILE': index}
        try:
            self.git('read-tree', base if base else '--empty', env=env)
            for relative in sorted(set(deletions) - set(updates)):
                confined(self.root, relative)
                self.git('update-index', '--force-remove', '--', relative, env=env)
            for relative, data in sorted(updates.items()):
                confined(self.root, relative)
                blob = self.git('hash-object', '-w', '--stdin', input=data).decode().strip()
                self.git('update-index', '--add', '--cacheinfo', f'100644,{blob},{relative}', env=env)
            tree = self.git('write-tree', env=env).decode().strip()
            identity = {f'GIT_{role}_{key}': value for role in ('AUTHOR', 'COMMITTER')
                        for key, value in [('NAME', author['name']), ('EMAIL', author['email']),
                                           ('DATE', f'{timestamp} +0000')]}
            parent = ['-p', base] if base else []
            return self.git('commit-tree', tree, *parent, input=message.encode(), env=identity).decode().strip()
        finally:
            Path(index).unlink(missing_ok=True)

    def advance(self, ref, commit, expected):
        result = self.git('update-ref', ref, commit, expected, check=False)
        if result.returncode:
            current = self.head(ref)
            if current == commit:
                return
            raise StudError('changed_head', 'The option changed outside this request; its workspace is preserved.',
                            expected=expected, current=current)

    def checkout_clean(self):
        return not self.git('status', '--porcelain', '--untracked-files=all').strip()

    def synchronize(self, ref, base, commit):
        """Check against the old tree: update-ref may have already moved HEAD."""
        current_ref = self.git('symbolic-ref', '-q', 'HEAD', check=False).stdout.decode().strip()
        if current_ref != ref:
            return 'different_checkout'
        # An unchanged tracked working tree must match the previous tree, and the
        # user's index must too. Untracked files are preserved by read-tree -u.
        staged = self.git('diff', '--cached', '--quiet', base, '--', check=False)
        unstaged = self.git('diff', '--quiet', '--', check=False)
        if staged.returncode or unstaged.returncode:
            return 'local_edits_preserved'
        previous_paths = set(self.files(base))
        for name in self.files(commit):
            if name in previous_paths:
                continue
            # Git read-tree is allowed to replace ignored untracked files.
            # Stud is not: inspect every added path and its ancestors first.
            target = self.root / name
            if target.exists() or target.is_symlink():
                return 'local_edits_preserved'
            for parent in target.parents:
                if parent == self.root:
                    break
                if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                    return 'local_edits_preserved'
        result = self.git('read-tree', '-u', '-m', base, commit, check=False)
        return 'synchronized' if result.returncode == 0 else 'local_edits_preserved'

    def workspace(self, request_id, head):
        destination = confined(self.root, f'.stud/workspaces/{request_id}')
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.git('worktree', 'add', '--detach', str(destination), head)
        # Git checkout filters may rewrite line endings. Requests start from the
        # exact committed modeling bytes that determine source identity.
        for name in source_files(destination, manifest_at(destination)):
            body = self.read_file(head, name)
            if body is not None:
                atomic_write(confined(destination, name), body)
        return destination

    def options(self):
        refs = self.git('for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads/stud/').decode().splitlines()
        result = []
        for row in refs:
            ref, head = row.split()
            option_id = ref.rsplit('/', 1)[-1]
            raw = self.read_file(head, f'records/options/{option_id}.json')
            import json
            record = json.loads(raw) if raw else dict(id=option_id, label=option_id)
            result.append(dict(**record, ref=ref, head=head))
        return result

    def option(self, option_id):
        for option in self.options():
            if option['id'] == option_id:
                return option
        raise StudError('unknown_option', f'Unknown design option: {option_id}')

    def checkpoint_report(self, checkpoint):
        import json
        from .source import matches_source, source_identity
        target = self.head(checkpoint)
        evidence = self.git('log', '-1', '--format=%H', target, '--', 'checkpoints').decode().strip()
        if not evidence:return None
        changed = self.git('diff-tree', '--root', '--no-commit-id', '--name-only', '-r', evidence, '--', 'checkpoints').decode().splitlines()
        reports = [json.loads(self.read_file(evidence, name)) for name in changed if name.endswith('.json')]
        if not reports:return None
        report=reports[-1]
        # Metadata-only descendants inherit evidence. External source or input
        # commits do not acquire an ancestor's model/estimate by implication.
        manifest=json.loads(self.read_file(target,'stud.json'))
        files={name:self.read_file(target,name) for name in self.files(target) if matches_source(name,manifest)}
        if source_identity(files)!=report['source_id']:return None
        raw=self.read_file(target,'estimating.json')
        if json.loads(raw or '{}')!=report.get('estimating_inputs',{}):return None
        return dict(**report,evidence_checkpoint=evidence)


def initialize(root, name=None, *, units='mm'):
    """Explicitly enroll only modeling files; never sweep up unrelated edits."""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root / 'stud.json').exists():
        raise StudError('already_initialized', 'The project already has a stud manifest.')
    if not (root / 'design.py').is_file():
        raise StudError('missing_source', 'Create design.py before initializing project history.')
    history = History(root)
    existing = history.git('rev-parse', '--show-toplevel', check=False)
    if existing.returncode == 0 and Path(existing.stdout.decode().strip()).resolve() != root:
        raise StudError('nested_repository', 'Create this project outside another repository, or give it its own repository first.')
    if existing.returncode != 0:
        history.git('init')
    base_result = history.git('rev-parse', '--verify', 'HEAD', check=False)
    base = base_result.stdout.decode().strip() if base_result.returncode == 0 else None
    if (root / 'estimating.json').exists():
        raise StudError('conversion_conflict', 'Existing estimating.json must be inventoried and migrated explicitly; it will not be overwritten.')
    if base and (root / '.gitignore').exists():
        tracked_ignore = history.read_file(base, '.gitignore')
        if tracked_ignore != (root / '.gitignore').read_bytes():
            raise StudError('conversion_conflict', 'Save or separately reconcile existing .gitignore edits before conversion.')
    project_id, option_id = identifier('project'), identifier('option')
    manifest = new_manifest(name or root.name, project_id,units=units)
    write_json(root / 'stud.json', manifest)
    write_json(root / 'estimating.json', {'schema_version': 1, 'currency': 'USD', 'overrides': {},
                                          'allowances': {}, 'quote_selection': {}, 'tax_rate': '0',
                                          'contingency_rate': '0'})
    option = dict(id=option_id, label='Main', created_from=base)
    write_json(root / f'records/options/{option_id}.json', option)
    ignore = root / '.gitignore'
    existing_ignore = ignore.read_text() if ignore.exists() else ''
    ignore.write_text(existing_ignore + '\n# stud local coordination and rebuildable artifacts\n.stud/\n__pycache__/\n*.pyc\n')
    owned = source_files(root, manifest) + ['estimating.json', f'records/options/{option_id}.json', '.gitignore']
    updates = {name: (root / name).read_bytes() for name in owned}
    commit = history.commit(base, updates, [], 'Initialize stud project\n', history.author(), int(time.time()))
    ref = f'refs/heads/stud/{option_id}'
    history.git('update-ref', ref, commit, '0' * len(commit))
    if base is None:
        history.git('symbolic-ref', 'HEAD', ref)
        history.git('read-tree', commit)
    write_json(root / '.stud/state.json', dict(schema_version=1, project_id=project_id,
               active_option=option_id, active_request=None, displayed_build=None, last_valid_build=None,
               latest_build=None, sequence=0))
    return dict(project_id=project_id, option_id=option_id, checkpoint=commit, manifest=manifest)
