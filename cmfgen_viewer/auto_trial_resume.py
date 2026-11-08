"""Keep verified global-Ng pairs provisional across clean interruptions."""
from dataclasses import replace
from pathlib import Path
import re
import shutil

from . import auto_history
from .runner_recipe import RunnerError

NAME = 'global-ng-resume.json'
MAX_RESUMES = 2
EXTRA = ('OBSFLUX', 'MEANOPAC')


def _policy_version():
    from .auto_policies import POLICIES
    return next((p.version for p in POLICIES if p.id == 'global_ng'), None)


def begin(model, plan, decision, recovery, journal):
    """Before seeding, bind the original state and diagnostics to this trial."""
    from .workflow_permissions import copy_readable, mkdir_readable
    from .runner_auto import RECOVERY_NAMES
    if any(auto_history.digest(model/n) != auto_history.digest(recovery/n) for n in RECOVERY_NAMES):
        raise RunnerError('Trial baseline does not match its conservative recovery')
    if (model/'.cmfgen-runs'/NAME).exists():
        retire(model)
    folder = journal/'trial-resume'
    mkdir_readable(folder, exist_ok=True)
    for name in EXTRA:
        copy_readable(model/name, folder/('baseline-'+name))
    return {'version': 1, 'policy_id': 'global_ng', 'policy_version': _policy_version(), 'resumes': 0,
            'owner': str(journal.relative_to(model)), 'owner_action': None,
            'baseline_identity': auto_history.identity(model, plan),
            'baseline': decision.evidence,
            'baseline_diagnostics': {name: auto_history.digest(folder/('baseline-'+name)) for name in EXTRA},
            'baseline_folder': str(folder.relative_to(model))}


def _path(model, name):
    root = model/'.cmfgen-runs'
    path = model/name
    if not path.is_relative_to(root) or '..' in path.parts:
        raise RunnerError('Resume state must remain inside the run archive')
    cursor = path
    while cursor != model:
        if cursor.is_symlink():
            raise RunnerError('Unsafe provisional trial archive')
        cursor = cursor.parent
    return path


def _candidate(model, name):
    path = _path(model, name)
    if path.parent.name != 'trial-resume' or not re.fullmatch(r'recovery-[0-9a-f]{8}', path.name):
        raise RunnerError('Invalid provisional snapshot location')
    return path


def save_pair(model, plan, state, pair, evidence, journal, action):
    from .runner import _json
    from .runner_auto import _capture, RECOVERY_NAMES
    from .workflow_permissions import copy_readable
    if pair not in (1, 2) or evidence['checkpoint'] != state['baseline']['checkpoint']+2*pair:
        raise RunnerError('Only fully validated intermediate pairs can be saved')
    folder = journal/'trial-resume'
    folder.mkdir(exist_ok=True)
    previous = state.get('candidate')
    candidate = _capture(model, folder)
    for name in EXTRA:
        copy_readable(model/name, candidate/name)
    hashes = {name: auto_history.digest(candidate/name) for name in (*RECOVERY_NAMES, *EXTRA)}
    value = {**state, 'completed_pairs': pair, 'candidate': str(candidate.relative_to(model)),
             'candidate_hashes': hashes, 'candidate_identity': auto_history.identity(model, plan),
             'owner': str(journal.relative_to(model)),
             'pair_owner': str(journal.relative_to(model)),
             'owner_action': str(Path(action['directory']).relative_to(model)),
             'evidence': evidence}
    _json(model/'.cmfgen-runs'/NAME, value)
    # Publish before reclaiming the old snapshot; cancellation always retains
    # either the old complete pair or the new complete pair.
    if previous and previous != value['candidate']:
        old = _candidate(model, previous)
        try:
            shutil.rmtree(old)
        except OSError:
            pass  # The newly published complete pair remains authoritative.
    return value


def load(model, plan):
    """Resume only after confirmed rollback to the exact original baseline."""
    try:
        if plan.get('fresh_start') or plan.get('initialization'):
            raise RunnerError('Fresh initialization cannot resume a provisional trial')
        value = auto_history._read(model/'.cmfgen-runs'/NAME)
        if (value.get('version') != 1 or value.get('policy_id') != 'global_ng' or
                type(value.get('policy_version')) is not int or
                value.get('policy_version') != _policy_version() or
                type(value.get('resumes')) is not int or not 0 <= value['resumes'] < MAX_RESUMES or
                type(value.get('completed_pairs')) is not int or value['completed_pairs'] not in (1, 2)):
            raise RunnerError('No supported provisional trial remains within its resume limit')
        if set(value.get('baseline_diagnostics', {})) != set(EXTRA):
            raise RunnerError('Incomplete accepted diagnostic manifest')
        from .auto_ng import _full
        evidence = value['evidence']
        end = value['baseline']['checkpoint']+2*value['completed_pairs']
        if (not _full(evidence) or evidence['checkpoint'] != end or
                [r['global_iteration'] for r in evidence['records']] != [end-1, end]):
            raise RunnerError('The saved pair lacks consecutive full verification evidence')
        owner = _path(model, value['owner'])
        old = auto_history._read(owner/'result.json')
        action_path = _path(model, value['owner_action'])
        action = auto_history._read(action_path/'action.json')
        if (old.get('status') not in {'cancelled', 'timeout', 'stopped'} or old.get('recovery_error') or
                action_path.parent != owner or action.get('policy_id') != 'global_ng' or
                action.get('evidence') != value['baseline'] or action.get('trial_outcome') != 'aborted'):
            raise RunnerError('Only safely interrupted, rolled-back trials can resume')
        pair_owner = auto_history._read(_path(model, value['pair_owner'])/'result.json')
        if not any(a.get('status') == 'succeeded' and a.get('evidence') == evidence and
                   a.get('global_ng_check', {}).get('pair') == value['completed_pairs']
                   for a in pair_owner.get('attempts', [])):
            raise RunnerError('The source journal does not confirm the completed pair')
        if value['baseline_identity'] != auto_history.identity(model, plan):
            raise RunnerError('The accepted baseline changed; do not rewind newer progress')
        from .runner_auto import RECOVERY_NAMES
        if set(value['candidate_hashes']) != set((*RECOVERY_NAMES, *EXTRA)):
            raise RunnerError('Incomplete provisional snapshot manifest')
        candidate = _candidate(model, value['candidate'])
        for name, digest in value['candidate_hashes'].items():
            if Path(name).name != name or auto_history.digest(candidate/name) != digest:
                raise RunnerError('The saved provisional pair changed or is incomplete')
        folder = _path(model, value['baseline_folder'])
        if any(auto_history.digest(folder/('baseline-'+n)) != h for n, h in value['baseline_diagnostics'].items()):
            raise RunnerError('Accepted baseline diagnostics changed')
        remaining = 6-2*value['completed_pairs']
        if (plan['auto']['max_iterations'] < remaining+3 or
                plan['auto']['max_attempts'] < (remaining//2)+1):
            raise RunnerError('Insufficient budget to finish the resumed trial and independent verification')
        return {'usable': True, 'state': value}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return {'usable': False, 'reason': str(exc)}


def activate(model, plan, value, journal, *, action_directory):
    """Restore the saved pair; caller already retained the conservative baseline."""
    from .runner import _json, _publish
    from .runner_auto import _restore
    from .workflow_permissions import mkdir_readable
    from .auto_ng import trial_decision
    candidate = _candidate(model, value['candidate'])
    decision = replace(trial_decision(value['baseline'], global_trial=True), policy_id='global_ng')
    action_dir = Path(action_directory)
    if action_dir.parent != journal or not re.fullmatch(r'action-\d{3}', action_dir.name):
        raise RunnerError('Invalid resume action directory')
    mkdir_readable(action_dir)
    record = {'kind': 'global_ng', 'policy_id': 'global_ng', 'reversible_trial': True,
              'directory': str(action_dir), 'status': 'planned', 'evidence': value['baseline'],
              'reason': 'Resume verified provisional pairs without repeating extrapolation',
              'resumed_from': value['owner'], 'completed_pairs': value['completed_pairs']}
    # Register ownership before publishing any checkpoint byte. The controller's
    # final rollback covers interruption during restoration as well.
    _json(action_dir/'action.json', record)
    updated = {**value, 'resumes': value['resumes']+1, 'owner': str(journal.relative_to(model)),
               'owner_action': str(action_dir.relative_to(model))}
    _json(model/'.cmfgen-runs'/NAME, updated)
    _restore(model, candidate, report_directory=journal)
    for name in EXTRA:
        _publish(candidate/name, model/name)
    if auto_history.identity(model, plan) != value['candidate_identity']:
        raise RunnerError('Restored provisional pair identity does not match its saved state')
    record['status'] = 'applied'
    _json(action_dir/'action.json', record)
    return decision, record, updated


def restore_diagnostics(model, state):
    from .runner import _publish
    if set(state['baseline_diagnostics']) != set(EXTRA):
        raise RunnerError('Invalid accepted diagnostic file names')
    folder = _path(model, state['baseline_folder'])
    for name, expected in state['baseline_diagnostics'].items():
        source = folder/('baseline-'+name)
        if auto_history.digest(source) != expected:
            raise RunnerError('Cannot restore changed baseline diagnostics')
        _publish(source, model/name)


def retire(model):
    path = model/'.cmfgen-runs'/NAME
    if path.is_symlink():
        raise RunnerError('Unsafe provisional trial pointer')
    if path.exists():
        value = auto_history._read(path)
        candidate = _candidate(model, value['candidate'])
        path.unlink()
        if candidate.exists():
            shutil.rmtree(candidate)
