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
GLOBAL_RECEIPT = 'global-ng-trials.json'


def fingerprint(proposal):
    pointer = {k: v for k, v in proposal['pointer'].items() if k != 'file'}
    identity = [proposal['inputs']['SCRTEMP'], pointer]
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def _receipts(model, *, global_trial=False):
    parent = Path(model)/'.cmfgen-runs'
    path = parent/(GLOBAL_RECEIPT if global_trial else RECEIPT)
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


def mark_attempt(model, proposal, action_directory, *, global_trial=False):
    """Persist before mutation; a rollback must not erase retry suppression."""
    path, attempts = _receipts(model, global_trial=global_trial)
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


def _validate(ctx, baseline, pair, *, global_trial=False):
    from .auto_policies import TrialRejected
    e = ctx.evidence
    label = 'Global Ng' if global_trial else 'Bounded Ng'
    try:
        if (not _full(e) or len(e['records']) != 2 or
                [r['global_iteration'] for r in e['records']] !=
                [baseline['checkpoint']+2*pair-1, baseline['checkpoint']+2*pair] or
                e['checkpoint'] != baseline['checkpoint']+2*pair):
            raise RunnerError(f'{label} needs consecutive full fresh-BA/free-T solves without transitions')
        metrics = _metrics(e)
        if max(metrics) > min(10, 2*baseline['correction_metric']):
            raise RunnerError(f'{label} population transient exceeded its safety limit')
        current = checkpoint_physics(ctx.model)
        checks = compare_physics(baseline['physical'], current)
        if max(checks.values()) > 1e-10:
            raise RunnerError(f'{label} follow-up violated conservation')
        guard = guard_measurements(ctx.model, ctx.before)
        old = baseline['guard']
        if (guard['luminosity_min'] < max(.5, old['luminosity_min']-.001) or
                guard['luminosity_max'] > min(2, old['luminosity_max']+.001)):
            raise RunnerError(f'{label} degraded the luminosity profile')
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
                raise RunnerError(f'{label} did not settle with improved significant corrections')
            old_deviation = max(abs(old['luminosity_min']-1), abs(old['luminosity_max']-1))
            deviation = max(abs(guard['luminosity_min']-1), abs(guard['luminosity_max']-1))
            retained = .9 if global_trial else .995
            if (energy > retained*baseline['energy'] or deviation >= old_deviation or
                    (global_trial and deviation > .9*old_deviation)):
                raise RunnerError(f'{label} did not retain a measurable thermal benefit')
    except (ImportError, OSError, ValueError) as exc:
        raise TrialRejected(str(exc)) from exc
    key = 'global_ng_check' if global_trial else 'bounded_ng_check'
    return {key: dict(pair=pair, accepted=pair == 3,
            correction_metrics=metrics, guard=guard, absolute_energy_residual=energy,
            physical_checks=checks)}


def bounded_ng_trial(ctx):
    return _trial(ctx)


def global_ng_trial(ctx):
    return _trial(ctx, global_trial=True)


def _global_cooldown(ctx):
    """Keep both extrapolators off until eight new ordinary solves are observed."""
    for action in ctx.prior_actions + ctx.actions:
        if action.get('policy_id') != 'global_ng':
            continue
        start = action.get('evidence', {}).get('checkpoint')
        if not isinstance(start, int):
            return True
        end = start+(6 if action.get('trial_outcome') == 'accepted' else 0)
        current = ctx.evidence.get('checkpoint', 0)
        ordinary = {r['global_iteration'] for e in ctx.history if _full(e)
                    for r in e['records'] if end < r['global_iteration'] <= current}
        if current < end+8 or len(ordinary) < 8:
            return True
    return False


def _slow_thermal_tail(rows):
    """Require a large, nearly stationary flux error at an unchanged target."""
    targets, deviations = [], []
    for row in rows:
        generated, target = row.get('luminosity_generated'), row.get('luminosity_target')
        if (not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0
                    for v in (generated, target))):
            return False
        targets.append(target)
        deviations.append(generated/target-1)
    errors = [abs(v) for v in deviations]
    return (bool(errors) and min(errors) >= .02 and
            all(v*deviations[0] > 0 for v in deviations) and
            max(targets)/min(targets)-1 <= 1e-10 and
            .95 <= errors[-1]/errors[0] <= 1.01 and
            all(b <= 1.02*a for a, b in zip(errors, errors[1:])))


def _trial(ctx, *, global_trial=False):
    from .auto_policies import Decision, Declined, RecoveryStep
    from .auto_recovery import repaired_runtime
    policy = 'global_ng' if global_trial else 'bounded_ng'
    prior = [a for a in ctx.actions if a.get('policy_id') == policy]
    cooldown = _global_cooldown(ctx)
    if cooldown and not global_trial:
        return None
    if (ctx.phase != 'iterate' or ctx.evidence.get('candidate') or
            ctx.remaining_iterations < 9 or ctx.remaining_attempts < 4 or
            (prior and not global_trial) or
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
    minimum = max(.1, 5*epsilon) if global_trial else 1
    ratio = metrics[-1]/metrics[0] if metrics[0] else math.inf
    steady = .9 <= ratio <= 1.01 if global_trial else .9 <= ratio < 1
    if (not all(minimum <= v < 10 for v in metrics) or not steady or
            any(b > 1.1*a for a, b in zip(metrics, metrics[1:])) or
            oscillating_region({**ctx.evidence, 'raw_temperature_steps': thermal}, [], localized_only=False)):
        return None
    if global_trial and not _slow_thermal_tail(rows):
        return None
    try:
        guard = guard_measurements(ctx.model, ctx.before)
        if (guard['inner_tau_ross'] < 50 or guard['luminosity_min'] < .5 or
                guard['luminosity_max'] > 2 or
                max(abs(guard['luminosity_min']-1), abs(guard['luminosity_max']-1)) < (.05 if global_trial else .02)):
            return None
        if cooldown:
            ends = [a['evidence']['checkpoint']+(6 if a.get('trial_outcome') == 'accepted' else 0)
                    for a in ctx.prior_actions + ctx.actions if a.get('policy_id') == 'global_ng']
            if not ends or rows[0]['global_iteration'] <= max(ends):
                return None
            return Decision('continue', 'Observe eight healthy ordinary full solves before another global Ng trial')
        if global_trial:
            from .global_ng import propose as global_propose
            proposal = global_propose(ctx.model)
        else:
            proposal = propose(ctx.model)
        if proposal is None or fingerprint(proposal) in _receipts(ctx.model, global_trial=global_trial)[1]:
            return None
        baseline = dict(checkpoint=ctx.evidence['checkpoint'], correction_metric=metrics[-1],
                        counts=ctx.evidence['counts'], epsilon_percent=ctx.evidence['epsilon_percent'],
                        physical=checkpoint_physics(ctx.model), guard=guard,
                        energy=_energy(ctx.model, ctx.evidence['counts']['nd']), proposal=proposal)
        if baseline['energy'] <= 0:
            return None
    except (ImportError, OSError, ValueError) as exc:
        raise Declined(('Global Ng' if global_trial else 'Bounded Ng')+' prerequisites unavailable: '+str(exc)) from exc
    return trial_decision(baseline, global_trial=global_trial)


def trial_decision(baseline, *, global_trial=False):
    """Rebuild the same validators when continuing a saved provisional trial."""
    from .auto_policies import Decision, RecoveryStep
    policy = 'global_ng' if global_trial else 'bounded_ng'
    reason = ('Slow deep thermal mode with a severely bounded native Ng proposal; '
              'test a positive global extrapolation over six ordinary full solves'
              if global_trial else 'Slow full-solve tail with a rejected native Ng proposal; '
              'test one bounded affine step over six full solves')
    return Decision('action', reason,
        action=policy, evidence=baseline, reversible_trial=True,
        changes={'VADAT': {'COMP_F': 'T', 'COMP_BA': 'T', 'N_FIX_BA': '0', 'FIX_BA': '0.0'}},
        caches=('BAMAT', 'BAMATPNT', 'EDDFACTOR', 'EDDFACTOR_INFO'),
        steps=tuple(RecoveryStep(policy+suffix, 2,
                    lambda c, pair=pair: _validate(c, baseline, pair, global_trial=global_trial),
                    native_options={'global_ng_probe': True} if global_trial else {})
                    for pair, suffix in enumerate(('_settle1', '_settle2', '_check'), 1)))
