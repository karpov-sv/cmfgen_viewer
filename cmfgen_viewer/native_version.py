"""Dated revisions reported by the maintained cumulative CMFGEN patch stream."""
from datetime import date
from functools import lru_cache
import os
from pathlib import Path
import re
import subprocess
import tempfile

PATCH_STREAM = 'CMFGEN_VIEWER_PATCH'
MINIMUM_PATCH_REVISION = '2026-10-31.1'
OUTPUT_PREFIX = 'CMFGEN viewer patch revision:'


def revision_key(value):
    match = re.fullmatch(r'(\d{4}-\d{2}-\d{2})\.([1-9]\d*)', value or '')
    if not match:
        raise ValueError('Invalid CMFGEN patch revision')
    return date.fromisoformat(match[1]), int(match[2])


def _identity(path):
    st = path.stat()
    return str(path), st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


@lru_cache(maxsize=64)
def _probe(identity):
    path = Path(identity[0])
    env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    # Old executables may ignore --version. An empty directory and closed stdin
    # prevent them from finding a real model or starting its calculation.
    with tempfile.TemporaryDirectory(prefix='cmfgen-version-') as folder, tempfile.TemporaryFile() as output:
        try:
            result = subprocess.run([str(path), '--version'], cwd=folder, env=env,
                                    stdin=subprocess.DEVNULL, stdout=output,
                                    stderr=subprocess.DEVNULL, timeout=5)
            output.seek(0)
            text = output.read(4097)
            if result.returncode or len(text) > 4096 or _identity(path) != identity:
                return None
            lines = text.decode('ascii').splitlines()
        except (OSError, subprocess.TimeoutExpired, UnicodeError):
            return None
    versions = [line.split() for line in lines if line.startswith(PATCH_STREAM)]
    if len(versions) != 1 or len(versions[0]) != 2 or versions[0][0] != PATCH_STREAM:
        return None
    revision = versions[0][1]
    try:
        revision_key(revision)
    except ValueError:
        return None
    return revision


def executable_revision(executable):
    try:
        return _probe(_identity(Path(executable).resolve(strict=True)))
    except (OSError, ValueError):
        return None


def supports_revision(plan, *, minimum=MINIMUM_PATCH_REVISION):
    revision = executable_revision(plan.get('executable', ''))
    return revision is not None and revision_key(revision) >= revision_key(minimum)


def output_revision(path):
    """Read the producing revision from a file header, never for runtime gating."""
    try:
        with Path(path).open(errors='replace') as stream:
            text = stream.read(65536)
        matches = re.findall(re.escape(OUTPUT_PREFIX)+r'[ \t]*(\S+)[ \t]*$', text, re.M)
        if len(matches) != 1:
            return None
        revision_key(matches[0])
        return matches[0]
    except (OSError, ValueError):
        return None
