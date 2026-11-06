"""Provisional bounded Ng fallback for a slow, thermally unbalanced tail.

Six full solves are deliberately required: the measured population transient
can worsen through the first four solves. Acceptance is progress, not numerical
convergence; the ordinary independent convergence verification still follows.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from .auto_diagnostics import control_value, number, oscillating_region
from .auto_hydro import enabled, guard_measurements, structure_fixed
from .auto_performance import _metrics, _thermal_complete
from .bounded_ng import propose
from .checkpoint_physics import checkpoint_physics, compare_physics
from .parsers.common import parse_float_token
from .runner_recipe import RunnerError
from .workflow_permissions import make_readable, mkdir_readable


RECEIPT = 'bounded-ng-trials.json'


def fingerprint(proposal):
    pointer = {k: v for k, v in proposal['pointer'].items() if k != 'file'}
    identity = [proposal['inputs']['SCRTEMP'], pointer]
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def _receipts(model):
    parent = Path(model)/'.cmfgen-runs'
    path = parent/RECEIPT
    if parent.is_symlink() or path.is_symlink():
        raise RunnerError('Unsafe bounded Ng attempt receipt')
    if not path.exists():
        return path, {}
    info = path.stat()
    if not path.is_file() or info.st_nlink != 1 or info.st_size > 8*1024**2:
        raise RunnerError('Invalid bounded Ng attempt receipt')
    value = json.loads(path.read_text())
    if (not isinstance(value, dict) or
            any(not isinstance(k, str) or len(k) != 64 or not isinstance(v, str)
                for k, v in value.items())):
        raise RunnerError('Invalid bounded Ng attempt receipt')
    return path, value


def mark_attempt(model, proposal, action_directory):
    """Persist before mutation; a rollback must not erase retry suppression."""
    path, attempts = _receipts(model)
    key = fingerprint(proposal)
    if key in attempts:
        raise RunnerError('This checkpoint has already had a bounded Ng trial')
    attempts[key] = str(action_directory)
    encoded = json.dumps(attempts, sort_keys=True).encode()
    if len(encoded) > 8*1024**2:
        raise RunnerError('Bounded Ng attempt receipt is full')
    mkdir_readable(path.parent, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.ng-receipt-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        make_readable(temporary)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _energy(model, nd):
    path = model/'OBSFLUX'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32*1024**2:
        raise RunnerError('Missing/unsafe energy residual for bounded Ng')
    lines = path.read_text().splitlines()
    heads = [i for i, line in enumerate(lines)
             if line.strip().startswith('Departure from Rad Equilibrium Correction')]
    if not heads:
        raise RunnerError('Missing radiative-equilibrium energy residual')
    values = []
    for line in lines[heads[-1]+1:]:
        if not line.strip() and not values:
            continue
        row = [parse_float_token(token) for token in line.split()]
        if not row or any(v is None for v in row):
            break
        values.extend(row)
        if len(values) >= nd:
            break
    if len(values) != nd or not all(math.isfinite(v) for v in values):
        raise RunnerError('Incomplete radiative-equilibrium energy residual')
    energy = sum(abs(v) for v in values)
    if not math.isfinite(energy):
        raise RunnerError('Unrepresentable radiative-equilibrium energy residual')
    return energy


def _full(evidence):
    rows = evidence.get('records', [])
    return (len(rows) >= 2 and evidence['full_iterations'] == evidence['iterations'] == len(rows)
            and not any(evidence.get(k) for k in ('hydro_revisions', 'ng_accelerations',
                        'checkpoint_updates', 'source_changed', 'population_cycle'))
            and all(r.get('ba_computed') is True and not r.get('temperature_fixed')
                    and not r.get('lambda_iteration') and
                    r.get('major_species_minimum_scale') == 1 for r in rows)
            and _thermal_complete(evidence)
            and len(evidence['raw_temperature_steps']) == len(rows)
            and max(abs(v) for row in evidence['raw_temperature_steps'] for v in row) <= .1)


def _validate(ctx, baseline, pair):
    from .auto_policies import TrialRejected
    e = ctx.evidence
    try:
        if (not _full(e) or len(e['records']) != 2 or
                [r['global_iteration'] for r in e['records']] !=
                [baseline['checkpoint']+2*pair-1, baseline['checkpoint']+2*pair] or
                e['checkpoint'] != baseline['checkpoint']+2*pair):
            raise RunnerError('Bounded Ng needs consecutive full fresh-BA/free-T solves without transitions')
        metrics = _metrics(e)
        if max(metrics) > min(10, 2*baseline['correction_metric']):
            raise RunnerError('Bounded Ng population transient exceeded its safety limit')
        current = checkpoint_physics(ctx.model)
        checks = compare_physics(baseline['physical'], current)
        if max(checks.values()) > 1e-10:
            raise RunnerError('Bounded Ng follow-up violated conservation')
        guard = guard_measurements(ctx.model, ctx.before)
        old = baseline['guard']
        if (guard['luminosity_min'] < max(.5, old['luminosity_min']-.001) or
                guard['luminosity_max'] > min(2, old['luminosity_max']+.001)):
            raise RunnerError('Bounded Ng degraded the luminosity profile')
        energy = _energy(ctx.model, e['counts']['nd'])
        if pair == 3:
            previous = baseline['counts']
            counts = e['counts']
            if (metrics[-1] >= baseline['correction_metric'] or metrics[-1] > metrics[-2] or
                    max(metrics) > baseline['correction_metric'] or
                    any(counts[k] != previous[k] for k in ('nd', 'nt')) or
                    counts['totals'].keys() != previous['totals'].keys() or
                    any(v > previous['totals'][k] for k, v in counts['totals'].items()
                        if float(k.removesuffix('%')) >= baseline['epsilon_percent'])):
                raise RunnerError('Bounded Ng did not settle with improved significant corrections')
            old_deviation = max(abs(old['luminosity_min']-1), abs(old['luminosity_max']-1))
            deviation = max(abs(guard['luminosity_min']-1), abs(guard['luminosity_max']-1))
            if energy > .995*baseline['energy'] or deviation >= old_deviation:
                raise RunnerError('Bounded Ng did not retain a measurable thermal benefit')
    except (ImportError, OSError, ValueError) as exc:
        raise TrialRejected(str(exc)) from exc
    return {'bounded_ng_check': dict(pair=pair, accepted=pair == 3,
            correction_metrics=metrics, guard=guard, absolute_energy_residual=energy,
            physical_checks=checks)}


def bounded_ng_trial(ctx):
    from .auto_policies import Decision, Declined, RecoveryStep
    from .auto_recovery import repaired_runtime
    if (ctx.phase != 'iterate' or ctx.evidence.get('candidate') or
            ctx.remaining_iterations < 9 or ctx.remaining_attempts < 4 or
            any(a.get('policy_id') == 'bounded_ng' for a in ctx.actions) or
            not repaired_runtime(ctx.native_plan, minimum='2026-11-02.1') or
            not structure_fixed(ctx.model) or not enabled(ctx.model, 'DO_NG') or
            not enabled(ctx.model, 'COMP_BA') or
            control_value(ctx.model, 'VADAT', 'SCALE_OPT', '').upper() != 'MAJOR' or
            any(number(ctx.model, 'VADAT', k, -1) != 0 for k in ('N_FIX_BA', 'FIX_BA'))):
        return None
    epsilon = ctx.evidence.get('epsilon_percent')
    if not isinstance(epsilon, (int, float)) or not math.isfinite(epsilon) or epsilon <= 0:
        return None
    # At least six observed solves in a single unchanged physical regime.
    history = ctx.history[-3:]
    if not history or not all(_full(e) for e in history):
        return None
    rows = [r for e in history for r in e['records']][-6:]
    thermal = [v for e in history for v in e['raw_temperature_steps']][-6:]
    if len(rows) != 6 or [r['global_iteration'] for r in rows] != list(
            range(ctx.evidence['checkpoint']-5, ctx.evidence['checkpoint']+1)):
        return None
    try:
        metrics = _metrics({'records': rows})
    except ValueError:
        return None  # Missing measurements cannot authorize an optional trial.
    if (not all(1 <= v < 10 for v in metrics) or
            not .9 <= metrics[-1]/metrics[0] < 1 or
            any(b > 1.1*a for a, b in zip(metrics, metrics[1:])) or
            oscillating_region({**ctx.evidence, 'raw_temperature_steps': thermal}, [], localized_only=False)):
        return None
    try:
        guard = guard_measurements(ctx.model, ctx.before)
        if (guard['inner_tau_ross'] < 50 or guard['luminosity_min'] < .5 or
                guard['luminosity_max'] > 2 or
                max(abs(guard['luminosity_min']-1), abs(guard['luminosity_max']-1)) < .02):
            return None
        proposal = propose(ctx.model)
        if proposal is None or fingerprint(proposal) in _receipts(ctx.model)[1]:
            return None
        baseline = dict(checkpoint=ctx.evidence['checkpoint'], correction_metric=metrics[-1],
                        counts=ctx.evidence['counts'], epsilon_percent=ctx.evidence['epsilon_percent'],
                        physical=checkpoint_physics(ctx.model), guard=guard,
                        energy=_energy(ctx.model, ctx.evidence['counts']['nd']), proposal=proposal)
        if baseline['energy'] <= 0:
            return None
    except (ImportError, OSError, ValueError) as exc:
        raise Declined('Bounded Ng prerequisites unavailable: '+str(exc)) from exc
    return Decision('action', 'Slow full-solve tail with a rejected native Ng proposal; '
                    'test one bounded affine step over six full solves',
        action='bounded_ng', evidence=baseline, reversible_trial=True,
        changes={'VADAT': {'COMP_F': 'T', 'COMP_BA': 'T', 'N_FIX_BA': '0', 'FIX_BA': '0.0'}},
        caches=('BAMAT', 'BAMATPNT', 'EDDFACTOR', 'EDDFACTOR_INFO'),
        steps=tuple(RecoveryStep(name, 2, lambda c, pair=pair: _validate(c, baseline, pair))
                    for pair, name in enumerate(('bounded_ng_settle1', 'bounded_ng_settle2',
                                                 'bounded_ng_check'), 1)))
