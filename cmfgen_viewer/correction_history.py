"""Bounded, read-only convergence plot history; never input to convergence acceptance."""
import json
from html import escape
import math
from pathlib import Path
import re

from .model_convergence import _convergence_plots, _parse_iteration_records, _run_segments
from .model_history import safe_path, HistoryError

MAX_RUNS = 250
MAX_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 5000
METRICS = ('solver_maximum_change', 'maximum_increase_percent',
           'maximum_decrease_percent', 'spectrum_latest_change_percent')
RUN_ID = re.compile(r'^\d{8}T\d{6}Z-(?:auto-)?[a-f0-9]{8}$')


def _finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _records(values):
    result = []
    if not isinstance(values, list):
        return result
    for value in values[:MAX_RECORDS]:
        if not isinstance(value, dict):
            continue
        iteration = value.get('global_iteration')
        solver = value.get('solver_maximum_change')
        if (type(iteration) is not int or not 0 <= iteration < 2**53 or
                not _finite_number(solver) or solver < 0):
            continue  # Do not display an incomplete solve as an archived correction.
        row = {'global_iteration':iteration, 'run_iteration':len(result)+1}
        for key in METRICS:
            number = value.get(key)
            if _finite_number(number) and number >= 0:
                row[key] = number
        luminosity = value.get('luminosity_difference_percent')
        if _finite_number(luminosity):
            row['luminosity_difference_percent'] = luminosity
        row['lambda_iteration'] = value.get('lambda_iteration') is True
        row['temperature_fixed'] = value.get('temperature_fixed') is True
        row['ba_computed'] = value.get('ba_computed') if type(value.get('ba_computed')) is bool else None
        result.append(row)
    return result


def _fingerprint(records):
    return json.dumps(records, sort_keys=True, allow_nan=False)


def correction_history(model):
    """Separate invocations retain their own traces, including rewinds/failed trials."""
    budget = MAX_BYTES
    limited = False

    def read(path, *, tail=False):
        nonlocal budget, limited
        try:
            if path.is_symlink() or not path.is_file():
                return ''
            size = path.stat().st_size
            count = min(size, MAX_FILE_BYTES, budget)
            if count < size:
                limited = True
                if not tail:
                    return ''
            if count <= 0:
                return ''
            with path.open('rb') as stream:
                if count < size:
                    stream.seek(size-count)
                    stream.readline()
                data = stream.read(count)
            budget -= len(data)
            return data.decode('utf-8', errors='replace')
        except OSError:
            return ''

    def archived(relative):
        try:
            return safe_path(model, relative)
        except HistoryError:
            return None

    def document(path):
        try:
            value = json.loads(read(path)) if path else {}
            return value if isinstance(value, dict) else {}
        except (ValueError, RecursionError):
            return {}

    current = _run_segments(read(model/'OUTGEN', tail=True))
    current_stamp = current[-1][0] if current else None
    current_rows = _records(_parse_iteration_records(current[-1][1])) if current else []
    current_fingerprint = _fingerprint(current_rows)
    chunks = {}

    def add(stamp, rows, label, status, phase=''):
        nonlocal limited
        if isinstance(rows, list) and len(rows) > MAX_RECORDS:
            limited = True
        rows = _records(rows)
        if not rows or ((stamp == current_stamp or stamp is None) and _fingerprint(rows) == current_fingerprint):
            return
        key = (stamp, _fingerprint(rows))
        chunks[key] = dict(records=rows, label=str(label)[:160],
                          status=status[:120] if isinstance(status, str) else 'unknown',
                          phase=phase[:120] if isinstance(phase, str) else '')

    for index, (stamp, text) in enumerate(current[:-1]):
        add(stamp, _parse_iteration_records(text), stamp or f'Earlier OUTGEN segment {index+1}', 'earlier OUTGEN')
    root = archived(Path('.cmfgen-runs'))
    folders = []
    if root and root.is_dir():
        folders = sorted((p for p in root.iterdir() if RUN_ID.fullmatch(p.name) and
                          not p.is_symlink() and p.is_dir()), key=lambda p:p.name)
        if len(folders) > MAX_RUNS:
            limited = True
        folders = folders[-MAX_RUNS:]
    overrides = {}
    for folder in reversed(folders):
        if '-auto-' not in folder.name:
            continue
        report = document(archived(Path('.cmfgen-runs')/folder.name/'result.json'))
        attempts = report.get('attempts', [])
        if not isinstance(attempts, list):
            continue
        attempts = attempts[:MAX_RUNS]
        rollback_start = None
        rollback = report.get('provisional_recovery_rolled_back')
        for index, attempt in enumerate(attempts):
            decision = attempt.get('decision') if isinstance(attempt, dict) else None
            if (rollback and isinstance(decision, dict) and decision.get('policy_id') == rollback and
                    decision.get('kind') == 'action' and decision.get('steps')):
                rollback_start = index
        for index, attempt in enumerate(attempts):
            if not isinstance(attempt, dict):
                continue
            # Foreign-machine absolute paths are labels only, never opened.
            name = str(attempt.get('journal', '')).replace('\\','/').rstrip('/').rsplit('/',1)[-1]
            evidence = attempt.get('evidence') or {}
            if RUN_ID.fullmatch(name) and isinstance(evidence, dict):
                overrides[name] = (evidence.get('records', []),
                    'rolled back' if attempt.get('checkpoint_restored') or
                        (rollback_start is not None and index >= rollback_start) else attempt.get('status', 'unknown'),
                    attempt.get('phase', ''))
    # Newest runs get priority when the byte limit is reached.
    names = sorted({p.name for p in folders if '-auto-' not in p.name} | set(overrides), reverse=True)
    if len(names) > MAX_RUNS:
        limited = True
    for name in names[:MAX_RUNS]:
        relative = Path('.cmfgen-runs')/name
        log = archived(relative/'main/OUTGEN')
        segments = _run_segments(read(log, tail=True)) if log else []
        override = overrides.get(name)
        metadata = document(archived(relative/'result.json')) if not override else {}
        status = override[1] if override else metadata.get('status', 'unknown')
        for index, (stamp, text) in enumerate(segments):
            last = index == len(segments)-1
            rows = override[0] if override and _records(override[0]) and last else _parse_iteration_records(text)
            add(stamp, rows, name, status if last else 'earlier appended segment', override[2] if override and last else '')
        if override and not segments:
            add(None, override[0], name, status, override[2])
    data = []
    luminosity_data = []
    seen = set()
    record_count = 0
    run_count = 0
    for chunk in sorted(chunks.values(), key=lambda c:c['label'], reverse=True):
        rows = chunk['records']
        if record_count+len(rows) > MAX_RECORDS:
            limited = True
            continue
        record_count += len(rows)
        plots = _convergence_plots(rows)
        if not plots or not plots[0]['data']:
            continue
        run_count += 1
        by_iteration = {r['global_iteration']:r for r in rows}
        for plot in plots:
            destination = luminosity_data if plot['history_key'] == 'luminosity_data' else data
            for trace in plot['data']:
                name = trace['name']
                trace.update(name='Earlier: '+name, legendgroup='history:'+name,
                             showlegend=name not in seen, opacity=.5)
                seen.add(name)
                if 'line' in trace:
                    trace['line'] = {**trace['line'], 'dash':'dot', 'width':1.5}
                trace['customdata'] = [[escape(chunk['label']),escape(chunk['status']),escape(chunk['phase']),
                    'Lambda' if by_iteration[x]['lambda_iteration'] else 'full',
                    'fixed T' if by_iteration[x]['temperature_fixed'] else 'variable T'] for x in trace['x']]
                trace['hovertemplate'] = ('Run %{customdata[0]}<br>%{customdata[1]} %{customdata[2]}<br>'
                    'Iteration %{x}: %{customdata[3]}, %{customdata[4]}<br>'+name+'=%{y:.6g}<extra></extra>')
                destination.append(trace)
    return dict(data=data, luminosity_data=luminosity_data, run_count=run_count, record_count=record_count, limited=limited,
                note='Earlier runs are separate dotted traces; repeated iteration numbers can reflect restarts or rollback. '
                     'Archived failures are included and labeled. History does not change convergence assessment.')
