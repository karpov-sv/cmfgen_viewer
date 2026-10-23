"""Bounded, read-only numerical checks for the common SCR_READ_V2 layout.

Recognize the 28-Feb-2004 pointer format, MODEL dimensions, duplicated geometry
header and DIR_ACC_PARS_GEN's 16,376-byte records of IEEE binary64 values.
Other layouts remain explicitly unverified; MODEL is not atomic provenance.
"""

import math
import os
import re
import stat
import struct
import sys

from .control_files import control_occurrences


RECORD_BYTES = 4094 * 4
WORDS_PER_RECORD = RECORD_BYTES // 8


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _words(stream, record, count, byte_order):
    stream.seek(record * RECORD_BYTES)
    while count:
        block = stream.read(RECORD_BYTES)
        if len(block) != RECORD_BYTES:
            raise ValueError('SCRTEMP is truncated in the selected checkpoint')
        used = min(count, WORDS_PER_RECORD)
        yield from struct.unpack_from(byte_order + str(used) + 'd', block)
        count -= used


def _geometry(values, nd):
    radii = values[:nd]
    return (all(math.isfinite(v) for v in values)
            and all(v >= sys.float_info.min for v in radii)
            and all(a > b for a, b in zip(radii, radii[1:])))


def inspect_checkpoint_health(model, pointer):
    """Inspect only the selected record; never rewind or modify checkpoint files."""
    result = {'status': 'unavailable', 'source': 'SCRTEMP', 'record': pointer['record']}
    if pointer['format_date'] != '28-Feb-2004':
        return {**result, 'reason': 'Unrecognized native checkpoint format'}
    metadata = model / 'MODEL'
    if not metadata.is_file():
        return {**result, 'reason': 'MODEL dimensions are unavailable'}
    with metadata.open(errors='replace') as stream:
        header = stream.read(65536).split('\f', 1)[0]
    dimensions = []
    for label in ('depth points', 'variables'):
        matches = re.findall(r'^\s*(\d+)\s+!(?:Total number|Number) of ' + label + r'\s*$', header, re.M)
        if len(matches) != 1:
            return {**result, 'reason': 'MODEL dimensions are missing or ambiguous'}
        dimensions.append(int(matches[0]))
    nd, nt = dimensions
    spec = control_occurrences((model / 'MODEL_SPEC').read_text()).get('ND', [])
    if (len(spec) != 1 or str(nd) != spec[0]['value'] or nd < 1 or nt < 2
            or nd > 1_000_000 or nd * nt > 100_000_000):
        return {**result, 'reason': 'Unsupported or inconsistent checkpoint dimensions'}
    population_records = (nd * nt + WORDS_PER_RECORD - 1) // WORDS_PER_RECORD
    geometry_records = (3 * nd + WORDS_PER_RECORD - 1) // WORDS_PER_RECORD
    header_records = max(2, geometry_records)
    descriptor = os.open(model / 'SCRTEMP', os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError('SCRTEMP must be an unshared regular file')
        if before.st_size < header_records * RECORD_BYTES:
            return {**result, 'reason': 'Native direct-record layout could not be established'}
        candidates = []
        for byte_order in ('<', '>'):
            geometry = list(_words(stream, 0, 3 * nd, byte_order))
            if _geometry(geometry, nd):
                candidates.append((byte_order, geometry))
        if len(candidates) != 1:
            return {**result, 'reason': 'Checkpoint geometry does not establish a supported byte order'}
        byte_order, header_geometry = candidates[0]
        if geometry_records == 1 and list(_words(stream, 1, 3 * nd, byte_order)) != header_geometry:
            return {**result, 'reason': 'Native duplicated geometry header could not be established'}
        result.update(layout='SCR_READ_V2/28-Feb-2004/binary64/16376',
                      byte_order='little' if byte_order == '<' else 'big', nd=nd, nt=nt)
        start = header_records + (pointer['record'] - 1) * (
            population_records + (geometry_records if pointer['writes_rvsig'] else 0))
        population_start = start + (geometry_records if pointer['writes_rvsig'] else 0)
        required = (population_start + population_records) * RECORD_BYTES
        if before.st_size < required or before.st_size % RECORD_BYTES:
            return {**result, 'status': 'failed', 'problem': 'SCRTEMP is truncated for the selected checkpoint'}
        geometry = list(_words(stream, start if pointer['writes_rvsig'] else 0, 3 * nd, byte_order))
        if not _geometry(geometry, nd):
            return {**result, 'status': 'failed', 'problem': 'Invalid selected checkpoint radius/velocity/gradient vectors'}
        nonfinite = invalid_t = invalid_ed = 0
        first_invalid = None
        for index, value in enumerate(_words(stream, population_start, nd * nt, byte_order)):
            variable = index % nt
            finite = math.isfinite(value)
            nonfinite += not finite
            bad_t = variable == nt - 1 and (not finite or value <= 0)
            bad_ed = variable == nt - 2 and (not finite or value <= 0)
            invalid_t += bad_t
            invalid_ed += bad_ed
            if first_invalid is None and (not finite or bad_t or bad_ed):
                first_invalid = {'depth': index // nt + 1, 'variable': variable + 1}
        if (_identity(before) != _identity(os.fstat(stream.fileno()))
                or _identity(before) != _identity((model / 'SCRTEMP').lstat())):
            raise ValueError('SCRTEMP changed during checkpoint validation; retry when the model is idle')
    result.update(nonfinite_populations=nonfinite, invalid_temperatures=invalid_t,
                  invalid_electron_densities=invalid_ed)
    if nonfinite or invalid_t or invalid_ed:
        return {**result, 'status': 'failed', 'first_invalid': first_invalid,
                'problem': (f"SCRTEMP checkpoint {pointer['record']} contains {nonfinite} nonfinite population values, "
                            f'{invalid_t} invalid temperatures and {invalid_ed} invalid electron densities')}
    return {**result, 'status': 'passed',
            'evidence': 'Selected binary checkpoint populations are finite; temperature and electron density are positive'}
