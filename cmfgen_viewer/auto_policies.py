"""Versioned diagnosis -> remedy registry for the unattended main-stage loop.

Rules inspect evidence and return declarative decisions. They never mutate
the workspace or launch processes. The controller owns locking, budgets,
rollback, execution and journals, including provisional multi-step remedies.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
import re
from typing import Callable

from .auto_diagnostics import control_value, number, oscillating_region, recovery_action
from .auto_hydro import bridge_evidence, enabled, guard_measurements, revisions
from .control_files import control_occurrences
from .model_initialization import lte_initialization_controls
from .pop_initialization import POP_MARKER, pop_source_evidence
from .runner_recipe import RunnerError

DEFAULT_MAX_ATTEMPTS = 100
DEFAULT_MAX_ITERATIONS = 500


@dataclass(frozen=True)
class RecoveryStep:
    name: str
    iterations: int
    validate: Callable
    native_options: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    kind: str  # continue, action, stop, converged
    reason: str
    policy_id: str = ''
    action: str = ''
    changes: dict = field(default_factory=dict)
    caches: tuple = ()
    steps: tuple = ()
    next_phase: str = 'iterate'
    evidence: dict = field(default_factory=dict)
    batch_iterations: int | None = None
    retain_failed_checkpoint: bool = False
    preserve_caches: bool = False

    def summary(self):
        return {'policy_id': self.policy_id, 'kind': self.kind, 'reason': self.reason,
                'action': self.action, 'changes': self.changes, 'caches': list(self.caches),
                'next_phase': self.next_phase, 'evidence': self.evidence,
                'batch_iterations': self.batch_iterations,
                'retain_failed_checkpoint': self.retain_failed_checkpoint,
                'preserve_caches': self.preserve_caches,
                'steps': [{'name': s.name, 'iterations': s.iterations,
                           'native_options': s.native_options} for s in self.steps]}


@dataclass(frozen=True)
class Context:
    model: object
    when: str
    native_plan: dict
    native_result: dict
    before: dict
    evidence: dict
    history: list
    phase: str
    actions: list
    log: str


@dataclass(frozen=True)
class Policy:
    id: str
    version: int
    when: str
    description: str
    evaluate: Callable
    max_applications: int | None = None


class Declined(Exception):
    """Recognized problem, but this remedy's prerequisites are not established."""


def _invalid_state(ctx):
    findings = [finding for step in ctx.native_result.get('passes', [])
                for finding in step.get('diagnostic_findings', [])
                if finding.get('code') in {'nonfinite_model_state', 'invalid_checkpoint'}]
    if findings:
        return Decision('stop', '; '.join(f['title'] + ': ' + f['message'] for f in findings),
                        evidence={'diagnostic_findings': findings})


def _pop_bootstrap_check(ctx):
    text = '\n'.join([ctx.log, *(p.get('diagnostic_tail', '') for p in ctx.native_result.get('passes', []))])
    if ((ctx.native_plan.get('initialization') or {}).get('method') != 'POP' or
            (ctx.native_result.get('initialization') or {}).get('method') != 'POP' or
            POP_MARKER not in text):
        raise RunnerError('POP recovery did not confirm native population interpolation and charge conservation')
    return {'pop_bootstrap_completed': True}


def _pop_continuation_check(ctx):
    if (ctx.native_plan.get('initialization') or
            ctx.native_plan['restart']['mode'] != 'continuation' or
            ctx.native_result.get('startup_observed', {}).get('mode') != 'continuation'):
        raise RunnerError('POP recovery did not verify continuation with normal initialization controls')
    return {'pop_recovery_verified': True}


def _pop(ctx):
    findings = [f for p in ctx.native_result.get('passes', [])
                for f in p.get('diagnostic_findings', []) if f.get('severity') == 'error']
    if (not any(f['code'] == 'initial_population_scaling' for f in findings) or
            control_value(ctx.model, 'VADAT', 'LIN_INT', '').upper().strip('.') not in {'T', 'TRUE'}):
        return None
    if {f['code'] for f in findings} != {'initial_population_scaling'}:
        raise Declined('Population initialization failure is accompanied by another diagnosed error')
    if ctx.native_plan['restart']['mode'] != 'fresh':
        raise Declined('POP recovery applies only to fresh startup; preserving the continuation checkpoint')
    texts = [ctx.log, *(p.get('diagnostic_tail', '') for p in ctx.native_result.get('passes', []))]
    if any(re.search(r'Current great iteration count is\s+\d+', text, re.I) for text in texts):
        raise Declined('Iteration already began; POP reseeding is not a continuation remedy')
    method = control_value(ctx.model, 'VADAT', 'DC_METH', '').upper()
    if ctx.native_plan.get('initialization') or ctx.native_result.get('initialization') or method == 'POP':
        raise Declined('Explicit initialization was already in use; another POP retry is unsupported')
    if method not in {'R', 'TR', 'ED', 'SPH_TAU'}:
        raise Declined('POP recovery requires an explicit legacy departure-coefficient interpolation method')
    try:
        evidence = pop_source_evidence(ctx.model, ctx.native_plan)
    except (OSError, ValueError) as exc:
        raise Declined(str(exc)) from exc
    return Decision('action', 'Confirmed fresh-start population failure with interpolation enabled; '
                    'try temporary DC_METH=POP and verify normal continuation',
                    action='pop_initialization', evidence=evidence,
                    steps=(RecoveryStep('pop_initialization', 2, _pop_bootstrap_check,
                                        {'pop_initialization': True}),
                           RecoveryStep('pop_continuation', 2, _pop_continuation_check)))


def _lte_bootstrap_check(ctx):
    if ((ctx.native_plan.get('initialization') or {}).get('method') != 'LTE' or
            (ctx.native_result.get('initialization') or {}).get('method') != 'LTE'):
        raise RunnerError('LTE recovery did not install the temporary initialization controls')
    return {'lte_bootstrap_completed': True,
            'lte_t_exc': ctx.native_plan['initialization']['t_exc']}


def _lte_continuation_check(ctx):
    if (ctx.native_plan.get('initialization') or
            ctx.native_plan['restart']['mode'] != 'continuation' or
            ctx.native_result.get('startup_observed', {}).get('mode') != 'continuation'):
        raise RunnerError('LTE recovery did not verify continuation with normal initialization controls')
    return {'lte_recovery_verified': True}


def _lte(ctx):
    # Interpolating source models belong to the POP rule; do not recommend
    # disabling interpolation as an alternative LTE recovery.
    if control_value(ctx.model, 'VADAT', 'LIN_INT', '').upper().strip('.') in {'T', 'TRUE'}:
        return None
    findings = [f for p in ctx.native_result.get('passes', [])
                for f in p.get('diagnostic_findings', []) if f.get('severity') == 'error']
    if not any(f['code'] == 'initial_population_scaling' for f in findings):
        return None
    if {f['code'] for f in findings} != {'initial_population_scaling'}:
        raise Declined('Population initialization failure is accompanied by another diagnosed error')
    if ctx.native_plan['restart']['mode'] != 'fresh':
        raise Declined('LTE recovery applies only to fresh startup; preserving the continuation checkpoint')
    texts = [ctx.log, *(p.get('diagnostic_tail', '') for p in ctx.native_result.get('passes', []))]
    if any(re.search(r'Current great iteration count is\s+\d+', text, re.I) for text in texts):
        raise Declined('Iteration already began; LTE reseeding is not a continuation remedy')
    if (ctx.native_plan.get('initialization') or ctx.native_result.get('initialization') or
            control_value(ctx.model, 'VADAT', 'DC_METH', '').upper() == 'LTE'):
        raise Declined('LTE initialization was already in use; another LTE retry is unsupported')
    if control_value(ctx.model, 'VADAT', 'LIN_INT', '').upper().strip('.') not in {'F', 'FALSE'}:
        raise Declined('Automatic LTE recovery requires explicit LIN_INT=F; interpolation controls are preserved')
    t_exc = number(ctx.model, 'VADAT', 'T_EXC', 1.0)
    try:
        lte_initialization_controls((ctx.model/'VADAT').read_text(), t_exc)
    except (OSError, ValueError) as exc:
        raise Declined(str(exc)) from exc
    return Decision('action', 'Confirmed fresh-start population failure before iteration; '
                    'retry with temporary LTE estimates and verify normal continuation',
                    action='lte_initialization', evidence={'t_exc': t_exc, 't_exc_units': '10000 K',
                        'diagnoses': list(dict.fromkeys(f['evidence'] for f in findings))},
                    steps=(RecoveryStep('lte_initialization', 2, _lte_bootstrap_check,
                                        {'lte_initialization': True, 't_exc': t_exc}),
                           RecoveryStep('lte_continuation', 2, _lte_continuation_check)))


def _hydro_bridge_check(ctx):
    if len(revisions(ctx.log)) != 1:
        raise RunnerError('Hydro bridge did not complete exactly one scheduled revision')
    return {'hydro_bridge_completed': True}


def _hydro_guarded_check(ctx):
    measured = guard_measurements(ctx.model, ctx.before)
    if not enabled(ctx.model, 'STOP_IF_MW', 'T') or not (
            0.5 <= measured['luminosity_min'] <= measured['luminosity_max'] <= 2):
        raise RunnerError('Guarded follow-up failed the luminosity checks')
    return {'guarded_measurements': measured, 'hydro_recovery_verified': True}


def _hydro(ctx):
    codes = {f['code'] for p in ctx.native_result.get('passes', [])
             for f in p.get('diagnostic_findings', []) if f.get('severity') == 'error'}
    if 'inner_flux_accuracy' not in codes:
        return None
    try:
        evidence = bridge_evidence(ctx.model, ctx.native_plan, ctx.native_result, ctx.before)
    except (OSError, ValueError) as exc:
        raise Declined(str(exc)) from exc
    return Decision('action', 'One scheduled hydro iteration with temporary STOP_IF_MW=F; '
                    'restore guard on every exit and require a guarded follow-up',
                    action='hydro_bootstrap', evidence=evidence,
                    steps=(RecoveryStep('hydro_bridge', 1, _hydro_bridge_check,
                                        {'hydro_recovery_probe': True}),
                           RecoveryStep('hydro_guarded', 2, _hydro_guarded_check)))


def _cache(ctx):
    if recovery_action(ctx.native_result) == 'radiation_cache':
        return Decision('action', 'Native explicitly reported incorrect reading of EDDFACTOR; '
                        'retry once from the restored checkpoint', action='radiation_cache',
                        caches=('EDDFACTOR', 'EDDFACTOR_INFO'))


def _nonfinite_cache(ctx):
    # An unknown layout or a generic native crash is never evidence of a
    # corrupt cache. Inspect only when reuse was explicitly requested.
    if control_value(ctx.model, 'VADAT', 'COMP_F', '').upper().strip('.') not in {'F', 'FALSE'}:
        return
    from .radiation_cache import inspect_radiation_cache
    evidence = inspect_radiation_cache(ctx.model)
    if evidence['status'] != 'nonfinite':
        return
    if enabled(ctx.model, 'USE_FIXED_J'):
        return Decision('stop', 'Nonfinite EDDFACTOR cannot be regenerated with USE_FIXED_J=T',
                        evidence=evidence)
    return Decision('action', 'Recognized EDDFACTOR contains nonfinite radiation data; '
                    'preserve it and regenerate radiation before native execution',
                    action='nonfinite_radiation_cache', changes={'VADAT': {'COMP_F': 'T'}},
                    caches=('EDDFACTOR', 'EDDFACTOR_INFO'), preserve_caches=True,
                    evidence=evidence)


def _verified(ctx):
    if ctx.phase == 'verify' and ctx.evidence['fresh_verified']:
        return Decision('converged', 'Verified with fresh Jacobians')


def _candidate(ctx):
    if ctx.evidence['candidate']:
        final = ctx.evidence.get('records', [])[-2:]
        if ctx.phase == 'advisory' and len(final) == 2 and all(r.get('ba_computed') for r in final):
            # Saved outputs can establish fresh final solves without proving
            # an independent invocation. Retain that provenance limitation,
            # but do not ask the user to repeat those same fresh solves.
            return None
        return _matrix('Two full steps meet the raw and native correction tolerance; '
                       'independently verify with fresh BA', next_phase='verify')


def _matrix(reason, next_phase='iterate'):
    return Decision('action', reason, action='fresh_jacobian', next_phase=next_phase,
                    changes={'VADAT': {'COMP_BA': 'T', 'N_FIX_BA': '0', 'FIX_BA': '0.0'}},
                    caches=('BAMAT', 'BAMATPNT'))


def relaxation_changes(model, evidence, history):
    region = oscillating_region(evidence, history)
    if region is None:
        return None
    if control_value(model, 'VADAT', 'SCALE_OPT', '').upper() != 'MAJOR':
        raise RunnerError('Measured oscillation requires review: automatic relaxation supports SCALE_OPT=MAJOR only')
    adjustment = model/'ADJUST_CORRECTIONS'
    keys = control_occurrences(adjustment.read_text()) if adjustment.exists() else {}
    if set(keys) - {'L_ST', 'L_END', 'RELAX', 'T_LIM'}:
        raise RunnerError('Existing ADJUST_CORRECTIONS contains other scoped controls; review before changing its depth range')
    old = number(model, 'ADJUST_CORRECTIONS', 'RELAX', 1.0)
    start = int(number(model, 'ADJUST_CORRECTIONS', 'L_ST', region[0]))
    end = int(number(model, 'ADJUST_CORRECTIONS', 'L_END', region[1]))
    start, end = min(start, region[0]), max(end, region[1])
    if not 1 <= start <= end <= evidence['counts']['nd']:
        raise RunnerError('Existing correction depth range is outside the model grid')
    if end-start+1 > max(1, evidence['counts']['nd']//3):
        raise RunnerError('Oscillation spans too much of the grid for automatic local relaxation')
    if old <= 0 or old > 1:
        raise RunnerError('Existing RELAX is outside the supported automatic under-relaxation range')
    if old <= 0.125:
        raise RunnerError('Persistent cycle at the minimum automatic RELAX; review physics/grid/linearization')
    value = 0.25 if old > 0.25 else 0.125
    return {'ADJUST_CORRECTIONS': {'L_ST': str(start), 'L_END': str(end),
                                  'RELAX': str(value), 'T_LIM': '0.2'}}


def _oscillation(ctx):
    if ctx.evidence.get('hydro_revisions'):
        return None  # This batch can contain temperature vectors on different grids.
    changes = relaxation_changes(ctx.model, ctx.evidence, ctx.history)
    if changes:
        return Decision('action', 'Persistent localized sign-alternating temperature requests; '
                        'restore the pre-relaxation cap so RELAX can act',
                        action='relaxation', changes=changes)


def _stall(ctx):
    if len(ctx.history) < 3:
        return None
    window = ctx.history[-3:]
    if any(h.get('hydro_revisions') for h in window):
        return None
    grids = [(h.get('counts', {}).get('nt'), h.get('counts', {}).get('nd')) for h in window]
    if any(None in grid for grid in grids) or len(set(grids)) != 1:
        return None
    records = [next((r for r in reversed(h['records'])
                     if not r.get('lambda_iteration') and not r.get('temperature_fixed')), {})
               for h in window]

    def valid(values):
        return all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0 for v in values)

    recent = [r.get('solver_maximum_change') for r in records]
    if not valid(recent):
        return None
    saturated = any(v >= 1.0e7 for v in recent)
    trends = {'solver_maximum_change': recent}
    if saturated:
        # SOLVEBA caps a requested decrease >=99.999% at 1e7. Equal caps
        # cannot demonstrate a plateau; use the uncapped printed extrema.
        trends = {key: [r.get(key) for r in records]
                  for key in ('maximum_increase_percent', 'maximum_decrease_percent')}
        if not all(valid(values) for values in trends.values()):
            return None
        thermal = [h.get('raw_temperature_steps', []) for h in window]
        if all(vectors and len(vectors[-1]) == h['counts']['nd'] and
               all(isinstance(v, (int, float)) and math.isfinite(v) for v in vectors[-1])
               for h, vectors in zip(window, thermal)):
            trends['raw_temperature_maximum_percent'] = [max(abs(v) for v in vectors[-1])
                                                         for vectors in thermal]
        # Counts describe the final solve, which may be a lambda step. Only
        # compare them when those final solves have the same iteration mode.
        modes = {(h['records'][-1].get('lambda_iteration', False),
                  h['records'][-1].get('temperature_fixed', False)) for h in window}
        if len(modes) == 1:
            totals = [h['counts']['totals'] for h in window]
            for label in sorted(set.intersection(*(set(t) for t in totals))):
                values = [t[label] for t in totals]
                if float(label.removesuffix('%')) >= ctx.evidence['epsilon_percent'] and valid(values):
                    trends['count_above_' + label] = values
    # Slow but consistent decay is progress, even when less than 10% per
    # batch. Do not interrupt it merely because convergence needs patience.
    improving = [key for key, values in trends.items()
                 if all(b < a for a, b in zip(values, values[1:])) or
                 min(values[1:]) < 0.98 * values[0]]
    evidence = {'saturated_solver_metric': saturated,
                'solver_maximum_changes': recent, 'correction_trends': trends,
                'improving_diagnostics': improving}
    if improving:
        if saturated:
            return Decision('continue', 'Uncapped correction diagnostics show progress despite a saturated solver metric',
                            evidence=evidence)
        return None
    if number(ctx.model, 'VADAT', 'N_FIX_BA', 0) != 0 or number(ctx.model, 'VADAT', 'FIX_BA', 0) != 0:
        return replace(_matrix('Corrections stalled; check the matrix before considering further changes'),
                       evidence=evidence)
    return Decision('stop', 'Corrections stalled despite fresh matrices; no supported automatic adjustment',
                    evidence=evidence)


def _fixed(ctx):
    if len(ctx.history) >= 3 and all(h['full_iterations'] == 0 for h in ctx.history[-3:]):
        return Decision('stop', 'No variable-temperature full steps in three batches')


# Order is explicit. Add a tested Policy here; the controller needs no new
# diagnosis branches. Version changes make saved previews require review again.
from .auto_recovery import (temperature_coupling, population_bootstrap, population_guard,
                            ray_refinement, ng_cadence)

POLICIES = (
    Policy('nonfinite_radiation_cache', 1, 'prepare', 'Preserve nonfinite EDDFACTOR and recompute radiation before execution', _nonfinite_cache, 1),
    Policy('invalid_numerical_state', 1, 'failure', 'Reject nonfinite model states and invalid selected checkpoints', _invalid_state),
    Policy('pop_initialization', 1, 'failure', 'Compatible saved-model population interpolation and verified continuation', _pop, 1),
    Policy('lte_initialization', 2, 'failure', 'Confirmed fresh-start population failure: temporary LTE and verified continuation', _lte, 1),
    Policy('hydro_bootstrap', 1, 'failure', 'Scheduled hydro recovery with guard restoration and follow-up', _hydro, 1),
    Policy('radiation_cache', 1, 'failure', 'Explicit EDDFACTOR mismatch recovery', _cache, 1),
    Policy('population_guard', 1, 'failure', 'Physically audited provisional checkpoint after explicit MAX_CHNG stop', population_guard, 1),
    Policy('ray_refinement', 1, 'failure', 'Negative-luminosity coarse-ray recovery with guarded verification', ray_refinement, 1),
    Policy('verified_convergence', 1, 'success', 'Independent fresh-Jacobian convergence acceptance', _verified),
    Policy('verify_candidate', 2, 'success', 'Fresh-Jacobian verification of a numerical candidate', _candidate),
    Policy('superlevel_temperature', 1, 'success', 'Superlevel temperature coupling before oscillation damping', temperature_coupling, 1),
    Policy('population_bootstrap', 1, 'success', 'Bounded fixed-T Lambda population recovery and full verification', population_bootstrap, 1),
    Policy('ng_cadence', 1, 'success', 'Contiguous batches permitting the first native Ng acceleration', ng_cadence, 1),
    Policy('local_relaxation', 2, 'success', 'Measured localized temperature oscillation damping', _oscillation, 2),
    Policy('stalled_corrections', 2, 'success', 'Fresh-matrix test for a stalled correction sequence', _stall, 1),
    Policy('fixed_temperature', 1, 'success', 'Detect absence of temperature-varying full steps', _fixed),
)


def manifest():
    if len({p.id for p in POLICIES}) != len(POLICIES):
        raise RunnerError('Duplicate automatic policy identifiers')
    if any(p.when not in {'prepare', 'failure', 'success'} or p.version < 1 or
           (p.max_applications is not None and p.max_applications < 1) for p in POLICIES):
        raise RunnerError('Invalid automatic policy declaration')
    return [{'id': p.id, 'version': p.version, 'when': p.when, 'description': p.description,
             'max_applications': p.max_applications} for p in POLICIES]


def choose(ctx):
    """Return one decision and the ordered diagnosis/refusal trail."""
    trail = []
    for policy in POLICIES:
        if policy.when != ctx.when:
            continue
        try:
            decision = policy.evaluate(ctx)
        except Declined as exc:
            trail.append({'policy_id': policy.id, 'outcome': 'ineligible', 'reason': str(exc)})
            continue
        except (OSError, ValueError) as exc:
            decision = Decision('stop', str(exc))
        if decision is None:
            trail.append({'policy_id': policy.id, 'outcome': 'not_matched'})
            continue
        if (decision.kind not in {'continue', 'action', 'stop', 'converged'} or
                (ctx.when == 'prepare' and (decision.kind == 'converged' or decision.steps or
                                            decision.batch_iterations is not None or decision.retain_failed_checkpoint)) or
                decision.next_phase not in {'iterate', 'verify'} or
                (decision.steps and decision.kind != 'action') or
                (decision.retain_failed_checkpoint and (not decision.steps or policy.id != 'population_guard')) or
                (decision.batch_iterations is not None and
                 (decision.kind != 'action' or type(decision.batch_iterations) is not int or
                  not 2 <= decision.batch_iterations <= 20)) or
                any(type(s.iterations) is not int or s.iterations < 1 or not callable(s.validate)
                    for s in decision.steps)):
            raise RunnerError(f'Invalid automatic decision from {policy.id}')
        used = sum(a.get('policy_id') == policy.id for a in ctx.actions)
        if decision.kind == 'action' and policy.max_applications is not None and used >= policy.max_applications:
            decision = Decision('stop', f'Automatic remedy {policy.id} exhausted its {policy.max_applications} application(s)')
        decision = replace(decision, policy_id=policy.id)
        trail.append({'policy_id': policy.id, 'outcome': decision.kind, 'reason': decision.reason})
        return decision, trail
    if ctx.when == 'prepare':
        return Decision('continue', 'Native preparation checks completed', policy_id='prepared'), trail
    if ctx.when == 'success':
        return Decision('continue', 'Continue from the accepted checkpoint', policy_id='continue'), trail
    titles = list(dict.fromkeys(f['title'] for p in ctx.native_result.get('passes', [])
                               for f in p.get('diagnostic_findings', []) if f.get('severity') == 'error'))
    reason = '; '.join(titles) or ctx.native_result.get('error') or 'Unrecognized native failure'
    refused = [t['reason'] for t in trail if t['outcome'] == 'ineligible']
    if refused:
        reason += '; no applicable remedy: ' + '; '.join(refused)
    return Decision('stop', reason, policy_id='unhandled'), trail
