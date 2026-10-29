"""Invocation-specific numerical evidence for the optional main-stage controller.

Decisions use raw corrections, never small applied steps alone. No binary
checkpoint layout or atomic-model semantics are assumed here.
"""
from array import array
from collections import deque
import math
import re

from .control_files import control_occurrences
from .model_convergence import (ITERATION_RE, SOLVER_CHANGE_RE,
                               _parse_iteration_records, _correction_summary)
from .model_quality import inspect_quality
from .native_diagnostics import latest_main_log
from .parsers.common import parse_float_token
from .runner_recipe import RunnerError, snapshot
from .runner_restart import inspect_restart
from .runner_validation import validate_rvtj_core


def control_value(model, filename, key, default=None, *, exact_key=False):
    path = model / filename
    if not path.exists():
        return default
    if path.stat().st_size > 1024 * 1024:
        raise RunnerError(f"Oversized control file: {filename}")
    rows = control_occurrences(path.read_text()).get(key.upper(), [])
    if len(rows) > 1:
        raise RunnerError(f"Ambiguous [{key}] in {filename}")
    if exact_key and rows and rows[0]['source_key'] != key:
        return default  # Native RD_STORE compares case-sensitive key strings.
    return rows[0]['value'] if rows else default


def number(model, filename, key, default=None):
    value = control_value(model, filename, key)
    if value is None:
        return default
    parsed = parse_float_token(str(value))
    if parsed is None or not math.isfinite(parsed):
        raise RunnerError(f"Invalid numeric [{key}] in {filename}")
    return parsed


def temperatures(model):
    """Read the small temperature vector, without requiring a plot/parser payload."""
    path = model / 'RVTJ'
    if not path.is_file():
        return []
    values, active = [], False
    with path.open() as stream:
        for line in stream:
            if re.match(r'^\s*Temperature(?:\s.*)?$', line, re.I):
                active = True
                continue
            if active and line.strip():
                row = [parse_float_token(t) for t in line.split()]
                if not row or any(v is None for v in row):
                    break
                values.extend(row)
    return values


def correction_counts(model):
    path = model / 'CORRECTION_SUM'
    if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise RunnerError('Missing or oversized CORRECTION_SUM')
    lines = path.read_text().splitlines()
    nt = next((int(m[1]) for l in lines if (m := re.search(r'\bNT\s*=\s*(\d+)', l))), None)
    header = next((i for i, l in enumerate(lines) if l.split()[:1] == ['Depth']), None)
    if nt is None or nt < 1 or header is None:
        raise RunnerError('Unrecognized CORRECTION_SUM header')
    labels = lines[header].split()[1:]
    thresholds = [parse_float_token(label.removesuffix('%')) for label in labels]
    if (not thresholds or any(t is None or not math.isfinite(t) or t <= 0 for t in thresholds)
            or thresholds != sorted(set(thresholds), reverse=True)):
        raise RunnerError('Invalid CORRECTION_SUM thresholds')
    rows = []
    for line in lines[header + 1:]:
        tokens = line.split()
        if not tokens:
            continue
        if len(tokens) != len(labels) + 1 or not all(t.isdigit() for t in tokens):
            raise RunnerError('Incomplete or malformed CORRECTION_SUM')
        row = list(map(int, tokens))
        if any(c < 0 or c > nt for c in row[1:]) or row[1:] != sorted(row[1:]):
            raise RunnerError('Invalid CORRECTION_SUM counts')
        rows.append(row)
    nd = number(model, 'MODEL_SPEC', 'ND')
    if nd is None or [r[0] for r in rows] != list(range(1, int(nd) + 1)):
        raise RunnerError('Incomplete CORRECTION_SUM depth grid')
    return {'nt': nt, 'nd': int(nd), 'totals': {label: sum(r[i+1] for r in rows)
                                             for i, label in enumerate(labels)}}


def raw_temperature_steps(path, offset, nt, nd):
    """Stream only new solution sections; bound work for pathological huge logs."""
    if not path.is_file():
        return []
    size = path.stat().st_size
    offset = offset if offset <= size else 0
    start = max(offset, size - 128 * 1024 * 1024)
    result = deque(maxlen=8)
    current = None
    prefix = str(nt).encode() + b'('
    with path.open('rb') as stream:
        if start:
            stream.seek(start - 1)
            if stream.read(1) != b'\n':
                stream.readline()  # Discard a partial line only.
        else:
            stream.seek(0)
        for line in stream:
            if line.strip() == b'STEQ SOLUTION ARRAY':
                current = [None] * nd
            elif current is not None and line.lstrip().startswith(prefix):
                m = re.match(rb'\s*\d+\(\s*(\d+)\)#\s*(.*)', line)
                if not m:
                    continue
                index = int(m[1]) - 1
                values = [parse_float_token(t.decode()) for t in m[2].split()]
                if index < 0 or index + len(values) > nd or any(v is None or not math.isfinite(v) for v in values):
                    current = None
                    continue
                current[index:index+len(values)] = [-100 * v for v in values]
                if all(v is not None for v in current):
                    result.append(current)
                    current = None
    return list(result)



def population_cycle(path, offset, nt, nd, epsilon):
    """Measure repeated raw population sign reversals without storing large logs.

    Require three complete solution arrays. A truncated tail, duplicate row,
    nonfinite value or unsupported size cannot authorize a remedy. These
    diagnostic thresholds never change the all-variable convergence criterion.
    """
    if not path.is_file() or nt < 3 or nd < 1 or nt * nd > 2_000_000:
        return None
    size = path.stat().st_size
    start = max(offset if offset <= size else 0, size - 128 * 1024**2)
    recent = deque(maxlen=3)
    current = seen = None
    count = 0
    pattern = re.compile(rb'\s*(\d+)\(\s*(\d+)\)#\s*(.*)')
    with path.open('rb') as stream:
        if start:
            stream.seek(start - 1)
            if stream.read(1) != b'\n':
                stream.readline()
        for line in stream:
            if line.strip() == b'STEQ SOLUTION ARRAY':
                current = array('d', [0.0]) * (nt * nd)
                seen = bytearray(nt * nd)
                count = 0
                continue
            if current is None:
                continue
            match = pattern.fullmatch(line.rstrip(b'\r\n'))
            if not match:
                continue
            variable, depth = int(match[1]), int(match[2])
            values = [parse_float_token(t.decode('ascii', errors='replace')) for t in match[3].split()]
            index = (variable - 1) * nd + depth - 1
            if (not 1 <= variable <= nt or not 1 <= depth <= nd or not values or
                    depth - 1 + len(values) > nd or any(seen[index:index+len(values)]) or
                    any(v is None or not math.isfinite(v) for v in values)):
                current = None
                recent.clear()  # Never bridge an invalid solution section.
                continue
            current[index:index+len(values)] = array('d', [-100*v for v in values])
            seen[index:index+len(values)] = bytes([1]) * len(values)
            count += len(values)
            if count == nt * nd:
                recent.append(current)
                current = None
    if len(recent) != 3:
        return None
    # Incomplete final sections cannot establish the final solved state.
    if current is not None:
        return None
    maxima = [max(abs(v) for v in row) for row in recent]
    if max(maxima) > 1.0:
        return None  # Only the small-correction tail has an established remedy.
    affected = []
    for i, (a, b, c) in enumerate(zip(*recent)):
        if i >= (nt - 2) * nd:  # Ne and T have separate diagnostics.
            break
        if (a*b < 0 and b*c < 0 and abs(c) >= epsilon and
                min(abs(a), abs(b)) >= .1*epsilon and abs(c) >= .8*abs(a)):
            affected.append(i % nd + 1)
    if not affected:
        return None
    return {'coordinates': len(affected), 'depth_start': min(affected),
            'depth_end': max(affected), 'raw_maxima_percent': maxima,
            'complete_solution_arrays': 3}


def ng_accelerations(text):
    """Return solved counters followed by explicit successful native Ng steps.

    CMFGEN saves another checkpoint and increments MAIN_COUNTER for Ng,
    without printing another radiation-iteration header. Failed attempts and
    unexplained counter gaps must not be interpreted as successful steps.
    """
    result, current, solved = [], None, False
    for line in text.splitlines():
        match = ITERATION_RE.search(line)
        if match:
            current, solved = int(match[1]), False
        match = SOLVER_CHANGE_RE.search(line)
        if match:
            value = parse_float_token(match[1])
            solved = value is not None and math.isfinite(value)
        if re.fullmatch(r'\s*NG Acceleration performed using NG_BAND=\s*\d+\s*', line):
            if current is None or not solved or current in result:
                raise RunnerError('Ambiguous native Ng completion evidence')
            result.append(current)
    return result


def assess(model, run, before, solution_offset, requested, *, hydro_revisions=()):
    """Reject stale or ambiguous evidence rather than declaring success."""
    for name in ('OUTGEN', 'CORRECTION_SUM', 'RVTJ'):
        if snapshot(model / name) == before.get(name):
            raise RunnerError(f'{name} was not refreshed by this attempt')
    from datetime import datetime
    started = datetime.fromisoformat(run['started_at']).timestamp()
    return _assess_outputs(model, solution_offset, requested, hydro_revisions, started)


def _assess_outputs(model, solution_offset, requested, hydro_revisions, started):
    from .runner import _tail
    validate_rvtj_core(model / 'RVTJ', model / 'MODEL_SPEC', finite_all=True)
    restart = inspect_restart(model)
    if restart['mode'] != 'continuation' or restart['errors']:
        raise RunnerError('No usable continuation checkpoint after the attempt')
    text = latest_main_log(_tail(model / 'OUTGEN', 32 * 1024 * 1024))
    records = _parse_iteration_records(text)
    if not records:
        raise RunnerError('No native iteration evidence; refusing an automatic restart')
    counters = [r['global_iteration'] for r in records]
    ng = ng_accelerations(text)
    adjusted_counters = set(hydro_revisions) | set(ng)

    def saved_counter(counter):
        return counter + (counter in hydro_revisions) + (counter in ng)

    expected = [saved_counter(a) + 1 for a in counters[:-1]]
    if (counters[1:] != expected or adjusted_counters - set(counters) or
            restart['pointer']['iterations'] != saved_counter(counters[-1])):
        raise RunnerError('Saved checkpoint and completed solver iterations do not agree')
    full = [r for r in records if not r.get('lambda_iteration') and not r.get('temperature_fixed')]
    eps = number(model, 'VADAT', 'EPS_TERM')
    if eps is None or eps <= 0:
        raise RunnerError('Automatic convergence requires a positive explicit [EPS_TERM]')
    counts = correction_counts(model)
    steps = (raw_temperature_steps(model / 'STEQ_VALS', solution_offset, counts['nt'], counts['nd'])
             if solution_offset is not None else [])
    # Match only complete printed vectors to the corresponding final records.
    thermal = []
    for record, vector in zip(records[-len(steps):] if steps else [], steps):
        if not record.get('lambda_iteration') and not record.get('temperature_fixed'):
            thermal.append(vector)
    def converged(r):
        values = [r.get(k) for k in ('solver_maximum_change', 'maximum_increase_percent', 'maximum_decrease_percent')]
        return all(v is not None and math.isfinite(v) and abs(v) < eps for v in values)
    candidate = (len(records) >= 2 and all(not r.get('lambda_iteration') and
                 not r.get('temperature_fixed') and converged(r) for r in records[-2:]))
    candidate = candidate and all(total == 0 for label, total in counts['totals'].items()
                                  if float(label.removesuffix('%')) >= eps)
    candidate = candidate and not any(r['global_iteration'] in adjusted_counters
                                      for r in records[-2:])
    quality = inspect_quality(model, records, text, started, requested,
                              _correction_summary(model, started))
    return {'records': records, 'full_iterations': len(full), 'iterations': len(records),
            'checkpoint': restart['pointer']['iterations'], 'hydro_revisions': list(hydro_revisions),
            'ng_accelerations': ng,
            'epsilon_percent': eps,
            'candidate': candidate, 'fresh_verified': candidate and all(r.get('ba_computed') for r in records[-2:]),
            'population_cycle': (population_cycle(model/'STEQ_VALS', solution_offset, counts['nt'], counts['nd'], eps)
                                 if solution_offset is not None and len(records) >= 3 and
                                 all(r in full for r in records[-3:]) and not adjusted_counters else None),
            'counts': counts, 'raw_temperature_steps': thermal, 'temperatures': temperatures(model),
            'quality': quality}


def oscillating_region(evidence, history, *, localized_only=True):
    """Locate a persistent cycle, excluding already shrinking modes."""
    nd = evidence['counts']['nd']
    vectors = evidence['raw_temperature_steps'][-5:]
    if len(vectors) < 3:
        profiles = [e['temperatures'] for e in history[-4:]]
        if len(profiles) >= 4 and all(len(t) == nd for t in profiles):
            vectors = [[100*(b/a-1) for a,b in zip(prev, cur)]
                       for prev,cur in zip(profiles, profiles[1:])]
    affected = []
    if len(vectors) >= 3:
        for depth in range(nd):
            values = [v[depth] for v in vectors]
            flips = sum(a*b < 0 for a,b in zip(values, values[1:]))
            if (flips >= 2 and min(abs(v) for v in values[-3:]) > max(evidence['epsilon_percent'], 0.05)
                    and abs(values[-1]) >= 0.6 * abs(values[0])):
                affected.append(depth+1)
    if affected and (not localized_only or max(affected)-min(affected)+1 <= max(1, nd//3)):
        return [min(affected), max(affected)]
    return None


def recovery_action(run):
    """Whitelisted post-exit recovery; generic crashes never imply cache corruption."""
    text = '\n'.join(str(p.get('diagnostic_tail', '')) for p in run.get('passes', []))
    if re.search(r'incorrect reading of EDDFACTOR\b', text, re.I):
        return 'radiation_cache'
    return None


def assess_existing(model):
    """Timestamp-screened historical evidence, never invocation/acceptance proof."""
    from .model_convergence import _read_limited_tail, _run_segments, _parse_run_started_epoch
    from .model_editor import model_inputs_modified_since_solution
    from .auto_hydro import revisions
    text, _ = _read_limited_tail(model/'OUTGEN', 32 * 1024**2)
    runs = _run_segments(text)
    started = _parse_run_started_epoch(runs[-1][0]) if runs else None
    if started is None or started > (model/'OUTGEN').stat().st_mtime + 2:
        raise RunnerError('No reliable latest native start timestamp; numerical policy checks need more provenance')
    for name in ('RVTJ', 'CORRECTION_SUM', 'MOD_SUM'):
        path = model/name
        if not path.is_file() or path.stat().st_mtime + 2 < started:
            raise RunnerError(f'{name} is missing or predates the latest native start')
    with (model/'MOD_SUM').open(errors='replace') as handle:
        if 'Model Finalized on:' not in handle.read(16384):
            raise RunnerError('MOD_SUM does not establish a completed run')
    if model_inputs_modified_since_solution(model):
        raise RunnerError('Inputs were edited after the solution; review historical evidence manually')
    anchor = max((model/name).stat().st_mtime for name in ('OUTGEN', 'MOD_SUM', 'RVTJ'))
    controls = ['VADAT', 'MODEL_SPEC', 'ADJUST_CORRECTIONS', 'RVSIG_COL', 'HYDRO_DEFAULTS']
    controls += [p.name for p in model.glob('*_IN')]
    if any((model/name).is_file() and (model/name).stat().st_mtime > anchor+2 for name in controls):
        raise RunnerError('A current input is newer than the saved solution')
    evidence = _assess_outputs(model, None, 0, revisions(runs[-1][1]), started)
    evidence['fresh_verified'] = False  # Historical evidence cannot certify an independent verification phase.
    return evidence


def convergence_status(evidence, *, historical=False):
    """Describe numerical evidence independently of physical-quality warnings."""
    records = evidence['records'][-2:]
    eps = evidence['epsilon_percent']
    # Native termination uses the ranked SOLVEBA metric. Report that criterion
    # separately from the controller's stricter two-step raw acceptance rule.
    native = len(records) == 2 and all(
        not r.get('lambda_iteration') and not r.get('temperature_fixed') and
        r['global_iteration'] not in evidence.get('hydro_revisions', []) and
        r.get('solver_maximum_change') is not None and
        math.isfinite(r['solver_maximum_change']) and abs(r['solver_maximum_change']) < eps
        for r in records)
    latest_raw = bool(records) and all(
        records[-1].get(k) is not None and math.isfinite(records[-1][k]) and abs(records[-1][k]) < eps
        for k in ('maximum_increase_percent', 'maximum_decrease_percent'))
    counts_ok = all(total == 0 for label, total in evidence['counts']['totals'].items()
                    if float(label.removesuffix('%')) >= eps)
    candidate = native and latest_raw and counts_ok
    fresh = all(r.get('ba_computed') for r in records)
    if candidate and fresh:
        status, label = 'converged', 'Numerically converged (native criterion) — fresh Jacobians'
    elif candidate:
        status, label = 'candidate', 'Convergence candidate — fresh-Jacobian verification needed'
    else:
        status, label = 'not_converged', 'Numerical convergence not reached'
    detail = (f"Final two full steps evaluated against the native ranked tolerance and the latest raw corrections checked against EPS_TERM={evidence['epsilon_percent']:g}%; "
              f"saved checkpoint {evidence['checkpoint']}.")
    if historical:
        detail += ' Based on timestamp-screened saved outputs; the original invocation and independent verification phase are unconfirmed.'
    detail += ' Physical-quality warnings are assessed separately.'
    return {'status': status, 'label': label, 'detail': detail}
