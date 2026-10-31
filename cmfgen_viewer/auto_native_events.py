"""Recognized checkpoint-only updates, separate from radiation solves."""
import re

from .control_files import control_occurrences
from .model_convergence import _parse_iteration_records
from .runner_recipe import RunnerError


def grid_revisions(process_text):
    result, counter, entered = [], None, False
    for line in process_text.splitlines():
        if 'Entering ADJUST_R_GRID_V4' in line:
            counter = None
            entered = True
        match = re.fullmatch(r'\s*Main counter:\s*(\d+)\s*', line)
        if match and entered:
            counter = int(match[1])
        if line.strip() == 'Adjusted R grid in ADJUST_R_GRID_V4':
            if counter is None or counter in result:
                raise RunnerError('Ambiguous radial-grid revision evidence')
            result.append(counter)
            counter = None
            entered = False
    return result


def checkpoint_updates(model, text, *, grids=(), grey_release=False):
    rows = control_occurrences((model/'VADAT').read_text())
    def enabled(key):
        return len(rows.get(key, [])) == 1 and rows[key][0]['value'].upper().strip('.') in {'T', 'TRUE'}
    events, grey_candidates = [], []
    headers = list(re.finditer(r'^\s*Current great iteration count is\s+(\d+)\s*$', text, re.M))
    for i, header in enumerate(headers):
        counter = int(header[1])
        block = text[header.start():headers[i+1].start() if i+1 < len(headers) else len(text)]
        record = _parse_iteration_records(block)[0]
        solved = isinstance(record.get('solver_maximum_change'), (int, float))
        kinds = []
        if counter in grids:
            if not solved or not enabled('REV_RGRID'):
                raise RunnerError('Radial-grid revision without an enabled completed solve')
            kinds.append('radial_grid')
        average = re.findall(r'Averaging of oscilating populations\s+performed on iteration\s+(\d+)', block)
        undo = re.findall(r'Last corrections undone for depths\s+(\d+)\s+to\s+(\d+)', block)
        if average or undo:
            if (not solved or len(average) > 1 or len(undo) > 1 or
                    (average and (not enabled('DO_AV') or int(average[0]) != counter+len(kinds))) or
                    (undo and (not enabled('DO_UNDO') or any(int(a) < 1 or int(b) < int(a) for a, b in undo)))):
                raise RunnerError('Ambiguous native averaging/undo evidence')
            # Both operations share AVERAGE_DONE and produce one saved update.
            # A later failed AVE_FLIPS overwrites AVERAGE_DONE from UNDO_IT;
            # in that case SOL is not committed and no counter is advanced.
            cancelled_undo = undo and not average and 'Error performing AV acceleration.' in block
            if cancelled_undo and not enabled('DO_AV'):
                raise RunnerError('Failed averaging without enabled native averaging')
            if not cancelled_undo:
                kinds.append('population_average' if average else 'population_undo')
        grey = re.findall(r'Iteration\s+\d+\s+--- Largest correction to T in GREY initialization loop is', block)
        if grey and grey_release and record.get('lambda_iteration') and solved and record['solver_maximum_change'] < 50:
            # Hydro can also invoke the same grey helper. Select the fixed-J
            # release only where one additional saved update is corroborated.
            from .auto_diagnostics import ng_accelerations
            from .auto_hydro import revisions
            from .runner_restart import read_pointer
            end = (int(headers[i+1][1])-1 if i+1 < len(headers)
                   else read_pointer(model/'POINT1')['iterations'])
            known = len(kinds) + (counter in revisions(text)) + (counter in ng_accelerations(text))
            if end-counter-known == 1:
                grey_candidates.append(counter)
        events.extend({'after_iteration': counter, 'kind': kind} for kind in kinds)
    if grey_release:
        if len(grey_candidates) != 1:
            raise RunnerError('Ambiguous fixed-J grey-release checkpoint evidence')
        events.append({'after_iteration': grey_candidates[0], 'kind': 'grey_release'})
    if set(grids) - {int(h[1]) for h in headers}:
        raise RunnerError('Native checkpoint update is outside the solved iteration records')
    return events
