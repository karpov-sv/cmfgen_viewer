"""Eligibility checks for the patched population-fraction initialization path."""
import math
from pathlib import Path

from .control_files import control_occurrences
from .parsers.common import parse_float_token

POP_MARKER = 'POP: interpolated source superlevel fractions; Ne set from charge conservation'


def pop_initialization_controls(contents):
    rows = control_occurrences(contents)
    for key in ('DC_METH', 'LIN_INT', 'POP_SCALE', 'LTE_EST'):
        if len(rows.get(key, [])) > 1:
            raise ValueError(f'Duplicate [{key}]; review before POP initialization')
    for key in ('LIN_INT', 'POP_SCALE'):
        if not rows.get(key) or rows[key][0]['value'].upper().strip('.') not in {'T', 'TRUE'}:
            raise ValueError(f'POP requires explicit [{key}]=T; existing interpolation settings are preserved')
    if rows.get('LTE_EST') and rows['LTE_EST'][0]['value'].upper().strip('.') not in {'F', 'FALSE'}:
        raise ValueError('POP requires LTE_EST=F when present')
    # Only DC_METH is overridden, with the ordinary temporary-control lifecycle.
    return {'DC_METH': 'POP'}


def supports_pop(executable):
    """Require the compiled native path's exact success marker, not nearby source."""
    marker = POP_MARKER.encode()
    path = Path(executable)
    if path.stat().st_size > 256 * 1024**2:
        return False
    tail = b''
    with path.open('rb') as stream:
        while chunk := stream.read(1024**2):
            data = tail + chunk
            if marker in data:
                return True
            tail = data[-len(marker):]
    return False


def _source_grid(path, full_levels=None):
    """Validate the native reader's three text formats without reconstructing atoms.

    Native POP still checks contiguous ion stages, atomic mappings, occupation
    convergence, and conservation. A failed native validation rolls back the trial.
    """
    if not path.is_file() or path.stat().st_size > 64 * 1024**2:
        raise ValueError(f'Missing or oversized POP source: {path.name}')
    with path.open() as stream:
        formatted = False
        fmt = ''
        for _ in range(11):
            line = stream.readline()
            if '!Format date' in line:
                formatted, fmt = True, line
                break
        if not formatted:
            stream.seek(0)
        def numbers():
            for line in stream:
                text = line.split('!', 1)[0].strip()
                if not text:
                    continue
                values = [parse_float_token(t) for t in text.split()]
                if any(v is None or not math.isfinite(v) for v in values):
                    raise ValueError(f'Invalid numeric POP source record: {path.name}')
                return values
            raise ValueError(f'Incomplete POP source: {path.name}')
        header = numbers()
        if len(header) != 4:
            raise ValueError(f'Invalid POP source header: {path.name}')
        nf, nd = header[2:]
        if nf != int(nf) or nd != int(nd) or nf < 1 or nd < 2 or nf > 100000 or nd > 100000:
            raise ValueError(f'Invalid POP source dimensions: {path.name}')
        nf, nd = int(nf), int(nd)
        if full_levels is not None and nf != full_levels:
            raise ValueError(f'POP source full-level count differs from MODEL_SPEC: {path.name}')
        logarithmic = '18-Nov-2010' in fmt or '10-Dec-2010' in fmt
        grid = []
        for _ in range(nd):
            row = numbers()
            if len(row) < (7 if formatted else 4):
                raise ValueError(f'Incomplete POP depth record: {path.name}')
            radius, seed, ne, temp = row[:4]
            clump = row[6] if formatted else 1.0
            if min(radius, ne, temp, clump) <= 0 or seed < 0:
                raise ValueError(f'Invalid physical POP source grid: {path.name}')
            if grid and radius >= grid[-1][0]:
                raise ValueError(f'Non-monotonic POP source radius: {path.name}')
            grid.append([radius, ne, temp, clump])
            count = 0
            while count < nf:
                values = numbers()
                if not logarithmic and formatted and min(values) < 0:
                    raise ValueError(f'Negative ordinary departure coefficient: {path.name}')
                count += len(values)
            if count != nf:
                raise ValueError(f'Wrong departure coefficient count: {path.name}')
        return grid


def pop_source_evidence(model, plan):
    """Require original, complete explicit-ion inputs on one matching saved grid."""
    from .runner_recipe import snapshot
    model = Path(model)
    pop_initialization_controls((model/'VADAT').read_text())
    if not supports_pop(plan['executable']):
        raise ValueError('Executable does not establish support for the patched DC_METH=POP path')
    rows = control_occurrences((model/'MODEL_SPEC').read_text())
    atoms = {}
    filenames = {}
    for path in model.glob('*_IN'):
        name = path.name.upper()
        if name in filenames:
            raise ValueError(f'Ambiguous source filename for POP: {name}')
        filenames[name] = path.name
    for key, entries in rows.items():
        if not key.endswith(('_ISF', '_NSF')):
            continue
        if len(entries) != 1:
            raise ValueError(f'Ambiguous POP atomic dimensions: {key}')
        values = [int(v.strip()) for v in entries[0]['value'].split(',')]
        expected = 3 if key.endswith('_ISF') else 2
        if len(values) != expected or min(values) < 0:
            raise ValueError(f'Invalid POP atomic dimensions: {key}')
        ns, nf = values[-2:]
        if ns:
            if nf < ns or nf < 1:
                raise ValueError(f'Invalid POP level mapping dimensions: {key}')
            name = key[:-4]+'_IN'
            name = filenames.get(name, name)
            if name in atoms:
                raise ValueError(f'Duplicate POP atomic specification: {name}')
            atoms[name] = nf
    if not atoms:
        raise ValueError('No explicit source atoms established in MODEL_SPEC for POP recovery')
    reviewed = {p['path']: p for p in plan['inputs']}
    # The native runner supplies T_IN from He2_IN for a fresh startup.
    sources = {'He2_IN': None, **atoms}
    grids = {}
    for name, nf in sources.items():
        path = model/name
        if reviewed.get(str(path)) != snapshot(path) or not reviewed[str(path)]['exists']:
            raise ValueError(f'POP requires an unchanged original input, not an AUTO_ADD-generated estimate: {name}')
        grids[name] = _source_grid(path, nf)
    reference = grids['He2_IN']
    for name, grid in grids.items():
        if len(grid) != len(reference) or any(
                abs(b/a-1) > tolerance
                for old, new in zip(reference, grid)
                for a, b, tolerance in zip(old, new, (1e-10, 1e-6, 1e-6, 1e-6))):
            raise ValueError(f'POP inputs do not describe one common source model: {name}')
    return {'source_depths': len(reference), 'source_atoms': sorted(atoms),
            'native_validation_required': 'contiguous stages, atomic mappings, occupation convergence and conservation'}
