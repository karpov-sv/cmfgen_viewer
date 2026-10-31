"""Replay supported native IT_SPECIFIER rotations and REVISE_R scheduling."""
from .control_files import control_occurrences
from .runner_recipe import RunnerError


def allows_full(model):
    """An explicit reachable FULL can release a scripted fixed-T phase."""
    path = model/'IT_SPECIFIER'
    if not path.is_file() or path.stat().st_size > 4*1024*1024:
        return False
    its = control_occurrences((model/'IN_ITS').read_text())
    def enabled(key, default=False):
        return (its[key][0]['value'].upper().strip('.') in {'T', 'TRUE'}
                if len(its.get(key, [])) == 1 else default)
    if enabled('DO_LAM_IT') and not enabled('DO_LAM_AUTO', True):
        return False  # The later IN_ITS reread overrides a scripted FULL.
    for line in path.read_text().splitlines()[:20]:
        if not line.strip() or line.lstrip().startswith('!'):
            continue
        option = line.split()[0].upper()
        if option.startswith(('NORM', 'NONE')):
            return False  # Native leaves all subsequent commands unvisited.
        if option == 'FULL':
            return True
    return False


def replay(before, after, counters):
    if before is None:
        if after is not None:
            raise RunnerError('IT_SPECIFIER appeared during native execution')
        return {}
    state = before
    scheduled = {}
    for counter in counters:
        original = state
        lines = [line[:80].rstrip() for line in state.splitlines()[:20]]
        if not lines:
            raise RunnerError('Native IT_SPECIFIER has no iteration option')
        for _ in range(len(lines)):
            lines[0] = lines[0].lstrip()
            first = lines[0]
            if not first or first.startswith('!'):
                lines = lines[1:]+lines[:1]
            elif first.startswith('REVISE_R'):
                scheduled[counter] = counter+1
                lines = lines[1:]+lines[:1]
            else:
                break
        else:
            raise RunnerError('IT_SPECIFIER has no iteration option')
        parts = lines[0].split()
        option = parts[0].upper().replace('FIX_', 'FIX')
        if option.startswith(('NORM', 'NONE')):
            state = original  # Native returns without writing its rotated buffer.
            continue
        if option not in {'DO_NG', 'DO_AV', 'LAM', 'FULL', 'FULL(FIXT)', 'FULL(FIXBA)',
                          'FULL(FIXT,FIXBA)', 'FULL(FIXBA,FIXT)'}:
            raise RunnerError('Unsupported native IT_SPECIFIER option')
        try:
            count = int(parts[1]) if len(parts) > 1 else 1
            done = int(parts[2]) if len(parts) > 2 else 0
            if count < 1 or not 0 <= done < count or len(parts) > 3:
                raise ValueError('Invalid cycle count')
        except ValueError as exc:
            raise RunnerError('Ambiguous native IT_SPECIFIER counters') from exc
        done += 1
        if done == count:
            lines = lines[1:]+[f'{option:<20}{count:4d}']
        else:
            lines[0] = f'{option:<20}{count:4d}   {done:4d}'
        state = '\n'.join(lines)+'\n'
    if [v.rstrip() for v in state.splitlines()] != [v.rstrip() for v in (after or '').splitlines()]:
        raise RunnerError('IT_SPECIFIER changed outside its native iteration cycle')
    return scheduled
