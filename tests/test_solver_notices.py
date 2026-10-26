"""Contextual solver review hints are explicit, finite and read-only."""
import pytest

from cmfgen_viewer.solver_notices import solver_settings_notices


@pytest.mark.parametrize('filename,text,active', [
    ('IN_ITS','F [DO_LAM_AUTO]\nF [DO_LAM_IT]\n', {'manual_lambda'}),
    ('IN_ITS','T [DO_LAM_AUTO]\nT [DO_LAM_IT]\n', {'lambda_start'}),
    ('IN_ITS','T [DO_LAM_AUTO]\nF [DO_LAM_IT]\n', set()),
    ('IN_ITS','', set()),
    ('IN_ITS','F [DO_LAM_AUTO]\nT [DO_LAM_AUTO]\n', set()),
    ('VADAT','1D12 [MAX_LAM]\nT [FIX_T]\nF [DO_NG]\n',
     {'large_lambda_limit','fixed_temperature','ng_disabled'}),
    ('VADAT','1D4 [MAX_LAM]\nF [FIX_T]\nT [DO_NG]\n', set()),
    ('VADAT','NaN [MAX_LAM]\n', set()),
    ('VADAT','Infinity [MAX_LAM]\n', set()),
    ('VADAT','bad [MAX_LAM]\n', set()),
    ('VADAT','1D12 [MAX_LAM]\n1D4 [MAX_LAM]\n', set()),
    ('VADAT','0.1 [VFRAC_FG]\nT [INCL_dSLdT]\nPOP [DC_METH]\n', set()),
    ('ADJUST_CORRECTIONS','0.25 [RELAX]\n', {'reduced_relaxation'}),
    ('ADJUST_CORRECTIONS','1 [RELAX]\n', set()),
    ('ADJUST_CORRECTIONS','0 [RELAX]\n', set()),
    ('ADJUST_CORRECTIONS','-1 [RELAX]\n', set()),
    ('OTHER','F [DO_LAM_AUTO]\n', set()),
])
def test_explicit_solver_notices(filename,text,active):
    notices=solver_settings_notices(text,filename)
    assert {n['id'] for n in notices if n['active']}==active
    assert all(n['tone'] in {'warning','info'} for n in notices)
