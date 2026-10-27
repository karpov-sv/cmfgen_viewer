"""Provisional performance trials; acceptance never substitutes for convergence."""
import math

from .auto_diagnostics import number, oscillating_region
from .auto_hydro import enabled, guard_measurements
from .runner_recipe import RunnerError


def _metrics(evidence):
    values = [[r.get(k) for k in ('solver_maximum_change', 'maximum_increase_percent',
                                'maximum_decrease_percent')] for r in evidence['records']]
    if not values or not all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0
                             for row in values for v in row):
        raise RunnerError('Performance trial needs finite uncapped correction measurements')
    return [max(row) for row in values]


def _counts_ok(current, previous):
    return (current['counts']['nd'] == previous['counts']['nd'] and
            current['counts']['nt'] == previous['counts']['nt'] and
            current['counts']['totals'].keys() == previous['counts']['totals'].keys() and
            all(v <= previous['counts']['totals'][k] for k, v in current['counts']['totals'].items()))


def _thermal_complete(evidence):
    rows = evidence.get('raw_temperature_steps', [])
    return len(rows) >= 2 and all(len(v) == evidence['counts']['nd'] and
        all(isinstance(x, (float, int)) and math.isfinite(x) for x in v) for v in rows)


def _baseline(ctx, *, reuse=False):
    from .auto_recovery import repaired_runtime
    batches = 2 if reuse else 3
    if (ctx.phase != 'iterate' or ctx.evidence.get('candidate') or len(ctx.history) < batches or
            ctx.remaining_iterations < 5 or ctx.remaining_attempts < 2):
        return None
    if not repaired_runtime(ctx.native_plan):
        return None
    history = ctx.history[-batches:]
    if any(e.get('hydro_revisions') or e.get('ng_accelerations') or len(e['records']) < 2 or
           e['full_iterations'] != e['iterations'] or not _thermal_complete(e) for e in history):
        return None
    if not all(_counts_ok(b, a) for a, b in zip(history, history[1:])):
        return None
    thermal = [v for e in history for v in e['raw_temperature_steps']]
    if oscillating_region({**ctx.evidence, 'raw_temperature_steps': thermal}, ctx.history, localized_only=False):
        return None
    try:
        metrics = [_metrics(e) for e in history]
    except ValueError:
        return None
    values = [m[-1] for m in metrics]
    if not ((reuse or all(max(m) <= 1 for m in metrics)) and
            all(a > b > 0 for a, b in zip(values, values[1:])) and
            values[-1] <= .8*values[0]):
        return None
    try:
        from .checkpoint_physics import checkpoint_physics, compare_physics
        physical = checkpoint_physics(ctx.model)
        compare_physics(physical, physical)
        guard = guard_measurements(ctx.model, ctx.before)
    except (ImportError, OSError, ValueError):
        return None  # Missing scientific evidence prevents tuning, not normal iteration.
    if guard['luminosity_min'] < .5 or guard['luminosity_max'] > 2:
        return None
    return dict(correction_metric=values[-1], counts=ctx.evidence['counts'],
                physical=physical, guard=guard,
                temperature_steps=thermal[-3:])


def _validate(ctx, baseline, *, reuse):
    from .auto_policies import TrialRejected
    e = ctx.evidence
    try:
        from .checkpoint_physics import checkpoint_physics, compare_physics
        if e['hydro_revisions'] or e.get('ng_accelerations') or e['full_iterations'] != e['iterations'] or len(e['records']) != 2:
            raise RunnerError('Trial needs exactly two full variable-temperature solves without grid/Ng revisions')
        if not _thermal_complete(e):
            raise RunnerError('Trial lacks complete temperature-request vectors')
        computed = [r.get('ba_computed') for r in e['records']]
        if computed != ([True, False] if reuse else [True, True]):
            raise RunnerError('Trial did not demonstrate the requested fresh/reused matrix schedule')
        metrics = _metrics(e)
        metric = metrics[-1]
        if (max(metrics) > baseline['correction_metric'] or metric >= baseline['correction_metric'] or
                not _counts_ok(e, {'counts': baseline['counts']})):
            raise RunnerError('Corrections or threshold counts worsened or failed to improve')
        thermal = {**e, 'raw_temperature_steps': [*baseline['temperature_steps'],
                                                *e.get('raw_temperature_steps', [])]}
        if oscillating_region(thermal, ctx.history, localized_only=False):
            raise RunnerError('Temperature cycling returned during the trial')
        guard = guard_measurements(ctx.model, ctx.before)
        old = baseline['guard']
        if (guard['luminosity_min'] < max(.5, old['luminosity_min']-.01) or
                guard['luminosity_max'] > min(2, old['luminosity_max']+.01)):
            raise RunnerError('Trial degraded the normalized luminosity profile')
        physics = compare_physics(baseline['physical'], checkpoint_physics(ctx.model))
    except (ImportError, OSError, ValueError) as exc:
        raise TrialRejected(str(exc)) from exc
    return {'performance_trial': dict(accepted=True, correction_metric=metric,
                                      matrix_schedule=computed, guard=guard, physical_checks=physics)}


def ba_reuse_trial(ctx):
    from .auto_policies import Decision, RecoveryStep
    if (any(a.get('policy_id') == 'ba_reuse_trial' for a in ctx.actions) or
            number(ctx.model, 'VADAT', 'N_FIX_BA', -1) != 0 or
            not enabled(ctx.model, 'COMP_BA') or not enabled(ctx.model, 'STORE_BA')):
        return None
    # Finish eligible automatic damping release with fresh BA before testing reuse.
    if _damping_release_settings(ctx) is not None:
        return None
    baseline = _baseline(ctx, reuse=True)
    if baseline is None:
        return None
    return Decision('action', 'Sustained healthy progress; provisionally reuse BA for one iteration',
        action='ba_reuse_trial', changes={'VADAT': {'N_FIX_BA': '1', 'FIX_BA': '0.0'}},
        evidence=baseline, reversible_trial=True,
        steps=(RecoveryStep('ba_reuse_check', 2, lambda c: _validate(c, baseline, reuse=True)),))


def _damping_release_settings(ctx):
    trials = [a for a in ctx.actions if a.get('policy_id') == 'relaxation_release']
    if (len(trials) >= 3 or any(a.get('trial_outcome') == 'rejected' for a in trials) or
            not any(a.get('kind') == 'relaxation' for a in ctx.actions)):
        return None
    current = number(ctx.model, 'ADJUST_CORRECTIONS', 'RELAX', 1)
    original = ctx.original_controls.get('ADJUST_CORRECTIONS', {}).get('RELAX', '1')
    from .parsers.common import parse_float_token
    ceiling = parse_float_token(original)
    if ceiling is None or not math.isfinite(ceiling) or not 0 < current < ceiling <= 1:
        return None
    # Release damping independently of matrix reuse, with fresh BA throughout.
    if number(ctx.model, 'VADAT', 'N_FIX_BA', -1) != 0 or number(ctx.model, 'VADAT', 'FIX_BA', -1) != 0:
        return None
    return current, ceiling


def relaxation_release(ctx):
    from .auto_policies import Decision, RecoveryStep
    settings = _damping_release_settings(ctx)
    if settings is None:
        return None
    current, ceiling = settings
    baseline = _baseline(ctx)
    if baseline is None:
        return None
    return Decision('action', 'Sustained healthy progress; provisionally reduce automatic correction damping',
        action='relaxation_release', changes={'ADJUST_CORRECTIONS': {'RELAX': str(min(ceiling, current*2))}},
        evidence=baseline, reversible_trial=True,
        steps=(RecoveryStep('relaxation_release_check', 2, lambda c: _validate(c, baseline, reuse=False)),))
