"""Read-only evidence of native negative-r²J replacements.

MOM_J_ERRORS depth indices belong to the internal transfer grid. They must not
be interpreted as atmosphere depth indices when VFRAC_MOM inserts points.
"""
import math
import re

from .parsers.common import parse_float_token
from .runner_recipe import snapshot


def negative_moment_intensities(model, before, started, iteration):
    path = model / 'MOM_J_ERRORS'
    if path.is_symlink() or not path.is_file():
        return None
    info = path.stat()
    if (info.st_size > 4 * 1024**2 or info.st_mtime < started or
            'MOM_J_ERRORS' not in before or snapshot(path) == before['MOM_J_ERRORS']):
        return None
    text = path.read_text()
    footer = re.fullmatch(
        r'(?s)(.*?)\s*Iteration No\s+(\d+)\s+'
        r'Error in MOM_J_CMF for the following frequencies:\s+'
        r'Number of frequencies for which error occurs:\s+(\d+)\s+(.*?)\s*', text)
    if footer is None or int(footer[2]) != iteration:
        return None
    frequencies = [parse_float_token(t) for t in footer[4].split()]
    if (len(frequencies) != int(footer[3]) or
            any(v is None or not math.isfinite(v) or v <= 0 for v in frequencies)):
        return None
    rows = []
    # Compact native output has a fourteen-column negative-J row, followed by
    # a five-value continuation containing the pre-solve RHS. Verbose layouts
    # and partial/broken records cannot establish this recognition signature.
    pending = None
    for line in footer[1].splitlines():
        tokens = line.split()
        if not tokens:
            continue
        values = [parse_float_token(t) for t in tokens]
        if any(v is None or not math.isfinite(v) for v in values):
            return None
        if pending is not None:
            if len(values) != 5:
                return None
            rows.append(pending)
            pending = None
            continue
        if (len(values) != 14 or not tokens[0].isdigit() or
                not 1 <= values[0] <= 1_000_000 or values[1] <= 0 or
                values[2] >= 0 or values[3] < 0 or values[4] <= 0 or values[5] < 0):
            return None
        pending = {'transfer_depth': int(values[0]), 'frequency': values[1],
                   'raw_r_squared_j': values[2]}
    recorded = sorted({r['frequency'] for r in rows})
    if (pending is not None or not rows or
            len(recorded) != len(frequencies) or
            any(not math.isclose(a, b, rel_tol=1e-6)
                for a, b in zip(recorded, sorted(frequencies)))):
        return None
    # Reject a file which changed while it was being interpreted.
    after = path.stat()
    if (info.st_size, info.st_mtime_ns, info.st_ino) != (
            after.st_size, after.st_mtime_ns, after.st_ino):
        return None
    return {'iteration': iteration, 'rows': len(rows), 'frequencies': len(frequencies),
            'minimum_raw_r_squared_j': min(r['raw_r_squared_j'] for r in rows),
            'transfer_depth_min': min(r['transfer_depth'] for r in rows),
            'transfer_depth_max': max(r['transfer_depth'] for r in rows),
            'sample': rows[:5], 'snapshot': snapshot(path)}
