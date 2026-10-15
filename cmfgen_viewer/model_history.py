"""Model-scoped archive inventory, control provenance, and reviewed housekeeping."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import uuid

from .model_editor import (
    EDITABLE_MODEL_FILES, MODEL_EDITOR_BACKUP_DIR, MODEL_PARAMETER_MAX_BYTES,
    ModelEditorError, _decode_text,
)
from .model_activity import model_mutation_guard
from .model_staging import MODEL_WRITE_LOCK
from .recovery_files import compact_recovery, RECOVERY_FILE_LIMIT, DIAGNOSTIC_FILES
from .workflow_permissions import open_readable

RUNS = '.cmfgen-runs'
BACKUPS = MODEL_EDITOR_BACKUP_DIR
BACKUP_LABELS = {'lte-hydro': 'LTE / Hydro promotion', 'lte-cleanup': 'LTE cleanup',
                 'hydro-alignment': 'Hydro alignment', 'history-restore': 'Restart recovery'}
BACKUP_GROUPS = set(BACKUP_LABELS)
STAGES = {'main', 'test', 'lte', 'hydro', 'continuum', 'flux-10', 'flux-15', 'flux-20'}


class HistoryError(ModelEditorError):
    pass


def safe_path(model, relative):
    """Archives must stay under this model and have no symlink components."""
    relative = Path(relative)
    if relative.is_absolute() or not relative.parts or '..' in relative.parts:
        raise HistoryError('Invalid archive path.')
    if not any(part in {RUNS, BACKUPS} for part in relative.parts[:2]):
        raise HistoryError('Path is not a model recovery archive.')
    if relative.parts[0] not in {RUNS, BACKUPS} and relative.parts[0] not in {'lte', 'obs'}:
        raise HistoryError('Invalid workspace archive path.')
    path = model
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise HistoryError('Archive symlinks cannot be followed.')
    if not path.exists():
        raise HistoryError('Archived file or directory no longer exists.')
    return path


def _json(path):
    try:
        if path.is_symlink() or path.stat().st_size > 8 * 1024 * 1024:
            return {}
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def _tree(path):
    """Metadata only: size large scientific files without reading their contents."""
    rows = []
    paths = [path]
    while paths:
        item = paths.pop()
        info = item.lstat()
        kind = 'link' if stat.S_ISLNK(info.st_mode) else 'directory' if stat.S_ISDIR(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode) else 'special'
        rows.append({'path': item.relative_to(path).as_posix() if item != path else '.',
                     'kind': kind, 'size': info.st_size, 'mtime_ns': info.st_mtime_ns,
                     'ctime_ns': info.st_ctime_ns, 'device': info.st_dev, 'inode': info.st_ino,
                     'mode': info.st_mode, 'links': info.st_nlink})
        if kind == 'directory':
            paths.extend(sorted(item.iterdir(), reverse=True))
    return sorted(rows, key=lambda row: row['path'])


def tree_signature(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def _created(path, result):
    try:
        value = result.get('finished_at') or result.get('started_at')
        if value:
            parsed = datetime.fromisoformat(value)
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (ValueError, TypeError):
        pass
    stamp = re.search(r'(\d{8}T\d{6})(?:\.(\d+))?Z', path.name)
    if stamp:
        try:
            return datetime.strptime(stamp[1], '%Y%m%dT%H%M%S').replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)


def _archive_roots(model):
    for workspace in ('', 'lte', 'obs'):
        for folder in (RUNS, BACKUPS):
            relative = Path(workspace) / folder
            root = model / relative
            if root.is_symlink() or not root.is_dir() or (workspace and (model / workspace).is_symlink()):
                continue
            yield relative, root


def _describe(path, model, kind):
    rows = _tree(path)
    plan, result = (_json(path / 'plan.json'), _json(path / 'result.json')) if path.is_dir() else ({}, {})
    created = _created(path, result).astimezone(timezone.utc)
    options = plan.get('stage_options')
    policy = plan.get('keep_large_files', options.get('keep_large_files') if isinstance(options, dict) else None)
    compaction = _json(path / '.recovery-compaction.json') if path.is_dir() else {}
    compacted = bool(compaction)
    if policy is None and path.is_dir():
        policy = _json(path / 'restore.json').get('keep_large_files')
    return {'id': path.relative_to(model).as_posix(), 'kind': kind,
        'name': path.name, 'created': created.isoformat(),
        'created_label': created.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
        'age_days': max(0, (datetime.now(timezone.utc) - created).days),
        'size': sum(row['size'] for row in rows if row['kind'] == 'file'),
        'count': sum(row['kind'] != 'directory' for row in rows),
        'status': str(result.get('status', 'Saved')).replace('_', ' ').capitalize(), 'stage': plan.get('stage', ''),
        'policy': 'Partly compacted' if compacted and compaction.get('warnings') else 'Compacted' if compacted else 'Full-size' if policy is True else 'Compact' if policy is False else 'Unrecorded',
        'signature': tree_signature(rows)}


def list_archives(model):
    entries, warnings = [], []
    for relative, root in _archive_roots(model):
        try:
            if root.name == RUNS:
                candidates = [(child, 'Runner journal') for child in root.iterdir() if child.is_dir() and not child.is_symlink()]
            else:
                candidates = []
                for folder, dirs, names in os.walk(root, followlinks=False):
                    directory = Path(folder)
                    dirs[:] = [name for name in dirs if not (directory / name).is_symlink()]
                    if directory == root:
                        for group in BACKUP_GROUPS:
                            if group in dirs:
                                candidates.extend((child, BACKUP_LABELS[group])
                                                  for child in (root / group).iterdir()
                                                  if child.is_dir() and not child.is_symlink())
                                dirs.remove(group)
                    candidates.extend((directory / name, 'Editor checkpoint') for name in names
                                      if name.endswith('.bak') and not (directory / name).is_symlink())
            for path, kind in candidates:
                try:
                    entries.append(_describe(path, model, kind))
                except (OSError, ValueError) as exc:
                    warnings.append(f'Could not inspect {path.relative_to(model)}: {exc}')
        except OSError as exc:
            warnings.append(f'Could not list {relative}: {exc}')
    return sorted(entries, key=lambda entry: entry['created'], reverse=True), warnings


def get_archive(model, archive_id):
    path = safe_path(model, archive_id)
    parts = Path(archive_id).parts
    local = parts[1:] if parts[0] in {'lte', 'obs'} else parts
    if local[0] == RUNS and len(local) == 2 and path.is_dir():
        kind = 'Runner journal'
    elif local[0] == BACKUPS and len(local) == 3 and local[1] in BACKUP_GROUPS and path.is_dir():
        kind = BACKUP_LABELS[local[1]]
    elif (local[0] == BACKUPS and path.is_file() and path.name.endswith('.bak')
          and not any(part in BACKUP_GROUPS for part in local[1:-1])):
        kind = 'Editor checkpoint'
    else:
        raise HistoryError('Select a recognized recovery archive.')
    return path, _describe(path, model, kind)


def control_target(model, archive_id, archived_file):
    """Infer only known control locations; never guess a scientific product's target."""
    archive = Path(archive_id)
    member = Path(archived_file)
    prefix = archive.parts[0] if archive.parts[0] in {'lte', 'obs'} else ''
    local = archive.parts[1:] if prefix else archive.parts
    if local[0] == BACKUPS and archive.name.endswith('.bak'):
        match = re.fullmatch(r'(.+)\.\d{8}T\d{6}(?:\.\d+)?Z\.[0-9a-f]+\.bak', archive.name)
        if not match:
            return None
        relative = Path(*local[1:-1]) / match[1]
    elif local[0] == BACKUPS:
        group = local[1] if len(local) > 1 else ''
        if group == 'lte-hydro':
            relative = member
        elif group == 'hydro-alignment' and member.as_posix() == 'HYDRO_PARAMS':
            relative = Path('lte/HYDRO_PARAMS')
        else:
            return None
    else:
        parts = list(member.parts)
        if not parts:
            return None
        if parts[0] == 'inputs':
            relative = Path(*parts[1:]) if len(parts) > 1 else Path('.')
        elif parts[0] == 'effective' and len(parts) == 2:
            plan = _json(model / archive / 'plan.json')
            relative = Path('lte' if plan.get('stage') in {'lte', 'hydro'} else '') / parts[1]
        elif parts[0] in STAGES:
            stage = parts.pop(0)
            if parts and parts[0] == 'before':
                parts.pop(0)
            if len(parts) != 1:
                return None
            relative = Path('lte' if stage in {'lte', 'hydro'} else 'obs' if stage.startswith('flux') or stage == 'continuum' else '') / parts[0]
        else:
            return None
    target = (Path(prefix) / relative).as_posix()
    # lte/ has its own allowlisted editor, accessed through the model toolbar.
    local_target = target.removeprefix('lte/') if target.startswith('lte/') else target
    if local_target not in EDITABLE_MODEL_FILES:
        return None
    current = model / target
    if current.is_symlink() or any(parent.is_symlink() for parent in current.parents if parent != model.parent and parent.is_relative_to(model)):
        return None
    return target if current.is_file() and current.stat().st_size <= MODEL_PARAMETER_MAX_BYTES else None


def archive_files(model, archive_id):
    path, entry = get_archive(model, archive_id)
    rows = _tree(path)
    files = []
    for row in rows:
        if row['kind'] == 'directory':
            continue
        relative = archive_id if path.is_file() else (Path(archive_id) / row['path']).as_posix()
        target = control_target(model, archive_id, row['path']) if row['kind'] == 'file' and row['size'] <= MODEL_PARAMETER_MAX_BYTES else None
        files.append({**row, 'archive_path': relative, 'target': target})
    return entry, files


def load_archived_control(model, archive_id, archived_file, expected_target=None):
    entry, files = archive_files(model, archive_id)
    row = next((row for row in files if row['archive_path'] == archived_file and row['target']), None)
    if row is None or (expected_target is not None and row['target'] != expected_target):
        raise HistoryError('This archive does not contain a restorable version of the selected control file.')
    path = safe_path(model, archived_file)
    if path.stat().st_size > MODEL_PARAMETER_MAX_BYTES:
        raise HistoryError('Archived control exceeds the editor size limit.')
    contents = _decode_text(path.read_bytes())
    current = model / row['target']
    current_contents = _decode_text(current.read_bytes())
    diff = ''.join(difflib.unified_diff(current_contents.splitlines(True), contents.splitlines(True),
                    fromfile='Current ' + row['target'], tofile='Archived ' + archived_file))
    return {'name': path.name, 'contents': contents, 'warnings': [], 'backup_relpath': archived_file,
            'target': row['target'], 'diff': diff, 'archive_id': entry['id']}


def control_versions(model, target):
    entries, _ = list_archives(model)
    versions = []
    for entry in entries:
        _, files = archive_files(model, entry['id'])
        for row in files:
            if row['target'] == target:
                versions.append({'name': Path(row['archive_path']).name, 'backup_relpath': row['archive_path'],
                    'archive_id': entry['id'], 'modified_display': entry['created_label'],
                    'modified_ns': row['mtime_ns'], 'size': row['size'], 'kind': entry['kind']})
    return versions


def preview_housekeeping(model, archive_ids, action):
    if action not in {'compact', 'delete'} or not archive_ids or len(archive_ids) > 200:
        raise HistoryError('Select archives and a supported cleanup action (up to 200 at once).')
    entries, size = [], 0
    for archive_id in dict.fromkeys(archive_ids):
        path, entry = get_archive(model, archive_id)
        # Fingerprint all members, including links, so changed previews never authorize a new tree.
        rows = _tree(path)
        if any(row['kind'] == 'special' for row in rows):
            raise HistoryError('Archives containing special files cannot be cleaned here.')
        if action == 'delete':
            released = entry['size']
        else:
            released = sum(row['size'] - (RECOVERY_FILE_LIMIT if Path(row['path']).name in DIAGNOSTIC_FILES or Path(row['path']).suffix == '.log' else 0)
                           for row in rows if row['kind'] == 'file' and row['links'] == 1
                           and row['size'] > RECOVERY_FILE_LIMIT and Path(row['path']).suffix not in {'.json', '.jsonl'})
        entries.append({**entry, 'signature': tree_signature(rows), 'reclaimable': released})
        size += released
    return {'action': action, 'entries': entries, 'reclaimable': size}


def apply_housekeeping(model, review):
    with MODEL_WRITE_LOCK, model_mutation_guard(model, HistoryError):
        current = preview_housekeeping(model, [entry['id'] for entry in review['entries']], review['action'])
        if [(entry['id'], entry['signature']) for entry in current['entries']] != [(entry['id'], entry['signature']) for entry in review['entries']]:
            raise HistoryError('An archive changed after preview; review the cleanup again.')
        warnings = []
        for entry in current['entries']:
            path = safe_path(model, entry['id'])
            if review['action'] == 'delete':
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            elif path.is_dir():
                result = compact_recovery(path)
                warnings.extend(result['warnings'])
                temporary = path / ('.recovery-compaction-' + uuid.uuid4().hex + '.tmp')
                try:
                    with open_readable(temporary, 'x') as stream:
                        json.dump({'compacted_at': datetime.now(timezone.utc).isoformat(), **result}, stream)
                    os.replace(temporary, path / '.recovery-compaction.json')
                finally:
                    temporary.unlink(missing_ok=True)
            elif path.stat().st_size > RECOVERY_FILE_LIMIT:
                path.unlink()
        return warnings
