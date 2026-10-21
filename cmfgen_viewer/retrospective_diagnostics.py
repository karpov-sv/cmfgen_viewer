"""Recompute advisory checks from existing outputs without inventing run history."""
from pathlib import Path

from . import auto_policies as policies
from .auto_diagnostics import assess_existing, convergence_status
from .main_recommendations import current_main_recommendations
from .model_convergence import inspect_model_convergence, _parse_run_started_epoch
from .model_run_diagnostics import diagnose_main_run
from .native_diagnostics import latest_main_log
from .model_convergence import _read_limited_tail


def inspect_main_recommendations(model, *, active=False, force=False, native=None):
    if active:
        return None
    model = Path(model)
    if not force:
        saved = current_main_recommendations(model)
        if saved:
            if not saved.get('convergence') and saved.get('evidence_status') == 'validated':
                try:
                    saved = {**saved, 'convergence': convergence_status(assess_existing(model), historical=True)}
                except (OSError, ValueError, KeyError):
                    pass
            return saved
    if not any((model/name).is_file() for name in ('OUTGEN', 'batch.log', 'MOD_SUM', 'RVTJ')):
        return None
    names = ('OUTGEN', 'MOD_SUM', 'RVTJ', 'CORRECTION_SUM', 'POINT1', 'POINT2', 'SCRTEMP',
             'VADAT', 'MODEL_SPEC', 'ADJUST_CORRECTIONS', 'J_COMP', 'OBSFLUX', 'MEANOPAC', 'HYDRO', 'batch.log')
    def signature():
        return [(name, (p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ctime_ns)
                 if (p := model/name).is_file() else None) for name in names]
    try:
        before = signature()
        report = _recompute(model, native)
        if before != signature():
            report.pop('convergence', None)
            report['findings'] = []
            report['evidence_status'] = 'unavailable'
            report['evidence_error'] = 'Model outputs or controls changed during inspection; recheck when idle.'
        return report
    except (OSError, ValueError, KeyError) as exc:
        return {'mode': 'retrospective', 'evidence_status': 'unavailable', 'findings': [],
                'summary': 'Existing model checks could not be completed.', 'evidence_error': str(exc)}


def _recompute(model, native):
    report = {'mode': 'retrospective', 'evidence_status': 'historical', 'findings': [],
              'summary': 'Recomputed from existing model outputs; original invocation provenance is unavailable.',
              'limitations': [
                  'No original pre-run snapshots or confirmed startup mode: recovery eligibility cannot be certified.',
                  'No compatible batch history: multi-batch stall and fixed-temperature rules cannot be established.',
                  'Historical STEQ_VALS vectors cannot be tied to this invocation: local oscillation damping is not inferred.',
                  'Candidates without two final fresh-Jacobian steps require independent verification.'],
              'policies': policies.manifest()}
    native = native if native is not None else diagnose_main_run(model)
    for finding in native.get('findings', []):
        report['findings'].append({'policy_id': finding['code'], 'title': finding['title'],
            'message': finding['message'], 'automatic_eligible': False,
            'recommendation': ' '.join(finding.get('suggestions', [])) +
                ' Automatic recovery prerequisites cannot be confirmed from historical outputs alone.'})
    text = latest_main_log(_read_limited_tail(model/'OUTGEN', 32 * 1024**2)[0])
    wrapper = model/'batch.log'
    if wrapper.is_file() and (not (model/'OUTGEN').exists() or wrapper.stat().st_mtime >= (model/'OUTGEN').stat().st_mtime):
        text += '\n' + latest_main_log(_read_limited_tail(wrapper, 4 * 1024**2)[0])
    # The original startup mode, exit status and baseline are explicitly unknown.
    # Failure policies can recognize signatures but cannot authorize a restart.
    context = policies.Context(model, 'failure', {'restart': {'mode': 'unknown'}},
        {'status': native.get('status', 'unknown'), 'passes': [
            {'diagnostic_findings': native.get('findings', []), 'diagnostic_tail': text, 'returncode': None}]},
        {}, {}, [], 'advisory', [], text)
    decision, _ = policies.choose(context)
    if decision.kind == 'action':
        report['findings'].append({'policy_id': decision.policy_id, 'title': 'Possible recovery from saved native diagnostics',
            'message': decision.reason, 'automatic_eligible': False,
            'recommendation': 'Review or restore a usable checkpoint before retrying. Original recovery baselines and automatic eligibility are unverified.',
            'proposal': decision.summary()})
    try:
        convergence = inspect_model_convergence(model)
        started = _parse_run_started_epoch(convergence.get('started_at'))
        quality = convergence.get('quality', {})
        for check in quality.get('checks', []):
            # Unknown start dates must not make unrelated auxiliary files current.
            if check['level'] != 'warning' or (started is None and check.get('path') != 'OUTGEN'):
                continue
            report['findings'].append({'policy_id': 'quality_'+check['code'], 'title': check['label'],
                'message': check['detail'], 'automatic_eligible': False,
                'recommendation': check['action'] + ' This is advisory screening of saved output.'})
        if native.get('status') == 'failed':
            report['evidence_error'] = 'Native diagnostics indicate a failed run; numerical success policies were not evaluated.'
            return report
        evidence = assess_existing(model)
        report['evidence_status'] = 'historical_screened'
        report['convergence'] = convergence_status(evidence, historical=True)
        ctx = policies.Context(model, 'success', {}, {}, {}, evidence, [evidence], 'advisory', [], '')
        for policy in policies.POLICIES:
            if policy.when != 'success':
                continue
            try:
                decision = policy.evaluate(ctx)
            except policies.Declined as exc:
                report['findings'].append({'policy_id': policy.id, 'title': policy.description,
                    'message': str(exc), 'automatic_eligible': False,
                    'recommendation': 'Review unmet prerequisites; historical evidence cannot authorize recovery.'})
                continue
            if decision is None or decision.kind in {'continue', 'converged'}:
                continue
            report['findings'].append({'policy_id': policy.id, 'title': policy.description,
                'message': decision.reason, 'automatic_eligible': False,
                'recommendation': 'Suggested from timestamp-screened historical outputs. Review current controls and restart state before acting; automatic eligibility is unverified.',
                'proposal': {**decision.summary(), 'policy_id': policy.id}})
    except (OSError, ValueError, KeyError) as exc:
        report['evidence_error'] = str(exc)
    return report
