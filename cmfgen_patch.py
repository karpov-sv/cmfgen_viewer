#!/usr/bin/env python3
"""Install/update the bundled CMFGEN source patches without changing local setup.

Uses only Python's standard library and git. No build or model run is launched.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid

REPO = Path(__file__).resolve().parent
DEFAULT_MANIFEST = REPO/'doc/developer/patches/cmfgen-current.json'
PRESERVED = {'Makefile_definitions', 'com/aliases_for_cmfgen.sh'}
STATE_DIR = '.cmfgen-patches'


class PatchError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def source_path(name):
    path = PurePosixPath(name)
    if (not re.fullmatch(r'[A-Za-z0-9_.+/-]+', name) or path.is_absolute()
            or any(p in {'.', '..', '.git', STATE_DIR, '.cmfgen-backups'} for p in path.parts)
            or str(path) != name):
        raise PatchError(f'Unsafe source path: {name}')
    return name


def git(*args, cwd=None):
    try:
        result = subprocess.run(['git', '-c', 'core.autocrlf=false', *args], cwd=cwd,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        raise PatchError('git is required to apply CMFGEN patches') from exc
    if result.returncode:
        raise PatchError(result.stderr.decode(errors='replace').strip() or 'git failed')
    return result.stdout


class Bundle:
    def __init__(self, manifest, patch):
        if manifest.get('schema_version') != 1 or not isinstance(manifest.get('files'), list):
            raise PatchError('Unsupported patch manifest schema')
        if not isinstance(manifest.get('baseline_release'), str) or not manifest['baseline_release']:
            raise PatchError('Missing upstream release identity')
        self.manifest = manifest
        self.patch = patch
        self.sha = digest(patch)
        if self.sha != manifest.get('patch_sha256'):
            raise PatchError('Patch checksum does not match its manifest')
        self.files = {}
        for item in manifest['files']:
            name = source_path(item['path'])
            if name in self.files:
                raise PatchError(f'Duplicate source path: {name}')
            if item.get('status') not in {'added', 'modified', 'deleted'}:
                raise PatchError(f'Unsupported patch operation: {name}')
            for key in ['sha256', 'baseline_sha256']:
                value = item.get(key)
                if value is not None and not re.fullmatch('[0-9a-f]{64}', value):
                    raise PatchError(f'Invalid {key}: {name}')
            if item['status'] != 'deleted' and not item.get('sha256'):
                raise PatchError(f'Missing target hash: {name}')
            if item['status'] != 'added' and not item.get('baseline_sha256'):
                raise PatchError(f'Missing upstream hash: {name}')
            self.files[name] = item
        # Refuse extra patch paths that are absent from the reviewed manifest.
        with tempfile.TemporaryDirectory(prefix='cmfgen-bundle-') as tmp:
            p = Path(tmp)/'source.patch';p.write_bytes(patch)
            rows = git('apply', '--numstat', '-z', str(p)).split(b'\0')
        names = {row.split(b'\t', 2)[2].decode() for row in rows if row}
        if names != set(self.files):
            raise PatchError('Patch paths do not match the manifest; renames are unsupported')
        self.revision = manifest.get('dated_patch_version', {}).get('revision')

    @classmethod
    def load(cls, manifest_path):
        manifest_path = Path(manifest_path)
        data = json.loads(manifest_path.read_text())
        name = source_path(data['patch_file'])
        if '/' in name:
            raise PatchError('The patch must be beside its manifest')
        return cls(data, (manifest_path.parent/name).read_bytes())

    def apply_file(self, folder, name, *, reverse=False):
        with tempfile.NamedTemporaryFile(prefix='cmfgen-apply-', suffix='.patch') as tmp:
            tmp.write(self.patch);tmp.flush()
            args = ['apply', '--whitespace=nowarn', '--include='+name]
            if reverse:
                args.append('--reverse')
            git(*args, tmp.name, cwd=folder)

    def compact(self):
        return {key: self.manifest[key] for key in
                ['schema_version', 'baseline_release', 'patch_file', 'patch_sha256', 'files', 'dated_patch_version']
                if key in self.manifest}


def safe_file(root, name):
    """Never follow source or parent links; preserve local settings separately."""
    path = root/name
    for parent in [path, *path.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise PatchError(f'Refusing symlink: {parent}')
    if path.exists():
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PatchError(f'Require an unshared regular file: {path}')
    return path


def current_hash(root, name):
    path = safe_file(root, name)
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(256*1024), b''):
            h.update(block)
    return h.hexdigest()


def read_state(root):
    folder = root/STATE_DIR
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise PatchError('Unsafe source-patch state directory')
    path = safe_file(root, STATE_DIR+'/installed.json')
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    patch_name = data['manifest']['patch_sha256']+'.patch'
    patch = safe_file(root, STATE_DIR+'/'+patch_name).read_bytes()
    return Bundle(data['manifest'], patch)


def history_bundles(repo, manifest_path):
    """Bootstrap older unrecorded installs from local repository history."""
    try:
        relative = Path(manifest_path).resolve().relative_to(repo.resolve()).as_posix()
        revisions = git('log', '--format=%H', '--', relative, cwd=repo).decode().splitlines()
    except (ValueError, PatchError):
        return
    seen = set()
    for revision in revisions:
        try:
            data = json.loads(git('show', revision+':'+relative, cwd=repo))
            if data['patch_sha256'] in seen:
                continue
            seen.add(data['patch_sha256'])
            name = source_path(data['patch_file'])
            patch_path = str(PurePosixPath(relative).parent/name)
            yield Bundle(data, git('show', revision+':'+patch_path, cwd=repo))
        except (OSError, ValueError, KeyError, IndexError, PatchError):
            continue  # Historical manifests may predate the updater's schema.


def plan_update(root, desired, previous=None, *, history=()):
    if previous and previous.manifest['baseline_release'] != desired.manifest['baseline_release']:
        raise PatchError('Changing the upstream release requires a fresh source tree')
    # Source stamps and retained patch state both guard against downgrades.
    def revision_key(value):
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}\.[1-9]\d*', value):
            raise PatchError('Invalid source patch revision: '+value)
        day, serial = value.rsplit('.', 1)
        return datetime.strptime(day, '%Y-%m-%d'), int(serial)
    revisions = [previous.revision] if previous and previous.revision else []
    version_file = safe_file(root, 'new_main/cmfgen_version.inc')
    if version_file.exists():
        match = re.search(r"PATCH_REVISION\s*=\s*'([^']+)'", version_file.read_text(), re.I)
        if match:
            revisions.append(match[1])
    if desired.revision:
        target_revision = revision_key(desired.revision)
    if revisions and (not desired.revision or any(revision_key(v) > target_revision for v in revisions)):
        raise PatchError('Installed source revision is newer than this patch set; refusing downgrade')
    names = set(desired.files) | (set(previous.files) if previous else set())
    changes, errors, images = [], [], {}
    bundles = [previous] if previous else []
    historic = iter(history)
    initial = {}
    for name in sorted(names-PRESERVED):
        try:
            actual = current_hash(root, name)
            initial[name] = actual
            target = desired.files.get(name)
            old = previous.files.get(name) if previous else None
            target_hash = target.get('sha256') if target else old.get('baseline_sha256')
            if actual == target_hash:
                continue
            baseline_hash = target.get('baseline_sha256') if target else old.get('baseline_sha256')
            known = None
            if actual != baseline_hash:
                while True:
                    known = next((b for b in bundles if b and b.manifest['baseline_release'] == desired.manifest['baseline_release']
                                  and name in b.files and b.files[name].get('sha256') == actual), None)
                    if known:
                        break
                    try:
                        bundles.append(next(historic))
                    except StopIteration:
                        raise PatchError('unrecognized local edits or unsupported upstream file')
            with tempfile.TemporaryDirectory(prefix='cmfgen-source-') as tmp:
                folder = Path(tmp);p = folder/name;p.parent.mkdir(parents=True, exist_ok=True)
                if actual is not None:
                    shutil.copy2(root/name, p)
                if known:
                    known.apply_file(folder, name, reverse=True)
                baseline = digest(p.read_bytes()) if p.exists() else None
                if baseline != baseline_hash:
                    raise PatchError('recognized old patch has a different upstream baseline')
                if target:
                    desired.apply_file(folder, name)
                postimage = p.read_bytes() if p.exists() else None
                if (digest(postimage) if postimage is not None else None) != target_hash:
                    raise PatchError('patched file does not match its target hash')
                images[name] = postimage
            changes.append({'path': name, 'before': actual, 'after': target_hash,
                            'operation': 'remove' if target_hash is None else 'add' if actual is None else 'update'})
        except (OSError, ValueError, PatchError) as exc:
            errors.append(f'{name}: {exc}')
    return {'revision': desired.revision, 'patch_sha256': desired.sha, 'changes': changes,
            'preserved': sorted(PRESERVED), 'errors': errors}, images, initial


def atomic_write(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp = tempfile.mkstemp(prefix='.cmfgen-patch-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush();os.fsync(stream.fileno())
        os.chmod(temp, stat.S_IMODE(mode))
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def patch_lock(root):
    try:
        import fcntl
    except ImportError as exc:
        raise PatchError('Source updates require POSIX file locking (Linux/macOS)') from exc
    folder = root/STATE_DIR
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise PatchError('Unsafe source-patch state directory')
    folder.mkdir(exist_ok=True)
    path = safe_file(root, STATE_DIR+'/lock')
    with path.open('a+b') as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PatchError('Another source update is in progress') from exc
        yield


def install(root, desired, report, images, initial):
    if report['errors']:
        raise PatchError('\n'.join(report['errors']))
    for name, expected in initial.items():
        if current_hash(root, name) != expected:
            raise PatchError(f'Source changed during review: {name}')
    backups = root/'.cmfgen-backups'
    if backups.is_symlink() or (backups.exists() and not backups.is_dir()):
        raise PatchError('Unsafe backup directory')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = backups/(stamp+'-source-patch-'+uuid.uuid4().hex[:8])
    backup.mkdir(parents=True)
    for name in images:
        path = root/name
        if path.exists():
            target = backup/'files'/name;target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    state = root/STATE_DIR/'installed.json'
    if state.exists():
        shutil.copy2(state, backup/'installed-before.json')
    (backup/'plan.json').write_text(json.dumps(report, indent=2)+'\n')
    state_before = state.read_bytes() if state.exists() else None
    state_after = (json.dumps({'schema_version': 1, 'manifest': desired.compact(),
                              'backup': str(backup)}, indent=2)+'\n').encode()
    written = []
    try:
        for name, data in images.items():
            path = safe_file(root, name)
            if current_hash(root, name) != initial[name]:
                raise PatchError(f'Source changed during installation: {name}')
            written.append(name)  # Also recover if a writer fails after replacement.
            if data is None:
                path.unlink()
            else:
                atomic_write(path, data, path.stat().st_mode if path.exists() else 0o644)
        for name, before in initial.items():
            expected = (digest(images[name]) if images[name] is not None else None) if name in images else before
            if current_hash(root, name) != expected:
                raise PatchError(f'Source changed during installation: {name}')
        # Retain the old patch too; one atomic state publication is enough for
        # the next update, even when releases remove or replace old hunks.
        atomic_write(root/STATE_DIR/(desired.sha+'.patch'), desired.patch)
        if (state.read_bytes() if state.exists() else None) != state_before:
            raise PatchError('Patch state changed during installation')
        atomic_write(state, state_after)
    except BaseException as exc:
        conflicts = []
        current_state = state.read_bytes() if state.exists() else None
        if current_state == state_after:
            if state_before is None:
                state.unlink()
            else:
                atomic_write(state, state_before)
        elif current_state != state_before:
            conflicts.append(STATE_DIR+'/installed.json')
        for name in reversed(written):
            expected = digest(images[name]) if images[name] is not None else None
            actual = current_hash(root, name)
            if actual == initial[name]:
                continue
            if actual != expected:
                conflicts.append(name);continue  # Preserve a concurrent external edit.
            old = backup/'files'/name
            if old.exists():
                atomic_write(root/name, old.read_bytes(), old.stat().st_mode)
                shutil.copystat(old, root/name)
            else:
                (root/name).unlink(missing_ok=True)
        raise PatchError(f'Update failed; owned changes rolled back. Backup: {backup}. '
                         f'External edits preserved: {conflicts}. {exc}') from exc
    return str(backup)


def update(root, manifest=DEFAULT_MANIFEST, *, check=False, repo=REPO):
    root = Path(root).expanduser().resolve()
    if not root.is_dir() or not (root/'new_main').is_dir():
        raise PatchError('Not a CMFGEN source tree (new_main/ is required)')
    desired = Bundle.load(manifest)
    def prepare():
        previous = read_state(root)
        return previous, plan_update(root, desired, previous,
                                     history=history_bundles(Path(repo), Path(manifest)))
    if check:
        previous, (report, _, _) = prepare()
        report['status'] = 'conflict' if report['errors'] else 'ready' if report['changes'] else 'current'
        return report
    with patch_lock(root):
        previous, (report, images, initial) = prepare()
        if report['errors']:
            raise PatchError('\n'.join(report['errors']))
        if not images and previous and previous.sha == desired.sha:
            report['status'] = 'current';return report
        report['backup'] = install(root, desired, report, images, initial)
        report['status'] = 'applied' if images else 'registered'
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='CMFGEN source checkout to patch')
    parser.add_argument('--check', action='store_true', help='Read-only preview; do not change the source tree')
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST, help='Alternate cumulative patch manifest')
    parser.add_argument('--json', action='store_true', help='Print the update plan as JSON')
    args = parser.parse_args(argv)
    try:
        report = update(args.source, args.manifest, check=args.check)
    except (OSError, ValueError, KeyError, IndexError, PatchError) as exc:
        print('ERROR: '+str(exc), file=sys.stderr);return 2
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"CMFGEN source patches: {report['status']} ({report['revision'] or report['patch_sha256'][:12]})")
        for item in report['changes']:
            print(f"  {item['operation']}: {item['path']}")
        for error in report['errors']:
            print('  CONFLICT: '+error)
        print('Preserved local setup: '+', '.join(report['preserved']))
        if report.get('backup'):
            print('Backup: '+report['backup'])
        if report['status'] in {'applied', 'registered'}:
            print('Source only; rebuild separately with: make -j1 clean all')
    return 2 if report['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
