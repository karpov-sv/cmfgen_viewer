"""Bound recovery storage while retaining metadata and useful diagnostic excerpts."""

import os
from pathlib import Path
import stat
import tempfile

from .workflow_permissions import copy_readable, make_readable

RECOVERY_FILE_LIMIT = 2 * 1024 * 1024
DIAGNOSTIC_FILES = {'OUTGEN', 'OUTLTE', 'OUT_FLUX', 'WIND_HYD', 'WARNINGS',
                    'TIMING', 'OUT_PARAMS', 'ML_COUNTER'}


def _diagnostic(path):
    return path.name in DIAGNOSTIC_FILES or path.suffix == '.log'


def _excerpt(source: Path, destination: Path):
    marker = b'\n\n[... middle of large diagnostic log omitted; enable keep_large_files for full logs ...]\n\n'
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


def copy_recovery(source: Path, destination: Path, *, keep_large_files=False):
    if keep_large_files or source.stat().st_size <= RECOVERY_FILE_LIMIT:
        copy_readable(source, destination)
    elif _diagnostic(source):
        _excerpt(source, destination)


def retire_recovery(source: Path, destination: Path, *, keep_large_files=False):
    if keep_large_files or source.stat().st_size <= RECOVERY_FILE_LIMIT:
        source.rename(destination)
        make_readable(destination)
    else:
        copy_recovery(source, destination, keep_large_files=False)
        source.unlink()


def compact_recovery(directory: Path, *, keep_large_files=False):
    """Compact only this operation's completed archive; never follow symlinks.

    JSON history is always kept. Call after a transaction has committed, when its
    large rollback files are no longer needed. Failed removals remain recoverable.
    """
    summary = {'keep_large_files': keep_large_files, 'file_limit_bytes': RECOVERY_FILE_LIMIT,
               'discarded_files': [], 'excerpted_logs': [], 'bytes_released': 0, 'warnings': []}
    if keep_large_files or directory.is_symlink() or not directory.exists():
        return summary
    for folder, _, names in os.walk(directory, followlinks=False):
        for name in names:
            path = Path(folder) / name
            try:
                info = path.lstat()
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or info.st_size <= RECOVERY_FILE_LIMIT or path.suffix in {'.json', '.jsonl'}):
                    continue
                relative = path.relative_to(directory).as_posix()
                if _diagnostic(path):
                    _excerpt(path, path)
                    summary['excerpted_logs'].append(relative)
                    summary['bytes_released'] += info.st_size - path.stat().st_size
                else:
                    path.unlink()
                    summary['discarded_files'].append(relative)
                    summary['bytes_released'] += info.st_size
            except OSError as exc:
                summary['warnings'].append(f'Could not compact {path.name}: {exc}')
    return summary
