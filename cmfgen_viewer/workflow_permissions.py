"""Readable workflow artifacts without changing the viewer's process-wide umask."""

import os
from pathlib import Path
import shutil
import stat


def readable_mode(mode: int, *, directory: bool = False) -> int:
    permissions = stat.S_IMODE(mode) | 0o444
    if directory or permissions & 0o111:
        permissions |= 0o111
    return permissions


def make_readable(path: Path) -> None:
    """Add public read/traverse access to regular artifacts, skipping symlinks."""
    info = path.lstat()
    if stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode):
        path.chmod(readable_mode(info.st_mode, directory=stat.S_ISDIR(info.st_mode)))


def mkdir_readable(path: Path, *, parents: bool = False, exist_ok: bool = False) -> None:
    created_parents = []
    if parents:
        parent = path.parent
        while not parent.exists():
            created_parents.append(parent)
            parent = parent.parent
    path.mkdir(mode=0o755, parents=parents, exist_ok=exist_ok)
    for directory in reversed(created_parents):
        make_readable(directory)
    make_readable(path)


def copy_readable(source, destination, *, follow_symlinks: bool = True):
    copied = shutil.copy2(source, destination, follow_symlinks=follow_symlinks)
    make_readable(Path(copied))
    return copied


def open_readable(path: Path, mode: str):
    stream = path.open(mode)
    try:
        os.fchmod(stream.fileno(), readable_mode(os.fstat(stream.fileno()).st_mode))
    except BaseException:
        stream.close()
        raise
    return stream
