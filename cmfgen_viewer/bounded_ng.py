"""Checkpoint-bound backoff of a rejected native Ng proposal.

The controller must hold the model mutation guard and retain a durable recovery
snapshot before calling apply(). All coordinates, including trace populations,
share one affine fraction. Native counters and geometry are never rewritten.
"""
from pathlib import Path
import hashlib
import math
import os
import shutil
import tempfile
import numpy as np
from .population_projection import _state
from .checkpoint_health import _words, WORDS_PER_RECORD, RECORD_BYTES
from .runner_recipe import RunnerError, snapshot
from .runner_restart import read_pointer
from .auto_diagnostics import control_value, number
FILES = ('POINT1', 'POINT2', 'SCRTEMP', 'MODEL', 'MODEL_SPEC', 'VADAT', 'IN_ITS',
         'ADJUST_CORRECTIONS', 'HYDRO_DEFAULTS', 'ADJUST_R_DEFAULTS', 'RVSIG_COL')

def digest(path):
    if path.is_symlink():
        raise RunnerError('Unsafe Ng input: ' + path.name)
    if not path.exists():
        return None
    info = path.stat()
    if not path.is_file() or info.st_nlink != 1:
        raise RunnerError('Unsafe Ng input: ' + path.name)
    cap = 512 * 1024**2 if path.name == 'SCRTEMP' else 16 * 1024**2
    if path.name.startswith('POINT'):
        cap = 4096
    if info.st_size > cap:
        raise RunnerError('Ng input too large: ' + path.name)
    with path.open('rb') as f:
        h = hashlib.sha256()
        for block in iter(lambda: f.read(1024**2), b''):
            h.update(block)
        return h.hexdigest()

def signatures(model):
    return {n: digest(model / n) for n in FILES}

def enabled(model, key):
    return control_value(model, 'VADAT', key, 'F').upper().strip('.') in {'T', 'TRUE'}

def physics(p, state):
    if not np.isfinite(p).all() or np.any(p <= 0):
        raise RunnerError('Nonpositive or nonfinite Ng populations')
    density = max(float(np.max(np.abs(p[:, ids].sum(axis=1) /
                  np.asarray(state[0]['element_densities'][str(k)]) - 1)))
                  for k, ids in state[4].items())
    charge = float(np.max(np.abs(p[:, :-2] @ state[5] / p[:, -2] - 1)))
    if not math.isfinite(density + charge) or max(density, charge) > 1e-10:
        raise RunnerError('Ng history/proposal violates conservation')
    return {'element_density_max_relative_change': density, 'charge_relative_error': charge}

def kernel(history):
    """Replay NGACCEL with sequential sums and its native 1e-13 EQUAL test.

    The tolerance comes from native X02AJF=1e-15, not numpy machine epsilon.
    Do not vectorize the reductions: their rounding affects singular branches.
    """
    x = history.reshape(4, -1)
    a1 = b1 = b2 = c1 = c2 = 0.0
    for values in zip(*x):
        (p0, p1, p2, p3) = map(float, values)
        w = 1 / p0 if p0 else 1.0
        if not math.isfinite(w):
            raise RunnerError('Ng weight is not representable')
        d0 = p0 - p1
        d1 = d0 + (p2 - p1)
        d2 = d0 + (p3 - p2)
        a1 += w * d1 * d1
        b1 += w * d1 * d2
        c1 += w * d0 * d1
        b2 += w * d2 * d2
        c2 += w * d0 * d2
    div1 = b2 * a1
    div2 = b1 * b1
    if not all(map(math.isfinite, (a1, b1, b2, c1, c2, div1, div2))):
        raise RunnerError('Nonfinite Ng normal equations')
    equal = div1 == div2 == 0 or (
        1 - div1 / div2 <= 1e-13 if abs(div2) > abs(div1)
        else div1 != 0 and 1 - div2 / div1 <= 1e-13)
    if equal:
        (a, b) = (c1 / a1, 0.0) if a1 else (0.0, c2 / b2) if b2 else (0.0, 0.0)
    else:
        (a, b) = ((b2 * c1 - b1 * c2) / (div1 - div2), (a1 * c2 - b1 * c1) / (div1 - div2))
    if not all(map(math.isfinite, (a, b))):
        raise RunnerError('Nonfinite Ng coefficients')
    with np.errstate(over='raise', invalid='raise'):
        result = x[0] + a * (x[1] - x[0]) + b * (x[2] - x[0])
    return result.reshape(history.shape[1:])

def _compute(model, maximum_fraction=0.125, maximum_T_percent=0.1):
    if not 0 < maximum_fraction <= 0.125 or not 0 < maximum_T_percent <= 0.1:
        raise RunnerError('Untested Ng bounds')
    unsupported = ('FIX_T', 'SN_MODEL', 'USE_FIXED_J', 'IMPURITY_CODE',
                   'USE_J_REL', 'USE_DJDT_RTE', 'FLUX_CAL_ONLY')
    if not enabled(model, 'DO_NG') or any(enabled(model, k) for k in unsupported):
        return None
    pointers = [read_pointer(model / n) for n in ('POINT1', 'POINT2')]
    if ({k: v for k, v in pointers[0].items() if k != 'file'} !=
            {k: v for k, v in pointers[1].items() if k != 'file'}):
        raise RunnerError('Ng pointers disagree')
    state = _state(model)
    pointer = state[1]
    (nd, nt) = state[2].shape
    if pointer['record'] < 4 or pointer['writes'] != 1 or (not pointer['writes_rvsig']):
        return None
    if pointer['last_ng'] >= pointer['iterations'] - 3:
        return None
    band = number(model, 'VADAT', 'BW_NG')
    if band is None or not math.isfinite(band) or band != int(band):
        raise RunnerError('Ambiguous Ng band')
    band = int(band)
    band = nd if band <= 0 or band >= nd else band
    gr = (3 * nd + WORDS_PER_RECORD - 1) // WORDS_PER_RECORD
    pr = (nt * nd + WORDS_PER_RECORD - 1) // WORDS_PER_RECORD
    history = []
    geometry = None
    with (model / 'SCRTEMP').open('rb') as f:
        for rec in range(pointer['record'], pointer['record'] - 4, -1):
            base = max(2, gr) + (rec - 1) * (pr + gr)
            geo = np.fromiter(_words(f, base, 3 * nd, state[7]), float).reshape(3, nd)
            p = np.fromiter(_words(f, base + gr, nt * nd, state[7]), float).reshape(nd, nt)
            physics(p, state)
            if geometry is None:
                geometry = geo
            if not np.array_equal(geo, geometry):
                raise RunnerError('Ng history geometry changed')
            history.append(np.concatenate([p, geo.T[:, :2], geo.T[:, 2:] + 1], axis=1))
    h = np.array(history)
    if not np.array_equal(h[0, :, :nt], state[2]) or snapshot(model / 'SCRTEMP') != state[-1]:
        raise RunnerError('Ng history changed while reading')
    if not np.isfinite(h).all() or np.any(h <= 0):
        raise RunnerError('Unsupported Ng history coordinates')
    if np.max(np.abs(100 * (h[:-1, :, nt - 1] / h[1:, :, nt - 1] - 1))) > 0.1:
        raise RunnerError('Ng history temperature changes exceed tested regime')
    proposed = np.empty_like(h[0])
    # Match the native overlapping first band when ND is not divisible by BW_NG.
    for k in range(nd, 0, -band):
        lo = max(k - band, 0)
        hi = lo + band
        proposed[lo:hi] = kernel(h[:, lo:hi])
    p = proposed[:, :nt]
    old = state[2]
    if not np.isfinite(p).all():
        raise RunnerError('Nonfinite native-equivalent proposal')
    ratios = p / old
    wrong = (p[:, -1] - old[:, -1]) * (old[:, -1] - h[1, :, nt - 1]) < 0
    native_bad = (np.min(ratios, axis=1) < 0.09) | (np.max(ratios, axis=1) > 10.1) | wrong
    # Native-admissible proposals belong to the native accelerator.
    if int(native_bad.sum()) <= 3:
        return None
    # A positive backoff cannot repair a temperature direction reversal.
    if wrong.any():
        return None
    alpha = 1.0
    while alpha >= 1 / 1024:
        new = old + alpha * (p - old)
        r = new / old
        temperature_change = 100 * np.max(np.abs(r[:, -1] - 1))
        if (np.isfinite(new).all() and np.all(new > 0) and
                np.max(np.abs(r - 1)) <= maximum_fraction and
                temperature_change <= maximum_T_percent):
            checks = physics(new, state)
            if np.array_equal(new, old):
                return None
            description = dict(alpha=alpha, band=band,
                native_rejected_depths=int(native_bad.sum()),
                maximum_fraction=maximum_fraction, maximum_T_percent=maximum_T_percent,
                ratio_min=float(r.min()), ratio_max=float(r.max()),
                maximum_temperature_change_percent=float(temperature_change),
                physical_checks=checks)
            return state, new, description
        alpha *= 0.5
    return None


def compute(model, maximum_fraction=0.125, maximum_T_percent=0.1):
    try:
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            return _compute(model, maximum_fraction, maximum_T_percent)
    except ArithmeticError as exc:
        raise RunnerError('Unrepresentable Ng arithmetic') from exc


def propose(model, maximum_fraction=0.125, maximum_T_percent=0.1):
    model = Path(model)
    before = signatures(model)
    result = compute(model, maximum_fraction, maximum_T_percent)
    if result is None:
        return None
    if signatures(model) != before:
        raise RunnerError('Ng inputs changed during proposal')
    (state, new, description) = result
    return {**description, 'inputs': before, 'pointer': state[1], 'checkpoint_snapshot': state[-1]}

def apply(model, plan, maximum_fraction=0.125, maximum_T_percent=0.1):
    """Caller holds write guard and retains a recovery snapshot."""
    model = Path(model)
    if not isinstance(plan, dict) or plan.get('inputs') != signatures(model):
        raise RunnerError('Stale Ng inputs')
    result = compute(model, maximum_fraction, maximum_T_percent)
    if result is None:
        raise RunnerError('Ng proposal no longer eligible')
    (state, new, description) = result
    if (any(plan.get(k) != v for k, v in description.items()) or
            plan.get('pointer') != state[1] or plan.get('checkpoint_snapshot') != state[-1]):
        raise RunnerError('Ng proposal descriptor changed')
    if shutil.disk_usage(model).free < (model / 'SCRTEMP').stat().st_size + 64 * 1024 ** 2:
        raise RunnerError('Insufficient atomic Ng staging space')
    (fd, name) = tempfile.mkstemp(prefix='.ng-restart-', dir=model)
    os.close(fd)
    temp = Path(name)
    try:
        shutil.copy2(model / 'SCRTEMP', temp)
        with temp.open('r+b') as f:
            f.seek(state[6] * RECORD_BYTES)
            f.write(new.astype(state[7] + 'f8').tobytes())
            f.flush()
            os.fsync(f.fileno())
        if signatures(model) != plan['inputs']:
            raise RunnerError('Ng inputs changed before publishing')
        os.replace(temp, model / 'SCRTEMP')
    finally:
        temp.unlink(missing_ok=True)
    after = _state(model)
    checks = physics(after[2], state)
    if after[1] != state[1] or after[0]['geometry'] != state[0]['geometry'] or (not np.array_equal(after[2], new)):
        raise RunnerError('Ng publication audit failed')
    return {**description, 'physical_checks': checks,
            'checkpoint_sha256': digest(model / 'SCRTEMP'), 'counter_unchanged': True}
