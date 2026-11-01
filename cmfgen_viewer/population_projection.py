"""Conservative, provisional repair of an isolated ionization spike.

This changes a restart guess, never an abundance, atmosphere grid, temperature,
or convergence criterion. Callers must hold the model write guard and retain a
complete rollback checkpoint until independent native continuation passes.
"""
import hashlib
import math
import os
from pathlib import Path
import re
import shutil
import tempfile

import numpy as np

from .checkpoint_health import RECORD_BYTES, WORDS_PER_RECORD, _words
from .checkpoint_physics import checkpoint_physics, compare_physics
from .runner_recipe import RunnerError, snapshot
from .runner_restart import inspect_restart
from .parsers.common import parse_float_token


def _digest(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise RunnerError('Localized population projection requires unshared regular files: '+path.name)
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()


def _state(model):
    path = model/'SCRTEMP'
    if path.stat().st_size > 512 * 1024**2:
        raise RunnerError('Localized population projection supports checkpoints up to 512 MiB')
    signature = snapshot(path)
    physical = checkpoint_physics(model)
    restart = inspect_restart(model)
    h, pointer = restart['binary_health'], restart['pointer']
    nd, nt = h['nd'], h['nt']
    gr = (3*nd+WORDS_PER_RECORD-1)//WORDS_PER_RECORD
    pr = (nd*nt+WORDS_PER_RECORD-1)//WORDS_PER_RECORD
    start = max(2, gr)+(pointer['record']-1)*(pr+(gr if pointer['writes_rvsig'] else 0))
    population_start = start+(gr if pointer['writes_rvsig'] else 0)
    order = '<' if h['byte_order'] == 'little' else '>'
    with path.open('rb') as stream:
        pops = np.fromiter(_words(stream, population_start, nd*nt, order), float).reshape(nd, nt)
    ions = []
    for line in (model/'MODEL').read_text().splitlines():
        row = line.split()
        if len(row) >= 12:
            try:
                ions.append((row[0], int(row[8])-1, int(row[2]), float(row[3]), int(row[9])))
            except ValueError:
                pass
    groups, charge = {}, np.zeros(nt-2)
    for i, (name, first, count, stage, species) in enumerate(ions):
        ids = list(range(first, first+count))
        charge[first:first+count] = stage-1
        if i == len(ions)-1 or ions[i+1][4] != species:
            ids.append(first+count)
            charge[ids[-1]] = stage
        groups.setdefault(species, []).extend(ids)
    # checkpoint_physics has already checked complete, nonoverlapping metadata.
    if signature != snapshot(path):
        raise RunnerError('Checkpoint changed during localized population inspection')
    return physical, pointer, pops, ions, groups, charge, population_start, order, signature


def _candidate(state, depth):
    physical, pointer, pops, ions, groups, charge, start, order, signature = state
    nd, nt = pops.shape
    d = depth-1
    if not 1 <= d < nd-1:
        return None
    temperatures = pops[d-1:d+2, -1]
    if max(temperatures)/min(temperatures) > 1.25:
        return None
    matches = []
    for name, first, count, stage, species in ions:
        totals = pops[d-1:d+2][:, groups[species]].sum(axis=1)
        if max(totals)/min(totals) > 4:
            continue
        fractions = pops[d-1:d+2, first:first+count].sum(axis=1)/totals
        if (min(fractions[[0, 2]]) <= 0 or fractions[1] < .05 or
                max(fractions[[0, 2]])/min(fractions[[0, 2]]) > 10):
            continue
        contrast = float(fractions[1]/max(fractions[0], fractions[2]))
        if contrast >= 100:
            matches.append((name, species, first, count, fractions.tolist(), contrast))
    if len(matches) != 1:
        return None  # Broader/multiple-element features need a separate diagnosis.
    name, species, first, count, fractions, contrast = matches[0]
    radii = np.array(physical['geometry'][:nd])
    log_radii = np.log(radii[d-1:d+2])
    if abs(log_radii[2]-log_radii[0]) < 1e-12:
        return None
    weight = float((log_radii[1]-log_radii[0])/(log_radii[2]-log_radii[0]))
    ids = groups[species]
    total = float(pops[d, ids].sum())
    left, right = pops[d-1, ids], pops[d+1, ids]
    left_fraction, right_fraction = left/left.sum(), right/right.sum()
    if np.all(left_fraction > 0) and np.all(right_fraction > 0):
        # This is also the arithmetic used by the retained native trial seed.
        fraction = np.exp((1-weight)*np.log(left_fraction)+weight*np.log(right_fraction))
        fraction /= fraction.sum()
        values = total*fraction
    else:
        # Avoid underflow in intermediate normalized fractions when the final
        # absolute populations can still be represented.
        logs = ((1-weight)*(np.log(left)-math.log(float(left.sum()))) +
                weight*(np.log(right)-math.log(float(right.sum()))))
        maximum = float(logs.max())
        normalization = maximum+math.log(float(np.exp(logs-maximum).sum()))
        values = np.exp(math.log(total)+logs-normalization)
        values *= total/float(values.sum())
    after = pops.copy()
    after[d, ids] = values
    after[d, -2] = after[d, :-2] @ charge
    if not np.isfinite(after).all() or np.any(after <= 0):
        raise RunnerError('Localized population projection cannot preserve representable positive populations')
    return {'depth': depth, 'reference_ion': name, 'species_id': species,
            'stage_fractions': fractions, 'contrast': contrast, 'log_radius_weight': weight,
            'variables': [i+1 for i in ids], 'old_electron_density': float(pops[d, -2]),
            'reference_variables': list(range(first+1, first+count+1)),
            'new_electron_density': float(after[d, -2])}, after


def propose_projection(model, depth):
    """Read-only proposal; thresholds identify a trial, never convergence."""
    state = _state(model)
    candidate = _candidate(state, depth)
    if candidate is None:
        return None
    description, after = candidate
    return {**description, 'dimensions': {'nd': state[2].shape[0], 'nt': state[2].shape[1]},
            'pointer': state[1], 'physical_baseline': state[0],
            'checkpoint_snapshot': state[-1], 'checkpoint_sha256': _digest(model/'SCRTEMP'),
            'model_sha256': _digest(model/'MODEL'),
            'model_spec_sha256': _digest(model/'MODEL_SPEC')}


def apply_projection(model, proposal):
    """Atomically apply the recomputed proposal; never accept supplied vectors."""
    required = {'checkpoint_sha256', 'model_sha256', 'model_spec_sha256', 'depth',
                'species_id', 'checkpoint_snapshot', 'pointer'}
    if not isinstance(proposal, dict) or not required <= proposal.keys():
        raise RunnerError('Incomplete localized population projection proposal')
    for name, key in [('SCRTEMP', 'checkpoint_sha256'), ('MODEL', 'model_sha256'),
                      ('MODEL_SPEC', 'model_spec_sha256')]:
        if _digest(model/name) != proposal.get(key):
            raise RunnerError('Localized population projection baseline changed: '+name)
    state = _state(model)
    if state[-1] != proposal['checkpoint_snapshot'] or state[1] != proposal['pointer']:
        raise RunnerError('Localized population projection checkpoint changed after diagnosis')
    candidate = _candidate(state, proposal['depth'])
    if candidate is None or candidate[0]['species_id'] != proposal['species_id']:
        raise RunnerError('Localized population projection signature no longer matches')
    description, values = candidate
    descriptor, name = tempfile.mkstemp(prefix='.projected-SCRTEMP-', dir=model)
    os.close(descriptor)
    temporary = Path(name)
    try:
        shutil.copy2(model/'SCRTEMP', temporary)
        with temporary.open('r+b') as stream:
            stream.seek(state[6]*RECORD_BYTES)
            stream.write(values.astype(state[7]+'f8').tobytes())
            stream.flush()
            os.fsync(stream.fileno())
        if state[-1] != snapshot(model/'SCRTEMP'):
            raise RunnerError('Checkpoint changed before publishing localized population projection')
        os.replace(temporary, model/'SCRTEMP')
    finally:
        temporary.unlink(missing_ok=True)
    checks = compare_physics(state[0], checkpoint_physics(model), fixed_temperature=True)
    return {**description, 'physical_checks': checks,
            'checkpoint_sha256': _digest(model/'SCRTEMP'),
            'restart_counter_unchanged': inspect_restart(model)['pointer'] == state[1]}


def projected_raw_requests(model, evidence, variables, depth):
    """Read this attempt's complete raw solutions at the repaired coordinates."""
    path = model/'STEQ_VALS'
    offset = evidence.get('solution_start_offset')
    nt, nd = evidence['counts']['nt'], evidence['counts']['nd']
    wanted = set(variables) | {nt-1}  # Include the local electron-density target.
    if (offset is None or not path.is_file() or not 0 <= offset <= path.stat().st_size or
            not wanted or min(wanted) < 1 or max(wanted) >= nt or not 1 <= depth <= nd or
            not 1 <= len(evidence['records']) <= 8):
        raise RunnerError('Projection verification needs fresh, bounded raw population solutions')
    records, current = [], None
    pattern = re.compile(rb'\s*(\d+)\(\s*(\d+)\)#\s*(.*)')
    start = max(offset, path.stat().st_size-128*1024**2)
    with path.open('rb') as stream:
        if start:
            stream.seek(start-1)
            if stream.read(1) != b'\n':
                stream.readline()
        for line in stream:
            if line.strip() == b'STEQ SOLUTION ARRAY':
                if current is not None:
                    raise RunnerError('Incomplete raw population solution during projection verification')
                current = {}
                continue
            if current is None:
                continue
            match = pattern.fullmatch(line.rstrip(b'\r\n'))
            if not match:
                continue
            variable, first = int(match[1]), int(match[2])
            values = [parse_float_token(t.decode('ascii', errors='replace')) for t in match[3].split()]
            if (not 1 <= variable <= nt or not 1 <= first <= nd or
                    first+len(values)-1 > nd or not values or
                    any(v is None or not math.isfinite(v) for v in values)):
                raise RunnerError('Invalid raw population solution during projection verification')
            if variable in wanted and first <= depth < first+len(values):
                if variable in current:
                    raise RunnerError('Duplicate raw population coordinate during projection verification')
                current[variable] = values[depth-first]
            if variable == nt and first+len(values)-1 == nd:
                if current.keys() != wanted:
                    raise RunnerError('Missing repaired coordinates in raw population solution')
                records.append({'maximum_decrease_percent': max(0., 100*max(current.values())),
                                'maximum_decrease_variable': max(current, key=current.get),
                                'maximum_increase_percent': max(0., -100*min(current.values())),
                                'nonpositive_unlimited_variables': sorted(v for v, value in current.items() if value >= 1),
                                'nonpositive_population_targets': sum(value >= 1 for v, value in current.items() if v != nt-1),
                                'nonpositive_electron_target': current[nt-1] >= 1,
                                'nonpositive_unlimited_targets': sum(v >= 1 for v in current.values())})
                current = None
    if current is not None or len(records) != len(evidence['records']):
        raise RunnerError('Raw population solutions do not match the completed native solves')
    return records


def _projection_response(ctx, proposal, observed, attempts):
    from .auto_hydro import guard_measurements
    from .auto_policies import VerificationPending
    state = _state(ctx.model)
    physics = compare_physics(proposal['physical_baseline'], state[0])
    guard = guard_measurements(ctx.model, ctx.before)
    if not .5 <= guard['luminosity_min'] <= guard['luminosity_max'] <= 2:
        raise RunnerError('Localized population projection failed the luminosity guards')
    if (ctx.evidence.get('hydro_revisions') or ctx.evidence.get('checkpoint_updates') or
            ctx.evidence.get('ng_accelerations')):
        raise RunnerError('Localized population projection needs an unaccelerated fixed-structure follow-up')
    rows = projected_raw_requests(ctx.model, ctx.evidence, proposal['reference_variables'], proposal['depth'])
    element_rows = projected_raw_requests(ctx.model, ctx.evidence, proposal['variables'], proposal['depth'])
    for record, raw, element_raw in zip(ctx.evidence['records'], rows, element_rows):
        if (record.get('lambda_iteration') or record.get('temperature_fixed') or
                not record.get('ba_computed')):
            continue
        if raw['nonpositive_unlimited_targets']:
            raise RunnerError('Full solves still request nonpositive populations at the repaired ion/depth')
        if any(r['iteration'] == record['global_iteration'] for r in observed):
            raise RunnerError('Repeated native counter cannot provide an independent projection check')
        observed.append({'iteration': record['global_iteration'], 'reference_ion': proposal['reference_ion'],
                         **raw, 'other_ion_nonpositive_targets': element_raw['nonpositive_unlimited_targets']})
    matches = [ion for ion in state[3] if ion[0] == proposal['reference_ion']
               and ion[4] == proposal['species_id']]
    if len(matches) != 1:
        raise RunnerError('Localized population projection ion metadata changed')
    name, first, count, stage, species = matches[0]
    d, pops = proposal['depth']-1, state[2]
    fractions = pops[d-1:d+2, first:first+count].sum(axis=1)/pops[d-1:d+2][:, state[4][species]].sum(axis=1)
    denominator = max(fractions[0], fractions[2])
    contrast = float(fractions[1]/denominator) if denominator else (0. if fractions[1] == 0 else math.inf)
    if contrast >= 10:
        raise RunnerError('Native continuation recreated the isolated ionization spike')
    checks = {'physical_checks': physics, 'guard': guard, 'remaining_contrast': contrast,
              'full_solve_requests': list(observed),
              'native_source_changed': bool(ctx.evidence.get('source_changed'))}
    attempts.append(ctx.evidence['iterations'])
    if len(observed) < 2:
        if len(attempts) >= 2:
            raise RunnerError('Localized population projection did not obtain two full checks within two bounded batches')
        raise VerificationPending('Require a second full variable-temperature fresh-BA response to the localized repair',
                                  {'population_projection_check': checks})
    return {'population_projection_check': checks}


def localized_population_projection(ctx):
    """Recognize a persistent impossible full-step target at one isolated spike."""
    from .auto_diagnostics import control_value, number
    from .auto_hydro import enabled, structure_fixed
    from .auto_policies import Decision, Declined, RecoveryStep
    from .auto_recovery import repaired_runtime
    if (ctx.native_plan.get('restart', {}).get('mode') != 'continuation' or
            ctx.evidence.get('candidate') or ctx.evidence.get('source_changed') or
            not structure_fixed(ctx.model)):
        return None
    if any(enabled(ctx.model, key) for key in ('USE_J_REL', 'USE_DJDT_RTE', 'INC_GRID', 'SN_MODEL',
                                              'USE_FIXED_J', 'FIX_T', 'FIX_NE', 'FIX_IMP')):
        return None
    if (control_value(ctx.model, 'VADAT', 'SCALE_OPT', '').upper() != 'MAJOR' or
            control_value(ctx.model, 'VADAT', 'INCL_dSLdT', 'F', exact_key=True).upper().strip('.') not in {'T', 'TRUE'} or
            number(ctx.model, 'VADAT', 'N_FIX_BA', -1) != 0 or
            number(ctx.model, 'VADAT', 'FIX_BA', -1) != 0):
        return None
    if any(ctx.evidence.get(key) for key in ('hydro_revisions', 'ng_accelerations', 'checkpoint_updates')):
        return None
    # Require both bad solves in this validated invocation, so their complete
    # raw arrays can tie the impossible targets to the actual outlier ion.
    full = [r for r in ctx.evidence.get('records', [])
            if not r.get('lambda_iteration') and not r.get('temperature_fixed')][-2:]
    if len(full) != 2:
        return None
    for row in full:
        decrease, scale = row.get('maximum_decrease_percent'), row.get('major_species_minimum_scale')
        if (not row.get('ba_computed') or not isinstance(decrease, (int, float)) or
                not math.isfinite(decrease) or decrease < 1e6 or
                not isinstance(scale, (int, float)) or not math.isfinite(scale) or not 0 < scale <= .01):
            return None
    depth = full[-1].get('maximum_decrease_depth')
    if not isinstance(depth, int) or depth != full[0].get('maximum_decrease_depth'):
        return None
    if not repaired_runtime(ctx.native_plan):
        raise Declined('Localized population projection requires an authenticated repaired runtime')
    try:
        proposal = propose_projection(ctx.model, depth)
    except (OSError, ValueError) as exc:
        raise Declined(str(exc)) from exc
    if proposal is None:
        return None
    if any(proposal['dimensions'][k] != ctx.evidence.get('counts', {}).get(k) for k in ('nt', 'nd')):
        raise Declined('Localized population projection diagnostics do not match the binary checkpoint dimensions')
    try:
        raw = projected_raw_requests(ctx.model, ctx.evidence, proposal['reference_variables'], depth)
    except (OSError, ValueError) as exc:
        raise Declined(str(exc)) from exc
    bound = [(row, values) for row, values in zip(ctx.evidence['records'], raw) if row in full]
    if len(bound) != 2 or any(values['maximum_decrease_percent'] < 1e6 or
            values['maximum_decrease_variable'] not in proposal['reference_variables'] or
            len(set(values['nonpositive_unlimited_variables']) & set(proposal['reference_variables'])) <
                math.ceil(len(proposal['reference_variables'])/2) for row, values in bound):
        return None
    observed, attempts = [], []
    return Decision('action', 'Repeated fresh full solves request impossible decreases at one isolated '
                    'ionization spike; conservatively interpolate that element at this depth, '
                    'recompute charge-balanced Ne, and require two bounded full native responses',
                    action='localized_population_projection',
                    changes={'VADAT': {'COMP_BA': 'T', 'N_FIX_BA': '0', 'FIX_BA': '0.0'}},
                    caches=('BAMAT', 'BAMATPNT', 'EDDFACTOR', 'EDDFACTOR_INFO'),
                    evidence={'projection': proposal, 'full_decreases_percent': [r['maximum_decrease_percent'] for r in full],
                              'offending_ion_requests': [v for r, v in bound]},
                    steps=(RecoveryStep('population_projection_full', 2,
                        lambda c: _projection_response(c, proposal, observed, attempts), repeat_on_native_fallback=True),))
