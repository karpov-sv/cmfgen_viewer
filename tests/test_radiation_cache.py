"""Recognized radiation-cache diagnosis and real automatic-run preparation."""
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
import pytest

from test_runner_auto import auto_workspace
from cmfgen_viewer import radiation_cache
from cmfgen_viewer.auto_diagnostics import control_value
from cmfgen_viewer.auto_hydro import capture_controls, native_updates
from cmfgen_viewer.auto_policies import Context, choose
from cmfgen_viewer.recovery_files import compact_recovery
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner_auto import _action
from cmfgen_viewer.runner_recipe import RunnerError


def cache(model, *, order='<', word=8, integer=4, bad=None):
    nd, count = 2, 4
    size = (nd+1)*word
    data = bytearray((14+count)*size)
    dtype = np.dtype(order+f'f{word}')
    kind = 'i' if integer == 4 else 'q'
    struct.pack_into(order+kind, data, size, 10)
    struct.pack_into(order+kind*3, data, 2*size, 15, count, nd)
    data[4*size:5*size] = np.array([1, 0, 0], dtype=dtype).tobytes()
    for i in range(count):
        values = np.array([1+i, 2+i, 1000-i], dtype=dtype)
        if bad and i == bad[0]:
            values[bad[1]] = bad[2]
        data[(14+i)*size:(15+i)*size] = values.tobytes()
    (model/'EDDFACTOR').write_bytes(data)
    (model/'EDDFACTOR_INFO').write_text(
        '12-Apr-2017 !INFO format date\n23-Jan-2017 !File format date\n'
        f'2 {size} {word} 1 {integer} {"T" if order=="<" else "F"}\n'
        'ND RECL WORD_SIZE UNIT_SIZE INT_SIZE LIT_END\n')
    return bytes(data)


@pytest.mark.parametrize('order,word,integer', [('<',8,4),('>',8,4),('<',4,4),('>',4,4),('<',8,8),('>',8,8)])
def test_cache_layout_and_chunked_last_record_scan(tmp_path, monkeypatch, order, word, integer):
    original = cache(tmp_path, order=order, word=word, integer=integer, bad=(3,1,float('nan')))
    monkeypatch.setattr(radiation_cache, 'CHUNK_BYTES', 24)
    result = radiation_cache.inspect_radiation_cache(tmp_path)
    assert result['status'] == 'nonfinite'
    assert result['first_bad'] == {'record':18, 'depth':2, 'frequency':997,
                                   'component':'intensity', 'value':'nan'}
    assert result['nonfinite_values'] == 1
    assert result['records_scanned'] == 4
    assert result['sha256'] == hashlib.sha256(original).hexdigest()
    json.dumps(result, allow_nan=False)
    assert (tmp_path/'EDDFACTOR').read_bytes() == original


@pytest.mark.parametrize('bad', [(0,0,float('inf')),(1,2,float('-inf'))])
def test_infinity_and_invalid_frequency_are_json_safe(tmp_path, bad):
    cache(tmp_path, bad=bad)
    result = radiation_cache.inspect_radiation_cache(tmp_path)
    assert result['status'] == 'nonfinite'
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('fault', ['missing_info','unknown_format','record_size','truncated',
                                   'incomplete','old_rv_pointer','bad_cont_pointer','symlink','hardlink'])
def test_unknown_or_unsafe_layout_never_authorizes_repair(tmp_path, fault):
    cache(tmp_path, bad=(0,0,float('nan')))
    p, info = tmp_path/'EDDFACTOR', tmp_path/'EDDFACTOR_INFO'
    if fault == 'missing_info': info.unlink()
    elif fault == 'unknown_format': info.write_text(info.read_text().replace('23-Jan-2017','23-Jan-2000'))
    elif fault == 'record_size': info.write_text(info.read_text().replace('2 24 8', '2 32 8'))
    elif fault == 'truncated': p.write_bytes(p.read_bytes()[:-1])
    elif fault in {'incomplete','old_rv_pointer','bad_cont_pointer'}:
        data = bytearray(p.read_bytes())
        if fault == 'incomplete': struct.pack_into('<d',data,4*24,0)
        elif fault == 'old_rv_pointer': struct.pack_into('<i',data,24,18)
        else: struct.pack_into('<i',data,2*24,999)
        p.write_bytes(data)
    elif fault == 'symlink':
        p.rename(tmp_path/'other');p.symlink_to('other')
    elif fault == 'hardlink':
        import os
        os.link(p,tmp_path/'other')
    assert radiation_cache.inspect_radiation_cache(tmp_path)['status'] == 'unverified'


def test_scan_limit_leaves_cache_untouched(tmp_path, monkeypatch):
    original = cache(tmp_path,bad=(0,0,float('nan')))
    monkeypatch.setattr(radiation_cache, 'MAX_SCAN_BYTES', 1)
    assert radiation_cache.inspect_radiation_cache(tmp_path)['status'] == 'unverified'
    assert (tmp_path/'EDDFACTOR').read_bytes() == original


def test_healthy_cache_is_not_modified(auto_workspace):
    model, plan = auto_workspace
    original = cache(model)
    with (model/'VADAT').open('a') as f: f.write('F [COMP_F]\n')
    result = run_plan(plan())
    assert result['status'] == 'succeeded', result
    assert not any(a['kind']=='nonfinite_radiation_cache' for a in result['actions'])
    assert control_value(model,'VADAT','COMP_F') == 'F'
    assert (model/'EDDFACTOR').read_bytes() == original


def test_nonfinite_cache_is_preserved_and_recomputed_before_first_launch(auto_workspace):
    model, plan = auto_workspace
    original = cache(model,bad=(0,0,float('nan')))
    metadata = (model/'EDDFACTOR_INFO').read_bytes()
    with (model/'VADAT').open('a') as f: f.write('F [COMP_F]\nT [DO_HYDRO]\n')
    (model/'HYDRO_DEFAULTS').write_text('2 [ITS_DONE]\n2 [N_ITS]\n')
    (model/'ROSSELAND_LTE_TAB').write_text(
        '1 !Number of temperatures\n1 !Number of densities\n1 2 3 4 5 6 7 8\n')
    exe = model.parent/'cmf/exe/cmfgen_dev.exe'
    # A real subprocess verifies the inputs at launch, and emits the native
    # fresh-start reset that previously masked the Bstar3100 failure.
    with exe.open('a') as f:
        f.write("\nassert get('VADAT','COMP_F','F')=='T'\nassert not (p/'EDDFACTOR').exists()\n")
        f.write("if attempt==1:\n (p/'HYDRO_DEFAULTS').write_text('0 [ITS_DONE]\\n2 [N_ITS]\\n')\n"
                " (p/'OUTGEN').write_text((p/'OUTGEN').read_text().replace('Model started on: now\\n',"
                "'Model started on: now\\nStarting a new model.\\n"
                "Setting ITS_DONE keyword in HYDRO_DEFAULTS to 0\\n',1))\n")
    result = run_plan(plan(fresh_start=True))
    assert result['status'] == 'succeeded', result
    assert len(result['attempts']) == 2  # no failed native attempt charged
    assert result['attempts'][-1]['evidence']['fresh_verified']
    assert result['actions'][0]['kind'] == 'nonfinite_radiation_cache'
    action = result['actions'][0]
    assert action['evidence']['first_bad']['record'] == 15
    assert action['evidence']['sha256'] == hashlib.sha256(original).hexdigest()
    assert Path(action['preserved_caches']['EDDFACTOR']).read_bytes() == original
    assert Path(action['preserved_caches']['EDDFACTOR_INFO']).read_bytes() == metadata
    assert 'HYDRO_DEFAULTS' in result['attempts'][0]['native_control_updates']
    assert control_value(model,'VADAT','COMP_F') == 'T'
    assert (model/'HYDRO_DEFAULTS').read_text().startswith('0 [ITS_DONE]')
    compact_recovery(Path(action['directory']))
    assert Path(action['preserved_caches']['EDDFACTOR']).read_bytes() == original
    saved = json.loads((Path(action['directory'])/'action.json').read_text())
    assert saved['evidence'] == action['evidence']


@pytest.mark.parametrize('controls', ['T [COMP_F]\n','F [COMP_F]\nT [USE_FIXED_J]\n'])
def test_recompute_request_and_fixed_radiation_constraints(tmp_path, controls):
    original = cache(tmp_path,bad=(0,0,float('nan')))
    (tmp_path/'VADAT').write_text(controls)
    ctx = Context(tmp_path,'prepare',{}, {}, {}, {}, [], 'iterate', [], '')
    decision, _ = choose(ctx)
    assert decision.kind == ('stop' if 'USE_FIXED_J' in controls else 'continue')
    assert (tmp_path/'EDDFACTOR').read_bytes() == original


def test_cache_remedy_is_bounded(tmp_path):
    cache(tmp_path,bad=(0,0,float('nan')))
    (tmp_path/'VADAT').write_text('F [COMP_F]\n')
    ctx = Context(tmp_path,'prepare',{}, {}, {}, {}, [], 'iterate',
                  [{'policy_id':'nonfinite_radiation_cache'}], '')
    decision, _ = choose(ctx)
    assert decision.kind == 'stop' and 'exhausted' in decision.reason


@pytest.mark.parametrize('changed', ['EDDFACTOR', 'EDDFACTOR_INFO'])
def test_changed_cache_is_not_retired_using_stale_diagnosis(tmp_path, changed):
    original = cache(tmp_path,bad=(0,0,float('nan')))
    (tmp_path/'VADAT').write_text('F [COMP_F]\n')
    evidence = radiation_cache.inspect_radiation_cache(tmp_path)
    with (tmp_path/changed).open('ab') as stream:
        stream.write(b'edited')
    journal = tmp_path/'journal';journal.mkdir()
    with pytest.raises(RunnerError,match='changed after diagnosis'):
        _action(tmp_path,journal,[],'nonfinite_radiation_cache','test',
                changes={'VADAT':{'COMP_F':'T'}}, caches=('EDDFACTOR','EDDFACTOR_INFO'),
                evidence=evidence,preserve_caches=True)
    assert (tmp_path/'EDDFACTOR').exists() and (tmp_path/'EDDFACTOR_INFO').exists()
    assert (tmp_path/'VADAT').read_text() == 'F [COMP_F]\n'
    if changed == 'EDDFACTOR_INFO': assert (tmp_path/'EDDFACTOR').read_bytes() == original


def test_preparation_does_not_turn_a_later_unknown_failure_into_success(auto_workspace):
    model, plan = auto_workspace
    original = cache(model,bad=(0,0,float('nan')))
    with (model/'VADAT').open('a') as stream: stream.write('F [COMP_F]\n')
    result = run_plan(plan('unknown'))
    assert result['status'] == 'needs_review', result
    assert len(result['attempts']) == 1
    assert len(result['actions']) == 1
    assert 'numerical_convergence' not in result
    assert Path(result['actions'][0]['preserved_caches']['EDDFACTOR']).read_bytes() == original


RESET = 'Starting a new model.\nSetting ITS_DONE keyword in HYDRO_DEFAULTS to 0\n'


@pytest.mark.parametrize('fault', ['none','unconfirmed','no_message','other_value','other_comment','continuation'])
def test_fresh_reset_needs_verified_startup_and_no_unrelated_edits(tmp_path, fault):
    (tmp_path/'VADAT').write_text('T [DO_HYDRO]\n')
    p = tmp_path/'HYDRO_DEFAULTS';p.write_text('2 [ITS_DONE]\n3 [N_ITS]\n')
    before = capture_controls(tmp_path)
    after = '0 [ITS_DONE]\n3 [N_ITS]\n'
    if fault == 'other_value': after = after.replace('3 [N_ITS]','2 [N_ITS]')
    elif fault == 'other_comment': after += '! user edit\n'
    p.write_text(after)
    if fault == 'none':
        assert native_updates(tmp_path,RESET,before,fresh_start=True)['HYDRO_DEFAULTS']['after'] == after
    else:
        with pytest.raises(RunnerError):
            native_updates(tmp_path,'' if fault=='no_message' else RESET,before,
                           fresh_start=fault not in {'unconfirmed','continuation'})
        assert p.read_text() == after


def test_fresh_reset_then_hydro_revision_counts_from_zero(tmp_path):
    (tmp_path/'VADAT').write_text('T [DO_HYDRO]\n1 [RSTAR]\n')
    (tmp_path/'MODEL_SPEC').write_text('2 [ND]\n1 [NC]\n3 [NP]\n')
    (tmp_path/'RVSIG_COL').write_text('2 !Number of depth points\n2 20 0 0.1 1\n1 10 0 100 2\n')
    (tmp_path/'HYDRO_DEFAULTS').write_text('2 [ITS_DONE]\n3 [N_ITS]\n')
    before = capture_controls(tmp_path)
    (tmp_path/'VADAT').write_text('T [DO_HYDRO]\n1.1 [RSTAR]\n')
    (tmp_path/'RVSIG_COL').write_text('2 !Number of depth points\n2.2 20 0 0.1 1\n1.1 10 0 100 2\n')
    (tmp_path/'HYDRO_DEFAULTS').write_text('1 [ITS_DONE]\n2 [N_ITS]\n')
    text = RESET + 'Current great iteration count is 1\nRevised hydrostatic structure and output new RVSIG_COL file\n'
    adopted = native_updates(tmp_path,text,before,fresh_start=True)
    assert set(adopted) == {'VADAT','RVSIG_COL','HYDRO_DEFAULTS'}
    with pytest.raises(RunnerError,match='counters'):
        native_updates(tmp_path,text,before,fresh_start=False)
