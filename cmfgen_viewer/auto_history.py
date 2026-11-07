"""Content-authenticated accepted trends for restart diagnosis, never convergence credit."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import stat

from .recovery_files import INPUT_FILES
from .runner_recipe import RunnerError
from .runner_restart import read_pointer

NAME = 'auto-history.json'
LIMIT = 8*1024**2
STATE = ('SCRTEMP', 'POINT1', 'POINT2', 'MODEL', 'RVTJ', 'MOD_SUM',
         'CORRECTION_SUM')
DIAGNOSTICS = ('OUTGEN', 'OBSFLUX', 'MEANOPAC', 'MOM_J_ERRORS')


def digest(path, *, external=False):
    path = Path(path)
    if path.is_symlink() and not external:
        raise RunnerError('Unsafe restart-history file: '+path.name)
    if not path.exists():
        return None
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > 2*1024**3:
        raise RunnerError('Unsupported restart-history file: '+path.name)
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            h.update(block)
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise RunnerError('File changed during restart-history inspection')
    return h.hexdigest()


def identity(model, plan):
    model = Path(model).resolve()
    names = set(STATE) | INPUT_FILES | {'atomic_links.json'}
    names.update(p.name for p in model.glob('*_IN') if p.name != 'T_IN')
    names.update(Path(r['path']).name for r in plan.get('local_atomic_files', []))
    roles = {link['name']: link['target'] for link in plan.get('links', []) if link['name'] != 'T_IN'}
    names.difference_update(roles)
    for name, target in roles.items():
        link = model/name
        if link.is_symlink() and link.resolve() != Path(target).resolve():
            raise RunnerError('Atomic link target changed: '+name)
    # File roles + contents allow a copied model, without trusting copied mtimes.
    return {'files': {n: digest(model/n) for n in sorted(names)},
            'executable': digest(plan['executable'], external=True),
            'atomic': {name: digest(target, external=True) for name, target in roles.items()},
            'external_inputs': {str(Path(r['path'])): digest(r['path'], external=True)
                                for r in plan.get('inputs', [])
                                if not Path(r['path']).is_relative_to(model)}}


def regime(value):
    value = {**value, 'files': {n: h for n, h in value['files'].items() if n not in STATE}}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1 or path.stat().st_size > LIMIT:
        raise RunnerError('Missing or unsafe accepted restart history')
    def finite(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('Nonfinite accepted history')
        return result
    def invalid(value):
        raise ValueError('Invalid JSON number in accepted history: '+value)
    return json.loads(path.read_text(), parse_float=finite, parse_constant=invalid)


def _history(rows, checkpoint):
    """Validate chronological accepted batches; transitions are hard boundaries."""
    if not isinstance(rows, list) or len(rows) > 8:
        raise RunnerError('Malformed restart history')
    previous = None
    result = []
    for original in rows:
        e = deepcopy(original)
        records = e['records']
        if (not records or e['iterations'] != len(records) or
                any(e.get(k) for k in ('hydro_revisions', 'ng_accelerations',
                    'checkpoint_updates', 'source_changed'))):
            raise RunnerError('Restart history crosses a physical transition')
        numbers = [r['global_iteration'] for r in records]
        if numbers != list(range(numbers[0], numbers[0]+len(numbers))) or numbers[-1] != e['checkpoint']:
            raise RunnerError('Nonconsecutive restart history')
        if previous is not None and numbers[0] != previous+1:
            raise RunnerError('Restart history has an iteration gap')
        previous = e['checkpoint']
        e['fresh_verified'] = False
        result.append(e)
    if result and previous != checkpoint:
        raise RunnerError('Restart history does not end at the selected checkpoint')
    return result


def load(model, plan, *, exclude=None):
    """Fail closed to fresh observations; diagnostic mismatch may be refreshed."""
    model = Path(model).resolve()
    try:
        if plan.get('fresh_start') or plan.get('initialization') or plan.get('restart', {}).get('mode') != 'continuation':
            raise RunnerError('Fresh initialization cannot reuse continuation history')
        if (model/'.cmfgen-runs').is_symlink():
            raise RunnerError('Unsafe restart-history archive')
        path = model/'.cmfgen-runs'/NAME
        if not path.exists() and not path.is_symlink():
            return _legacy(model, plan, exclude=exclude)
        value = _read(path)
        if value.get('version') != 1 or value['identity'] != identity(model, plan):
            raise RunnerError('Checkpoint, controls, atomic data or executable no longer match accepted history')
        checkpoint = read_pointer(model/'POINT1')['iterations']
        history = _history(value['history'], checkpoint)
        if value.get('raw_log') != digest(model/'STEQ_VALS'):
            for e in history:
                e['solution_start_offset'] = None
        actions = value.get('actions', [])
        if not isinstance(actions, list) or any(not isinstance(a, dict) for a in actions):
            raise RunnerError('Malformed accepted remedy history')
        if any(a.get('policy_id') != 'global_ng' or
               type(a.get('evidence', {}).get('checkpoint')) is not int or
               a.get('trial_outcome') not in {'accepted', 'rejected', 'aborted'} for a in actions):
            raise RunnerError('Invalid historical cooldown evidence')
        # Treat all saved decisions as historical. They can inform cooldowns,
        # but neither spend this invocation's budgets nor certify convergence.
        return {'usable': True, 'history': history, 'actions': actions,
                'checkpoint': checkpoint, 'source': value.get('journal'),
                'regime': regime(value['identity']),
                'refresh_required': value['diagnostics'] != {n: digest(model/n) for n in DIAGNOSTICS}}
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        return {'usable': False, 'reason': str(exc), 'history': [], 'actions': []}


def save(model, plan, history, actions, journal):
    """Caller holds the model guard and has committed this state as accepted."""
    from .runner import _json
    model = Path(model).resolve()
    parent = model/'.cmfgen-runs'
    if parent.is_symlink() or (parent/NAME).is_symlink():
        raise RunnerError('Unsafe restart-history destination')
    checkpoint = read_pointer(model/'POINT1')['iterations']
    rows = _history(history[-8:], checkpoint)
    compact_actions = [{k: a[k] for k in ('policy_id', 'evidence', 'trial_outcome') if k in a}
                       for a in actions if a.get('policy_id') == 'global_ng']
    # Only the starting counter is needed for a cooldown, not the seed descriptor.
    for a in compact_actions:
        a['evidence'] = {'checkpoint': a.get('evidence', {}).get('checkpoint')}
    value = {'version': 1, 'checkpoint': checkpoint, 'journal': str(journal),
             'identity': identity(model, plan), 'history': rows,
             'actions': compact_actions[-16:],
             'raw_log': digest(model/'STEQ_VALS'),
             'diagnostics': {n: digest(model/n) for n in DIAGNOSTICS}}
    encoded = json.dumps(value, allow_nan=False)
    if len(encoded.encode()) > LIMIT:
        raise RunnerError('Accepted restart history is too large')
    parent.mkdir(exist_ok=True)
    _json(parent/NAME, value)


def _legacy(model, plan, *, exclude=None):
    """Bridge older automatic journals only with their matching rolling recovery.

    Old large-file dependencies lack content hashes. They must still have the
    exact original filesystem fingerprint; moving/rebuilding those dependencies
    requires fresh evidence. Model/checkpoint copies are compared by contents.
    """
    from .runner_recipe import snapshot
    root = model/'.cmfgen-runs'
    if root.is_symlink() or not root.is_dir():
        raise RunnerError('No accepted automatic history')
    checkpoint = read_pointer(model/'POINT1')['iterations']
    folders = sorted((p for p in root.iterdir() if p.is_dir() and '-auto-' in p.name), reverse=True)
    for folder in folders[:40]:
        if exclude is not None and folder == Path(exclude):
            continue
        if folder.is_symlink():
            raise RunnerError('Unsafe automatic history archive')
        old = _read(folder/'result.json')
        if old.get('kind') != 'auto':
            continue
        if old.get('recovery_error'):
            raise RunnerError('Previous automatic state was not finalized safely')
        recovery_info = _read(folder/'recovery.json')
        recovery = folder/recovery_info['directory']
        if recovery.parent != folder or recovery.is_symlink():
            raise RunnerError('Unsafe accepted recovery directory')
        if digest(recovery/'SCRTEMP') != digest(model/'SCRTEMP'):
            raise RunnerError('Latest accepted recovery is not the selected checkpoint')
        for name in STATE:
            if digest(recovery/name) != digest(model/name):
                raise RunnerError('Accepted recovery differs: '+name)
        attempts = [a for a in old.get('attempts', []) if a.get('evidence') and
                    not a.get('checkpoint_restored') and not a.get('provisional_checkpoint_discarded') and
                    a['evidence'].get('checkpoint', checkpoint+1) <= checkpoint]
        if not attempts and not old.get('actions'):
            continue  # A stopped diagnostic-only restart did not advance the state.
        if not attempts or attempts[-1]['evidence']['checkpoint'] != checkpoint:
            raise RunnerError('No accepted evidence at the selected checkpoint')
        native_name = Path(attempts[-1]['journal']).name
        native = root/native_name
        if native.is_symlink() or native.parent != root:
            raise RunnerError('Unsafe native history archive')
        native_plan = _read(native/'plan.json')
        saved_exe = native_plan['executable_snapshot']
        current_exe = snapshot(Path(plan['executable']))
        if (saved_exe.get('sha256') != current_exe.get('sha256') or
                (not saved_exe.get('sha256') and saved_exe != current_exe)):
            raise RunnerError('Historical executable identity cannot be established')
        manifest = _read(native/'fresh-inputs.json')
        if not manifest.get('complete'):
            raise RunnerError('Historical input bundle is incomplete')
        saved_names = set()
        for record in manifest['files']:
            name = record['target']
            if Path(name).name != name or digest(model/name) != record['sha256']:
                raise RunnerError('Historical physical input differs: '+name)
            saved_names.add(name)
        required = {p.name for p in model.glob('*_IN') if p.name != 'T_IN'}
        if not required <= saved_names:
            raise RunnerError('An unrecorded population/source input was added')
        for dependency in manifest['dependencies']:
            path = Path(dependency['path'])
            if dependency.get('sha256'):
                if digest(path, external=True) != dependency['sha256']:
                    raise RunnerError('Historical atomic data changed')
            elif snapshot(path) != dependency:
                raise RunnerError('Historical atomic data identity cannot be established')
        # Also require the same declared atomic roles and targets. Otherwise
        # the current plan could select different unrecorded data.
        if {(r['name'], r['target']) for r in native_plan['links'] if r['name'] != 'T_IN'} != {
                (r['name'], r['target']) for r in plan['links'] if r['name'] != 'T_IN'}:
            raise RunnerError('Atomic role declarations changed')
        rows = []
        for entry in attempts:
            e = entry['evidence']
            if (entry.get('phase') not in {'iterate', 'verify'} or
                    any(e.get(k) for k in ('hydro_revisions', 'ng_accelerations',
                        'checkpoint_updates', 'source_changed'))):
                rows = []
                continue
            if rows and e['records'][0]['global_iteration'] != rows[-1]['checkpoint']+1:
                rows = []
            rows.append(e)
            if entry.get('decision', {}).get('kind') == 'action':
                rows = []
        rows = _history(rows[-8:], checkpoint)
        for e in rows:
            e['solution_start_offset'] = None  # Old raw logs may include discarded attempts.
        actions = [a for a in old.get('actions', []) if a.get('policy_id') == 'global_ng']
        actions = [{**a, 'trial_outcome': a.get('trial_outcome') or 'aborted'} for a in actions]
        return {'usable': True, 'history': rows, 'actions': actions,
                'checkpoint': checkpoint, 'source': str(folder), 'refresh_required': bool(rows),
                'legacy': True}
    raise RunnerError('No authenticated accepted history available')


def validate_refresh(model, before, checkpoint_before):
    """Output-only mode must produce radiation, never a population update."""
    from .auto_hydro import guard_measurements
    from .auto_ng import _energy
    from .model_convergence import _parse_iteration_records
    from .runner import _tail
    try:
        if any(digest(model/n) != h for n, h in checkpoint_before.items()):
            raise RunnerError('Output-only diagnostics changed a restart file')
        records = _parse_iteration_records(_tail(model/'OUTGEN', 32*1024**2))
        if not records or any(r.get('solver_maximum_change') is not None for r in records):
            raise RunnerError('Output-only diagnostics must not perform population solves')
        guard_measurements(model, before)
        from .auto_diagnostics import number
        _energy(model, int(number(model, 'MODEL_SPEC', 'ND')))
    except (OSError, ValueError) as exc:
        return [str(exc)]
    return []


def inputs_unchanged(model, plan, journal, *, ignore=(), require_complete=True):
    """Confirm run-start inputs/dependencies before promoting ordinary evidence."""
    from .runner_recipe import snapshot
    manifest = _read(Path(journal)/'fresh-inputs.json')
    if (require_complete and not manifest.get('complete')) or snapshot(Path(plan['executable'])) != plan['executable_snapshot']:
        return False
    for record in manifest['files']:
        if Path(record['target']).name != record['target']:
            return False
        if record['target'] not in ignore and digest(Path(model)/record['target']) != record['sha256']:
            return False
    for record in manifest['dependencies']:
        if record.get('sha256'):
            if digest(record['path'], external=True) != record['sha256']:
                return False
        elif snapshot(Path(record['path'])) != record:
            return False
    return True
