"""Explicit model cleanup that leaves no new recovery journal behind."""
import json
from pathlib import Path
import re
import shutil

from .detached_jobs import JOB_DIR, snapshot_job
from .lte_cleanup import inspect_lte_cleanup
from .model_activity import inspect_model_activity, model_mutation_guard, LOCK_NAME, RUN_LOCK_NAME
from .model_history import _tree, tree_signature
from .model_staging import MODEL_WRITE_LOCK, _build_cleanup_plan, _human_size

ARCHIVE_DIRS = ('.cmfgen-runs', '.cmfgen-viewer-backups')
METADATA_FILES = {LOCK_NAME, RUN_LOCK_NAME, '.cmfgen-viewer-input-modified.json'}
TEMP_PREFIXES = ('.cmfgen-edit-', '.cmfgen-promote-', '.cmfgen-lte-',
                 '.cmfgen-create-', '.recovery-compaction-', '.runner-control-',
                 '.runner-product-', '.report-', '.diagnostic-')


class FullCleanupError(ValueError):
    pass


def _job_records(model, errors, warnings):
    """Find model-owned records even when the viewer's root is an ancestor."""
    owners = {model, model / 'lte', model / 'obs'}
    roots = [model / name for name in ('lte', 'obs')] + [model, *model.parents]
    for base in roots:
        root = base / JOB_DIR
        if root.is_symlink() or not root.is_dir() or base.is_symlink():
            continue
        try:
            directories = list(root.iterdir())
        except OSError as exc:
            warnings.append(f'Could not inspect job archive {root}: {exc}')
            continue
        for directory in directories:
            if (directory.is_symlink() or not directory.is_dir()
                    or not re.fullmatch(r'[a-f0-9]{32}', directory.name)):
                continue
            request = directory / 'request.json'
            try:
                if request.is_symlink() or request.stat().st_size > 1024 * 1024:
                    continue
                data = json.loads(request.read_text())
                raw_model = data.get('model')
                if not isinstance(raw_model, str) or not Path(raw_model).is_absolute():
                    continue
                if Path(raw_model).resolve() not in owners:
                    continue
                try:
                    job = snapshot_job(base, directory.name, include_result=False)
                    if job['active']:
                        errors.append(f'Runner job {directory.name} is still active or its status is uncertain.')
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    errors.append(f'Cannot establish that runner job {directory.name} has finished: {exc}')
                yield directory
            except (OSError, ValueError, AttributeError) as exc:
                warnings.append(f'Could not identify owner of job record {directory}: {exc}; left untouched.')


def build_full_cleanup_plan(model):
    model = model.expanduser().resolve()
    entries, errors, warnings = {}, [], []

    def include(path, reason):
        path = Path(path)
        try:
            rows = _tree(path)
            if any(row['kind'] == 'special' for row in rows):
                errors.append(f'Cleanup target contains special files: {path}')
                return
            size = sum(row['size'] for row in rows if row['kind'] == 'file' or row['kind'] == 'link')
            name = path.relative_to(model).as_posix() if path.is_relative_to(model) else str(path)
            entries[str(path)] = {'name': name, 'path': str(path), 'reason': reason,
                'kind': rows[0]['kind'] if path.is_symlink() or not path.is_dir() else 'directory',
                'size': size, 'human_size': _human_size(size), 'signature': tree_signature(rows)}
        except OSError as exc:
            errors.append(f'Could not inspect cleanup target {path}: {exc}')

    for workspace in ('', 'lte', 'obs'):
        folder = model / workspace
        if folder.is_symlink() or not folder.is_dir():
            continue
        try:
            cleanup = inspect_lte_cleanup(folder) if workspace == 'lte' else _build_cleanup_plan(workspace or model.name, folder)
            for entry in cleanup['entries']:
                include(folder / entry['name'], entry['reason'])
            for path in folder.iterdir():
                if path.name in METADATA_FILES or path.name.startswith(TEMP_PREFIXES):
                    include(path, 'Viewer/runner metadata, lock, or temporary workspace')
            job_root = folder / JOB_DIR
            if job_root.is_dir() and not job_root.is_symlink() and not any(job_root.iterdir()):
                include(job_root, 'Empty detached runner job store')
            for name in ARCHIVE_DIRS:
                path = folder / name
                if path.exists() or path.is_symlink():
                    include(path, 'Recovery archives and run history')
        except (ValueError, OSError) as exc:
            errors.append(f'Could not inspect workspace {folder}: {exc}')
    for path in _job_records(model, errors, warnings):
        include(path, 'Detached runner job record for this model')
    activity = inspect_model_activity(model)
    if not activity['safe_to_modify']:
        errors.append(activity['reason'] or 'Model activity is uncertain.')
    ordered = sorted(entries.values(), key=lambda entry: entry['path'])
    total = sum(entry['size'] for entry in ordered)
    return {'command': 'cleanup', 'model': str(model), 'workspace': 'all', 'full': True,
            'entries': ordered, 'entry_count': len(ordered),
            'total_size': total, 'human_size': _human_size(total), 'activity': activity,
            'warnings': ['Full cleanup permanently removes the listed recovery data and run history; no new recovery archive is created.', *warnings],
            'errors': errors, 'ready': not errors}


def run_full_cleanup(plan):
    model = Path(plan['model'])
    with MODEL_WRITE_LOCK, model_mutation_guard(model, FullCleanupError):
        current = build_full_cleanup_plan(model)
        if not current['ready']:
            raise FullCleanupError('; '.join(current['errors']))
        lock_path = model / LOCK_NAME
        # Acquiring the guard may create a lock absent from the reviewed plan.
        planned_lock = any(entry['path'] == str(lock_path) for entry in plan['entries'])
        compared = current['entries'] if planned_lock else [
            entry for entry in current['entries'] if entry['path'] != str(lock_path)]
        if compared != plan['entries']:
            raise FullCleanupError('Cleanup targets changed after planning; inspect a fresh plan.')
        removed, failures = [], []
        for entry in compared:
            if entry['path'] == str(lock_path):
                continue
            path = Path(entry['path'])
            try:
                if path.is_symlink() or not path.is_dir():
                    path.unlink()
                else:
                    shutil.rmtree(path)
                removed.append(entry['name'])
            except OSError as exc:
                failures.append({'name': entry['name'], 'error': str(exc)})
        # Shared job stores may contain other models' records. Only tidy empty
        # stores inside this model; never remove a shared ancestor's store.
        for folder in (model, model / 'lte', model / 'obs'):
            root = folder / JOB_DIR
            if folder.is_symlink() or root.is_symlink():
                continue
            try:
                root.rmdir()
            except OSError:
                pass
        # Last mutation: release the pathname while still holding its inode.
        # Writers that opened it earlier must reject that detached inode.
        try:
            lock_path.unlink()
            if planned_lock:
                removed.append(LOCK_NAME)
        except OSError as exc:
            failures.append({'name': LOCK_NAME, 'error': str(exc)})
        return {'status': 'failed' if failures else 'succeeded' if removed else 'unchanged',
                'removed': removed, 'removed_count': len(removed), 'failures': failures}
