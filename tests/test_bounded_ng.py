"""Native record transactions and conservative eligibility boundaries."""
import json
import os
import struct
from types import SimpleNamespace

import numpy as np
import pytest

from test_population_projection import projection_model
from cmfgen_viewer import bounded_ng as ng
from cmfgen_viewer.auto_ng import mark_attempt, fingerprint
from cmfgen_viewer.checkpoint_health import RECORD_BYTES
from cmfgen_viewer.runner_recipe import RunnerError


@pytest.fixture
def ng_model(projection_model):
    model = projection_model
    (model/'VADAT').write_text('T [DO_NG]\nF [FIX_T]\n2 [BW_NG]\n')
    def pack(values):
        data = np.asarray(values, dtype='<f8').tobytes()
        return data+bytes(RECORD_BYTES-len(data))
    geo = [6.,5.,4.,3.,2.]+[20.]*5+[0.]*5
    data = pack(geo)*2
    for j in reversed(range(4)):
        neutral = .001+.3*1.01**j
        h0, h1 = 1e10*neutral, 1e10*(1-neutral)
        data += pack(geo)+pack([[h0,h1,5e8,5e8,h1+5e8,1+.001*(1.01**j-1)]]*5)
    data += pack(geo)+pack([[h0,h1,5e8,5e8,h1+5e8,1.]]*5)
    (model/'SCRTEMP').write_bytes(data)
    for name in ['POINT1','POINT2']:
        (model/name).write_text('28-Feb-2004 !Format date\n4 40 1 -1000 T\n')
    return model


def test_native_backoff_transaction_preserves_history_geometry_and_counters(ng_model):
    model = ng_model
    before = (model/'SCRTEMP').read_bytes()
    pointers = [(model/n).read_bytes() for n in ['POINT1','POINT2']]
    plan = ng.propose(model)
    assert plan and plan['native_rejected_depths'] == 5
    assert plan['ratio_min'] >= .875 and plan['ratio_max'] <= 1.125
    assert plan['maximum_temperature_change_percent'] <= .1
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


@pytest.mark.parametrize('name', ['SCRTEMP','POINT1','VADAT','MODEL_SPEC'])
def test_stale_inputs_are_refused_without_write(ng_model, name):
    plan = ng.propose(ng_model)
    with (ng_model/name).open('ab') as stream:
        stream.write(b'\n')
    before = (ng_model/'SCRTEMP').read_bytes()
    with pytest.raises(RunnerError, match='Stale'):
        ng.apply(ng_model, plan)
    assert (ng_model/'SCRTEMP').read_bytes() == before


def test_descriptor_tampering_is_refused(ng_model):
    plan = ng.propose(ng_model)
    plan['alpha'] *= 2
    before = (ng_model/'SCRTEMP').read_bytes()
    with pytest.raises(RunnerError, match='descriptor'):
        ng.apply(ng_model, plan)
    assert (ng_model/'SCRTEMP').read_bytes() == before


@pytest.mark.parametrize('flag', ['FIX_T','SN_MODEL','USE_FIXED_J','IMPURITY_CODE',
                                  'USE_J_REL','USE_DJDT_RTE','FLUX_CAL_ONLY'])
def test_unsupported_modes_are_not_eligible(ng_model, flag):
    path = ng_model/'VADAT'
    path.write_text(path.read_text().replace(f'F [{flag}]', f'T [{flag}]')+
                    ('' if flag == 'FIX_T' else f'T [{flag}]\n'))
    assert ng.propose(ng_model) is None


@pytest.mark.parametrize('fault', ['geometry','zero','charge','temperature','pointer','recent_ng'])
def test_history_guards(ng_model, fault):
    path = ng_model/'SCRTEMP'
    data = bytearray(path.read_bytes())
    if fault == 'geometry':struct.pack_into('<d',data,2*RECORD_BYTES,7.)
    if fault == 'zero':struct.pack_into('<d',data,3*RECORD_BYTES,0.)
    if fault == 'charge':struct.pack_into('<d',data,3*RECORD_BYTES+4*8,1.)
    if fault == 'temperature':struct.pack_into('<d',data,3*RECORD_BYTES+5*8,2.)
    path.write_bytes(data)
    if fault == 'pointer':(ng_model/'POINT2').write_text('28-Feb-2004 !Format date\n4 41 1 -1000 T\n')
    if fault == 'recent_ng':
        for n in ['POINT1','POINT2']:(ng_model/n).write_text('28-Feb-2004 !Format date\n4 40 1 39 T\n')
        assert ng.propose(ng_model) is None
    else:
        with pytest.raises(RunnerError):ng.propose(ng_model)


@pytest.mark.parametrize('fault', ['low_space','copy_failure','cancel','replace_failure'])
def test_staging_failures_do_not_publish_partial_state(ng_model, monkeypatch, fault):
    plan = ng.propose(ng_model)
    before = (ng_model/'SCRTEMP').read_bytes()
    if fault == 'low_space':monkeypatch.setattr(ng.shutil,'disk_usage',lambda p:SimpleNamespace(free=0))
    else:
        def fail(*a, **kw):
            if fault == 'cancel':raise KeyboardInterrupt()
            raise OSError('injected ENOSPC')
        monkeypatch.setattr(ng.shutil if fault != 'replace_failure' else ng.os,
                            'copy2' if fault != 'replace_failure' else 'replace',fail)
    with pytest.raises((RunnerError,OSError,KeyboardInterrupt)):
        ng.apply(ng_model, plan)
    assert (ng_model/'SCRTEMP').read_bytes() == before
    assert not list(ng_model.glob('.ng-restart-*'))


@pytest.mark.parametrize('kind', ['symlink','hardlink','oversized'])
def test_unsafe_inputs_are_refused(ng_model, tmp_path, kind):
    path = ng_model/'RVSIG_COL'
    if kind == 'symlink':path.symlink_to(ng_model/'missing')
    elif kind == 'hardlink':os.link(ng_model/'VADAT', path)
    else:
        with path.open('wb') as stream:stream.truncate(17*1024**2)
    with pytest.raises(RunnerError):ng.propose(ng_model)


def test_receipt_survives_restoration_and_blocks_the_identical_checkpoint(ng_model):
    plan = ng.propose(ng_model)
    before = (ng_model/'SCRTEMP').read_bytes()
    mark_attempt(ng_model, plan, 'action-1')
    ng.apply(ng_model, plan)
    (ng_model/'SCRTEMP').write_bytes(before)
    new_plan = ng.propose(ng_model)
    assert fingerprint(new_plan) == fingerprint(plan)
    with pytest.raises(RunnerError,match='already'):
        mark_attempt(ng_model, new_plan, 'action-2')
    assert json.loads((ng_model/'.cmfgen-runs/bounded-ng-trials.json').read_text()) == {
        fingerprint(plan):'action-1'}


def test_singular_kernel_retains_constant_history():
    h = np.ones((4,5,6))
    assert np.array_equal(ng.kernel(h), h[0])


def test_native_admissible_proposal_is_left_alone(ng_model):
    data = bytearray((ng_model/'SCRTEMP').read_bytes())
    latest = data[9*RECORD_BYTES:10*RECORD_BYTES]
    for record in [3,5,7]:data[record*RECORD_BYTES:(record+1)*RECORD_BYTES]=latest
    (ng_model/'SCRTEMP').write_bytes(data)
    assert ng.propose(ng_model) is None


def test_wrong_temperature_direction_cannot_be_repaired_by_positive_backoff(ng_model, monkeypatch):
    original = ng.kernel
    def wrong(history):
        result = original(history)
        result[:,-4] = 1.01*history[0,:,-4]  # Physical T precedes the three geometry coordinates.
        return result
    monkeypatch.setattr(ng,'kernel',wrong)
    before=(ng_model/'SCRTEMP').read_bytes()
    assert ng.propose(ng_model) is None
    assert (ng_model/'SCRTEMP').read_bytes()==before


@pytest.mark.parametrize('kind', ['malformed','symlink','oversized'])
def test_unsafe_receipts_are_refused(ng_model, kind):
    plan=ng.propose(ng_model)
    parent=ng_model/'.cmfgen-runs';parent.mkdir()
    path=parent/'bounded-ng-trials.json'
    if kind=='malformed':path.write_text('[]')
    elif kind=='symlink':path.symlink_to(ng_model/'missing')
    else:
        with path.open('wb') as stream:stream.truncate(9*1024**2)
    with pytest.raises((RunnerError,ValueError)):
        mark_attempt(ng_model,plan,'a')


def test_irregular_kernel_matches_independent_native_output():
    # Frozen output from the native Fortran operator, including geometry
    # coordinates and very small populations. No native installation is needed.
    from pathlib import Path
    data=json.loads(Path(__file__).with_name('bounded_ng_native_fixture.json').read_text())
    h=np.asarray(data['history'])
    np.testing.assert_allclose(ng.kernel(h), data['native'],rtol=2e-13,atol=0)
