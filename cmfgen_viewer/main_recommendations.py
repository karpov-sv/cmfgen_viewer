"""Read-only end-of-run advice using the automatic recovery policy registry.

Execution success, validated numerical evidence, and remedy eligibility remain
separate. No decision returned here is applied to the model.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import auto_policies as policies
from .auto_diagnostics import assess, convergence_status
from .auto_hydro import revisions
from .runner_recipe import snapshot
from .recovery_files import INPUT_FILES

EVIDENCE_FILES = ('OUTGEN', 'CORRECTION_SUM', 'RVTJ', 'OBSFLUX', 'MEANOPAC')
CONTROLS = ('VADAT', 'MODEL_SPEC', 'ADJUST_CORRECTIONS', 'RVSIG_COL', 'HYDRO_DEFAULTS')
CURRENT_FILES = (*EVIDENCE_FILES, *CONTROLS, 'MODEL', 'MOD_SUM', 'POINT1', 'POINT2', 'SCRTEMP', 'STEQ_VALS')


def _control_paths(model):
    names = set(CONTROLS) | (INPUT_FILES - {'IN_ITS'})
    names.update(p.name for p in model.glob('*_IN') if p.name != 'T_IN')
    return [model / name for name in sorted(names)]


def _fingerprint(model):
    paths = set(_control_paths(model)) | {model / name for name in CURRENT_FILES}
    return [snapshot(path) for path in sorted(paths)]


def _history_key(model, plan):
    controls = []
    for path in _control_paths(model):
        name = path.name
        if path.is_symlink() or (path.exists() and path.stat().st_size > 4 * 1024**2):
            return None
        controls.append((name, hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None))
    return hashlib.sha256(json.dumps([controls, plan['executable_snapshot']], sort_keys=True).encode()).hexdigest()


def _recent_results(model, exclude=None):
    root = model / '.cmfgen-runs'
    if not root.is_dir() or root.is_symlink():
        return
    paths = sorted((p for p in root.glob('*/result.json') if not p.is_symlink()),
                   key=lambda p: p.stat().st_mtime_ns, reverse=True)
    for path in paths[:40]:
        if path.parent.is_symlink() or str(path.parent) == exclude:
            continue
        try:
            if path.stat().st_size > 8 * 1024**2:
                yield {'stage': 'main', 'status': 'unreadable'}
                continue
            result = json.loads(path.read_text())
            if isinstance(result, dict) and (result.get('stage') == 'main' or result.get('kind') == 'auto'):
                yield result
        except (OSError, ValueError, TypeError):
            # An unreadable intervening journal cannot establish continuity.
            yield {'stage': 'main', 'status': 'unreadable'}


def _history(model, plan, result, key, before):
    """Use consecutive compatible batches, never reuse a failed/reset sequence."""
    history = []
    checkpoint = (plan.get('restart', {}).get('pointer') or {}).get('iterations')
    if not key or plan.get('restart', {}).get('mode') != 'continuation':
        return history
    for old in _recent_results(model, result['journal']):
        report = old.get('main_diagnostics') or {}
        evidence = report.get('evidence') or {}
        if not history:
            saved = {Path(f['path']).name: f for f in report.get('fingerprint', [])}
            if any(saved.get(name) != before.get(name) for name in EVIDENCE_FILES):
                break
        if (old.get('status') != 'succeeded' or report.get('history_key') != key or
                report.get('policies') != policies.manifest() or evidence.get('checkpoint') != checkpoint or
                evidence.get('hydro_revisions')):
            break
        history.insert(0, evidence)
        checkpoint = report.get('starting_checkpoint')
        if len(history) == 3:
            break
    return history


def analyze_main_end(model, plan, result, before, solution_offset):
    from .runner import _tail
    model = Path(model)
    report = {'mode': 'advisory', 'findings': [], 'policies': policies.manifest(),
              'summary': 'Run ended; numerical evidence could not be assessed.',
              'evidence_status': 'unavailable', 'executable': snapshot(Path(plan['executable']))}
    if result['status'] in {'cancelled', 'timeout', 'runner_error'} or not result.get('passes'):
        report['summary'] = 'Run interrupted or runner controls need review; automatic remedies were not assessed.'
        return report
    log = _tail(model / 'OUTGEN', 32 * 1024**2)
    evidence = {}
    history = []
    when = 'failure'
    if result['status'] == 'succeeded':
        try:
            requested = int(plan['passes'][0].get('overrides', {}).get('NUM_ITS', '0'))
            evidence = assess(model, result, before, solution_offset, requested,
                              hydro_revisions=revisions(log))
            if (plan['restart']['mode'] == 'continuation' and
                    result.get('startup_observed', {}).get('mode') != 'continuation'):
                raise ValueError('Native continuation was not confirmed')
            report['convergence'] = convergence_status(evidence)
            key = _history_key(model, plan)
            history = [] if evidence['hydro_revisions'] else _history(model, plan, result, key, before) + [evidence]
            # Only bounded summaries needed for cross-batch trend/profile rules.
            report.update(evidence_status='validated', history_key=key,
                          starting_checkpoint=(plan.get('restart', {}).get('pointer') or {}).get('iterations'),
                          evidence={k: evidence[k] for k in ('checkpoint', 'full_iterations', 'temperatures',
                                                            'counts', 'hydro_revisions')})
            report['evidence']['records'] = evidence['records'][-8:]
            report['evidence']['raw_temperature_steps'] = evidence['raw_temperature_steps'][-1:]
            report['batches_assessed'] = len(history)
            when = 'success'
        except (OSError, ValueError, KeyError) as exc:
            report['evidence_error'] = str(exc)
            report['summary'] = 'Execution completed, but numerical evidence is incomplete. Review outputs before continuing.'
            report['fingerprint'] = _fingerprint(model)
            return report
    ctx = policies.Context(model, when, plan, result, before, evidence, history, 'advisory', [], log)
    for policy in policies.POLICIES:
        if policy.when != when:
            continue
        try:
            decision = policy.evaluate(ctx)
        except (policies.Declined, OSError, ValueError) as exc:
            report['findings'].append({'policy_id': policy.id, 'title': policy.description,
                'message': str(exc), 'automatic_eligible': False,
                'recommendation': 'Investigate the unmet prerequisites before applying this remedy; auto mode will decline it too.'})
            continue
        if decision is None or decision.kind == 'continue':
            continue
        eligible = decision.kind == 'action'
        report['findings'].append({'policy_id': policy.id, 'title': policy.description,
            'message': decision.reason, 'automatic_eligible': eligible,
            'recommendation': ('Auto mode can handle this condition when its restart and recovery prerequisites are satisfied. '
                               'Review the proposed controls, cache retirement, or recovery steps below.' if eligible else
                               'Review the model physics, grid, and iteration controls; no automatic remedy is established.'),
            'proposal': {**decision.summary(), 'policy_id': policy.id}})
        if when == 'failure' and decision.kind == 'stop':
            # Match the controller's terminal rejection: lower-priority
            # remedies must not be advertised for an invalid model state.
            break
    if when == 'failure':
        report['summary'] = ('Recognized failure: review the recommendations and restart state before retrying.'
                             if report['findings'] else
                             'No supported automatic remedy identified. Review native diagnostics and logs before retrying.')
    elif report['findings']:
        report['summary'] = 'End-of-run checks found conditions needing attention or independent verification.'
    else:
        report['summary'] = ('No registered problem detected in the available evidence. This does not certify convergence '
                             'or physical quality; multi-batch rules require consecutive compatible runs.')
    report['fingerprint'] = _fingerprint(model)
    return report


def current_main_recommendations(model, *, active=False):
    """Expose stored advice only while its exact model/output evidence is current."""
    if active:
        return None
    try:
        model = Path(model)
        result = next(_recent_results(model), {})
        report = result.get('main_diagnostics')
        executable = (report or {}).get('executable') or {}
        if (report and executable.get('path') and executable == snapshot(Path(executable['path'])) and
                report.get('policies') == policies.manifest() and
                report.get('fingerprint') == _fingerprint(model)):
            return report
    except (OSError, ValueError, TypeError):
        pass
    return None
