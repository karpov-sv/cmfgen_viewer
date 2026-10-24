"""Track edits coupled to RVSIG_COL and review isolated native revisions."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import uuid

from .control_files import control_occurrences
from .parsers.common import parse_float_token
from .model_activity import model_mutation_guard
from .model_staging import MODEL_WRITE_LOCK
from .workflow_permissions import mkdir_readable, open_readable

STATE_FILE = '.cmfgen-structure-update.json'
MODIFIED_FILE = '.cmfgen-viewer-input-modified.json'
SOURCES = ('VADAT', 'MODEL_SPEC', 'RVSIG_COL')
VELOCITY_KEYS = ('MDOT', 'RSTAR', 'VINF', 'BETA', 'VEL_OPT', 'RMAX', 'VCORE',
                 'VPHOT', 'VINF2', 'BETA2', 'EPS', 'EPS2', 'SCL_HT')
RETIRE = ('POINT1', 'POINT2', 'SCRTEMP', 'BAMAT', 'BAMATPNT', 'EDDFACTOR', 'J_COMP')
LIMIT = 2 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_text(path, *, limit=LIMIT):
    if path.stat().st_size > limit:
        raise ValueError(f'{path.name} exceeds the structure-update size limit.')
    return path.read_bytes().decode('utf-8')


def value(text, key):
    rows = control_occurrences(text).get(key, [])
    if len(rows) != 1:
        return None
    return rows[0]['value'].strip()


def number(text, key):
    result = parse_float_token(value(text, key) or '')
    if result is None or not math.isfinite(result) or result <= 0:
        raise ValueError(f'Structure update requires one finite positive [{key}].')
    return result


def uses_rvsig(text):
    return (value(text, 'VEL_OPT') or '').upper().startswith('RVSIG_COL')


def _same(a, b):
    def normalized(text):
        result = parse_float_token(text)
        return result if result is not None and math.isfinite(result) else text.upper()
    return len(a) == len(b) and all(normalized(x['value']) == normalized(y['value']) for x, y in zip(a, b))


def changed_keys(old, new, keys):
    a, b = control_occurrences(old), control_occurrences(new)
    return [key for key in keys if not _same(a.get(key, []), b.get(key, []))]


def _read_state(model):
    path = model / STATE_FILE
    if path.is_symlink():
        raise ValueError('Structure-update metadata must not be a symlink.')
    if not path.exists():
        return None
    state = json.loads(read_text(path, limit=8 * LIMIT))
    if not isinstance(state, dict) or state.get('version') != 1 or not isinstance(state.get('baseline'), dict) or not all(isinstance(state['baseline'].get(n), str) for n in SOURCES):
        raise ValueError('Invalid structure-update baseline; restore its recovery copy.')
    return state


def _write_state(model, state):
    from .model_editor import _atomic_replace
    _atomic_replace(model / STATE_FILE, (json.dumps(state, indent=2) + '\n').encode(), mode=0o644)


def review_warning(model, filename, old, new):
    if filename not in {'VADAT', 'MODEL_SPEC'}:
        return []
    vadat = new if filename == 'VADAT' else read_text(model / 'VADAT')
    if not (uses_rvsig(vadat) or (filename == 'VADAT' and uses_rvsig(old))):
        return []
    keys = changed_keys(old, new, VELOCITY_KEYS if filename == 'VADAT' else ('ND',))
    if not keys:
        return []
    return ['RVSIG_COL structure update required after changing ' + ', '.join(keys) +
            '. Saving these controls does not revise the tabulated hydrostatic/velocity structure. '
            'Use Update structure before starting a new atmosphere calculation.']


def track_before_edit(model, filename, old, new):
    """Save the original structure and controls before the first relevant edit."""
    if not review_warning(model, filename, old, new):
        return
    state = _read_state(model)
    if state is None or not state.get('pending', True):
        baseline = {name: read_text(model / name) if (model / name).is_file() else '' for name in SOURCES}
        baseline[filename] = old
        _write_state(model, {'version': 1, 'pending': True, 'baseline': baseline,
                            'captured_at': datetime.now(timezone.utc).isoformat()})


def inspect_structure_update(model):
    model = Path(model)
    available = False
    try:
        available = (model / 'VADAT').is_file() and uses_rvsig(read_text(model / 'VADAT'))
        state = _read_state(model)
        if state is None or not state.get('pending', True):
            return {'required': False, 'changes': [], 'tracked': False, 'available': available}
        old = state['baseline']
        current = {name: read_text(model / name) if (model / name).is_file() else '' for name in SOURCES}
        changes = changed_keys(old['VADAT'], current['VADAT'], VELOCITY_KEYS)
        changes += changed_keys(old['MODEL_SPEC'], current['MODEL_SPEC'], ('ND',))
        structure_changed = current['RVSIG_COL'] != old['RVSIG_COL']
        required = bool((changes or structure_changed) and uses_rvsig(current['VADAT']))
        return {'required': required, 'tracked': True, 'changes': changes,
                'available': available,
                'message': ('RVSIG_COL needs review/update after changes to ' + ', '.join(changes) + '.'
                            if changes else 'RVSIG_COL differs from the saved pre-edit structure.'),
                'structure_changed': structure_changed}
    except (OSError, ValueError, KeyError) as exc:
        return {'required': True, 'tracked': True, 'changes': [], 'message': str(exc), 'available': available}


def finish_structure_edit(model):
    """A full reversion resolves pending work; future native revisions are independent."""
    state = _read_state(model)
    status = inspect_structure_update(model) if state else {}
    if state and state.get('pending', True) and not status['required'] and not status['changes']:
        state['pending'] = False
        _write_state(model, state)


def parse_grid(text, *, require_indices=False):
    declared, rows = None, []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(('!', '#')):
            continue
        if declared is None:
            if re.search(r'!\s*Number of depth points', line, re.I):
                declared = int(stripped.split()[0])
            continue
        tokens = stripped.split('!', 1)[0].split()
        if len(tokens) < 3:
            raise ValueError('Incomplete RVSIG_COL row.')
        if require_indices and (len(tokens) not in {4, 5, 6} or tokens[-1] != str(len(rows) + 1)):
            raise ValueError('Candidate rows must include sequential depth indices 1 through ND.')
        if len(tokens) >= 4:
            extra = [parse_float_token(t) for t in tokens[3:-1]]
            if any(v is None or not math.isfinite(v) for v in extra):
                raise ValueError('Nonfinite additional RVSIG_COL columns.')
            if len(tokens) == 6 and any(v <= 0 for v in extra):
                raise ValueError('Density and clumping columns must be positive.')
        numbers = [parse_float_token(t) for t in tokens[:3]]
        if any(v is None or not math.isfinite(v) for v in numbers):
            raise ValueError('Nonfinite RVSIG_COL data.')
        rows.append(numbers)
    if declared is None or not 3 <= declared <= 5000 or len(rows) != declared:
        raise ValueError('RVSIG_COL must declare 3–5000 points with exactly that many rows.')
    if any(r <= 0 or v <= 0 or sigma < -1 for r, v, sigma in rows):
        raise ValueError('RVSIG_COL requires positive radii/velocities and sigma >= -1.')
    if any(a[0] <= b[0] for a, b in zip(rows, rows[1:])):
        raise ValueError('RVSIG_COL radii must decrease strictly.')
    return rows


def _grid_text(rows):
    return (f'{len(rows)} !Number of depth points\n\n' +
            ''.join(f'{r:.14e} {v:.14e} {s:.14e} {i}\n' for i, (r, v, s) in enumerate(rows, 1)))


def _fingerprints(model):
    result = {}
    for name in (*SOURCES, STATE_FILE, MODIFIED_FILE, 'IN_ITS', *RETIRE):
        path = model / name
        if path.is_symlink():
            raise ValueError(f'{name} must not be a symlink for a structure update.')
        if path.exists():
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError(f'{name} must be an unshared regular file.')
            # Checkpoints may be huge; use inode/time metadata, never read them here.
            result[name] = [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]
            if name in (*SOURCES, STATE_FILE, MODIFIED_FILE, 'IN_ITS'):
                result[name].append(digest(path.read_bytes()))
        else:
            result[name] = None
    return result


def _replace_control(text, key, new):
    rows = control_occurrences(text).get(key, [])
    if len(rows) != 1:
        raise ValueError(f'Update requires exactly one [{key}] control.')
    row = rows[0]
    lines = text.splitlines(keepends=True)
    i = row['line_index']
    lines[i] = lines[i][:row['value_start']] + new + lines[i][row['value_end']:]
    return ''.join(lines)


def _native(executable, folder, rows, mode, answers, logs):
    (folder / 'RVSIG_COL_OLD').write_text(_grid_text(rows))
    # GRAMON requests a device on the first plot, then one E per plot.
    stdin = '\n'.join(['RVSIG_COL_OLD', 'F', mode, *map(str, answers),
                        'RVSIG_COL_NEW', '/null', 'E', 'E']) + '\n'
    result = subprocess.run([str(executable)], cwd=folder, input=stdin, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20,
        env={**os.environ, 'PGPLOT_DEV': '/null', 'OMP_NUM_THREADS': '1'})
    logs.append({'mode': mode, 'answers': answers, 'returncode': result.returncode,
                 'log': result.stdout[-65536:]})
    if result.returncode != 0 or not (folder / 'RVSIG_COL_NEW').is_file():
        raise ValueError(f'rev_rvsig {mode} failed; no structure has been installed. ' + result.stdout[-1500:])
    output = (folder / 'RVSIG_COL_NEW').read_text()
    (folder / 'RVSIG_COL_NEW').unlink()
    return parse_grid(output), output


def build_structure_plan(model, *, cmfgen_root=None, velocity_type=2, connection_velocity=10,
                         candidate=None):
    """Generate in scratch space or validate an explicitly supplied candidate."""
    model = Path(model)
    before = _fingerprints(model)
    current = {n: read_text(model / n) if (model / n).is_file() else '' for n in SOURCES}
    if not uses_rvsig(current['VADAT']):
        raise ValueError('Update structure is available only with VEL_OPT=RVSIG_COL.')
    target_nd = number(current['MODEL_SPEC'], 'ND')
    if target_nd != int(target_nd) or not 3 <= target_nd <= 5000:
        raise ValueError('ND must be an integer between 3 and 5000.')
    nc = parse_float_token(value(current['MODEL_SPEC'], 'NC') or '')
    np_value = number(current['MODEL_SPEC'], 'NP')
    if nc is None or not math.isfinite(nc) or nc < 0 or nc != int(nc) or np_value != int(np_value):
        raise ValueError('NC and NP must be integer ray counts (NC >= 0, NP > 0).')
    spec = current['MODEL_SPEC']
    if np_value < target_nd + nc:
        np_value = int(target_nd + nc)
        spec = _replace_control(spec, 'NP', str(np_value))
    logs = []
    if candidate is None:
        state = _read_state(model)
        if state is None or not state.get('pending', True):
            raise ValueError('No saved pre-edit baseline. Supply a manually prepared candidate instead.')
        old = state['baseline']
        for key in ('SN_MODEL', 'VAR_MDOT'):
            if (value(current['VADAT'], key) or '').upper().strip('.') in {'T', 'TRUE'}:
                raise ValueError(f'Guided updates do not support [{key}]=T; supply a prepared candidate.')
        if any(len(line.split('!', 1)[0].split()) > 5 for line in old['RVSIG_COL'].splitlines()
               if line.strip() and not line.lstrip().startswith(('!', '#'))):
            raise ValueError('Guided updates support R/V/sigma structures with an optional Tau column only; '
                             'supply a candidate that preserves the density/clumping columns.')
        if current['RVSIG_COL'] != old['RVSIG_COL']:
            raise ValueError('RVSIG_COL changed since the baseline. Review a manually prepared candidate instead.')
        changes = changed_keys(old['VADAT'], current['VADAT'], VELOCITY_KEYS)
        unsupported = set(changes) - {'MDOT', 'RSTAR', 'VINF', 'BETA'}
        if unsupported:
            raise ValueError('Native guided update does not cover ' + ', '.join(sorted(unsupported)) +
                             '; supply a manually prepared candidate.')
        executable = Path(cmfgen_root or '') / 'exe/rev_rvsig.exe'
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError('Configure cmfgen_root with an executable exe/rev_rvsig.exe.')
        executable = executable.resolve()
        rows = parse_grid(old['RVSIG_COL'])
        old_radius = number(old['VADAT'], 'RSTAR')
        rows = [[r * old_radius / rows[-1][0], v, s] for r, v, s in rows]
        output = _grid_text(rows)
        if velocity_type not in {1, 2, 6}:
            raise ValueError('Supported wind prescriptions are 1, 2 and 6.')
        if velocity_type == 6 and set(changes) & {'VINF', 'BETA'}:
            raise ValueError('Type 6 retains the existing wind law; choose type 1 or 2 for VINF/BETA changes.')
        with tempfile.TemporaryDirectory(prefix='cmfgen-structure-') as scratch:
            folder = Path(scratch)
            if changes:
                old_mdot = number(old['VADAT'], 'MDOT')
                new_mdot = number(current['VADAT'], 'MDOT')
                connection = float(connection_velocity)
                if not math.isfinite(connection) or connection <= 0:
                    raise ValueError('Connection velocity must be finite and positive.')
                mode = 'SCLR' if 'RSTAR' in changes else 'MDOT'
                search_velocity = connection if mode == 'SCLR' else connection * old_mdot / new_mdot
                if not rows[-2][1] < search_velocity < rows[1][1]:
                    raise ValueError('Connection velocity must lie safely inside the old velocity grid '
                                     '(after the native mass-loss scaling for MDOT).')
                if mode == 'SCLR':
                    answers = [number(current['VADAT'], 'RSTAR'), connection, old_mdot, new_mdot,
                               number(old['VADAT'], 'LSTAR'), velocity_type]
                else:
                    answers = [old_mdot, new_mdot, velocity_type]
                if velocity_type != 6:
                    answers += [number(current['VADAT'], 'VINF'), number(current['VADAT'], 'BETA')]
                if mode == 'MDOT':
                    answers += [connection]
                rows, output = _native(executable, folder, rows, mode, answers, logs)
            if len(rows) != target_nd:
                rows, output = _native(executable, folder, rows, 'NEW_ND', [int(target_nd)], logs)
        origin = str(executable)
        executable_hash = digest(executable.read_bytes())
    else:
        output = candidate
        rows = parse_grid(output)
        origin, executable_hash = 'Reviewed candidate supplied by user', None
    rows = parse_grid(output, require_indices=True)
    if len(rows) != target_nd:
        raise ValueError('Candidate depth count differs from MODEL_SPEC [ND].')
    vinf = number(current['VADAT'], 'VINF')
    if vinf > 0.1 and abs(rows[0][1] - vinf) / rows[0][1] > 0.1:
        raise ValueError('Candidate outer velocity differs from VINF by more than 10%.')
    rmax = rows[0][0] / rows[-1][0]
    vadat = current['VADAT']
    if not math.isclose(number(vadat, 'RMAX'), rmax, rel_tol=1e-10):
        vadat = _replace_control(vadat, 'RMAX', f'{rmax:.12g}')
    if _fingerprints(model) != before:
        raise ValueError('Model files changed during candidate generation; review again.')
    replacements = {'RVSIG_COL': output}
    if vadat != current['VADAT']:
        replacements['VADAT'] = vadat
    if spec != current['MODEL_SPEC']:
        replacements['MODEL_SPEC'] = spec
    diffs = {n: '\n'.join(difflib.unified_diff(current[n].splitlines(), text.splitlines(),
                            fromfile=n + ' (current)', tofile=n + ' (candidate)'))
             for n, text in replacements.items()}
    plan = {'version': 1, 'model': str(model.resolve()), 'fingerprints': before,
            'controls': {n: current[n] for n in ('VADAT', 'MODEL_SPEC')},
            'replacements': replacements, 'diffs': diffs,
            'origin': origin, 'executable_sha256': executable_hash, 'native_runs': logs,
            'summary': {'depths': len(rows), 'impact_parameters': int(np_value),
                        'inner_radius': rows[-1][0], 'outer_radius': rows[0][0],
                        'rmax': rmax, 'outer_velocity': rows[0][1],
                        'minimum_velocity': min(row[1] for row in rows)},
            'retire': [name for name in RETIRE if before[name] is not None],
            'warnings': ['Applying this update archives binary checkpoints and radiation/matrix caches. '
                         'The next run initializes from existing text inputs; review their compatibility. '
                         'This action does not export populations, run hydrostatic equilibrium, or certify convergence.']}
    plan['review_digest'] = digest(json.dumps(plan, sort_keys=True).encode())
    return plan


def apply_structure_plan(model, plan):
    from .model_editor import _atomic_replace, _write_modified_marker
    model = Path(model)
    if (not isinstance(plan, dict) or plan.get('version') != 1 or
            not isinstance(plan.get('replacements'), dict) or
            not all(isinstance(k, str) and isinstance(v, str) and len(v.encode()) <= LIMIT
                    for k, v in plan['replacements'].items()) or
            not isinstance(plan.get('retire'), list) or
            not all(isinstance(n, str) for n in plan['retire']) or
            not isinstance(plan.get('fingerprints'), dict)):
        raise ValueError('Invalid structure review; generate a new candidate.')
    supplied = dict(plan)
    reviewed = supplied.pop('review_digest', '')
    if digest(json.dumps(supplied, sort_keys=True).encode()) != reviewed or plan.get('model') != str(model.resolve()):
        raise ValueError('Invalid structure review; generate a new candidate.')
    if (not {'RVSIG_COL'} <= set(plan['replacements']) <= {'RVSIG_COL', 'VADAT', 'MODEL_SPEC'} or
            set(plan['retire']) - set(RETIRE)):
        raise ValueError('Invalid structure update targets.')
    with MODEL_WRITE_LOCK, model_mutation_guard(model):
        if _fingerprints(model) != plan['fingerprints']:
            raise ValueError('Model changed after review; generate a new candidate.')
        # Validate even a persisted plan before touching the live structure.
        parse_grid(plan['replacements']['RVSIG_COL'], require_indices=True)
        root = model / '.cmfgen-viewer-backups'
        if root.is_symlink():
            raise ValueError('Recovery directory must not be a symlink.')
        archive = root / ('structure-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-') + uuid.uuid4().hex[:8])
        mkdir_readable(archive, parents=True)
        moved, installed = [], []
        targets = [*plan['replacements'], STATE_FILE, MODIFIED_FILE]
        try:
            for name in [*targets, *plan['retire']]:
                if (model / name).exists():
                    os.replace(model / name, archive / name)
                    moved.append(name)
            for name, text in plan['replacements'].items():
                mode = stat.S_IMODE((archive / name).stat().st_mode) if (archive / name).exists() else 0o644
                installed.append(name)
                _atomic_replace(model / name, text.encode(), mode=mode)
            installed.append(STATE_FILE)
            _write_state(model, {'version': 1, 'pending': False, 'baseline': {n: read_text(model / n) for n in SOURCES},
                                 'captured_at': datetime.now(timezone.utc).isoformat()})
            with open_readable(archive / 'operation.json', 'w') as stream:
                json.dump(plan, stream, indent=2)
            installed.append(MODIFIED_FILE)
            _write_modified_marker(model, file_relpath='RVSIG_COL',
                                   backup_relpath=(archive / 'RVSIG_COL').relative_to(model).as_posix())
        except BaseException:
            for name in reversed(installed):
                (model / name).unlink(missing_ok=True)
            for name in reversed(moved):
                os.replace(archive / name, model / name)
            raise
        return {'status': 'succeeded', 'archive_path': str(archive), 'retired': plan['retire']}
