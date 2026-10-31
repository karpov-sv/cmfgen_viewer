"""Guarded remedies established by the Bstar3010 investigation.

No atmosphere seeds, abundances, fitted histories or stopping tolerances are
transferred from that model. Every adjustment is provisional until its native
follow-up passes; only the normal fresh verification policy declares success.
"""
import math

from .auto_diagnostics import control_value, number
from .auto_hydro import guard_measurements, structure_fixed
from .auto_recovery import repaired_runtime
from .control_files import control_occurrences
from .runner_recipe import RunnerError



def _baseline(ctx):
    if (ctx.evidence.get('hydro_revisions') or ctx.evidence.get('source_changed') or ctx.evidence.get('ng_accelerations') or
            ctx.evidence.get('candidate') or not structure_fixed(ctx.model) or
            not repaired_runtime(ctx.native_plan)):
        return None
    records = ctx.evidence.get('records', [])
    if len(records) < 2 or any(r.get('lambda_iteration') or r.get('temperature_fixed')
                               or not r.get('ba_computed') for r in records):
        return None
    values = [r.get(k) for r in records for k in
              ('solver_maximum_change', 'maximum_increase_percent', 'maximum_decrease_percent')]
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 for v in values):
        return None
    try:
        from .checkpoint_physics import checkpoint_physics, compare_physics
        physical = checkpoint_physics(ctx.model)
        compare_physics(physical, physical)
        guard = guard_measurements(ctx.model, ctx.before)
    except (OSError, ValueError):
        return None
    if not .5 <= guard['luminosity_min'] <= guard['luminosity_max'] <= 2:
        return None
    return {'physical': physical, 'guard': guard, 'raw_maximum_percent': max(values[-3:]),
            'counts': ctx.evidence['counts']}


def _validate(ctx, baseline):
    from .checkpoint_physics import checkpoint_physics, compare_physics
    records = ctx.evidence['records']
    if (len(records) < 2 or ctx.evidence.get('source_changed') or
            ctx.evidence.get('hydro_revisions') or ctx.evidence.get('ng_accelerations') or
            any(r.get('lambda_iteration') or r.get('temperature_fixed') or not r.get('ba_computed')
                for r in records)):
        raise RunnerError('Convergence remedy requires full fresh-BA solves with unchanged structure and source')
    values = [records[-1].get(k) for k in
              ('solver_maximum_change', 'maximum_increase_percent', 'maximum_decrease_percent')]
    if (not all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0 for v in values) or
            max(values) >= baseline['raw_maximum_percent']):
        raise RunnerError('Convergence remedy did not reduce the raw maximum request')
    old, new = baseline['counts'], ctx.evidence['counts']
    if (old['nt'] != new['nt'] or old['nd'] != new['nd'] or
            old['totals'].keys() != new['totals'].keys() or
            any(v > old['totals'][k] for k, v in new['totals'].items())):
        raise RunnerError('Convergence remedy increased correction counts or changed the model grid')
    physics = compare_physics(baseline['physical'], checkpoint_physics(ctx.model))
    guard = guard_measurements(ctx.model, ctx.before)
    if not .5 <= guard['luminosity_min'] <= guard['luminosity_max'] <= 2:
        raise RunnerError('Convergence remedy failed the luminosity guards')
    return {'convergence_remedy_check': {'raw_maximum_percent': max(values),
                                        'physical_checks': physics, 'guard': guard}}


def population_relaxation(ctx):
    from .auto_policies import Decision, Declined, RecoveryStep
    cycle = ctx.evidence.get('population_cycle')
    if not cycle:
        return None
    if control_value(ctx.model, 'VADAT', 'SCALE_OPT', '').upper() != 'MAJOR':
        raise Declined('Population damping requires native SCALE_OPT=MAJOR')
    path = ctx.model/'ADJUST_CORRECTIONS'
    rows = control_occurrences(path.read_text()) if path.exists() else {}
    if any(len(v) != 1 for v in rows.values()) or set(rows) - {'L_ST', 'L_END', 'RELAX', 'T_LIM'}:
        raise Declined('Existing correction controls cannot safely be broadened for population damping')
    nd = ctx.evidence['counts']['nd']
    if (number(ctx.model, 'ADJUST_CORRECTIONS', 'RELAX', 1) != 1 or
            number(ctx.model, 'ADJUST_CORRECTIONS', 'L_ST', 1) != 1 or
            number(ctx.model, 'ADJUST_CORRECTIONS', 'L_END', nd) != nd):
        return None  # Preserve caller's existing damping and scoped controls.
    baseline = _baseline(ctx)
    if baseline is None:
        return None
    return Decision('action', 'Small raw population requests repeatedly reverse sign without decaying; '
                    'try native RELAX=0.5 and check fresh full continuation',
                    action='population_relaxation',
                    changes={'ADJUST_CORRECTIONS': {'L_ST': '1', 'L_END': str(nd), 'RELAX': '0.5'},
                             'VADAT': {'COMP_BA': 'T', 'N_FIX_BA': '0', 'FIX_BA': '0.0'}},
                    caches=('BAMAT', 'BAMATPNT'), evidence={**baseline, 'population_cycle': cycle},
                    steps=(RecoveryStep('population_relaxation_check', 3, lambda c: _validate(c, baseline)),))


def stalled_transfer_refinement(ctx):
    from .auto_policies import Decision, RecoveryStep, _stall
    stalled = _stall(ctx)
    if stalled is None or stalled.kind != 'stop':
        return None
    if any(control_value(ctx.model, 'VADAT', key, 'F').upper().strip('.') in {'T', 'TRUE'}
           for key in ('USE_J_REL', 'USE_DJDT_RTE', 'INC_GRID', 'SN_MODEL', 'USE_FIXED_J')):
        return None  # Established here for ordinary steady-state transfer only.
    fg = number(ctx.model, 'VADAT', 'VFRAC_FG', 20000)
    mom = number(ctx.model, 'VADAT', 'VFRAC_MOM', 20000)
    if min(fg, mom) <= 0 or max(fg, mom) <= .1:
        return None
    baseline = _baseline(ctx)
    if baseline is None:
        return None
    changes = {key: '0.1' for key, value in [('VFRAC_FG', fg), ('VFRAC_MOM', mom)] if value > .1}
    changes.update(COMP_F='T', COMP_BA='T', N_FIX_BA='0', FIX_BA='0.0')
    return Decision('action', 'Small corrections stalled with fresh matrices and coarse transfer sampling; '
                    'try VFRAC_FG/VFRAC_MOM=0.1 on the existing atmosphere grid',
                    action='stalled_transfer_refinement', changes={'VADAT': changes},
                    caches=('EDDFACTOR', 'EDDFACTOR_INFO', 'BAMAT', 'BAMATPNT'),
                    evidence={**baseline, 'old_VFRAC_FG': fg, 'old_VFRAC_MOM': mom},
                    steps=(RecoveryStep('transfer_refinement_check', 3, lambda c: _validate(c, baseline)),))
