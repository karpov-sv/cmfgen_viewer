"""Conservative element/charge checks for recognized native checkpoint metadata.

Used by the large Lambda bootstrap, whose temporary MAX_LAM must not silently
lose element abundance. Unknown layouts or incomplete ion tables are refused.
"""
import os
import numpy as np

from .checkpoint_health import RECORD_BYTES, WORDS_PER_RECORD, _identity, _words
from .runner_restart import inspect_restart
from .runner_recipe import RunnerError


def checkpoint_physics(model):
    restart = inspect_restart(model)
    health = restart.get('binary_health', {})
    if restart['errors'] or health.get('status') != 'passed':
        raise RunnerError('Population recovery requires a recognized healthy binary checkpoint')
    nd, nt = health['nd'], health['nt']
    if nd*nt > 5_000_000:
        raise RunnerError('Checkpoint too large for automatic population-conservation verification')
    ions = []
    for line in (model/'MODEL').read_text().splitlines():
        row = line.split()
        if len(row) >= 12:
            try:
                ions.append((int(row[8])-1, int(row[2]), float(row[3]), int(row[9])))
            except ValueError:
                pass
    charge = np.zeros(nt-2)
    groups = {}
    covered = []
    for i, (start, count, stage, species) in enumerate(ions):
        ids = list(range(start, start+count))
        if i == len(ions)-1 or ions[i+1][3] != species:
            ids.append(start+count)
        if start < 0 or count < 1 or not 1 <= stage <= 100 or ids[-1] >= nt-2:
            raise RunnerError('Invalid ion metadata for population conservation')
        covered.extend(ids)
        charge[start:start+count] = stage-1
        if len(ids) > count:
            charge[ids[-1]] = stage
        groups.setdefault(species, []).extend(ids)
    if sorted(covered) != list(range(nt-2)):
        raise RunnerError('Incomplete or overlapping MODEL ion table for population conservation')
    pointer = restart['pointer']
    gr = (3*nd+WORDS_PER_RECORD-1)//WORDS_PER_RECORD
    pr = (nt*nd+WORDS_PER_RECORD-1)//WORDS_PER_RECORD
    start = max(2, gr)+(pointer['record']-1)*(pr+(gr if pointer['writes_rvsig'] else 0))
    order = '<' if health['byte_order'] == 'little' else '>'
    fd = os.open(model/'SCRTEMP', os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        geo = list(_words(stream, start if pointer['writes_rvsig'] else 0, 3*nd, order))
        pops = np.fromiter(_words(stream, start+(gr if pointer['writes_rvsig'] else 0), nd*nt, order), float).reshape(nd,nt)
        if _identity(before) != _identity(os.fstat(stream.fileno())) or _identity(before) != _identity((model/'SCRTEMP').lstat()):
            raise RunnerError('Checkpoint changed during conservation verification')
    error = float(np.max(np.abs(pops[:,:-2] @ charge / pops[:,-2]-1)))
    if not np.isfinite(pops).all() or np.any(pops <= 0) or not np.isfinite(error) or error > 1e-6:
        raise RunnerError('Population recovery checkpoint fails positivity or charge conservation')
    return {'geometry':geo, 'temperature':pops[:,-1].tolist(),
            'element_densities':{str(k):pops[:,ids].sum(axis=1).tolist() for k,ids in groups.items()},
            'charge_relative_error':error}


def compare_physics(before, after, *, fixed_temperature=False):
    if before['geometry'] != after['geometry'] or before['element_densities'].keys() != after['element_densities'].keys():
        raise RunnerError('Population recovery changed geometry or atomic setup')
    error = max(float(np.max(np.abs(np.array(after['element_densities'][k])/v-1)))
                for k,v in before['element_densities'].items())
    if not np.isfinite(error) or error > 1e-6:
        raise RunnerError('Population recovery lost element abundance')
    if fixed_temperature and before['temperature'] != after['temperature']:
        raise RunnerError('Fixed-temperature population bootstrap changed temperature')
    return {'element_density_max_relative_change':error, 'charge_relative_error':after['charge_relative_error']}
