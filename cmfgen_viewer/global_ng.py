"""Provisional global extrapolation for a smooth, deep thermal slow mode.

The controller owns the mutation guard and durable rollback until six ordinary
full solves demonstrate retained benefit. Native convergence credit is unchanged.
"""
import math
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

from . import bounded_ng
from .population_projection import _state
from .checkpoint_health import _words, WORDS_PER_RECORD, RECORD_BYTES
from .checkpoint_physics import compare_physics
from .runner_recipe import RunnerError, snapshot
from .auto_diagnostics import control_value

def coefficients(history):
    """Native absolute-population weighting, accumulated in numpy long double.

    This is a geometric reconstruction experiment, not bitwise NGACCEL replay.
    The native constant geometry coordinates are retained in the reduction.
    """
    x = np.asarray(history).reshape(4, -1).astype(np.longdouble)
    if not np.isfinite(x).all() or np.any(x <= 0):
        raise ValueError('History must have finite, positive coordinates')
    with np.errstate(over='raise', invalid='raise', divide='raise'):
        d0 = x[0] - x[1]
        d1 = d0 + x[2] - x[1]
        d2 = d0 + x[3] - x[2]
        w = 1 / x[0]
        a1 = np.sum(w*d1*d1)
        b1 = np.sum(w*d1*d2)
        b2 = np.sum(w*d2*d2)
        c1 = np.sum(w*d0*d1)
        c2 = np.sum(w*d0*d2)
        u, v = a1*b2, b1*b1
        if u == v == 0 or abs(u-v) <= 1e-13*max(abs(u), abs(v)):
            a, b = (c1/a1, 0) if a1 else (0, c2/b2) if b2 else (0, 0)
        else:
            a, b = (b2*c1-b1*c2)/(u-v), (a1*c2-b1*c1)/(u-v)
    a, b = float(a), float(b)
    if not math.isfinite(a+b):
        raise ValueError('Unrepresentable extrapolation coefficients')
    return a, b


def calculate(history, groups, charge):
    """Return one provisional conserved seed under fixed, verified trial caps.

    Input is newest-first (4, ND, NT+3): populations, Ne, T, R, V, sigma+1.
    It must represent four fresh free-T ordinary solves in one physical regime;
    verifying that provenance is the caller's responsibility. No floors,
    population exclusion, native-solve credit, or convergence decision occurs.
    """
    h = np.asarray(history, dtype=float)
    if h.ndim != 3 or h.shape[0] != 4 or h.shape[2] < 6:
        raise ValueError('Four complete population/geometry states required')
    nt = h.shape[2]-3
    ids = [int(i) for group in groups.values() for i in group]
    if sorted(ids) != list(range(nt-2)) or len(charge) != nt-2:
        raise ValueError('Species/charge metadata must cover every population once')
    if not np.isfinite(h).all() or np.any(h <= 0):
        raise ValueError('Finite positive history required')
    if not np.array_equal(h[:,:,-3:], np.broadcast_to(h[0,:,-3:],h[:,:,-3:].shape)):
        raise ValueError('History geometry changed')
    old = h[0,:,:nt]
    for p in h[:,:,:nt]:
        for group in groups.values():
            if np.max(np.abs(p[:,group].sum(axis=1)/old[:,group].sum(axis=1)-1)) > 1e-10:
                raise ValueError('History species density changed')
        if np.max(np.abs(p[:,:-2]@charge/p[:,-2]-1)) > 1e-10:
            raise ValueError('History charge is inconsistent')
    if np.max(np.abs(100*(h[:-1,:,nt-1]/h[1:,:,nt-1]-1))) > .1:
        raise ValueError('Temperature history exceeds the trial regime')
    a, b = coefficients(h)
    logs = np.log(h[:,:,:nt])
    proposed = logs[0]+a*(logs[1]-logs[0])+b*(logs[2]-logs[0])
    step = proposed-np.log(old)
    if not np.isfinite(step).all():
        raise ValueError('Unrepresentable geometric proposal')
    if not np.any(step) or np.any(step[:,-1]*(old[:,-1]-h[1,:,nt-1]) < 0):
        return None
    alpha = 1.
    while alpha >= 1/1024:
        try:
            with np.errstate(over='raise', invalid='raise', divide='raise', under='ignore'):
                new = np.exp(np.log(old)+alpha*step)
                for group in groups.values():
                    new[:,group] *= old[:,group].sum(axis=1)[:,None]/new[:,group].sum(axis=1)[:,None]
                new[:,-2] = new[:,:-2]@charge
                ratios = new/old
            valid = (np.isfinite(new).all() and np.all(new > 0) and
                     ratios.min() >= .1 and ratios.max() <= 10 and
                     np.max(np.abs(ratios[:,-1]-1)) <= .01)
        except FloatingPointError:
            valid = False
        if valid:
            if np.array_equal(new, old):
                return None
            density_error = max(float(np.max(np.abs(new[:,g].sum(axis=1)/old[:,g].sum(axis=1)-1))) for g in groups.values())
            charge_error = float(np.max(np.abs(new[:,:-2]@charge/new[:,-2]-1)))
            if max(density_error,charge_error) > 1e-10:
                raise ValueError('Geometric reconstruction failed conservation')
            return new, dict(alpha=alpha, a=a, b=b, ratio_min=float(ratios.min()),ratio_max=float(ratios.max()),max_temperature_change_percent=float(100*np.max(np.abs(ratios[:,-1]-1))),element_density_relative_error=density_error,charge_relative_error=charge_error)
        alpha *= .5
    return None




def compute(model):
    model = Path(model)
    try:
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            affine = bounded_ng._compute(model, temperature_direction_required=False)
    except ArithmeticError as exc:
        raise RunnerError('Unrepresentable native Ng diagnostic') from exc
    if affine is None or affine[2]['alpha'] > 1/16:
        return None
    if (bounded_ng.enabled(model, 'USE_EHB') or
            control_value(model, 'MODEL_SPEC', 'NUM_BNDS', '').strip() != '3'):
        return None
    state = affine[0]
    nd, nt = state[2].shape
    pointer = state[1]
    gr = (3*nd+WORDS_PER_RECORD-1)//WORDS_PER_RECORD
    pr = (nd*nt+WORDS_PER_RECORD-1)//WORDS_PER_RECORD
    history = []
    with (model/'SCRTEMP').open('rb') as stream:
        for rec in range(pointer['record'], pointer['record']-4, -1):
            base = max(2, gr)+(rec-1)*(pr+gr)
            geo = np.fromiter(_words(stream, base, 3*nd, state[7]), float).reshape(3, nd)
            pops = np.fromiter(_words(stream, base+gr, nt*nd, state[7]), float).reshape(nd, nt)
            history.append(np.concatenate([pops, geo.T[:,:2], geo.T[:,2:]+1], axis=1))
    history = np.array(history)
    if not np.array_equal(history[0,:,:nt], state[2]) or snapshot(model/'SCRTEMP') != state[-1]:
        raise RunnerError('Checkpoint changed during global Ng inspection')
    try:
        result = calculate(history, state[4], state[5])
    except (ArithmeticError, ValueError) as exc:
        raise RunnerError('Unsupported global Ng history: '+str(exc)) from exc
    if result is None:
        return None
    new, description = result
    description.update(kind='global_geometric_ng', band=nd,
                       native_rejected_depths=affine[2]['native_rejected_depths'],
                       native_temperature_reversal_depths=affine[2]['native_temperature_reversal_depths'],
                       bounded_affine_alpha=affine[2]['alpha'],
                       population_ratio_bounds=[.1, 10.], maximum_T_percent=1.)
    bounded_ng.physics(new, state)
    return state, new, description


def propose(model):
    """Read-only numerical proposal; the policy establishes solve provenance."""
    model = Path(model)
    before = bounded_ng.signatures(model)
    result = compute(model)
    if result is None:
        return None
    if before != bounded_ng.signatures(model):
        raise RunnerError('Global Ng inputs changed during diagnosis')
    state, new, description = result
    return {**description, 'inputs': before, 'pointer': state[1], 'checkpoint_snapshot': state[-1]}


def apply(model, proposal):
    """Recompute and atomically publish; caller retains recovery until verified."""
    model = Path(model)
    if not isinstance(proposal, dict) or proposal.get('inputs') != bounded_ng.signatures(model):
        raise RunnerError('Stale global Ng proposal')
    result = compute(model)
    if result is None:
        raise RunnerError('Global Ng is no longer eligible')
    state, new, description = result
    if (any(proposal.get(k) != v for k, v in description.items()) or
            proposal.get('pointer') != state[1] or proposal.get('checkpoint_snapshot') != state[-1]):
        raise RunnerError('Global Ng descriptor changed')
    if shutil.disk_usage(model).free < (model/'SCRTEMP').stat().st_size+64*1024**2:
        raise RunnerError('Insufficient space for atomic global Ng staging')
    descriptor, name = tempfile.mkstemp(prefix='.global-ng-restart-', dir=model)
    os.close(descriptor)
    temporary = Path(name)
    try:
        shutil.copy2(model/'SCRTEMP', temporary)
        with temporary.open('r+b') as stream:
            stream.seek(state[6]*RECORD_BYTES)
            stream.write(new.astype(state[7]+'f8').tobytes())
            stream.flush()
            os.fsync(stream.fileno())
        if proposal['inputs'] != bounded_ng.signatures(model):
            raise RunnerError('Checkpoint changed before global Ng publication')
        os.replace(temporary, model/'SCRTEMP')
    finally:
        temporary.unlink(missing_ok=True)
    actual = _state(model)
    if (actual[1] != state[1] or actual[0]['geometry'] != state[0]['geometry'] or
            not np.array_equal(actual[2], new)):
        raise RunnerError('Global Ng publication audit failed')
    checks = compare_physics(state[0], actual[0])
    bounded_ng.physics(actual[2], state)
    return {**description, 'physical_checks': checks,
            'checkpoint_sha256': bounded_ng.digest(model/'SCRTEMP'), 'counter_unchanged': True}
