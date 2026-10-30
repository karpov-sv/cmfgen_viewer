"""Evidence for the native source-function opacity limiter's invalid floor."""
import math
import re

from .parsers.common import parse_float_token

SOURCE_FLOOR_MARKER = 'CMFGEN diagnostic: SRCE_CHK nonpositive opacity floor'


def source_floor_measurements(text):
    """Parse one contiguous native report; never combine separate failures."""
    reports = list(re.finditer(re.escape(SOURCE_FLOOR_MARKER), text))
    if not reports:
        return None
    block = '\n'.join(text[reports[-1].end():].splitlines()[:4])
    fields = re.findall(r'\b([A-Z_]+)\s*=\s*(\S+)', block)
    values = {}
    for key, token in fields:
        value = parse_float_token(token)
        if key in values or value is None or not math.isfinite(value):
            return None
        values[key] = value
    required = {'ITERATION','DEPTH','FREQUENCY','CHI','CHI_CONT','CHI_NOSCAT',
                'ETA','ETA_CONT','CHI_SCAT'}
    if set(values) != required:
        return None
    if any(values[key] < 1 or not values[key].is_integer() for key in ('ITERATION','DEPTH')):
        return None
    return values


def source_opacity_recovery(ctx):
    from .auto_policies import Decision, Declined
    from .auto_diagnostics import control_value, number
    findings = [f for p in ctx.native_result.get('passes', [])
                for f in p.get('diagnostic_findings', []) if f.get('severity') == 'error']
    matches = [f for f in findings if f.get('code') == 'source_opacity_floor']
    if not matches:
        return None
    if {f['code'] for f in findings} != {'source_opacity_floor'}:
        raise Declined('Source-opacity failure has additional diagnosed errors; review the model state')
    if control_value(ctx.model, 'VADAT', 'NEG_OPAC_OPT', '').upper() != 'SRCE_CHK':
        raise Declined('Opacity recovery requires the failing SRCE_CHK option still to be selected')
    measurements = [f.get('measurements') for f in matches]
    if any(not v for v in measurements):
        raise Declined('Source-opacity recovery lacks complete finite native measurements')
    nd = number(ctx.model, 'MODEL_SPEC', 'ND')
    for v in measurements:
        if not (nd and v['DEPTH'] <= nd and v['FREQUENCY'] > 0 and
                v['CHI'] <= 0 and v['CHI_NOSCAT'] < 0 and
                min(v['ETA'], v['ETA_CONT'], v['CHI_SCAT']) > 0 and
                0.1 * v['CHI_SCAT'] > 0):
            raise Declined('Native evidence does not establish a negative source floor with positive scattering')
    # This changes the existing limiter, not populations or structure. Ordinary
    # guarded execution may now use hydro/population remedies as needed; final
    # convergence still requires its independent fresh-Jacobian verification.
    return Decision('action', 'SRCE_CHK produced a nonpositive opacity floor from negative absorption; '
                    'select the native ESEC_CHK limiter and rebuild radiation and BA',
                    action='source_opacity',
                    changes={'VADAT': {'NEG_OPAC_OPT': 'ESEC_CHK', 'COMP_BA': 'T',
                                       'N_FIX_BA': '0', 'FIX_BA': '0.0'}},
                    caches=('BAMAT', 'BAMATPNT', 'EDDFACTOR', 'EDDFACTOR_INFO'),
                    evidence={'native_measurements': measurements})


def _opacity_lte_seed_check(ctx):
    from .runner_recipe import RunnerError
    if not ctx.evidence.get('initialized_only') or not ctx.evidence.get('charge_relative_error', 1) < 1e-6:
        raise RunnerError('Opacity LTE recovery did not establish an audited initialization-only checkpoint')
    return {'opacity_lte_seed_initialized': True}


def opacity_lte_seed(ctx):
    """Reset a diagnosed fresh POP radiation seed before guarded continuation."""
    from .auto_policies import Decision, Declined, RecoveryStep
    from .auto_diagnostics import control_value
    from .auto_hydro import guard_measurements, structure_fixed
    from .auto_recovery import repaired_runtime, _bootstrap_check, _population_full_check
    from .model_initialization import opacity_lte_seed_controls
    from .pop_initialization import POP_MARKER
    from .model_convergence import _parse_iteration_records
    codes = {f.get('code') for p in ctx.native_result.get('passes', [])
             for f in p.get('diagnostic_findings', []) if f.get('severity') == 'error'}
    repaired_floor = any(a.get('policy_id') == 'source_opacity' for a in ctx.actions)
    has_structure = (ctx.model/'lte').is_symlink() or any(
        p.exists() or p.is_symlink() for p in (ctx.model/'lte/FIN_CAL_GRID',ctx.model/'lte/RVSIG_COL_NEW'))
    if codes != {'inner_flux_accuracy'} or not (repaired_floor or has_structure):
        return None
    passes = ctx.native_result.get('passes', [])
    if (ctx.native_result.get('status') != 'invalid_output' or len(passes) != 1 or
            passes[0].get('returncode') != 0 or
            passes[0].get('startup_observed', {}).get('mode') != 'fresh'):
        raise Declined('Opacity LTE seed requires an isolated zero-exit fresh-start luminosity safeguard stop')
    if (ctx.native_plan.get('restart', {}).get('mode') != 'fresh' or
            (repaired_floor and control_value(ctx.model, 'VADAT', 'NEG_OPAC_OPT', '').upper() != 'ESEC_CHK') or
            POP_MARKER not in ctx.log):
        raise Declined('Opacity LTE seed requires the same fresh POP start after the diagnosed limiter recovery')
    records = _parse_iteration_records(ctx.log)
    if (len(records) != 1 or records[0]['global_iteration'] != 1 or
            records[0].get('solver_maximum_change') is not None):
        raise Declined('Opacity LTE seed never reseeds after a population solve or a continuation')
    if not repaired_runtime(ctx.native_plan, required=('line-jacobian-v1','ba-restart-v1','lte-charge-v1')):
        raise Declined('Opacity LTE seed requires an authenticated charge-consistent LTE build')
    measured = guard_measurements(ctx.model, ctx.before, require_positive=False)
    if measured['luminosity_min'] >= 0:
        return None  # A moderate positive deficit belongs to startup hydro.
    from .lte_structure_seed import lte_structure_source
    structure = None
    if has_structure:
        try:
            structure = lte_structure_source(ctx.model)
        except (OSError, ValueError) as exc:
            raise Declined(str(exc)) from exc
    if not structure_fixed(ctx.model) or control_value(ctx.model, 'VADAT', 'SCALE_OPT', '').upper() != 'MAJOR':
        raise Declined('Opacity LTE population bootstrap requires a fixed structure and SCALE_OPT=MAJOR')
    t_exc = min(1.0, structure['temperature_min']) if structure else 1.0
    opacity_lte_seed_controls((ctx.model/'VADAT').read_text(), t_exc, structure=bool(structure))
    label = 'the matching, promoted LTE/hydro temperature profile' if structure else 'the same temperature grid'
    return Decision('action', 'Fresh POP radiation has a nonpositive luminosity profile before its first population solve; '
                    f'initialize LTE populations using {label}, fill tiny seeds with fixed-T Lambda solves, '
                    'then verify guarded full continuation',
                    action='opacity_lte_seed',
                    changes={'VADAT': {'COMP_BA': 'T', 'N_FIX_BA': '0', 'FIX_BA': '0.0'}},
                    caches=('BAMAT','BAMATPNT','EDDFACTOR','EDDFACTOR_INFO'),
                    steps=(RecoveryStep('opacity_lte_seed', 0, _opacity_lte_seed_check,
                                        {'lte_structure_seed': True, 't_exc': t_exc} if structure else
                                        {'opacity_lte_seed': True, 't_exc': t_exc}, initialization_only=True),
                           RecoveryStep('opacity_population_lambda', 3, _bootstrap_check,
                                        {'population_recovery_probe': True}),
                           RecoveryStep('opacity_population_full', 2, _population_full_check,
                                        repeat_on_native_fallback=True)),
                    evidence={'seed_luminosity': measured, 't_exc': t_exc, 'structure_seed': structure,
                              'temporary_controls': {'LIN_INT':'F','IT_ON_T':'F','DC_METH':'LTE',
                                                     'LTE_EST':'T' if structure else 'unchanged'}})
