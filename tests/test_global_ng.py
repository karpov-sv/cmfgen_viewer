"""Positive global extrapolation: real native-layout transactions and refusal guards."""
import json
import os
import struct
from types import SimpleNamespace

import numpy as np
import pytest

from test_population_projection import projection_model
from cmfgen_viewer import global_ng as ng
from cmfgen_viewer.auto_ng import mark_attempt as _mark_attempt, fingerprint

def mark_attempt(*args):
    return _mark_attempt(*args, global_trial=True)
from cmfgen_viewer.checkpoint_health import RECORD_BYTES
from cmfgen_viewer.runner_recipe import RunnerError


@pytest.fixture
def global_model(projection_model):
    model = projection_model
    (model/'VADAT').write_text('T [DO_NG]\nF [FIX_T]\n2 [BW_NG]\n')
    def pack(values):
        data = np.asarray(values, dtype='<f8').tobytes()
        return data+bytes(RECORD_BYTES-len(data))
    geo = [6.,5.,4.,3.,2.]+[20.]*5+[0.]*5
    data = pack(geo)*2
    for j in reversed(range(4)):
        neutral = -1+1.3*1.005**j
        h0, h1 = 1e10*neutral, 1e10*(1-neutral)
        data += pack(geo)+pack([[h0,h1,5e8,5e8,h1+5e8,1+.001*(1.005**j-1)]]*5)
    data += pack(geo)+pack([[h0,h1,5e8,5e8,h1+5e8,1.]]*5)
    (model/'SCRTEMP').write_bytes(data)
    for name in ['POINT1','POINT2']:
        (model/name).write_text('28-Feb-2004 !Format date\n4 40 1 -1000 T\n')
    with (model/'MODEL_SPEC').open('a') as stream:stream.write('3 [NUM_BNDS]\n')
    return model


def test_native_backoff_transaction_preserves_history_geometry_and_counters(global_model):
    model = global_model
    before = (model/'SCRTEMP').read_bytes()
    pointers = [(model/n).read_bytes() for n in ['POINT1','POINT2']]
    plan = ng.propose(model)
    assert plan and plan['native_rejected_depths'] == 5
    assert plan['ratio_min'] >= .1 and plan['ratio_max'] <= 10
    assert plan['max_temperature_change_percent'] <= 1
    assert (model/'SCRTEMP').read_bytes() == before
    plan['populations'] = [0]  # Caller arrays have no authority.
    result = ng.apply(model, plan)
    after = (model/'SCRTEMP').read_bytes()
    start = 9*RECORD_BYTES
    assert before[:start] == after[:start]
    assert before[start+30*8:] == after[start+30*8:]
    assert before[start:start+30*8] != after[start:start+30*8]
    assert [(model/n).read_bytes() for n in ['POINT1','POINT2']] == pointers
    assert result['counter_unchanged']
    assert max(result['physical_checks'].values()) < 1e-10


def test_banded_temperature_reversal_cannot_veto_a_safe_global_direction(global_model, monkeypatch):
    from cmfgen_viewer import bounded_ng
    native_kernel = bounded_ng.kernel

    def reversed_banded_temperature(history):
        result = native_kernel(history)
        result[:, -4] = history[0, :, -4]+abs(history[0, :, -4]-history[1, :, -4])
        return result

    monkeypatch.setattr(bounded_ng, 'kernel', reversed_banded_temperature)
    before = (global_model/'SCRTEMP').read_bytes()
    assert bounded_ng.propose(global_model) is None
    proposal = ng.propose(global_model)
    assert proposal and proposal['native_temperature_reversal_depths'] > 0
    state, populations, _ = ng.compute(global_model)
    assert np.all(populations[:, -1] <= state[2][:, -1])
    assert (global_model/'SCRTEMP').read_bytes() == before
    assert ng.apply(global_model, proposal)['counter_unchanged']


@pytest.mark.parametrize('name', ['SCRTEMP','POINT1','VADAT','MODEL_SPEC'])
def test_stale_inputs_are_refused_without_write(global_model, name):
    plan = ng.propose(global_model)
    with (global_model/name).open('ab') as stream:
        stream.write(b'\n')
    before = (global_model/'SCRTEMP').read_bytes()
    with pytest.raises(RunnerError, match='Stale'):
        ng.apply(global_model, plan)
    assert (global_model/'SCRTEMP').read_bytes() == before


def test_descriptor_tampering_is_refused(global_model):
    plan = ng.propose(global_model)
    plan['alpha'] *= 2
    before = (global_model/'SCRTEMP').read_bytes()
    with pytest.raises(RunnerError, match='descriptor'):
        ng.apply(global_model, plan)
    assert (global_model/'SCRTEMP').read_bytes() == before


@pytest.mark.parametrize('flag', ['FIX_T','SN_MODEL','USE_FIXED_J','IMPURITY_CODE',
                                  'USE_J_REL','USE_DJDT_RTE','FLUX_CAL_ONLY','USE_EHB'])
def test_unsupported_modes_are_not_eligible(global_model, flag):
    path = global_model/'VADAT'
    path.write_text(path.read_text().replace(f'F [{flag}]', f'T [{flag}]')+
                    ('' if flag == 'FIX_T' else f'T [{flag}]\n'))
    assert ng.propose(global_model) is None


@pytest.mark.parametrize('fault', ['geometry','zero','charge','temperature','pointer','recent_ng'])
def test_history_guards(global_model, fault):
    path = global_model/'SCRTEMP'
    data = bytearray(path.read_bytes())
    if fault == 'geometry':struct.pack_into('<d',data,2*RECORD_BYTES,7.)
    if fault == 'zero':struct.pack_into('<d',data,3*RECORD_BYTES,0.)
    if fault == 'charge':struct.pack_into('<d',data,3*RECORD_BYTES+4*8,1.)
    if fault == 'temperature':struct.pack_into('<d',data,3*RECORD_BYTES+5*8,2.)
    path.write_bytes(data)
    if fault == 'pointer':(global_model/'POINT2').write_text('28-Feb-2004 !Format date\n4 41 1 -1000 T\n')
    if fault == 'recent_ng':
        for n in ['POINT1','POINT2']:(global_model/n).write_text('28-Feb-2004 !Format date\n4 40 1 39 T\n')
        assert ng.propose(global_model) is None
    else:
        with pytest.raises(RunnerError):ng.propose(global_model)


@pytest.mark.parametrize('fault', ['low_space','copy_failure','cancel','replace_failure'])
def test_staging_failures_do_not_publish_partial_state(global_model, monkeypatch, fault):
    plan = ng.propose(global_model)
    before = (global_model/'SCRTEMP').read_bytes()
    if fault == 'low_space':monkeypatch.setattr(ng.shutil,'disk_usage',lambda p:SimpleNamespace(free=0))
    else:
        def fail(*a, **kw):
            if fault == 'cancel':raise KeyboardInterrupt()
            raise OSError('injected ENOSPC')
        monkeypatch.setattr(ng.shutil if fault != 'replace_failure' else ng.os,
                            'copy2' if fault != 'replace_failure' else 'replace',fail)
    with pytest.raises((RunnerError,OSError,KeyboardInterrupt)):
        ng.apply(global_model, plan)
    assert (global_model/'SCRTEMP').read_bytes() == before
    assert not list(global_model.glob('.global-ng-restart-*'))


@pytest.mark.parametrize('kind', ['symlink','hardlink','oversized'])
def test_unsafe_inputs_are_refused(global_model, tmp_path, kind):
    path = global_model/'RVSIG_COL'
    if kind == 'symlink':path.symlink_to(global_model/'missing')
    elif kind == 'hardlink':os.link(global_model/'VADAT', path)
    else:
        with path.open('wb') as stream:stream.truncate(17*1024**2)
    with pytest.raises(RunnerError):ng.propose(global_model)


def test_receipt_survives_restoration_and_blocks_the_identical_checkpoint(global_model):
    plan = ng.propose(global_model)
    before = (global_model/'SCRTEMP').read_bytes()
    mark_attempt(global_model, plan, 'action-1')
    ng.apply(global_model, plan)
    (global_model/'SCRTEMP').write_bytes(before)
    new_plan = ng.propose(global_model)
    assert fingerprint(new_plan) == fingerprint(plan)
    with pytest.raises(RunnerError,match='already'):
        mark_attempt(global_model, new_plan, 'action-2')
    assert json.loads((global_model/'.cmfgen-runs/global-ng-trials.json').read_text()) == {
        fingerprint(plan):'action-1'}




def test_native_admissible_proposal_is_left_alone(global_model):
    data = bytearray((global_model/'SCRTEMP').read_bytes())
    latest = data[9*RECORD_BYTES:10*RECORD_BYTES]
    for record in [3,5,7]:data[record*RECORD_BYTES:(record+1)*RECORD_BYTES]=latest
    (global_model/'SCRTEMP').write_bytes(data)
    assert ng.propose(global_model) is None




@pytest.mark.parametrize('kind', ['malformed','symlink','oversized'])
def test_unsafe_receipts_are_refused(global_model, kind):
    plan=ng.propose(global_model)
    parent=global_model/'.cmfgen-runs';parent.mkdir()
    path=parent/'global-ng-trials.json'
    if kind=='malformed':path.write_text('[]')
    elif kind=='symlink':path.symlink_to(global_model/'missing')
    else:
        with path.open('wb') as stream:stream.truncate(9*1024**2)
    with pytest.raises((RunnerError,ValueError)):
        mark_attempt(global_model,plan,'a')




def physical_history(tiny_neutral=False):
    groups={1:[0,1],2:[2,3]};charge=np.array([0.,1.,0.,1.]);rows=[]
    for j in range(4):
        neutral=-1+1.3*1.005**j
        h0,h1=1e10*neutral,1e10*(1-neutral)
        he0=1e-240 if tiny_neutral else 5e8
        he1=5e8
        rows.append([[h0,h1,he0,he1,h1+he1,1+.001*(1.005**j-1),r,20.,1.] for r in [6.,5.,4.,3.,2.]])
    return np.array(rows),groups,charge


def test_geometric_calculation_preserves_tiny_ions_without_floors():
    history,groups,charge=physical_history(tiny_neutral=True);before=history.copy()
    values,report=ng.calculate(history,groups,charge)
    np.testing.assert_array_equal(history,before)
    assert np.isfinite(values).all() and (values>0).all()
    assert values[:,2].max()<1e-230
    for ids in groups.values():np.testing.assert_allclose(values[:,ids].sum(axis=1),history[0][:,ids].sum(axis=1),rtol=1e-13)
    np.testing.assert_array_equal(values[:,-2],values[:,:-2]@charge)
    assert report['ratio_min']>=.1 and report['ratio_max']<=10


def test_constant_history_does_not_publish_roundoff_as_progress():
    history,groups,charge=physical_history()
    assert ng.calculate(np.repeat(history[:1],4,axis=0),groups,charge) is None


def test_global_temperature_reversal_is_refused(monkeypatch):
    history,groups,charge=physical_history()
    monkeypatch.setattr(ng,'coefficients',lambda h:(1.,0.))
    assert ng.calculate(history,groups,charge) is None


@pytest.mark.parametrize('key',['a','maximum_T_percent','population_ratio_bounds'])
def test_global_math_and_caps_cannot_be_supplied_by_the_caller(global_model,key):
    plan=ng.propose(global_model);before=(global_model/'SCRTEMP').read_bytes()
    plan[key]=0
    with pytest.raises(RunnerError,match='descriptor'):ng.apply(global_model,plan)
    assert (global_model/'SCRTEMP').read_bytes()==before
