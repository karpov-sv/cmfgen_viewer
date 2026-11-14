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


def _counts_ok(current, previous, *, significant=False):
    epsilon = current.get('epsilon_percent') if significant else 0
    if not isinstance(epsilon, (int, float)) or not math.isfinite(epsilon) or epsilon < 0 or (significant and epsilon == 0):
        return False
    return (current['counts']['nd'] == previous['counts']['nd'] and
            current['counts']['nt'] == previous['counts']['nt'] and
            current['counts']['totals'].keys() == previous['counts']['totals'].keys() and
            all(v <= previous['counts']['totals'][k] for k, v in current['counts']['totals'].items()
                if float(k.removesuffix('%')) >= epsilon))


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
    if reuse and not _counts_ok(ctx.evidence, ctx.evidence, significant=True):
        return None
    history = ctx.history[-batches:]
    if any(e.get('hydro_revisions') or e.get('ng_accelerations') or len(e['records']) < 2 or
           e['full_iterations'] != e['iterations'] or not _thermal_complete(e) for e in history):
        return None
    counts_improving = all(_counts_ok(b, a, significant=reuse)
                           for a, b in zip(history, history[1:]))
    thermal = [v for e in history for v in e['raw_temperature_steps']]
    if oscillating_region({**ctx.evidence, 'raw_temperature_steps': thermal}, ctx.history, localized_only=False):
        return None
    try:
        metrics = [_metrics(e) for e in history]
    except ValueError:
        return None
    values = [m[-1] for m in metrics]
    improving = (counts_improving and (reuse or all(max(m) <= 1 for m in metrics)) and
            all(a > b > 0 for a, b in zip(values, values[1:])) and
            values[-1] <= .8*values[0])
    slow = False
    if reuse and not improving:
        # The deep thermal tail can be healthy while relative corrections of
        # trace ions barely move. Test computational savings separately from
        # extrapolation; require six ordinary observations of this regime.
        from .auto_ng import _full, _slow_thermal_tail
        from .auto_hydro import structure_fixed
        history = ctx.history[-3:]
        rows = [r for e in history for r in e['records']][-6:]
        try:
            flat_metrics = _metrics({'records': rows})
        except ValueError:
            return None
        counters = [r.get('global_iteration') for r in rows]
        complete_thermal = [v for e in history for v in e.get('raw_temperature_steps', [])][-6:]
        slow = (all(_full(e) for e in history) and structure_fixed(ctx.model) and
                all(a['counts']['nd'] == b['counts']['nd'] and
                    a['counts']['nt'] == b['counts']['nt'] and
                    a['counts']['totals'].keys() == b['counts']['totals'].keys()
                    for a, b in zip(history, history[1:])) and
                len(rows) == 6 and all(.1 <= v <= 10 for v in flat_metrics) and
                all(type(i) is int for i in counters) and
                counters == list(range(counters[0], counters[0]+6)) and
                counters[-1] == ctx.evidence.get('checkpoint') and
                not oscillating_region({**ctx.evidence, 'raw_temperature_steps': complete_thermal},
                                       ctx.history, localized_only=False) and
                .9 <= flat_metrics[-1]/flat_metrics[0] <= 1.01 and
                max(flat_metrics)/min(flat_metrics) <= 1.1 and _slow_thermal_tail(rows))
    if not (improving or slow):
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
    result = dict(correction_metric=values[-1], counts=ctx.evidence['counts'],
                epsilon_percent=ctx.evidence.get('epsilon_percent'),
                physical=physical, guard=guard,
                temperature_steps=thermal[-3:])
    if slow:
        from .auto_ng import _energy
        deviation = max(abs(guard['luminosity_min']-1), abs(guard['luminosity_max']-1))
        if guard.get('inner_tau_ross', 0) < 50 or deviation < .02:
            return None
        try:
            energy = _energy(ctx.model, ctx.evidence['counts']['nd'])
        except (OSError, ValueError):
            return None
        if energy <= 0:
            return None
        result.update(slow_thermal_tail=True, energy=energy,
                      checkpoint=ctx.evidence['checkpoint'],
                      correction_limit=1.05*values[-1])
    return result


def _validate(ctx, baseline, *, reuse):
    from .auto_policies import TrialRejected
    e = ctx.evidence
    try:
        from .checkpoint_physics import checkpoint_physics, compare_physics
        if (e['hydro_revisions'] or e.get('ng_accelerations') or e.get('checkpoint_updates') or
                e.get('source_changed') or e['full_iterations'] != e['iterations'] or len(e['records']) != 2):
            raise RunnerError('Trial needs exactly two full variable-temperature solves without grid/Ng revisions')
        if not _thermal_complete(e):
            raise RunnerError('Trial lacks complete temperature-request vectors')
        computed = [r.get('ba_computed') for r in e['records']]
        if computed != ([True, False] if reuse else [True, True]):
            raise RunnerError('Trial did not demonstrate the requested fresh/reused matrix schedule')
        metrics = _metrics(e)
        metric = metrics[-1]
        slow = reuse and baseline.get('slow_thermal_tail', False)
        if slow and (any(r.get('temperature_fixed') or r.get('lambda_iteration') or
                         r.get('major_species_minimum_scale') != 1 for r in e['records']) or
                     [r.get('global_iteration') for r in e['records']] !=
                     [baseline['checkpoint']+1, baseline['checkpoint']+2] or
                     e.get('checkpoint') != baseline['checkpoint']+2):
            raise RunnerError('Slow-tail BA reuse needs consecutive ordinary free-T solves')
        limit = baseline['correction_limit'] if slow else baseline['correction_metric']
        if (max(metrics) > limit or (not slow and metric >= baseline['correction_metric']) or
                (slow and metric > metrics[0]) or
                not _counts_ok(e, {'counts': baseline['counts']}, significant=reuse)):
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
        if slow:
            from .auto_ng import _energy
            old_deviation = max(abs(old['luminosity_min']-1), abs(old['luminosity_max']-1))
            deviation = max(abs(guard['luminosity_min']-1), abs(guard['luminosity_max']-1))
            if (_energy(ctx.model, e['counts']['nd']) > .999*baseline['energy'] or
                    deviation > .999*old_deviation):
                raise RunnerError('BA reuse did not retain thermal progress in the slow tail')
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
    reason = ('Healthy deep thermal tail; provisionally reuse BA for one iteration'
              if baseline.get('slow_thermal_tail') else
              'Sustained healthy progress; provisionally reuse BA for one iteration')
    return Decision('action', reason,
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
