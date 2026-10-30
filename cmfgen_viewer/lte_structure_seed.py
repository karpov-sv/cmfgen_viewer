"""Validate a model's own LTE/hydro thermal seed before a fresh-only reset."""
import math
from pathlib import Path

from .control_files import control_occurrences
from .parsers.common import parse_float_token
from .runner_validation import validate_rvsig_structure


def lte_structure_source(model):
    from .runner_recipe import snapshot

    model = Path(model)
    folder = model/'lte'
    source = folder/'FIN_CAL_GRID'
    paired = folder/'RVSIG_COL_NEW'
    controls = folder/'VADAT'
    paths = [source, paired, controls, model/'RVSIG_COL', model/'MODEL_SPEC']
    dependencies = [controls]
    hydro_controls = folder/'HYDRO_PARAMS'
    if hydro_controls.exists() or hydro_controls.is_symlink():
        dependencies.append(hydro_controls)
    if folder.is_symlink() or any(
            p.is_symlink() or not p.is_file() or p.stat().st_nlink != 1
            for p in [*paths, *dependencies]):
        raise ValueError('LTE structure seed needs local unshared FIN_CAL_GRID, VADAT and paired promoted hydro grid')
    if any(p.stat().st_size > 2*1024**2 for p in [*paths, *dependencies]):
        raise ValueError('LTE structure seed files are unexpectedly large')
    if paired.read_bytes() != (model/'RVSIG_COL').read_bytes():
        raise ValueError('LTE structure seed belongs to an unpromoted or different hydro grid')
    if min(source.stat().st_mtime_ns, paired.stat().st_mtime_ns) < max(
            p.stat().st_mtime_ns for p in dependencies):
        raise ValueError('LTE structure outputs predate their control files')
    original = control_occurrences((model/'VADAT').read_text())
    lte = control_occurrences(controls.read_text())
    keys = {'TEFF', 'LOGG', 'LSTAR', 'MDOT'} | {k for k in original.keys() | lte.keys() if k.endswith('/X')}
    for key in keys:
        a, b = original.get(key, []), lte.get(key, [])
        if len(a) != 1 or len(b) != 1:
            raise ValueError(f'LTE structure seed lacks an unambiguous matching [{key}]')
        av, bv = parse_float_token(a[0]['value']), parse_float_token(b[0]['value'])
        if (av is None or bv is None or not all(math.isfinite(v) for v in (av, bv))
                or abs(av-bv) > 1e-8*max(abs(av), abs(bv), 1e-30)):
            raise ValueError(f'LTE structure seed has different [{key}]')
    validate_rvsig_structure(paired, model/'MODEL_SPEC')
    hydro = []
    for line in paired.read_text().splitlines():
        parts = line.split()
        if len(parts) == 5 and parts[-1].isdigit():
            values = [parse_float_token(t) for t in parts[:4]]
            if all(v is not None for v in values):
                hydro.append(values)
    lines = source.read_text().splitlines()
    if not lines or lines[0].split()[:7] != ['Index', 'R', 'TAU', 'V', 'T', 'Na', 'Ne/Na']:
        raise ValueError('Unrecognized LTE structure seed header')
    rows = []
    for line in lines[1:]:
        if not line.strip():
            continue
        values = [parse_float_token(t) for t in line.split()]
        if len(values) != 10 or any(v is None or not math.isfinite(v) for v in values):
            raise ValueError('Incomplete or nonfinite LTE structure seed row')
        if values[0] != len(rows)+1 or min(values[i] for i in (1, 4, 5, 6)) <= 0 or min(values[2:4]) < 0:
            raise ValueError('Invalid LTE structure seed index, geometry or thermodynamic state')
        if not math.isfinite(values[5]*values[6]) or values[5]*values[6] <= 0:
            raise ValueError('LTE structure seed electron density is not finite and positive')
        rows.append(values)
    if not rows or len(rows) != len(hydro):
        raise ValueError('LTE structure seed depth count differs from the promoted grid')
    for row, grid in zip(rows, hydro):
        if abs(row[1]/grid[0]-1) > 1e-4 or abs(row[3]-grid[1]) > 1e-4*max(abs(grid[1]), 1e-12):
            raise ValueError('LTE structure seed radii/velocities differ from the promoted grid')
    if any(b[1] >= a[1] or b[2] < a[2] for a, b in zip(rows, rows[1:])):
        raise ValueError('LTE structure seed radius/optical-depth order is invalid')
    return {'source': snapshot(source),
            'dependencies': [snapshot(p) for p in paths[1:]+dependencies[1:]],
            'depths': len(rows), 'temperature_min': min(r[4] for r in rows),
            'temperature_max': max(r[4] for r in rows),
            'temperatures': [r[4] for r in rows]}
