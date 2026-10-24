"""Read-only inspection of recognized native EDDFACTOR caches.

Only the 2017 direct-access layout is recognized. Unknown layouts are never
interpreted as corrupt. Scan in chunks, without mapping a live native file.
"""
from pathlib import Path
import hashlib
import math
import os
import stat
import struct

import numpy as np

MAX_SCAN_BYTES = 2 * 1024**3
CHUNK_BYTES = 4 * 1024**2


def inspect_radiation_cache(model):
    model = Path(model)
    path, info = model/'EDDFACTOR', model/'EDDFACTOR_INFO'
    result = {'status': 'absent', 'file': 'EDDFACTOR'}
    if not path.exists():
        return result
    result['status'] = 'unverified'
    for item in (path, info):
        if item.is_symlink():
            return {**result, 'reason': 'Symlinked radiation cache or metadata'}
        if not item.exists():
            return {**result, 'reason': 'Missing radiation-cache metadata'}
        mode = item.stat()
        if not stat.S_ISREG(mode.st_mode) or mode.st_nlink != 1:
            return {**result, 'reason': 'Radiation cache is not a private regular file'}
    if info.stat().st_size > 4096 or path.stat().st_size > MAX_SCAN_BYTES:
        return {**result, 'reason': 'Radiation cache exceeds bounded inspection limits'}
    info_before = info.stat()
    info_bytes = info.read_bytes()
    text = info_bytes.decode(errors='replace')
    rows = [line.split('!', 1)[0].split() for line in text.splitlines()]
    if (len(rows) < 3 or rows[0] != ['12-Apr-2017'] or
            rows[1] != ['23-Jan-2017'] or len(rows[2]) != 6):
        return {**result, 'reason': 'Unsupported radiation-cache format'}
    try:
        nd, recl, word, unit, integer = map(int, rows[2][:5])
    except ValueError:
        return {**result, 'reason': 'Unrecognized radiation-cache dimensions'}
    endian = rows[2][5].upper().strip('.')
    record_bytes = recl * unit
    if (not 1 <= nd <= 100000 or word not in (4, 8) or integer not in (4, 8) or
            unit not in (1, 4, 8) or record_bytes != word*(nd+1) or
            endian not in {'T', 'F'} or record_bytes < 3*integer):
        return {**result, 'reason': 'Unsupported radiation-cache binary layout'}
    order = '<' if endian == 'T' else '>'
    dtype = np.dtype(order + f'f{word}')
    intfmt = order + ('i' if integer == 4 else 'q')
    result.update(depths=nd, record_bytes=record_bytes, byte_order=endian)
    digest = hashlib.sha256()
    first_bad = None
    bad_values = 0
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        if before.st_size > MAX_SCAN_BYTES:
            return {**result, 'reason': 'Radiation cache exceeds bounded inspection limits'}
        if before.st_size % record_bytes or before.st_size <= 14*record_bytes:
            return {**result, 'reason': 'Incomplete radiation-cache record layout'}
        header = stream.read(14*record_bytes)
        if len(header) != 14*record_bytes:
            return {**result, 'reason': 'Radiation cache changed during inspection'}
        digest.update(header)
        marker = float(np.frombuffer(header[4*record_bytes:5*record_bytes], dtype=dtype)[0])
        rv = struct.unpack_from(intfmt, header, record_bytes)[0]
        cont, count, depths = struct.unpack_from(order + ('iii' if integer == 4 else 'qqq'),
                                                header, 2*record_bytes)
        records = before.st_size // record_bytes
        # Restrict recognition to the normal 2017 header, not older files with
        # radius vectors appended among records that otherwise resemble J.
        if (not math.isfinite(marker) or marker != 1 or rv != 10 or depths != nd or
                cont < 15 or count < 1 or cont+count-1 > records):
            return {**result, 'reason': 'Unverified radiation-cache completion or record pointers'}
        per_chunk = max(1, CHUNK_BYTES // record_bytes)
        offset = 14
        remaining = before.st_size - len(header)
        while remaining:
            payload = stream.read(min(per_chunk*record_bytes, remaining))
            if not payload or len(payload) % record_bytes:
                return {**result, 'reason': 'Radiation cache changed during inspection'}
            remaining -= len(payload)
            digest.update(payload)
            values = np.frombuffer(payload, dtype=dtype).reshape(-1, nd+1)
            bad = ~np.isfinite(values)
            bad_values += int(bad.sum())
            if first_bad is None and bad.any():
                row, col = divmod(int(np.argmax(bad)), nd+1)
                tag = float(values[row, -1])
                first_bad = {'record': offset+int(row)+1,
                             'depth': int(col)+1 if col < nd else None,
                             'frequency': tag if math.isfinite(tag) else None,
                             'component': 'intensity' if col < nd else 'frequency',
                             'value': str(float(values[row, col]))}
            offset += len(values)
        after = os.fstat(stream.fileno())
    signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if (signature(before) != signature(after) or signature(before) != signature(path.stat()) or
            signature(info_before) != signature(info.stat())):
        return {**result, 'reason': 'Radiation cache changed during inspection'}
    return {**result, 'status': 'nonfinite' if first_bad else 'finite',
            'records_scanned': records-14, 'nonfinite_values': bad_values,
            'first_bad': first_bad, 'sha256': digest.hexdigest(), 'size': before.st_size,
            'info_sha256': hashlib.sha256(info_bytes).hexdigest()}
