"""Bounded, opt-in main-stage convergence controller.

All tested remedies are selected automatically through auto_policies. This
module owns guarded execution, provisional recovery steps and durable reports.
"""
from datetime import datetime, timezone
from pathlib import Path
import shutil
import time
import uuid

from .auto_diagnostics import assess, number
from .auto_hydro import NATIVE_CONTROLS, capture_controls, enabled, native_updates, revisions
from . import auto_policies as policies
from .control_files import control_occurrences
from .model_activity import model_mutation_guard, model_run_reservation
from .native_diagnostics import latest_main_log
from .recovery_files import retire_recovery
from .runner_controls import _patch
from .runner_recipe import RunnerError, build_run_plan, snapshot
from .runner_restart import RESTART_FILES
from .workflow_permissions import copy_readable, mkdir_readable, open_readable

RECOVERY_NAMES = (*RESTART_FILES, *NATIVE_CONTROLS, 'ADJUST_CORRECTIONS', 'MODEL', 'RVTJ', 'MOD_SUM',
                  'OUTGEN', 'CORRECTION_SUM', 'CORRECTION_LINK')
DYNAMIC_NAMES = set(RECOVERY_NAMES) | {'WARNINGS', 'STEQ_VALS'}


def configure_auto(plan, *, cmfgen_root, atomic_root,
                   max_attempts=policies.DEFAULT_MAX_ATTEMPTS,
                   max_iterations=policies.DEFAULT_MAX_ITERATIONS):
    """Attach an explicit policy and budget to a read-only main-stage preview."""
    if plan.get('kind') == 'sequence' and plan.get('stages') == ['main', 'flux']:
        initial = configure_auto(plan['initial_plan'], cmfgen_root=cmfgen_root, atomic_root=atomic_root,
                                 max_attempts=max_attempts, max_iterations=max_iterations)
        result = {**plan, 'initial_plan': initial, 'auto': initial['auto']}
        result['stage_options'] = {**plan['stage_options'], 'automatic_main': {
            'max_attempts': max_attempts, 'max_iterations': max_iterations,
            'policies': initial['auto']['policies']}}
        return result
    if plan.get('kind') or plan.get('stage') != 'main':
        raise RunnerError('--auto supports main or main followed by flux')
    if max_attempts < 2 or max_iterations < 2:
        raise RunnerError('Automatic mode requires at least 2 attempts and 2 total iterations')
    model = Path(plan['model'])
    eps = number(model, 'VADAT', 'EPS_TERM')
    if eps is None or eps <= 0:
        raise RunnerError('--auto requires a positive explicit [EPS_TERM]')
    if enabled(model, 'FIX_T') and not enabled(model, 'DO_T_AUTO'):
        raise RunnerError('--auto requires variable temperature or explicit [DO_T_AUTO]=T')
    batch = plan['passes'][0]['overrides'].get('NUM_ITS')
    batch = int(batch) if batch is not None else 5
    if batch < 2:
        raise RunnerError('--auto requires at least 2 iterations per batch')
    result = dict(plan)
    reviewed = {r['path'] for r in plan['inputs']}
    result['inputs'] = [*plan['inputs'], *(snapshot(model/n) for n in NATIVE_CONTROLS
                                          if str(model/n) not in reviewed)]
    result['kind'] = 'auto'
    registry = policies.manifest()
    result['auto'] = {'version': 3, 'batch_iterations': batch,
                      'max_attempts': max_attempts, 'max_iterations': max_iterations,
                      'policies': registry,
                      'cmfgen_root': str(Path(cmfgen_root).resolve()),
                      'atomic_root': str(Path(atomic_root).resolve()),
                      'actions': ['continue', *[p['description'] for p in registry]],
                      'excluded': ['source/executable changes', 'depth/moment grid or atomic-data changes',
                                   'manual physical parameter changes', 'LTE reseeding of continuation checkpoints',
                                   'unrestricted safeguard bypass'],
                      'acceptance': 'Two final full, variable-T iterations with fresh BA, native metric and absolute raw corrections below EPS_TERM; scientific quality is reported separately.',
                      'retention': 'Original controls, per-action evidence and one rolling full restart snapshot. Changed solver controls remain installed; large regenerated caches may be discarded.'}
    return result


def _safe(path):
    if path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_nlink != 1)):
        raise RunnerError(f'Unsafe automatic-mode file: {path}')


def _signature(path):
    info = snapshot(path)
    return (info['exists'], info.get('size'), info.get('sha256')) if info.get('sha256') else info


def _capture(model, journal, previous=None):
    """Commit a new rolling recovery snapshot before removing its predecessor."""
    from .runner import _json
    paths = [model/n for n in RECOVERY_NAMES]
    for path in paths:
        _safe(path)
    size = sum(p.stat().st_size for p in paths if p.exists())
    if shutil.disk_usage(model).free < size + 64*1024**2:
        raise RunnerError('Insufficient disk space for the full automatic recovery snapshot')
    target = journal / ('recovery-' + uuid.uuid4().hex[:8])
    mkdir_readable(target)
    present = []
    try:
        for path in paths:
            if path.exists():
                copy_readable(path, target/path.name)
                present.append(path.name)
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    _json(journal/'recovery.json', {'directory': target.name, 'present_files': present})
    if previous:
        try:
            shutil.rmtree(previous)
        except OSError as exc:
            # The new snapshot is already committed; do not report the old
            # (possibly partly removed) directory as the recovery checkpoint.
            try:
                with open_readable(journal/'recovery-cleanup.log', 'a') as stream:
                    stream.write(f'Could not remove superseded {previous}: {exc}\n')
            except OSError:
                pass  # recovery.json still identifies the committed snapshot.
    return target


def _restore(model, recovery, *, report_directory=None):
    from .runner import _publish, _json
    report = (report_directory or recovery.parent) / ('restore-' + uuid.uuid4().hex[:8] + '.json')
    caches = [model/name for name in ('BAMAT', 'BAMATPNT', 'EDDFACTOR', 'EDDFACTOR_INFO')]
    record = {'snapshot': str(recovery), 'status': 'planned',
              'files': list(RECOVERY_NAMES), 'invalidated_caches': []}
    for path in caches:
        _safe(path)
        if path.exists():
            record['invalidated_caches'].append(snapshot(path))
    _json(report, record)
    for name in RECOVERY_NAMES:
        destination = model/name
        _safe(destination)
        source = recovery/name
        if source.exists():
            _publish(source, destination)
        else:
            destination.unlink(missing_ok=True)
    # A failed attempt may have replaced caches for a later population state.
    # Regenerate them rather than mixing them with the restored checkpoint.
    for path in caches:
        if path.exists():
            retire_recovery(path, recovery/('invalidated-' + path.name))
    record['status'] = 'restored'
    _json(report, record)


def _action(model, journal, actions, kind, reason, changes=None, caches=(), *, policy_id='',
            evidence=None, preserve_caches=False):
    """One journaled, reversible control action. Cache removals are whitelisted."""
    from .runner import _json, _write_control
    folder = journal / f'action-{len(actions)+1:03d}'
    mkdir_readable(folder)
    record = {'kind': kind, 'policy_id': policy_id, 'reason': reason, 'changes': changes or {},
              'retired_caches': [], 'status': 'planned', 'directory': str(folder)}
    record['evidence'] = evidence or {}
    if preserve_caches and set(caches) - {'EDDFACTOR', 'EDDFACTOR_INFO'}:
        raise RunnerError('Only diagnosed radiation caches may be preserved by an automatic action')
    actions.append(record)
    _json(folder/'action.json', record)
    rendered = {}
    for name, values in (changes or {}).items():
        if name not in {'VADAT', 'ADJUST_CORRECTIONS'}:
            raise RunnerError('Unsupported automatic control target')
        path = model/name
        _safe(path)
        text = path.read_text() if path.exists() else ''
        rows = control_occurrences(text)
        if any(len(v)>1 for v in rows.values()):
            raise RunnerError(f'Ambiguous controls in {name}; automatic changes refused')
        if path.exists():
            copy_readable(path, folder/name)
        rendered[name] = _patch(text, values).encode()
    for name in caches:
        if name not in {'BAMAT', 'BAMATPNT', 'EDDFACTOR', 'EDDFACTOR_INFO'}:
            raise RunnerError('Unsupported automatic cache retirement')
        path = model/name
        _safe(path)
        if preserve_caches:
            import hashlib
            key = 'sha256' if name == 'EDDFACTOR' else 'info_sha256'
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024*1024), b''):
                    digest.update(block)
            if digest.hexdigest() != (evidence or {}).get(key):
                raise RunnerError('Radiation cache changed after diagnosis; preserving current files for review')
    for name in caches:
        path = model/name
        if path.exists():
            record['retired_caches'].append(snapshot(path))
            _json(folder/'action.json', record)
            if preserve_caches:
                # .bak also survives the ordinary recovery-compaction policy.
                # Rename within the model filesystem; do not duplicate a large
                # cache or replace it with the runner's bounded log excerpt.
                from .workflow_permissions import make_readable
                destination = folder/(name + '.bak')
                path.rename(destination)
                make_readable(destination)
                record.setdefault('preserved_caches', {})[name] = str(destination)
            else:
                retire_recovery(path, folder/name)
    for name, data in rendered.items():
        path = model/name
        from .workflow_permissions import readable_mode
        _write_control(path, data, readable_mode(path.stat().st_mode if path.exists() else 0o644))
    record['status'] = 'applied'
    _json(folder/'action.json', record)
    return record


def _issue_report(journal, plan, result, native_result):
    """Leave a bounded, reproducible handoff for debugging the next missing rule."""
    from .runner import _json
    report = {'schema_version': 1, 'model': plan['model'], 'status': result['status'],
              'reason': result.get('reason'), 'policies': plan['auto']['policies'],
              'executable': plan['executable_snapshot'],
              'recovery_directory': result['recovery_directory'],
              'preparation': result.get('preparation'),
              'attempts': [{k: a[k] for k in ('attempt', 'phase', 'status', 'journal',
                            'decision', 'policy_evaluations', 'validation_error') if k in a}
                           for a in result['attempts']],
              'last_native_result': {'status': (native_result or {}).get('status'),
                  'error': (native_result or {}).get('error'),
                  'passes': [{k: p[k] for k in ('status', 'returncode', 'problems',
                              'diagnostic_findings', 'diagnostic_tail') if k in p}
                             for p in (native_result or {}).get('passes', [])]}}
    _json(journal/'issue.json', report)
    with open_readable(journal/'issue.md', 'w') as stream:
        stream.write(f"# Automatic main run: {result['status']}\n\n{result.get('reason', '')}\n\n"
                     f"Model: {plan['model']}\n\nRecovery: {result['recovery_directory']}\n\n"
                     "The structured issue.json contains the native failure evidence and policy decisions. "
                     "plan.json records the reviewed inputs, executable and work limits. Each attempt's "
                     "journal retains its native logs. A new remedy should reproduce this issue, "
                     "define its eligibility and verification, and add regression tests before registration.\n")
    result['issue_report'] = str(journal/'issue.json')


def run_auto_plan(plan, emit=None):
    from .runner import run_plan, _json, _tail
    if not plan['ready']:
        raise RunnerError('Automatic preflight failed: ' + '; '.join(plan['errors']))
    if plan['auto'].get('policies') != policies.manifest():
        raise RunnerError('Automatic policies changed since preview; prepare a new plan')
    model = Path(plan['model'])
    options = plan['auto']
    batch_iterations = options['batch_iterations']
    with model_run_reservation(model, RunnerError):
        with model_mutation_guard(model, RunnerError):
            for old in [*plan['inputs'], plan['executable_snapshot']]:
                if snapshot(Path(old['path'])) != old:
                    raise RunnerError(f"Input changed since automatic preflight: {old['path']}")
            root = model/'.cmfgen-runs'
            if root.is_symlink():
                raise RunnerError('Refusing symlinked run archive')
            mkdir_readable(root, exist_ok=True)
            run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-auto-' + uuid.uuid4().hex[:8]
            journal = root/run_id
            mkdir_readable(journal)
            _json(journal/'plan.json', plan)
            originals = journal/'original-controls'
            mkdir_readable(originals)
            for name in (*NATIVE_CONTROLS, 'ADJUST_CORRECTIONS'):
                _safe(model/name)
                if (model/name).exists():
                    copy_readable(model/name, originals/name)
            paths = {Path(r['path']) for r in plan['inputs'] if Path(r['path']).name not in DYNAMIC_NAMES}
            paths.update(model/n for n in (*NATIVE_CONTROLS, 'ADJUST_CORRECTIONS'))
            expected = {path: _signature(path) for path in paths}
            recovery = _capture(model, journal)
        result = {'run_id': run_id, 'stage': 'main', 'kind': 'auto', 'status': 'running',
                  'journal': str(journal), 'started_at': datetime.now(timezone.utc).isoformat(),
                  'attempts': [], 'actions': [], 'iterations_used': 0,
                  'scientific_acceptance': 'not assessed'}

        def event(kind, **values):
            item = {'event': kind, 'run_id': run_id, 'time': datetime.now(timezone.utc).isoformat(),
                    'stage': 'main', **values}
            with open_readable(journal/'events.jsonl', 'a') as stream:
                import json
                stream.write(json.dumps(item, allow_nan=False)+'\n')
            if emit:
                emit(item)

        def check_inputs():
            if snapshot(Path(plan['executable'])) != plan['executable_snapshot']:
                raise RunnerError('Executable changed during automatic execution; review before continuing')
            for path, signature in expected.items():
                if _signature(path) != signature:
                    raise RunnerError(f'Input changed during automatic execution: {path}; preserving the edit')

        def action(decision):
            nonlocal recovery
            with model_mutation_guard(model, RunnerError):
                check_inputs()
                record = _action(model, journal, result['actions'], decision.action, decision.reason,
                                 decision.changes, decision.caches, policy_id=decision.policy_id,
                                 evidence=decision.evidence, preserve_caches=decision.preserve_caches)
                if not decision.steps and pending is None:
                    recovery = _capture(model, journal, recovery)
                for path in expected:
                    expected[path] = _signature(path)
            _json(journal/'result.json', result)
            event('auto_action', action=record)

        def restore(source=None):
            _restore(model, source or recovery, report_directory=journal)
            for name in (*NATIVE_CONTROLS, 'ADJUST_CORRECTIONS'):
                expected[model/name] = _signature(model/name)

        history = []
        initializing = True
        base_phase = 'iterate'
        pending = None
        step_index = 0
        native_result = None
        working = None
        working_root = journal/'provisional'
        deadline = time.monotonic()+plan['timeout'] if plan.get('timeout') is not None else None
        _json(journal/'result.json', result)
        try:
            event('auto_started', policy=options)
            with model_mutation_guard(model, RunnerError):
                check_inputs()
                preparation, trail = policies.choose(policies.Context(
                    model, 'prepare', plan, {}, {}, {}, [], 'iterate', result['actions'], ''))
                result['preparation'] = {'decision': preparation.summary(), 'policy_evaluations': trail}
            event('auto_preparation', **result['preparation'])
            if preparation.kind == 'stop':
                raise RunnerError(preparation.reason)
            if preparation.kind == 'action':
                action(preparation)
            elif preparation.kind != 'continue':
                raise RunnerError('Unsupported automatic preparation decision')
            for attempt in range(1, options['max_attempts']+1):
                step = pending.steps[step_index] if pending else None
                phase = step.name if step else base_phase
                remaining = options['max_iterations']-result['iterations_used']
                minimum = sum(s.iterations for s in pending.steps[step_index:]) if pending else (2 if base_phase == 'verify' else 1)
                attempts_needed = len(pending.steps)-step_index if pending else 1
                if remaining < minimum or options['max_attempts']-attempt+1 < attempts_needed:
                    result.update(status='limit_reached', reason='Insufficient budget to complete the pending recovery or verification')
                    break
                if deadline is not None and time.monotonic() >= deadline:
                    result.update(status='timeout', reason='Shared automatic execution timeout reached')
                    break
                requested = step.iterations if step else (3 if base_phase == 'verify' else batch_iterations)
                batch = min(requested, remaining)
                with model_mutation_guard(model, RunnerError):
                    check_inputs()
                    step_options = step.native_options if step else {}
                    if set(step_options) - {'hydro_recovery_probe', 'lte_initialization', 't_exc', 'pop_initialization', 'population_recovery_probe'}:
                        raise RunnerError('Recovery step requested unsupported native options')
                    kwargs = {key: plan.get(key) for key in ('threads', 'memory_mib', 'no_core_dumps')}
                    native = build_run_plan(model, stage='main', cmfgen_root=Path(options['cmfgen_root']),
                        atomic_root=Path(options['atomic_root']), iterations=batch,
                        fresh_start=bool(initializing and plan.get('fresh_start')),
                        lte_initialization=bool(step_options.get('lte_initialization',
                            initializing and (plan.get('initialization') or {}).get('method') == 'LTE')),
                        pop_initialization=bool(step_options.get('pop_initialization',
                            initializing and (plan.get('initialization') or {}).get('method') == 'POP')),
                        t_exc=step_options.get('t_exc', (plan.get('initialization') or {}).get('t_exc', 1.0)),
                        timeout=max(0.001, deadline-time.monotonic()) if deadline is not None else None,
                        **kwargs)
                    if not native['ready']:
                        result.update(status='preflight_failed', reason='; '.join(native['errors']))
                        break
                    if 'hydro_recovery_probe' in step_options:
                        native['hydro_recovery_probe'] = step_options['hydro_recovery_probe']
                    if step_options.get('population_recovery_probe'):
                        native['population_recovery_probe'] = True
                    before = {name: snapshot(model/name) for name in ('OUTGEN','CORRECTION_SUM','RVTJ','OBSFLUX','MEANOPAC')}
                    if pending and pending.policy_id == 'population_bootstrap':
                        from .checkpoint_physics import checkpoint_physics
                        before['checkpoint_physics'] = checkpoint_physics(model)
                    elif pending and pending.policy_id == 'population_guard':
                        from .checkpoint_physics import checkpoint_physics
                        before['checkpoint_physics'] = checkpoint_physics(model)
                    elif native['restart']['mode'] == 'continuation':
                        from .auto_recovery import repaired_runtime
                        if repaired_runtime(native):
                            from .checkpoint_physics import checkpoint_physics
                            try:
                                before['checkpoint_physics'] = checkpoint_physics(model)
                            except (OSError, ValueError):
                                pass  # Unknown atomic/layout metadata cannot authorize guard recovery.
                    controls_before = capture_controls(model)
                    solution_offset = (model/'STEQ_VALS').stat().st_size if (model/'STEQ_VALS').exists() else 0
                    if pending:
                        mkdir_readable(working_root, exist_ok=True)
                        working = _capture(model, working_root, working)
                event('auto_attempt', attempt=attempt, phase=phase, requested_iterations=batch)
                _json(journal/f'attempt-{attempt:03d}-plan.json', native)
                result['iterations_used'] += batch
                _json(journal/'result.json', result)
                last_progress = None

                def forward(item):
                    nonlocal last_progress
                    if emit:
                        emit({**item, 'auto_attempt': attempt, 'auto_phase': phase})
                    if item['event'] == 'progress' and item.get('current') != last_progress:
                        last_progress = item.get('current')
                        event('auto_observation', attempt=attempt, progress=item)

                native_result = run_plan(native, forward, diagnose_main=False)
                entry = {'attempt': attempt, 'phase': phase, 'requested_iterations': batch,
                         'charged_iterations': batch, 'status': native_result['status'],
                         'journal': native_result['journal']}
                result['attempts'].append(entry)
                _json(journal/'result.json', result)
                with model_mutation_guard(model, RunnerError):
                    text = latest_main_log(_tail(model/'OUTGEN', 32*1024*1024))
                    observed = native_result.get('startup_observed', {})
                    adopted = native_updates(model, text, controls_before,
                        fresh_start=native['restart']['mode'] == 'fresh' and observed.get('mode') == 'fresh')
                    if adopted:
                        entry['native_control_updates'] = adopted
                        for name in adopted:
                            expected[model/name] = _signature(model/name)
                    check_inputs()
                    failure = native_result if native_result['status'] != 'succeeded' else None
                    evidence = {}

                    def context(when, outcome=native_result):
                        return policies.Context(model, when, native, outcome, before, evidence,
                                                history, phase if pending else base_phase, result['actions'], text)

                    if failure is None:
                        try:
                            observed = native_result['passes'][-1].get('startup_observed', {})
                            if native['restart']['mode'] == 'continuation' and observed.get('mode') != 'continuation':
                                raise RunnerError('Native continuation was not confirmed')
                            evidence = assess(model, native_result, before, solution_offset, batch,
                                              hydro_revisions=revisions(text))
                            if step:
                                entry.update(step.validate(context('success')) or {})
                        except (OSError, ValueError) as exc:
                            failure = {**native_result, 'status': 'invalid_evidence', 'error': str(exc)}
                            entry['validation_error'] = str(exc)
                    if failure is not None:
                        if native_result['status'] in {'cancelled', 'timeout'}:
                            restore()
                            entry['checkpoint_restored'] = True
                            result.update(status=native_result['status'], reason='Native attempt interrupted; stable restart restored')
                            break
                        decision, trail = policies.choose(context('failure', failure))
                        if pending and decision.steps:
                            decision = policies.Decision('stop', 'Nested multi-step recovery is unsupported; '
                                f'{pending.policy_id} failed at {step.name}', policy_id=decision.policy_id)
                        entry['decision'] = decision.summary()
                        entry['policy_evaluations'] = trail
                        if decision.retain_failed_checkpoint and decision.kind == 'action' and not pending:
                            entry['checkpoint_provisional'] = True
                        elif pending and decision.kind == 'action':
                            # A known simple fix (e.g. stale radiation cache)
                            # retries this step, without repeating the guard-off
                            # bridge or committing the provisional atmosphere.
                            restore(working)
                            entry['restored_state'] = 'recovery_step'
                        else:
                            restore()
                        entry['checkpoint_restored'] = not entry.get('checkpoint_provisional', False)
                    else:
                        entry['evidence'] = evidence
                        result['iterations_used'] += evidence['iterations'] - batch
                        entry['charged_iterations'] = evidence['iterations']
                        if evidence['iterations'] > batch:
                            restore()
                            result.update(status='limit_reached', reason='Native execution exceeded its requested iteration budget')
                            break
                        # A multi-step remedy remains provisional until ALL
                        # validators pass. One baseline covers the entire recipe.
                        if not pending or step_index == len(pending.steps)-1:
                            recovery = _capture(model, journal, recovery)
                        initializing = False
                if failure is None:
                    if pending:
                        step_index += 1
                        if step_index == len(pending.steps):
                            entry['recovery_verified'] = pending.policy_id
                            pending = None
                            base_phase = 'iterate'
                            history = []  # Do not mix correction trends across a recovery.
                    if evidence['hydro_revisions']:
                        history = []  # Mixed pre/post-hydro vectors are not a trend baseline.
                        event('auto_history_reset', attempt=attempt, hydro_revisions=evidence['hydro_revisions'],
                              reason='Native hydrostatic revision; correction trends restart with subsequent batches')
                    else:
                        history.append(evidence)
                    _json(journal/'result.json', result)
                    event('auto_assessment', attempt=attempt, candidate=evidence['candidate'],
                          counts=evidence['counts']['totals'], checkpoint=evidence['checkpoint'],
                          solver_maximum_changes=[r.get('solver_maximum_change') for r in evidence['records']])
                    if pending:
                        continue
                    decision, trail = policies.choose(context('success'))
                    entry['decision'] = decision.summary()
                    entry['policy_evaluations'] = trail
                _json(journal/'result.json', result)
                event('auto_decision', attempt=attempt, decision=decision.summary(), evaluations=trail)
                if decision.kind == 'converged':
                    if base_phase != 'verify' or not evidence.get('fresh_verified'):
                        raise RunnerError('Policy requested convergence without independent fresh-Jacobian evidence')
                    result.update(status='succeeded', numerical_convergence='verified with fresh Jacobians',
                                  scientific_acceptance='requires separate quality review', quality=evidence['quality'],
                                  final_checkpoint=evidence['checkpoint'])
                    break
                if decision.kind == 'stop':
                    result.update(status='needs_review', reason=decision.reason)
                    break
                if decision.kind == 'action':
                    if decision.batch_iterations is not None:
                        if options['max_iterations']-result['iterations_used'] < decision.batch_iterations:
                            result.update(status='limit_reached', reason='Insufficient budget for the contiguous recovery batch')
                            break
                    if decision.steps:
                        if (sum(s.iterations for s in decision.steps) > options['max_iterations']-result['iterations_used'] or
                                len(decision.steps) > options['max_attempts']-attempt):
                            if decision.retain_failed_checkpoint:
                                with model_mutation_guard(model, RunnerError):
                                    check_inputs()
                                    restore()
                                entry['checkpoint_restored'] = True
                                entry['checkpoint_provisional_rolled_back'] = True
                            result.update(status='limit_reached', reason='Insufficient budget to complete the selected recovery and its verification')
                            break
                    if decision.steps:
                        pending = decision
                        step_index = 0
                    action(decision)
                    if decision.batch_iterations is not None:
                        batch_iterations = decision.batch_iterations
                        result['batch_iterations'] = batch_iterations
                    history = []
                    if not decision.steps:
                        base_phase = decision.next_phase
                elif decision.kind != 'continue':
                    raise RunnerError(f'Unknown automatic decision kind: {decision.kind}')
            else:
                result.update(status='limit_reached', reason='Automatic attempt budget exhausted')
        except KeyboardInterrupt:
            result.update(status='cancelled', reason='Automatic run cancelled')
            try:
                with model_mutation_guard(model, RunnerError):
                    check_inputs()
                    restore()
            except (OSError, ValueError) as exc:
                result['reason'] += f'; recovery left for review: {exc}'
        except (OSError, ValueError) as exc:
            result.update(status='needs_review', reason=str(exc))
        except Exception as exc:
            result.update(status='runner_error', reason=f'{type(exc).__name__}: {exc}')
        finally:
            if pending:
                try:
                    with model_mutation_guard(model, RunnerError):
                        check_inputs()
                        restore()
                    result['provisional_recovery_rolled_back'] = pending.policy_id
                except (OSError, ValueError) as exc:
                    result['recovery_error'] = str(exc)
            result['finished_at'] = datetime.now(timezone.utc).isoformat()
            result['recovery_directory'] = str(recovery)
            if working_root.exists():
                try:
                    shutil.rmtree(working_root)
                except OSError as exc:
                    result['cleanup_warning'] = str(exc)
            if result['status'] in {'needs_review', 'runner_error', 'limit_reached', 'preflight_failed'}:
                try:
                    _issue_report(journal, plan, result, native_result)
                except OSError as exc:
                    result['issue_report_error'] = str(exc)
            _json(journal/'result.json', result)
        event('auto_finished', status=result['status'], reason=result.get('reason'), journal=str(journal))
        return result
