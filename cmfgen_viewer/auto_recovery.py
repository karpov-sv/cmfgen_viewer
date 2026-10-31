"""Evidence-driven numerical remedies established by the Bstar3502 investigation."""
import math
from pathlib import Path
import re

from .auto_diagnostics import control_value, number, oscillating_region
from .auto_hydro import enabled, structure_fixed
from .parsers.common import parse_float_token
from .runner_recipe import RunnerError, snapshot

from .native_version import MINIMUM_PATCH_REVISION, supports_revision


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def repaired_runtime(plan, *, minimum=MINIMUM_PATCH_REVISION):
    """Require the dated revision reported by the selected native executable."""
    return supports_revision(plan, minimum=minimum)


def temperature_coupling(ctx):
    from .auto_policies import Decision
    value = control_value(ctx.model, 'VADAT', 'INCL_dSLdT', 'F', exact_key=True)
    if (ctx.evidence.get('hydro_revisions') or value.upper().strip('.') in {'T', 'TRUE'} or
            not oscillating_region(ctx.evidence, ctx.history)):
        return None
    return Decision('action', 'Persistent temperature cycle with superlevel temperature derivatives disabled; '
                    'enable INCL_dSLdT and recompute BA before considering damping',
                    action='superlevel_temperature',
                    changes={'VADAT': {'INCL_DSLDT': 'T', 'COMP_BA': 'T', 'N_FIX_BA': '0', 'FIX_BA': '0.0'}},
                    caches=('BAMAT', 'BAMATPNT'),
                    evidence={'oscillating_depths': oscillating_region(ctx.evidence, ctx.history)})


def _luminosity(model):
    path = model/'OBSFLUX'
    if not path.is_file() or path.stat().st_size > 32*1024**2:
        raise RunnerError('Missing or oversized OBSFLUX for ray refinement')
    text = path.read_text()
    headers = list(re.finditer(r'^\s*Normalized luminosity check \(normalized by L\[ND\]\)[^\n]*\n', text, re.M))
    if not headers:
        raise RunnerError('No normalized luminosity profile for ray refinement')
    values = []
    for line in text[headers[-1].end():].splitlines():
        if not line.strip() and not values:
            continue
        row = [parse_float_token(t) for t in line.split()]
        if not row or any(v is None for v in row):
            break
        values.extend(row)
    nd = number(model, 'MODEL_SPEC', 'ND')
    if len(values) != nd or any(not math.isfinite(v) for v in values):
        raise RunnerError('Incomplete luminosity profile for ray refinement')
    return values


def ray_refinement(ctx):
    from .auto_policies import Decision, Declined, RecoveryStep
    codes = {f.get('code') for p in ctx.native_result.get('passes', [])
             for f in p.get('diagnostic_findings', []) if f.get('severity') == 'error'}
    if 'inner_flux_accuracy' not in codes:
        return None
    if ctx.native_plan.get('restart', {}).get('mode') != 'continuation':
        return None
    if not structure_fixed(ctx.model):
        raise Declined('Ray refinement requires a fixed structure; scheduled hydro recovery is assessed separately')
    path = ctx.model/'OBSFLUX'
    if snapshot(path) == ctx.before.get('OBSFLUX'):
        raise Declined('Ray refinement requires a refreshed luminosity profile')
    values = _luminosity(ctx.model)
    if min(values) >= 0:
        return None  # An ordinary luminosity mismatch is not this demonstrated transport collapse.
    fg = number(ctx.model, 'VADAT', 'VFRAC_FG', 20000)
    mom = number(ctx.model, 'VADAT', 'VFRAC_MOM', 20000)
    if fg <= .1:
        raise Declined('Negative luminosities persist with VFRAC_FG<=0.1; no finer-ray remedy established')
    family_grid = any(enabled(ctx.model, key) for key in ('USE_J_REL', 'USE_DJDT_RTE', 'INC_GRID'))
    capability = 'CMFGEN viewer patch revision '+MINIMUM_PATCH_REVISION
    if (family_grid or mom != 20000) and not repaired_runtime(
            ctx.native_plan):
        raise Declined('Inserted moment grids and alternate solver families require a supported '
                       + capability + ' repair')
    return Decision('action', 'Negative normalized luminosities with coarse formal rays; refine VFRAC_FG to0.1 '
                    'on the existing moment grid and require guarded full continuation',
                    action='ray_refinement', changes={'VADAT': {'VFRAC_FG': '0.1', 'COMP_BA': 'T',
                                                             'N_FIX_BA': '0', 'FIX_BA': '0.0'}},
                    caches=('EDDFACTOR', 'EDDFACTOR_INFO', 'BAMAT', 'BAMATPNT'),
                    steps=(RecoveryStep('refined_ray_check', 2, _ray_check),),
                    evidence={'old_VFRAC_FG': fg, 'VFRAC_MOM': mom, 'luminosity_min': min(values)})


def _ray_check(ctx):
    from .auto_hydro import guard_measurements
    data = guard_measurements(ctx.model, ctx.before)
    if data['luminosity_min'] < .5 or data['luminosity_max'] > 2:
        raise RunnerError('Refined-ray continuation still fails guarded luminosity agreement')
    records = ctx.evidence['records']
    if len(records) < 2 or not all(r.get('ba_computed') for r in records):
        raise RunnerError('Refined-ray check needs two completed fresh-BA solves')
    # A repaired radiation field can expose extreme tiny-population seeds.
    # Native fixed-T/Lambda steps are valid here; the separate bootstrap and
    # final full-temperature verification policies handle those populations.
    return {'refined_ray_guarded_check': data}


def _full_check(ctx):
    records = ctx.evidence['records']
    if (len(records) < 2 or not all(not r.get('lambda_iteration') and not r.get('temperature_fixed')
                                  and r.get('ba_computed') for r in records[-2:])):
        raise RunnerError('Recovery needs two completed full variable-temperature solves with fresh BA')
    return {'full_fresh_recovery_verified': True}


def _bootstrap_check(ctx):
    records = ctx.evidence['records']
    # Native convergence may shorten a three-solve request to two solves:
    # the converged solve plus its final-output loop. Do not treat arbitrary
    # partial output as early convergence, or weaken the later full check.
    eps = ctx.evidence['epsilon_percent']
    early = len(records) == 2 and all(
        _finite(r.get(key)) and 0 <= r[key] < eps
        for r in records for key in ('solver_maximum_change',
                                    'maximum_increase_percent', 'maximum_decrease_percent'))
    if ((len(records) != 3 and not early) or ctx.evidence.get('ng_accelerations') or
            not all(r.get('lambda_iteration') and r.get('temperature_fixed') and r.get('ba_computed')
                    for r in records)):
        raise RunnerError('Population bootstrap needs three fixed-T Lambda solves with fresh BA, or two below EPS_TERM')
    extrema = [(r.get('maximum_increase_percent'), r.get('maximum_decrease_percent')) for r in records]
    if not all(_finite(v) and v >= 0 for pair in extrema for v in pair):
        raise RunnerError('Population bootstrap has incomplete uncapped correction extrema')
    values = [max(pair) for pair in extrema]
    if not all(math.isfinite(v) and v >= 0 for v in values) or (not early and values[-1] >= values[0]):
        raise RunnerError('Population bootstrap did not reduce uncapped population corrections')
    return {'population_bootstrap_extrema_percent': values,
            'population_bootstrap_early_completion': early,
            'checkpoint_physics': _population_physics_check(ctx, fixed_temperature=True)}


def _population_physics_check(ctx, *, fixed_temperature=False):
    from .checkpoint_physics import checkpoint_physics, compare_physics
    return compare_physics(ctx.before['checkpoint_physics'], checkpoint_physics(ctx.model),
                           fixed_temperature=fixed_temperature)


def _population_full_check(ctx):
    from .auto_policies import VerificationPending
    physics = _population_physics_check(ctx)
    records = ctx.evidence['records']
    if len(records) < 2 or not all(r.get('ba_computed') for r in records):
        raise RunnerError('Population verification needs two completed fresh-BA solves')
    if any(r.get('lambda_iteration') or r.get('temperature_fixed') for r in records[-2:]):
        full = sum(not r.get('lambda_iteration') and not r.get('temperature_fixed')
                   for r in records)
        raise VerificationPending(
            'Native Lambda/fixed-temperature fallback; continue verification until two consecutive '
            'full variable-temperature fresh-BA solves complete',
            {'checkpoint_physics': physics, 'verification_full_steps': full})
    return {**_full_check(ctx), 'checkpoint_physics': physics}


def population_bootstrap(ctx):
    from .auto_policies import Decision, Declined, RecoveryStep
    full = ctx.evidence.get('records', [])
    def increased(r, limit):
        value = r.get('maximum_increase_percent')
        return r.get('ba_computed') and _finite(value) and value >= limit
    extreme = (len(full) >= 2 and all(increased(r, 1e7)
                                     for r in full[-2:]))
    extreme = extreme or (full and increased(full[-1], 1e12))
    if ctx.evidence.get('hydro_revisions') or not extreme:
        return None
    if ctx.native_plan.get('restart', {}).get('mode') != 'continuation':
        return None
    if not structure_fixed(ctx.model):
        raise Declined('Population bootstrap is validated only on a fixed structure')
    if control_value(ctx.model, 'VADAT', 'SCALE_OPT', '').upper() != 'MAJOR':
        raise Declined('Population bootstrap is validated with SCALE_OPT=MAJOR')
    if not repaired_runtime(ctx.native_plan):
        raise Declined('Extreme-population bootstrap requires a supported build with repaired line Jacobians and BA restart')
    from .checkpoint_physics import checkpoint_physics
    try:
        checkpoint_physics(ctx.model)
    except (OSError, ValueError) as exc:
        raise Declined(str(exc)) from exc
    return Decision('action', 'Extreme population increases persist through fresh full solves; '
                    'fill tiny seeds with up to three fixed-T Lambda solves at MAX_LAM=1e12, '
                    'restore normal controls, and verify full continuation',
                    action='population_bootstrap',
                    changes={'VADAT': {'COMP_BA': 'T', 'N_FIX_BA': '0', 'FIX_BA': '0.0'}},
                    caches=('BAMAT', 'BAMATPNT'),
                    steps=(RecoveryStep('population_lambda', 3, _bootstrap_check,
                                        {'population_recovery_probe': True}),
                           RecoveryStep('population_full', 2, _population_full_check,
                                        repeat_on_native_fallback=True)),
                    evidence={'last_full_increases_percent': [r['maximum_increase_percent'] for r in full[-2:]]})


def population_guard(ctx):
    """Keep an invalid run invalid; independently audit its provisional state.

    Only the explicit native post-save MAX_CHNG stop qualifies. The controller
    retains its earlier recovery snapshot until the entire bootstrap/full
    procedure passes; this never accepts a failed run as a convergence result.
    """
    from .auto_policies import Declined
    text = '\n'.join([ctx.log, *(p.get('diagnostic_tail', '') for p in ctx.native_result.get('passes', []))])
    markers = ('Error - bad initial population guesses.', 'Predicted changes are too large.',
               'New populations written to SCRTEMP file.', 'Edit POINT1 file to recover older populations.')
    if not all(marker in text for marker in markers):
        return None
    passes = ctx.native_result.get('passes', [])
    if len(passes) != 1 or passes[0].get('returncode') != 0:
        raise Declined('MAX_CHNG recovery requires the explicit zero-exit native safeguard, not a crash')
    if 'checkpoint_physics' not in ctx.before:
        raise Declined('MAX_CHNG recovery needs an independently audited pre-attempt checkpoint')
    if ctx.native_plan.get('restart', {}).get('mode') != 'continuation':
        raise Declined('MAX_CHNG recovery never promotes a failed fresh initialization')
    from .checkpoint_physics import checkpoint_physics, compare_physics
    from .runner_restart import inspect_restart
    from .model_convergence import _parse_iteration_records
    records = _parse_iteration_records(ctx.log)
    start = ctx.native_plan['restart']['pointer']['iterations']
    end = inspect_restart(ctx.model).get('pointer') or {}
    if (len(records) != 1 or records[0].get('global_iteration') != start+1 or
            end.get('iterations') != start+1 or not records[0].get('ba_computed') or
            not _finite(records[0].get('solver_maximum_change')) or
            not _finite(records[0].get('maximum_increase_percent')) or
            records[0].get('maximum_increase_percent', 0) < 1e12):
        raise Declined('MAX_CHNG recovery requires exactly one completed fresh-BA solve and its saved checkpoint')
    try:
        physical = compare_physics(ctx.before['checkpoint_physics'], checkpoint_physics(ctx.model))
    except (OSError, ValueError) as exc:
        raise Declined(str(exc)) from exc
    # Reuse the identical bounded bootstrap prerequisites and validators.
    from dataclasses import replace
    evidence = {'records': records, 'hydro_revisions': []}
    decision = population_bootstrap(replace(ctx, evidence=evidence))
    if decision:
        return replace(decision, retain_failed_checkpoint=True,
                       reason='Explicit MAX_CHNG post-save stop; independently positive, charge/element-conserving '
                              'checkpoint retained provisionally for bounded Lambda recovery and full verification',
                       evidence={'guard_checkpoint':end, 'physical_checks':physical,
                                 'native_failure_status_preserved':ctx.native_result.get('status')})


def ng_cadence(ctx):
    from .auto_policies import Decision
    if len(ctx.history) < 2 or ctx.evidence.get('candidate'):
        return None
    if not enabled(ctx.model, 'DO_NG'):
        return None
    # This is specifically the native *first* Ng delay. Existing LAST_NG uses
    # an absolute interval and does not need this process-start workaround.
    from .runner_restart import inspect_restart
    pointer = inspect_restart(ctx.model).get('pointer') or {}
    if pointer.get('last_ng') != -1000:
        return None
    beg = number(ctx.model, 'VADAT', 'BEG_NG', 10)
    begin = number(ctx.model, 'VADAT', 'IBEG_NG', 25)
    if pointer.get('iterations', 0) < begin:
        return None
    for batch in ctx.history[-2:]:
        rows = batch.get('records', [])
        if (batch.get('hydro_revisions') or batch.get('ng_accelerations') or not 2 <= len(rows) <= 5 or
                not all(not r.get('lambda_iteration') and not r.get('temperature_fixed') and
                        _finite(r.get('solver_maximum_change')) and
                        0 <= r['solver_maximum_change'] < beg for r in rows)):
            return None
    return Decision('action', 'Repeated short full batches below BEG_NG have not permitted the first native Ng; '
                    'use eight contiguous physical solves while retaining native Ng safeguards',
                    action='ng_cadence', batch_iterations=8,
                    evidence={'last_ng': -1000, 'recent_batch_lengths': [len(h['records']) for h in ctx.history[-2:]]})
