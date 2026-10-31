"""Evidence and scope checks for native control updates and one hydro bridge.

The bridge follows the Bstar3500 investigation of 2026-10-21 and is selected
by the automatic registry. STOP_IF_MW controls two safeguards, so shallow/unknown optical depth is never
eligible. A successful bridge is provisional until an actual guarded run.
"""
import math
import re

from .auto_diagnostics import control_value, number
from .control_files import control_occurrences
from .model_convergence import _parse_iteration_records
from .native_diagnostics import latest_main_log
from .parsers.common import parse_float_token
from .runner_recipe import RunnerError, snapshot
from .runner_validation import validate_rvsig_structure

COUPLED_CONTROLS = ('VADAT', 'RVSIG_COL', 'HYDRO_DEFAULTS')
NATIVE_CONTROLS = (*COUPLED_CONTROLS, 'IN_ITS')
HYDRO_MESSAGE = 'Revised hydrostatic structure and output new RVSIG_COL file'


def enabled(model, key, default='F'):
    return control_value(model, 'VADAT', key, default).upper().strip('.') in {'T', 'TRUE'}


def revisions(text):
    """Return solver iterations followed by a completed native hydro revision."""
    result, current = [], None
    for line in text.splitlines():
        match = re.search(r'Current great iteration count is\s+(\d+)', line)
        if match:
            current = int(match[1])
        if HYDRO_MESSAGE in line:
            if current is None or current in result:
                raise RunnerError('Ambiguous native hydro completion evidence')
            result.append(current)
    return result


def _values(text):
    rows = control_occurrences(text)
    if any(len(v) != 1 for v in rows.values()):
        raise RunnerError('Ambiguous controls during native hydro handoff')
    return {key: row[0]['value'] for key, row in rows.items()}


def capture_controls(model):
    result = {}
    for name in NATIVE_CONTROLS:
        path = model/name
        if path.exists() and path.stat().st_size > 4*1024*1024:
            raise RunnerError(f'Oversized native handoff control: {name}')
        result[name] = path.read_text() if path.exists() else None
    return result


def native_updates(model, text, before, *, fresh_start=False):
    """Accept documented native-owned changes with matching solver evidence.

    Other input changes still stop the controller. This does not authenticate
    native writes against concurrent external shell edits; those are forbidden.
    """
    completed = revisions(text)
    after = capture_controls(model)
    changed = {n for n in NATIVE_CONTROLS if after[n] != before[n]}
    if not changed and not completed:
        return {}
    old = _values(before['VADAT'] or '')
    new = _values(after['VADAT'] or '')
    vd_keys = {k for k in old.keys() | new.keys() if old.get(k) != new.get(k)}
    allowed = set()
    records = _parse_iteration_records(text)
    hydro_before = before['HYDRO_DEFAULTS']
    reset = False
    if (fresh_start and enabled(model, 'DO_HYDRO') and hydro_before is not None and
            'Starting a new model.' in text and
            'Setting ITS_DONE keyword in HYDRO_DEFAULTS to 0' in text):
        rows = control_occurrences(hydro_before)
        old_h = _values(hydro_before)
        try:
            if int(old_h['ITS_DONE']) < 0:
                raise ValueError('Negative ITS_DONE')
        except (KeyError, ValueError) as exc:
            raise RunnerError('Invalid native fresh-start hydro counter') from exc
        # UPDATE_KEYWORD writes zero at column one and trims trailing blanks.
        expected = hydro_before.splitlines()
        index = rows['ITS_DONE'][0]['line_index']
        column = expected[index].index('[ITS_DONE]')
        expected[index] = '0' + ' ' * (column - 1) + expected[index][column:]
        hydro_before = '\n'.join(line.rstrip() for line in expected) + '\n'
        if not completed and [line.rstrip() for line in (after['HYDRO_DEFAULTS'] or '').splitlines()] != hydro_before.splitlines():
            raise RunnerError('Unexpected HYDRO_DEFAULTS edit during native fresh-start reset')
        reset = True
    if 'IN_ITS' in changed:
        old_its = _values(before['IN_ITS'] or '')
        new_its = _values(after['IN_ITS'] or '')
        transition = next((full['global_iteration'] for lam, full in zip(records, records[1:])
                           if lam.get('lambda_iteration') and not full.get('lambda_iteration')
                           and full['global_iteration'] == lam['global_iteration'] + 1
                           and 0 <= lam.get('solver_maximum_change', math.inf) < 50
                           and math.isfinite(full.get('solver_maximum_change', math.inf))), None)
        if (old_its.get('DO_LAM_IT', '').upper().strip('.') not in {'T', 'TRUE'} or
                old_its.get('DO_LAM_AUTO', 'T').upper().strip('.') not in {'T', 'TRUE'} or
                new_its.get('DO_LAM_IT', '').upper().strip('.') not in {'F', 'FALSE'} or
                transition is None):
            raise RunnerError('IN_ITS changed without a verified native automatic lambda-to-full transition; preserving it for review')
        # UPDATE_KEYWORD_LOG blanks the prefix and writes F in column one;
        # WR_KEY_WRD_FILE trims trailing blanks on every line. No other edit
        # (including an unrelated comment change) belongs to this handoff.
        expected = (before['IN_ITS'] or '').splitlines()
        row = control_occurrences(before['IN_ITS'])['DO_LAM_IT'][0]
        index = row['line_index']
        column = expected[index].index('[DO_LAM_IT]')
        expected[index] = 'F' + ' ' * (column - 1) + expected[index][column:]
        if [line.rstrip() for line in expected] != [line.rstrip() for line in (after['IN_ITS'] or '').splitlines()]:
            raise RunnerError('Unexpected IN_ITS edit during execution; preserving it for review')
    # CMFGEN can release an explicitly requested automatic fixed-T startup.
    if (old.get('DO_T_AUTO', '').upper().strip('.') in {'T', 'TRUE'} and
            old.get('FIX_T', '').upper().strip('.') in {'T', 'TRUE'} and
            new.get('FIX_T', '').upper().strip('.') in {'F', 'FALSE'} and
            any(not r.get('lambda_iteration') and r.get('solver_maximum_change', math.inf) < 50
                for r in records)):
        allowed.add('FIX_T')
    if completed:
        if not enabled(model, 'DO_HYDRO') or before['HYDRO_DEFAULTS'] is None:
            raise RunnerError('Hydro completion without the reviewed hydro configuration')
        old_h = _values(hydro_before)
        new_h = _values(after['HYDRO_DEFAULTS'] or '')
        try:
            delta = int(new_h['ITS_DONE']) - int(old_h['ITS_DONE'])
            remaining_delta = int(old_h['N_ITS']) - int(new_h['N_ITS'])
        except (KeyError, ValueError) as exc:
            raise RunnerError('Invalid native hydro counters') from exc
        if (delta != len(completed) or remaining_delta != delta or
                int(new_h['N_ITS']) < 0 or int(old_h['ITS_DONE']) < 0):
            raise RunnerError('Hydro counters do not match completed revisions')
        if 'RVSIG_COL' not in changed:
            raise RunnerError('Completed hydro revision did not refresh RVSIG_COL')
        validate_rvsig_structure(model/'RVSIG_COL', model/'MODEL_SPEC')
        h_keys = {k for k in old_h.keys() | new_h.keys() if old_h.get(k) != new_h.get(k)}
        if h_keys - {'ITS_DONE', 'N_ITS', 'HYDRO_OPT', 'OLD_TEFF'}:
            raise RunnerError('Unexpected HYDRO_DEFAULTS edit; preserving it for review')
        allowed.update({'RSTAR', 'RMAX', 'MASS', 'LSTAR', 'TEFF'})
        for key in (vd_keys & allowed) - {'FIX_T'}:
            value = parse_float_token(new.get(key, ''))
            if value is None or not math.isfinite(value) or value <= 0:
                raise RunnerError(f'Invalid native hydro [{key}]')
    elif changed - ({'VADAT', 'IN_ITS', 'HYDRO_DEFAULTS'} if reset else {'VADAT', 'IN_ITS'}):
        raise RunnerError('Structure controls changed without completed native hydro evidence')
    xray_keys = {'FIL_FAC_1', 'FIL_FAC_2'}
    xray_update = None
    if vd_keys & xray_keys:
        factors = [parse_float_token(v) for v in re.findall(
            r'^\s*XRAY_NORMALIZATION_FACTOR:\s*(\S+)\s*$', text, re.M)]
        if (not factors or any(v is None or not math.isfinite(v) or not .1 <= v <= 10 for v in factors) or
                not enabled(model, 'INC_XRAYS') or not enabled(model, 'SCL_XLUM') or enabled(model, 'XSLOW') or
                not any(not r.get('lambda_iteration') and
                        math.isfinite(r.get('solver_maximum_change', math.inf)) and
                        r.get('solver_maximum_change', math.inf) < 100 for r in records)):
            raise RunnerError('X-ray filling factors changed without verified native normalization evidence')
        factor = math.prod(factors)
        if not math.isfinite(factor):
            raise RunnerError('Nonfinite native X-ray normalization product')
        for key in xray_keys:
            a, b = parse_float_token(old.get(key, '')), parse_float_token(new.get(key, ''))
            if (a is None or b is None or not math.isfinite(a) or not math.isfinite(b) or min(a, b) < 0 or
                    not math.isfinite(a*factor) or not math.isclose(b, a*factor, rel_tol=5e-8,
                                                                 abs_tol=6e-9 if .01 < abs(a*factor) < 1e5 else 0)):
                raise RunnerError('X-ray filling-factor changes do not match the logged native multiplier')
        allowed.update(xray_keys)
        xray_update = {'factors': factors, 'requires_stable_source_verification': True}
    if vd_keys - allowed:
        raise RunnerError('Unexpected VADAT edit during execution; preserving it for review')
    result = {name: {'before': before[name], 'after': after[name]} for name in changed}
    if xray_update:
        result['VADAT']['xray_normalization'] = xray_update
    return result


def guard_measurements(model, before, *, require_positive=True):
    """Require fresh, complete, finite luminosity and optical-depth profiles."""
    from .runner import _tail
    nd = int(number(model, 'MODEL_SPEC', 'ND'))
    for name in ('OBSFLUX', 'MEANOPAC'):
        path = model/name
        current, old = snapshot(path), before.get(name) or {}
        unchanged = all(current.get(k) == old.get(k) for k in ('exists', 'size', 'mtime_ns', 'sha256'))
        if not path.is_file() or unchanged:
            raise RunnerError(f'No fresh {name} for hydro recovery')
    obs = _tail(model/'OBSFLUX', 8*1024*1024)
    headers = list(re.finditer(r'^\s*Normalized luminosity check \(normalized by L\[ND\]\)[^\n]*\n', obs, re.M))
    if not headers:
        raise RunnerError('Missing stellar normalized luminosity profile')
    luminosity = []
    for line in obs[headers[-1].end():].splitlines():
        if not line.strip() and not luminosity:
            continue
        row = [parse_float_token(t) for t in line.split()]
        if not row or any(v is None for v in row):
            break
        luminosity.extend(row)
    if (len(luminosity) != nd or any(not math.isfinite(v) for v in luminosity) or
            (require_positive and min(luminosity) <= 0)):
        raise RunnerError('Incomplete/invalid normalized luminosity profile')
    mean = _tail(model/'MEANOPAC', 4*1024*1024)
    if not mean.splitlines() or 'Tau(Ross)' not in mean.splitlines()[0]:
        raise RunnerError('Unrecognized MEANOPAC optical depths')
    tau = []
    for line in mean.splitlines()[1:]:
        row = line.split()
        if len(row) == 15 and row[1].isdigit():
            value = parse_float_token(row[2])
            if int(row[1]) != len(tau)+1 or value is None or not math.isfinite(value) or value < 0:
                raise RunnerError('Invalid MEANOPAC depth profile')
            tau.append(value)
    if len(tau) != nd or tau != sorted(tau) or tau[-1] < 30:
        raise RunnerError('Unknown/shallow inner optical depth; refusing to bypass STOP_IF_MW')
    return {'luminosity_min': min(luminosity), 'luminosity_max': max(luminosity),
            'inner_tau_ross': tau[-1]}


def bridge_evidence(model, native, result, before):
    """Restrict bypass to a guard stop immediately before a scheduled revision."""
    from .runner import _tail
    passes = result.get('passes', [])
    codes = {f['code'] for p in passes for f in p.get('diagnostic_findings', [])
             if f.get('severity') == 'error'}
    if (result['status'] != 'invalid_output' or codes != {'inner_flux_accuracy'} or
            any(p.get('returncode') != 0 for p in passes)):
        raise RunnerError('Failure is not an isolated zero-exit luminosity safeguard stop')
    if any(re.search(r'SIG(?:SEGV|FPE|ILL|ABRT)|Fortran runtime error|segmentation fault',
                     p.get('diagnostic_tail', ''), re.I) for p in passes):
        raise RunnerError('Luminosity warning accompanied by an unrelated native failure')
    if not enabled(model, 'STOP_IF_MW', 'T') or not enabled(model, 'DO_HYDRO'):
        raise RunnerError('Hydro recovery requires enabled DO_HYDRO and STOP_IF_MW')
    restart = native['restart']
    if (restart['mode'] != 'continuation' or restart['pointer']['iterations'] < 1 or
            passes[-1].get('startup_observed', {}).get('mode') != 'continuation'):
        raise RunnerError('Hydro recovery requires a previously reviewed continuation checkpoint')
    records = _parse_iteration_records(latest_main_log(_tail(model/'OUTGEN', 32*1024*1024)))
    iteration = restart['pointer']['iterations'] + 1
    if (len(records) != 1 or records[0]['global_iteration'] != iteration or
            'solver_maximum_change' in records[0]):
        raise RunnerError('Stop was not before the first population solve of this continuation')
    start = number(model, 'HYDRO_DEFAULTS', 'STRT_ITS')
    freq = number(model, 'HYDRO_DEFAULTS', 'FREQ_ITS')
    remaining = number(model, 'HYDRO_DEFAULTS', 'N_ITS')
    done = number(model, 'HYDRO_DEFAULTS', 'ITS_DONE')
    if (any(v is None or v != int(v) for v in (start, freq, remaining, done)) or
            freq <= 0 or remaining <= 0 or done < 0 or iteration < start or (iteration-start) % freq):
        raise RunnerError('No explicitly scheduled hydro revision at the stopped iteration')
    measured = guard_measurements(model, before)
    if measured['luminosity_min'] >= 0.5 and measured['luminosity_max'] <= 2:
        raise RunnerError('Luminosity profile does not corroborate the safeguard stop')
    return {'stopped_iteration': iteration, 'hydro_its_done_before': int(done), **measured}


def hydro_exhausted(model):
    """An explicitly completed schedule is fixed for subsequent solver remedies."""
    return (enabled(model, 'DO_HYDRO') and
            number(model, 'HYDRO_DEFAULTS', 'N_ITS') == 0 and
            (done := number(model, 'HYDRO_DEFAULTS', 'ITS_DONE')) is not None and
            done >= 1 and done == int(done))


def structure_fixed(model):
    if not enabled(model, 'DO_HYDRO') or hydro_exhausted(model):
        return True
    # An explicitly empty, complete schedule performs no structure changes,
    # including before its first revision. Startup-hydro recovery may still
    # rearm it when its stronger luminosity evidence qualifies.
    if number(model, 'HYDRO_DEFAULTS', 'N_ITS') != 0 or number(model, 'HYDRO_DEFAULTS', 'ITS_DONE') != 0:
        return False
    values = [number(model, 'HYDRO_DEFAULTS', key) for key in ('STRT_ITS','FREQ_ITS')]
    return all(v is not None and math.isfinite(v) and v >= 1 and v == int(v) for v in values)


def startup_hydro_evidence(model, native, result, before):
    """Bstar3512: copied zero-revision schedule blocks a positive POP startup."""
    from .pop_initialization import POP_MARKER
    from .checkpoint_physics import checkpoint_physics
    from .auto_recovery import repaired_runtime
    from .runner import _tail
    passes = result.get('passes', [])
    codes = {f['code'] for p in passes for f in p.get('diagnostic_findings', [])
             if f.get('severity') == 'error'}
    if (result['status'] != 'invalid_output' or len(passes) != 1 or
            codes != {'inner_flux_accuracy'} or passes[0].get('returncode') != 0):
        raise RunnerError('Startup hydro recovery needs an isolated zero-exit luminosity safeguard stop')
    if not enabled(model, 'DO_HYDRO') or not enabled(model, 'STOP_IF_MW', 'T'):
        raise RunnerError('Startup hydro recovery requires DO_HYDRO=T and STOP_IF_MW=T')
    if (number(model, 'HYDRO_DEFAULTS', 'N_ITS') != 0 or
            number(model, 'HYDRO_DEFAULTS', 'ITS_DONE') != 0 or
            number(model, 'HYDRO_DEFAULTS', 'STRT_ITS') != 2):
        raise RunnerError('Startup hydro recovery requires an unperformed zero-revision schedule starting at iteration 2')
    freq = number(model, 'HYDRO_DEFAULTS', 'FREQ_ITS')
    if freq is None or freq <= 0 or freq != int(freq):
        raise RunnerError('Startup hydro recovery needs a valid explicit hydro frequency')
    if (control_value(model, 'VADAT', 'DC_METH', '').upper() != 'POP' or
            enabled(model, 'FIX_T') or
            control_value(model, 'IN_ITS', 'DO_LAM_IT', 'F').upper().strip('.') not in {'F','FALSE'}):
        raise RunnerError('Startup hydro recovery is established only for variable-T full POP startup')
    if not repaired_runtime(native):
        raise RunnerError('Startup hydro recovery requires a supported dated CMFGEN patch revision')
    text = latest_main_log(_tail(model/'OUTGEN', 32*1024*1024))
    if re.search(r'SIG(?:SEGV|FPE|ILL|ABRT)|Fortran runtime error|segmentation fault',
                 text+'\n'+passes[0].get('diagnostic_tail', ''), re.I):
        raise RunnerError('Startup guard stop includes another native failure')
    restart = native['restart']
    fresh = restart['mode'] == 'fresh'
    observed = passes[0].get('startup_observed', {}).get('mode')
    if fresh:
        if observed != 'fresh' or POP_MARKER not in text:
            raise RunnerError('Fresh startup did not confirm native POP initialization')
        iteration = 1
    else:
        if (restart['mode'] != 'continuation' or observed != 'continuation' or
                restart['pointer']['iterations'] != 1):
            raise RunnerError('Unscheduled startup hydro recovery applies only at the first continuation')
        checkpoint_physics(model)
        iteration = 2
    records = _parse_iteration_records(text)
    if (len(records) != 1 or records[0]['global_iteration'] != iteration or
            'solver_maximum_change' in records[0]):
        raise RunnerError('Startup guard stop was not before its first population solve')
    measured = guard_measurements(model, before)
    if not (.25 <= measured['luminosity_min'] < .5 and measured['luminosity_max'] <= 2):
        raise RunnerError('Startup hydro recovery requires a moderate positive luminosity deficit (minimum 0.25–0.5, maximum <=2)')
    return {'fresh_seed_required': fresh, 'stopped_iteration': iteration, **measured}
