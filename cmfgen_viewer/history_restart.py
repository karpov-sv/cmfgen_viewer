"""Review and restore a complete, provenance-checked pre-run restart set."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid

from .model_history import HistoryError, get_archive, safe_path, _json, tree_signature, _tree
from .model_activity import model_mutation_guard
from .model_staging import MODEL_WRITE_LOCK
from .model_editor import MODEL_INPUT_MODIFIED_MARKER, mark_model_inputs_modified
from .model_workflow import MAIN_STATE_FILES
from .runner_restart import inspect_restart, RESTART_FILES
from .runner_recipe import snapshot
from .workflow_permissions import mkdir_readable, copy_readable, open_readable, make_readable
from .recovery_files import compact_recovery


class _ArchivedRestart:
    """Supply archived paths to the same read-only continuation checks as the runner."""
    def __init__(self, paths):
        self.paths = paths

    def __truediv__(self, name):
        return self.paths[name]


def preview_restart(model, archive_id, *, keep_large_files=False):
    archive, entry = get_archive(model, archive_id)
    plan = _json(archive / 'plan.json')
    stage = plan.get('stage')
    if entry['kind'] != 'Runner journal' or stage not in {'main', 'test'}:
        raise HistoryError('Native restart recovery requires a main or test journal.')
    before = plan.get('restart', {}).get('present_files', [])
    if ('SCRTEMP' not in before or not any(name in before for name in ('POINT1', 'POINT2'))
            or any(name not in RESTART_FILES for name in before)):
        raise HistoryError('This journal has no recorded pre-run continuation checkpoint.')
    source_paths = {}
    for name in RESTART_FILES:
        path = archive / 'restart-before' / name
        if name in before:
            safe_path(model, path.relative_to(model).as_posix())
            source_paths[name] = path
        else:
            if path.exists() or path.is_symlink():
                raise HistoryError(f'Unexpected archived {name}; restart provenance is inconsistent.')
            source_paths[name] = path
    for name in ('MODEL', 'RVTJ', 'MODEL_SPEC', 'VADAT'):
        candidates = [archive / 'inputs' / name]
        if name in {'MODEL', 'RVTJ'}:
            candidates.append(archive / stage / 'before' / name)
        path = next((path for path in candidates if path.is_file()), None)
        if path is None:
            raise HistoryError(f'Original {name} is not retained; this journal cannot restore a complete restart.')
        safe_path(model, path.relative_to(model).as_posix())
        source_paths[name] = path
    recorded = {}
    for record in plan.get('inputs', []):
        try:
            relative = Path(record['path']).relative_to(Path(plan['model'])).as_posix()
            recorded[relative] = record
        except (KeyError, ValueError, TypeError):
            continue
    for name, path in source_paths.items():
        if name in RESTART_FILES and name not in before:
            continue
        original = recorded.get(name, {})
        if not original.get('exists') or (original.get('size'), original.get('mtime_ns')) != (path.stat().st_size, path.stat().st_mtime_ns):
            raise HistoryError(f'Archived {name} does not match its original input record.')
        if original.get('sha256') and hashlib.sha256(path.read_bytes()).hexdigest() != original['sha256']:
            raise HistoryError(f'Archived {name} differs from its recorded input digest.')
    # Current physics and grid must still match the archived run's starting controls.
    controls = {}
    for name in ('VADAT', 'MODEL_SPEC'):
        current = model / name
        if current.is_symlink() or not current.is_file() or current.stat().st_nlink != 1:
            raise HistoryError(f'Current {name} must be an unshared regular control file.')
        if current.read_bytes() != source_paths[name].read_bytes():
            raise HistoryError(f'Current {name} differs from the archived controls. Review controls before recovering this restart.')
        controls[name] = snapshot(current)
    # Link targets present before the archived run are evidence about its saved checkpoint.
    link_path = archive / 'links-before.json'
    safe_path(model, link_path.relative_to(model).as_posix())
    old_links = _json(link_path)
    links = {}
    for link in plan.get('links', []):
        name = link.get('name', '')
        if not name or Path(name).name != name:
            raise HistoryError('Invalid recorded atomic link.')
        path = model / name
        old = old_links.get(name)
        if not old or not path.is_symlink() or os.readlink(path) != old:
            raise HistoryError(f'Atomic link {name} no longer matches the pre-run checkpoint environment.')
        target = path.resolve()
        if not target.is_file() or not os.access(target, os.R_OK):
            raise HistoryError(f'Atomic target for {name} is no longer readable.')
        links[name] = {'target': old, 'snapshot': snapshot(target)}
    try:
        restart = inspect_restart(_ArchivedRestart(source_paths))
    except (OSError, ValueError, KeyError) as exc:
        raise HistoryError(f'Archived checkpoint validation failed: {exc}') from exc
    if restart['mode'] != 'continuation' or restart['errors']:
        raise HistoryError('Archived checkpoint cannot continue: ' + '; '.join(restart['errors']))
    restore = {name: path.relative_to(model).as_posix() for name, path in source_paths.items()
               if name not in {'MODEL_SPEC', 'VADAT'} and (name not in RESTART_FILES or name in before)}
    current = {}
    for name in (*MAIN_STATE_FILES, MODEL_INPUT_MODIFIED_MARKER):
        path = model / name
        if path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_nlink != 1)):
            raise HistoryError(f'Unsafe current model state: {name}.')
        current[name] = snapshot(path)
    return {'archive_id': archive_id, 'archive_signature': tree_signature(_tree(archive)),
            'restore': restore, 'controls': controls, 'links': links, 'current': current,
            'restart': restart, 'keep_large_files': keep_large_files,
            'staging_bytes': sum((model / source).stat().st_size for source in restore.values())}


def apply_restart(model, review):
    with MODEL_WRITE_LOCK, model_mutation_guard(model, HistoryError):
        current = preview_restart(model, review['archive_id'], keep_large_files=review['keep_large_files'])
        if current != review:
            raise HistoryError('Model or archive changed after review; preview recovery again.')
        if shutil.disk_usage(model).free < review['staging_bytes'] + 1024**3:
            raise HistoryError('Insufficient space to stage recovery plus 1 GiB working headroom.')
        backup_root = model / '.cmfgen-viewer-backups'
        if backup_root.is_symlink() or (backup_root / 'history-restore').is_symlink():
            raise HistoryError('Recovery backup directories must not be symlinks.')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '-' + uuid.uuid4().hex[:8]
        backup = backup_root / 'history-restore' / stamp
        mkdir_readable(backup, parents=True)
        mkdir_readable(backup / 'before')
        mkdir_readable(backup / 'staged')
        moved, installed = [], []
        try:
            for name, source in review['restore'].items():
                copy_readable(safe_path(model, source), backup / 'staged' / name)
            for name in review['current']:
                target = model / name
                if target.is_file():
                    os.replace(target, backup / 'before' / name)
                    moved.append(name)
                    make_readable(backup / 'before' / name)
            for name in review['restore']:
                os.replace(backup / 'staged' / name, model / name)
                installed.append(name)
            installed.append(MODEL_INPUT_MODIFIED_MARKER)
            mark_model_inputs_modified(model, file_relpath='Recovered native restart',
                                       backup_relpath=backup.relative_to(model).as_posix())
            with open_readable(backup / 'restore.json', 'w') as stream:
                json.dump({'source': review['archive_id'], 'restored': list(review['restore']),
                           'backed_up': moved, 'keep_large_files': review['keep_large_files']}, stream)
        except (OSError, ValueError) as exc:
            failures = []
            for name in reversed(installed):
                try:
                    (model / name).unlink(missing_ok=True)
                except OSError as restore_exc:
                    failures.append(str(restore_exc))
            for name in reversed(moved):
                try:
                    os.replace(backup / 'before' / name, model / name)
                except OSError as restore_exc:
                    failures.append(str(restore_exc))
            detail = (' Rollback needs attention: ' + '; '.join(failures)) if failures else ''
            raise HistoryError(f'Could not restore restart: {exc}.{detail} Recovery copies: {backup}') from exc
        recovery = compact_recovery(backup, keep_large_files=review['keep_large_files'])
        try:
            (backup / 'staged').rmdir()
        except OSError as exc:
            recovery['warnings'].append(f'Restart restored, but staging directory cleanup failed: {exc}')
        return {'backup': backup.relative_to(model).as_posix(), 'recovery': recovery}
