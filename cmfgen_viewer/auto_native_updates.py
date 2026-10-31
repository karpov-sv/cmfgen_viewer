"""Evidence-based recognition of native ramp and automatic release controls."""
import math
import re

from .control_files import control_occurrences
from .model_convergence import _parse_iteration_records
from .parsers.common import parse_float_token
from .runner_recipe import RunnerError


def truth(values, key, default='F'):
    return values.get(key, default).upper().strip('.') in {'T', 'TRUE'}


def numeric(values, key):
    value = parse_float_token(values.get(key, ''))
    if value is None or not math.isfinite(value):
        raise RunnerError(f'Native transition requires finite [{key}]')
    return value


def close(a, b):
    return math.isclose(a, b, rel_tol=5e-7, abs_tol=0)


def native_rewrite_only(before, after, allowed):
    """Ignore native value-field formatting and trailing blanks, not other edits."""
    def masked(text):
        lines = text.splitlines()
        for key, rows in control_occurrences(text).items():
            if key in allowed:
                for row in rows:
                    i = row['line_index']
                    lines[i] = '<native>'+lines[i][row['key_start']-1:]
        return [line.rstrip() for line in lines]
    if masked(before) != masked(after):
        raise RunnerError('Unexpected edit alongside native control transition; preserving it for review')


def ramp_updates(old, new, its, text, process_text):
    """Validate native algorithms and logged values, never arbitrary key changes."""
    allowed, transitions = set(), []
    records = _parse_iteration_records(text)
    def eligible(limit, *, lam=False):
        return [r for r in records if (not lam or r.get('lambda_iteration')) and
                isinstance(r.get('solver_maximum_change'), (int, float)) and
                math.isfinite(r['solver_maximum_change']) and 0 <= r['solver_maximum_change'] < limit]
    def logged(pattern, source=text):
        values = [parse_float_token(v) for v in re.findall(pattern, source, re.M)]
        if any(v is None or not math.isfinite(v) for v in values):
            raise RunnerError('Nonfinite native ramp evidence')
        return values
    def add(keys, kind):
        allowed.update(keys)
        transitions.append(kind)
    if old.get('USE_FIXED_J') != new.get('USE_FIXED_J'):
        if not (truth(old, 'USE_FIXED_J') and not truth(new, 'USE_FIXED_J') and
                truth(its, 'DO_LAM_AUTO', 'T') and truth(its, 'DO_LAM_IT') and eligible(50, lam=True)):
            raise RunnerError('Fixed-J release lacks automatic Lambda convergence evidence')
        add({'USE_FIXED_J'}, 'fixed_j_release')
    # Each native advection update doubles its coefficient, capped at one.
    if old.get('ADV_RELAX') != new.get('ADV_RELAX'):
        values = logged(r'^\s*Have adjusted advection relaxation parameter to:\s*(\S+)\s*$')
        if not truth(old, 'INC_ADV') or not values or len(values) > len(eligible(100)):
            raise RunnerError('Advection ramp lacks native evidence')
        previous = numeric(old, 'ADV_RELAX')
        for value in values:
            if not 0 < previous < 1 or not close(value, min(1, previous*2)):
                raise RunnerError('Advection ramp does not match native doubling')
            previous = value
        if not close(previous, numeric(new, 'ADV_RELAX')):
            raise RunnerError('Advection control differs from logged ramp')
        add({'ADV_RELAX'}, 'advection_ramp')
    for flag, enabled_key, key, multipliers, kind in [
        ('GAMMA_SLOW', 'TRT_NON_TE', 'DECNRG_SCLFAC_BEG',
         (10, 100), 'decay_ramp'),
        ('ADD_SHOCK_POWER_SLOWLY', 'INC_SHOCK_POWER', 'SHOCK_POWER_FAC_BEG',
         (10,), 'shock_ramp'),
    ]:
        if old.get(key) == new.get(key) and old.get(flag) == new.get(flag):
            continue
        heading = ('Have adjusted radioactivity decay energy scale factor' if kind == 'decay_ramp'
                   else 'Have adjusted SHOCK POWERscale factor')
        values = logged(re.escape(heading)+r'\s*\n\s*New scale factor is\s+(\S+)')
        if not truth(old, flag) or not truth(old, enabled_key) or not truth(its, 'DO_LAM_IT'):
            raise RunnerError(f'{kind} lacks enabled native controls')
        previous = numeric(old, key)
        if not 0 < previous <= 1 or len(values) > len(eligible(100, lam=True)):
            raise RunnerError(f'Invalid {kind} evidence')
        for value in values:
            if previous >= 1 or not any(close(value, min(1, previous*m)) for m in multipliers):
                raise RunnerError(f'{kind} does not match native increments')
            previous = value
        if not close(previous, numeric(new, key)) or (not values and old.get(key) != new.get(key)):
            raise RunnerError(f'{kind} control differs from logged ramp')
        if old.get(flag) != new.get(flag):
            if truth(new, flag) or not close(previous, 1) or len(eligible(100, lam=True)) <= len(values):
                raise RunnerError(f'{kind} completion lacks a subsequent native Lambda solve')
        add({key, flag}, kind)
    slow_keys = {'XFI1_BEG', 'XFI2_BEG', 'XSLOW'}
    if any(old.get(k) != new.get(k) for k in slow_keys):
        if not truth(old, 'INC_XRAYS') or not truth(old, 'XSLOW') or not truth(its, 'DO_LAM_IT'):
            raise RunnerError('Gradual X-ray ramp lacks enabled native controls')
        values = [logged(r'^\s*Current filling factor is \(1st component\)\s*(\S+)\s*$', process_text),
                  logged(r'^\s*Current filling factor is \(2nd component\)\s*(\S+)\s*$', process_text)]
        if len(values[0]) != len(values[1]) or len(values[0]) > len(eligible(100, lam=True)):
            raise RunnerError('Incomplete gradual X-ray ramp evidence')
        multiplier = numeric(old, 'XSCL_FAC')
        if multiplier <= 1:
            raise RunnerError('Gradual X-ray multiplier must exceed one')
        reached = True
        for key, target_key, series in zip(('XFI1_BEG', 'XFI2_BEG'), ('FIL_FAC_1', 'FIL_FAC_2'), values):
            previous, target = numeric(old, key), numeric(old, target_key)
            if min(previous, target) < 0 or previous > target:
                raise RunnerError('Invalid gradual X-ray bounds')
            for value in series:
                if not close(value, min(previous*multiplier, target)):
                    raise RunnerError('Gradual X-ray ramp differs from native multiplier')
                previous = value
            if not close(previous, numeric(new, key)):
                raise RunnerError('Gradual X-ray control differs from logged ramp')
            reached = reached and close(previous, target)
        if old.get('XSLOW') != new.get('XSLOW'):
            if truth(new, 'XSLOW') or not reached or len(eligible(100, lam=True)) <= len(values[0]):
                raise RunnerError('Gradual X-ray completion lacks native evidence')
        add(slow_keys, 'xray_ramp')
    return allowed, transitions
