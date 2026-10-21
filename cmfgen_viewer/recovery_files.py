"""Bound recovery storage while retaining metadata and useful diagnostic excerpts."""

import os
import json
from pathlib import Path
import stat
import tempfile

from .workflow_permissions import copy_readable, make_readable

RECOVERY_FILE_LIMIT = 2 * 1024 * 1024
DIAGNOSTIC_FILES = {'OUTGEN', 'OUTLTE', 'OUT_FLUX', 'WIND_HYD', 'WARNINGS',
                    'TIMING', 'OUT_PARAMS', 'ML_COUNTER'}
INPUT_FILES = {'VADAT', 'MODEL_SPEC', 'IN_ITS', 'ADJUST_CORRECTIONS', 'GRID_PARAMS', 'HYDRO_PARAMS',
               'RVSIG_COL', 'ROSSELAND_LTE_TAB', 'HYDRO_DEFAULTS', 'ADJUST_R_DEFAULTS',
               'RDINR', 'IT_SPECIFIER', 'arnaud_rothenflug.dat', 'batch.sh', 'batch_ins.sh',
               'clean.sh', 'batobs.sh', 'bat_ins.sh', 'IN_FILE', 'CMF_FLUX_PARAM',
               'CMF_FLUX_PARAM_INIT', 'stdin.txt'}
CHECKPOINT_FILES = {'POINT1', 'POINT2', 'SCRTEMP', 'NEW_POINT1', 'NEW_POINT2', 'NEW_SCRTEMP'}


def retention_action(path, size, *, relative=None):
    """Compact storage preserves rerun inputs, metadata, and bounded diagnostics."""
    path = Path(path)
    if path.suffix in {'.json', '.jsonl', '.bak'}:
        return 'keep'
    if path.name in CHECKPOINT_FILES or path.name == 'T_IN':
        return 'discard'
    parts = Path(relative).parts if relative is not None else ()
    if (path.name in INPUT_FILES or path.name.endswith('_IN')
            or (parts and parts[0] == 'inputs')):
        return 'keep'
    if _diagnostic(path):
        return 'excerpt' if size > RECOVERY_FILE_LIMIT else 'keep'
    return 'discard'


def _diagnostic(path):
    return path.name in DIAGNOSTIC_FILES or path.suffix == '.log'


def _excerpt(source: Path, destination: Path):
    marker = b'\n\n[... middle of large diagnostic log omitted ...]\n\n'
    head = (RECOVERY_FILE_LIMIT - len(marker)) // 2
    tail = RECOVERY_FILE_LIMIT - len(marker) - head
    with source.open('rb') as stream:
        payload = stream.read(head)
        stream.seek(-tail, os.SEEK_END)
        payload += marker + stream.read(tail)
    descriptor, name = tempfile.mkstemp(prefix='.diagnostic-', dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(payload)
        make_readable(temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def copy_recovery(source: Path, destination: Path):
    action = retention_action(source, source.stat().st_size)
    if action == 'keep':
        copy_readable(source, destination)
    elif action == 'excerpt':
        _excerpt(source, destination)


def retire_recovery(source: Path, destination: Path):
    if retention_action(source, source.stat().st_size) == 'keep':
        source.rename(destination)
        make_readable(destination)
    else:
        copy_recovery(source, destination)
        source.unlink()


def _write_policy(directory, summary):
    temporary = None
    try:
        descriptor, name = tempfile.mkstemp(prefix='.recovery-compaction-', dir=directory)
        temporary = Path(name)
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(summary, stream, indent=2)
        make_readable(temporary)
        os.replace(temporary, directory / '.recovery-policy.json')
    except OSError as exc:
        summary['warnings'].append(f'Could not record recovery policy: {exc}')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def compact_recovery(directory: Path):
    """Keep fresh inputs and run evidence in a completed archive; never follow links.

    JSON history is always kept. Call after a transaction has committed, when its
    large rollback files are no longer needed. Failed removals remain recoverable.
    """
    summary = {'policy': 'fresh-inputs', 'diagnostic_limit_bytes': RECOVERY_FILE_LIMIT,
               'discarded_files': [], 'excerpted_logs': [], 'bytes_released': 0, 'warnings': []}
    if directory.is_symlink() or not directory.exists():
        return summary
    for folder, _, names in os.walk(directory, followlinks=False):
        for name in names:
            path = Path(folder) / name
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    continue
                relative = path.relative_to(directory).as_posix()
                action = retention_action(path, info.st_size, relative=relative)
                if action == 'keep':
                    continue
                if action == 'excerpt':
                    _excerpt(path, path)
                    summary['excerpted_logs'].append(relative)
                    summary['bytes_released'] += info.st_size - path.stat().st_size
                else:
                    path.unlink()
                    summary['discarded_files'].append(relative)
                    summary['bytes_released'] += info.st_size
            except OSError as exc:
                summary['warnings'].append(f'Could not compact {path.name}: {exc}')
    # A common policy record also covers workflow archives without a runner plan.
    _write_policy(directory, summary)
    return summary
