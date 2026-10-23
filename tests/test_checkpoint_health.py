"""Real binary checkpoint records, including stale-text and padding regressions."""

import struct

import pytest

from cmfgen_viewer.checkpoint_health import RECORD_BYTES, WORDS_PER_RECORD
from cmfgen_viewer.runner_restart import inspect_restart


def checkpoint_bytes(*, nd=2, nt=3, records=2, bad_record=None, bad_value=float('nan'),
                     writes_rvsig=True, byte_order='<'):
    geometry = list(range(nd + 1, 1, -1)) + [20.0] * nd + [0.0] * nd
    geometry_records = (3 * nd + WORDS_PER_RECORD - 1) // WORDS_PER_RECORD

    def pack(values):
        output = bytearray()
        for start in range(0, len(values), WORDS_PER_RECORD):
            row = values[start:start + WORDS_PER_RECORD]
            block = struct.pack(byte_order + str(len(row)) + 'd', *row)
            output.extend(block + bytes(RECORD_BYTES - len(block)))
        return output

    output = pack(geometry)
    if geometry_records == 1:
        output += pack(geometry)
    for record in range(1, records + 1):
        if writes_rvsig:
            output += pack(geometry)
        values = [v for depth in range(nd)
                  for v in ([1e7] * (nt - 2) + [1e10 * (depth + 1), 1.0 + depth])]
        if record == bad_record:
            values[0] = bad_value
        output += pack(values)
    return bytes(output)


def write_checkpoint(model, *, selected=2, **options):
    nd, nt = options.get('nd', 2), options.get('nt', 3)
    (model / 'MODEL_SPEC').write_text(f'{nd} [ND]\n1 [NC]\n{nd+1} [NP]\n')
    (model / 'VADAT').write_text('F [DO_HYDRO]\n')
    (model / 'MODEL').write_text(f'{nd} !Number of depth points\n{nt} !Total number of variables\n\f')
    logical = 'T' if options.get('writes_rvsig', True) else 'F'
    (model / 'POINT1').write_text(f'28-Feb-2004 !Format date\n{selected} {selected} 1 -1000 {logical}\n')
    (model / 'SCRTEMP').write_bytes(checkpoint_bytes(**options))


@pytest.mark.parametrize('byte_order', ['<', '>'])
@pytest.mark.parametrize('writes_rvsig', [True, False])
def test_selected_checkpoint_is_checked_despite_finite_stale_rvtj(tmp_path, byte_order, writes_rvsig):
    write_checkpoint(tmp_path, bad_record=2, byte_order=byte_order, writes_rvsig=writes_rvsig)
    (tmp_path / 'RVTJ').write_text('ND: 2\nRadius\n3 2\nVelocity\n20 20\n'
                                 'Temperature\n1 2\nElectron density\n1e10 2e10\n')
    result = inspect_restart(tmp_path)
    health = result['binary_health']
    assert health['status'] == 'failed'
    assert health['record'] == 2
    assert health['nonfinite_populations'] == 1
    assert health['first_invalid'] == {'depth': 1, 'variable': 1}
    assert result['health']['source'] == 'SCRTEMP'
    assert any('checkpoint 2' in error for error in result['errors'])
    assert inspect_restart(tmp_path, fresh_start=True)['binary_health']['status'] == 'not_checked'


@pytest.mark.parametrize('bad_value', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_atomic_population_is_rejected(tmp_path, bad_value):
    write_checkpoint(tmp_path, bad_record=2, bad_value=bad_value)
    assert inspect_restart(tmp_path)['binary_health']['status'] == 'failed'


def test_unselected_bad_record_does_not_poison_a_finite_selected_record(tmp_path):
    write_checkpoint(tmp_path, selected=1, bad_record=2)
    result = inspect_restart(tmp_path)
    assert result['health']['source'] == 'SCRTEMP'
    assert result['binary_health']['status'] == 'passed'
    assert not result['errors']


@pytest.mark.parametrize('nd,nt', [(2, 2050), (700, 3)])
def test_multirecord_populations_and_geometry_ignore_record_padding(tmp_path, nd, nt):
    write_checkpoint(tmp_path, nd=nd, nt=nt)
    result = inspect_restart(tmp_path)
    assert result['binary_health']['status'] == 'passed'
    assert result['binary_health']['nd'] == nd
    assert result['binary_health']['nt'] == nt
    assert not result['errors']


@pytest.mark.parametrize('variable,value,label', [(2, 0.0, 'invalid_electron_densities'),
                                                (3, -1.0, 'invalid_temperatures')])
def test_nonpositive_core_values_rejected(tmp_path, variable, value, label):
    write_checkpoint(tmp_path)
    with (tmp_path / 'SCRTEMP').open('r+b') as stream:
        # Two header records, then two geometry/population record pairs.
        stream.seek(5 * RECORD_BYTES + (variable - 1) * 8)
        stream.write(struct.pack('<d', value))
    health = inspect_restart(tmp_path)['binary_health']
    assert health['status'] == 'failed'
    assert health[label] == 1


def test_selected_checkpoint_geometry_must_be_finite(tmp_path):
    write_checkpoint(tmp_path)
    with (tmp_path / 'SCRTEMP').open('r+b') as stream:
        stream.seek(4 * RECORD_BYTES)
        stream.write(struct.pack('<d', float('nan')))
    assert 'radius/velocity/gradient' in inspect_restart(tmp_path)['binary_health']['problem']


@pytest.mark.parametrize('removed', [1, RECORD_BYTES])
def test_truncated_recognized_checkpoint_is_rejected(tmp_path, removed):
    write_checkpoint(tmp_path)
    path = tmp_path / 'SCRTEMP'
    with path.open('r+b') as stream:
        stream.truncate(path.stat().st_size - removed)
    assert 'truncated' in inspect_restart(tmp_path)['binary_health']['problem']


def test_unrecognized_layout_is_explicitly_unverified(tmp_path):
    write_checkpoint(tmp_path)
    (tmp_path / 'SCRTEMP').write_bytes(bytes(4096))
    result = inspect_restart(tmp_path)
    assert result['binary_health']['status'] == 'unavailable'
    assert any('Binary checkpoint health is unverified' in warning for warning in result['warnings'])
    assert result['health']['status'] != 'passed'


def test_binary_check_is_read_only(tmp_path):
    write_checkpoint(tmp_path, bad_record=2)
    paths = [tmp_path / name for name in ('SCRTEMP', 'POINT1', 'MODEL', 'VADAT')]
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
    inspect_restart(tmp_path)
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
