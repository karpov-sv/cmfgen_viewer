"""Prepare fresh native startup from the current text population outputs."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import stat
import uuid

from .model_activity import inspect_model_activity, model_mutation_guard
from .model_staging import MODEL_WRITE_LOCK
from .recovery_files import compact_recovery
from .runner_restart import RESTART_FILES
from .workflow_permissions import copy_readable, make_readable, mkdir_readable, open_readable


def _signature(path, *, required=False):
    try:
        info = path.lstat()
    except FileNotFoundError:
        if required:
            raise ValueError(f'Required output is missing: {path.name}')
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError(f'Require an unshared regular file: {path.name}')
    if required and not info.st_size:
        raise ValueError(f'Output is empty: {path.name}')
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def build_reseed_plan(model, *, keep_large_files=False):
    model = Path(model).resolve()
    entries, checkpoints, errors = [], [], []
    try:
        for folder in (model / '.cmfgen-viewer-backups',
                       model / '.cmfgen-viewer-backups/out2in'):
            if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
                raise ValueError(f'Recovery directory must be a real directory: {folder}')
        outputs = sorted(path.name for path in model.iterdir() if path.name.endswith('OUT'))
        if not outputs:
            errors.append('No *OUT population outputs were found.')
        destinations = set()
        for source in [*outputs, 'GAMMAS']:
            destination = 'GAMMAS_IN' if source == 'GAMMAS' else source[:-3] + '_IN'
            if destination in destinations:
                raise ValueError(f'Multiple outputs would replace {destination}.')
            destinations.add(destination)
            entries.append({'source': source, 'destination': destination,
                            'source_signature': _signature(model / source, required=True),
                            'destination_signature': _signature(model / destination)})
        for name in RESTART_FILES:
            signature = _signature(model / name)
            if signature is not None:
                checkpoints.append({'name': name, 'signature': signature})
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
    activity = inspect_model_activity(model)
    if not activity['safe_to_modify']:
        errors.append(activity['reason'] or 'Model activity is uncertain.')
    return {'command': 'out2in', 'model': str(model), 'entries': entries,
            'checkpoints': checkpoints, 'keep_large_files': keep_large_files,
            'activity': activity, 'errors': errors, 'ready': not errors,
            'warnings': ['The next main run starts from refreshed text inputs, not the binary checkpoint. '
                         'Outputs are preserved. Review population/grid and atomic-data compatibility before running.']}


def run_reseed_plan(plan):
    model = Path(plan['model'])
    with MODEL_WRITE_LOCK, model_mutation_guard(model):
        current = build_reseed_plan(model, keep_large_files=plan['keep_large_files'])
        if not current['ready']:
            raise ValueError('; '.join(current['errors']))
        if any(current[key] != plan[key] for key in ('entries', 'checkpoints')):
            raise ValueError('Restart inputs changed after planning; inspect a fresh plan.')
        archive = model / '.cmfgen-viewer-backups/out2in' / (
            datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ-') + uuid.uuid4().hex[:8])
        mkdir_readable(archive, parents=True)
        staged = archive / 'staged'
        previous = archive / 'previous'
        mkdir_readable(staged)
        mkdir_readable(previous)
        moved, installed = [], []
        try:
            # Stage all copies before changing any live input or checkpoint.
            for entry in current['entries']:
                copy_readable(model / entry['source'], staged / entry['destination'])
            for entry in current['entries']:
                if _signature(model / entry['source'], required=True) != entry['source_signature']:
                    raise ValueError(f"Output changed while copying: {entry['source']}")
                if _signature(model / entry['destination']) != entry['destination_signature']:
                    raise ValueError(f"Input changed while copying: {entry['destination']}")
            for entry in current['checkpoints']:
                if _signature(model / entry['name']) != entry['signature']:
                    raise ValueError(f"Checkpoint changed while copying: {entry['name']}")
            for entry in current['entries']:
                name = entry['destination']
                if entry['destination_signature'] is not None:
                    os.replace(model / name, previous / name)
                    moved.append(name)
                os.replace(staged / name, model / name)
                installed.append(name)
            for entry in current['checkpoints']:
                name = entry['name']
                os.replace(model / name, previous / name)
                moved.append(name)
            for name in moved:
                make_readable(previous / name)
            with open_readable(archive / 'operation.json', 'w') as stream:
                json.dump(current, stream, indent=2)
        except BaseException:
            # Keep complete rollback files until every replacement has succeeded.
            for name in reversed(installed):
                (model / name).unlink()
            for name in reversed(moved):
                os.replace(previous / name, model / name)
            shutil.rmtree(archive)
            raise
        staged.rmdir()
        recovery = compact_recovery(archive, keep_large_files=plan['keep_large_files'])
        return {'status': 'succeeded', 'archive_path': str(archive),
                'updated_inputs': installed, 'retired_checkpoints': [e['name'] for e in current['checkpoints']],
                'recovery': recovery}
