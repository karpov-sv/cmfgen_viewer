"""Complete fresh-start input bundles and reviewed, transactional restoration."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import uuid

from .control_files import control_occurrences
from .model_activity import model_mutation_guard
from .model_editor import MODEL_INPUT_MODIFIED_MARKER, mark_model_inputs_modified
from .model_history import HistoryError, get_archive, safe_path, _json, _tree, tree_signature
from .model_staging import MODEL_WRITE_LOCK
from .model_workflow import MAIN_STATE_FILES
from .recovery_files import INPUT_FILES, compact_recovery
from .runner_recipe import snapshot
from .workflow_permissions import copy_readable, mkdir_readable, open_readable, make_readable


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def _regular(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise HistoryError(f'Require an unshared regular file: {path}')
    return info


def capture_inputs(model, archive, plan):
    """Record pre-run inputs, never filling absent inputs from future live files."""
    required = {'VADAT', 'MODEL_SPEC', 'IN_ITS', 'He2_IN', 'GAMMAS_IN'}
    vadat = control_occurrences((model / 'VADAT').read_text())
    velocity = vadat.get('VEL_OPT', [])
    if velocity and velocity[0]['value'].strip().upper() == 'RVSIG_COL':
        required.add('RVSIG_COL')
    spec = control_occurrences((model / 'MODEL_SPEC').read_text())
    populations = {path.name.upper(): path.name for path in model.glob('*_IN')}
    method = vadat.get('DC_METH', [])
    if not method or method[0]['value'].strip().upper() != 'LTE':
        for key, rows in spec.items():
            if key.endswith(('_ISF', '_NSF')):
                dimensions = [int(value.strip()) for value in rows[0]['value'].split(',')]
                if dimensions[-2] > 0:
                    name = key[:-4] + '_IN'
                    required.add(populations.get(name.upper(), name))
    names = required | {path.name for path in model.iterdir()
                        if path.name in INPUT_FILES or path.name.endswith('_IN')
                        or path.name == 'atomic_links.json'}
    names.discard('T_IN')
    files, missing = [], []
    mkdir_readable(archive / 'inputs', exist_ok=True)
    needed = sum((model / name).lstat().st_size for name in names
                 if (model / name).exists() and not (model / name).is_symlink())
    can_save = shutil.disk_usage(model).free >= needed + 1024**3
    if not can_save:
        missing.append('Insufficient space to save the full input bundle plus 1 GiB working headroom')
    for name in sorted(names) if can_save else []:
        source = model / name
        if not source.exists() and not source.is_symlink():
            if name in required:
                missing.append(name)
            continue
        try:
            info = _regular(source)
            if not info.st_size:
                raise HistoryError(f'Empty input: {name}')
            before = digest(source)
            target = archive / 'inputs' / name
            copy_readable(source, target)
            if digest(target) != before or digest(source) != before:
                raise HistoryError(f'Input changed while archiving: {name}')
            files.append({'target': name, 'source': f'inputs/{name}',
                          'size': info.st_size, 'sha256': before})
        except (OSError, ValueError) as exc:
            missing.append(f'{name}: {exc}')
    # Atomic files remain external dependencies, identified but never copied.
    dependency_paths = {link['target'] for link in plan.get('links', [])
                        if link['name'] != 'T_IN' and not Path(link['target']).is_relative_to(model)}
    dependency_paths.update(record['path'] for record in plan.get('inputs', [])
                            if not Path(record['path']).is_relative_to(model))
    dependencies = [snapshot(Path(path)) for path in sorted(dependency_paths)]
    manifest = {'version': 1, 'model': str(model), 'stage': plan['stage'],
                'files': files, 'required': sorted(required), 'missing': missing,
                'dependencies': dependencies, 'complete': not missing,
                'meaning': 'Pre-run input controls; temporary runner overrides are recorded in the run plan.'}
    with open_readable(archive / 'fresh-inputs.json', 'w') as stream:
        json.dump(manifest, stream, indent=2)
    return manifest


def _state(model, input_names):
    """Inventory inputs and derived state that would otherwise belong to old controls."""
    paths = {model / name for name in (*MAIN_STATE_FILES, MODEL_INPUT_MODIFIED_MARKER,
             'GAMMAS', 'OBSFLUX', 'OUTGEN', 'WARNINGS', 'TIMING', 'OUT_PARAMS')}
    paths.update(model / name for name in set(input_names) | INPUT_FILES | {'atomic_links.json'})
    for path in model.iterdir():
        if path.name.endswith(('_IN', 'OUT')) or path.name.startswith('POP') or path.is_symlink():
            paths.add(path)
    obs = model / 'obs'
    if obs.is_dir() and not obs.is_symlink():
        for path in obs.iterdir():
            if path.name.startswith(('obs_fin', 'obs_cont')) or path.name in {
                'OBSFRAME', 'OUT_FLUX', 'batobs.log', 'EDDFACTOR', 'EDDFACTOR_INFO',
                'ES_J_CONV', 'ES_J_CONV_INFO', 'J_COMP', 'MEANOPAC', 'TRANS_INFO'}:
                paths.add(path)
    result = {}
    for path in sorted(paths):
        name = path.relative_to(model).as_posix()
        if path.is_symlink():
            if name in input_names or name == MODEL_INPUT_MODIFIED_MARKER:
                raise HistoryError(f'Unsafe current input: {name}')
            result[name] = {'kind': 'link', 'target': os.readlink(path), 'signature': tree_signature(_tree(path))}
        elif path.exists():
            _regular(path)
            result[name] = {'kind': 'file', 'signature': tree_signature(_tree(path))}
        else:
            result[name] = None
    return result


def preview_inputs(model, archive_id):
    archive, _ = get_archive(model, archive_id)
    manifest_path = archive / 'fresh-inputs.json'
    if not manifest_path.is_file():
        raise HistoryError('This archive has no saved fresh-run input bundle. Individual retained controls remain available.')
    safe_path(model, manifest_path.relative_to(model).as_posix())
    manifest = _json(manifest_path)
    if manifest.get('version') != 1 or manifest.get('stage') not in {'main', 'test'}:
        raise HistoryError('This archive has no supported fresh-run input bundle.')
    missing = manifest.get('missing', [])
    if not isinstance(missing, list) or not all(isinstance(name, str) for name in missing):
        raise HistoryError('Malformed fresh-run completeness record.')
    if not manifest.get('complete') or missing:
        raise HistoryError('Fresh-run inputs are incomplete: ' + ', '.join(missing))
    records = manifest.get('files', [])
    if (not isinstance(records, list) or any(not isinstance(entry, dict)
            or not isinstance(entry.get('target'), str) or not isinstance(entry.get('source'), str)
            or not isinstance(entry.get('size'), int) or entry['size'] <= 0
            or not isinstance(entry.get('sha256'), str) or len(entry['sha256']) != 64 for entry in records)
            or not isinstance(manifest.get('required'), list)
            or not all(isinstance(name, str) for name in manifest['required'])
            or not isinstance(manifest.get('dependencies', []), list)):
        raise HistoryError('Malformed fresh-run input manifest.')
    names = [entry['target'] for entry in records]
    mandatory = {'VADAT', 'MODEL_SPEC', 'IN_ITS', 'He2_IN', 'GAMMAS_IN'}
    if (not mandatory <= set(names) or not set(manifest.get('required', [])) <= set(names)
            or len(names) != len(set(names))):
        raise HistoryError('Fresh-run manifest is missing required inputs or contains duplicate targets.')
    for entry in records:
        name = entry['target']
        if (not name or Path(name).name != name or name in {'.', '..'}
                or not (name in INPUT_FILES or name.endswith('_IN') or name == 'atomic_links.json')
                or entry['source'] != f'inputs/{name}'):
            raise HistoryError('Invalid fresh-run input mapping.')
        try:
            source = safe_path(model, (Path(archive_id) / entry['source']).as_posix())
        except (FileNotFoundError, HistoryError) as exc:
            candidate = archive / entry['source']
            if not candidate.exists() and not candidate.is_symlink():
                raise HistoryError(f'Archived input is missing: {name}') from exc
            raise
        info = _regular(source)
        if info.st_size != entry['size'] or digest(source) != entry['sha256']:
            raise HistoryError(f'Archived input changed or is incomplete: {name}')
    for old in manifest.get('dependencies', []):
        if not isinstance(old, dict) or not isinstance(old.get('path'), str) or not Path(old['path']).is_absolute():
            raise HistoryError('Malformed external dependency record.')
        if not old.get('exists') or snapshot(Path(old['path'])) != old:
            raise HistoryError(f"Atomic dependency changed or is unavailable: {old['path']}")
    current = _state(model, names)
    return {'archive_id': archive_id, 'archive_signature': tree_signature(_tree(archive)),
            'files': records, 'dependencies': manifest.get('dependencies', []), 'current': current,
            'staging_bytes': sum(entry['size'] for entry in records),
            'warnings': ['Restore the saved pre-run controls. Temporary iteration/LTE initialization overrides are not reapplied. '
                         'Review main preflight after restoration; no calculation starts.']}


def apply_inputs(model, review):
    with MODEL_WRITE_LOCK, model_mutation_guard(model, HistoryError):
        current = preview_inputs(model, review['archive_id'])
        if current != review:
            raise HistoryError('Model or archive changed after review; preview fresh-input recovery again.')
        if shutil.disk_usage(model).free < review['staging_bytes'] + 1024**3:
            raise HistoryError('Insufficient space to stage inputs plus 1 GiB working headroom.')
        root = model / '.cmfgen-viewer-backups'
        if root.is_symlink() or (root / 'input-restore').is_symlink():
            raise HistoryError('Recovery backup directories must not be symlinks.')
        backup = root / 'input-restore' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ-') + uuid.uuid4().hex[:8])
        mkdir_readable(backup, parents=True)
        mkdir_readable(backup / 'staged')
        mkdir_readable(backup / 'before')
        moved, installed = [], []
        try:
            for entry in review['files']:
                source = safe_path(model, (Path(review['archive_id']) / entry['source']).as_posix())
                copy_readable(source, backup / 'staged' / entry['target'])
                if digest(backup / 'staged' / entry['target']) != entry['sha256']:
                    raise HistoryError('An archived input changed during staging.')
            if _state(model, [entry['target'] for entry in review['files']]) != review['current']:
                raise HistoryError('Working files changed during staging.')
            for name, record in review['current'].items():
                if record is not None:
                    destination = backup / 'before' / name
                    mkdir_readable(destination.parent, parents=True, exist_ok=True)
                    os.replace(model / name, destination)
                    moved.append(name)
                    make_readable(destination)
            for entry in review['files']:
                name = entry['target']
                os.replace(backup / 'staged' / name, model / name)
                installed.append(name)
            installed.append(MODEL_INPUT_MODIFIED_MARKER)
            mark_model_inputs_modified(model, file_relpath='Restored fresh-run inputs',
                                       backup_relpath=backup.relative_to(model).as_posix())
            with open_readable(backup / 'restore.json', 'w') as stream:
                json.dump({'source': review['archive_id'], 'restored': installed, 'retired': moved}, stream)
        except BaseException as exc:
            failures = []
            for name in reversed(installed):
                try:
                    (model / name).unlink(missing_ok=True)
                except OSError as problem:
                    failures.append(str(problem))
            for name in reversed(moved):
                try:
                    os.replace(backup / 'before' / name, model / name)
                except OSError as problem:
                    failures.append(str(problem))
            if failures:
                raise HistoryError(f'Restore failed: {exc}. Rollback needs attention: {failures}. Copies: {backup}') from exc
            raise
        recovery = compact_recovery(backup)
        try:
            (backup / 'staged').rmdir()
        except OSError as exc:
            recovery['warnings'].append(f'Inputs restored, but staging directory cleanup failed: {exc}')
        return {'backup': backup.relative_to(model).as_posix(), 'recovery': recovery}
