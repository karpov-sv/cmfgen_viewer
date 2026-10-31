"""Measured population-cycle diagnostics and provisional native recovery recipes."""
from dataclasses import replace
import hashlib
import json

import pytest

from test_runner_auto import auto_workspace
from test_auto_recovery import population_workspace, authenticate, unidentify
from test_auto_performance import performance_workspace
from cmfgen_viewer.auto_diagnostics import population_cycle, control_value
from cmfgen_viewer.runner import run_plan


def write_solutions(path, values, *, nt=4, nd=2):
    with path.open('w') as f:
        for value in values:
            f.write(' STEQ SOLUTION ARRAY\n\n')
            for i in range(1, nt+1):
                f.write(f'{i}( 1)# '+ ' '.join([str(-value/100 if i == 1 else 1.e-8)]*nd)+'\n')


def test_population_cycle_uses_raw_requests_and_preserves_small_coordinates(tmp_path):
    path=tmp_path/'STEQ_VALS'
    write_solutions(path,[.04,-.04,.04])
    e=population_cycle(path,0,4,2,.02)
    assert e['coordinates']==2 and e['complete_solution_arrays']==3
    assert e['depth_start']==1 and e['depth_end']==2
    assert e['raw_maxima_percent']==[.04]*3
    assert population_cycle(path,path.stat().st_size,4,2,.02) is None


@pytest.mark.parametrize('values', [[.04,.04,.04], [.04,-.02,.01], [.01,-.01,.01], [4,-4,4], [.04,-.04]])
def test_declining_or_unestablished_cycles_do_not_authorize_damping(tmp_path,values):
    path=tmp_path/'STEQ_VALS';write_solutions(path,values)
    assert population_cycle(path,0,4,2,.02) is None


@pytest.mark.parametrize('tail', [' STEQ SOLUTION ARRAY\n1( 1)# .0004 .0004\n',
                                 ' STEQ SOLUTION ARRAY\n1( 1)# NaN .0004\n'])
def test_incomplete_or_nonfinite_final_solution_is_not_cycle_evidence(tmp_path,tail):
    path=tmp_path/'STEQ_VALS';write_solutions(path,[.04,-.04,.04])
    path.write_text(path.read_text()+tail)
    assert population_cycle(path,0,4,2,.02) is None


@pytest.fixture
def convergence_workspace(performance_workspace):
    model,plan=performance_workspace
    exe=model.parent/'cmf/exe/cmfgen_dev.exe';code=exe.read_text()
    code=code.replace("out='Model started on: now\\n'", """if mode.startswith('tail_'):
 settled=relaxed if 'relax' in mode else float(get('VADAT','VFRAC_FG','20000'))<=.1 and float(get('VADAT','VFRAC_MOM','20000'))<=.1
 value=(.05 if mode.endswith('_bad') else .005) if settled else .04
out='Model started on: now\\n'""")
    anchor="  sol.write(f' 4( 1)# {t} 0.000001\\n')"
    assert anchor in code
    code=code.replace(anchor,"""  if mode.startswith('tail_'):
   raw=value/100*(-1 if 'relax' in mode and n%2 else 1)
   sol.write(f' 1( 1)# {raw} {raw}\\n 2( 1)# .000001 .000001\\n 3( 1)# .000001 .000001\\n')
"""+anchor)
    code+='''
if mode.startswith('tail_'):
 (p/'OBSFLUX').write_text('Normalized luminosity check (normalized by L[ND])\\n1 1\\n')
 (p/'MEANOPAC').write_text('Depth Tau(Ross)\\n'+''.join('a '+str(i)+' '+str(50*i)+' '+' '.join(['1']*12)+'\\n' for i in [1,2]))
'''
    exe.write_text(code)
    (model/'VADAT').write_text((model/'VADAT').read_text().replace('T [STORE_BA]','F [STORE_BA]')+
                             'F [DO_HYDRO]\n20000 [VFRAC_FG]\n20000 [VFRAC_MOM]\n')
    authenticate(model)
    return model,plan


@pytest.mark.parametrize('mode,policy,phase', [('tail_relax','population_relaxation','population_relaxation_check'),
                                              ('tail_grid','stalled_transfer_refinement','transfer_refinement_check')])
def test_remedy_requires_native_followup_and_independent_verification(convergence_workspace,mode,policy,phase):
    model,plan=convergence_workspace
    result=run_plan(plan(mode))
    assert result['status']=='succeeded',result
    assert result['attempts'][-1]['phase']=='verify'
    assert result['attempts'][-1]['evidence']['fresh_verified']
    trial=next(a for a in result['actions'] if a['policy_id']==policy)
    assert trial['changes']['VADAT']['N_FIX_BA']=='0'
    attempt=next(a for a in result['attempts'] if a['phase']==phase)
    assert attempt['convergence_remedy_check']['raw_maximum_percent']==.005
    assert attempt['recovery_verified']==policy
    assert control_value(model,'VADAT','EPS_TERM')=='0.02'
    if mode=='tail_relax':
        assert control_value(model,'ADJUST_CORRECTIONS','RELAX')=='0.5'
    else:
        assert control_value(model,'VADAT','VFRAC_FG')==control_value(model,'VADAT','VFRAC_MOM')=='0.1'


@pytest.mark.parametrize('mode,policy', [('tail_relax_bad','population_relaxation'),
                                       ('tail_grid_bad','stalled_transfer_refinement')])
def test_unproductive_adjustment_restores_accepted_checkpoint_and_inputs(convergence_workspace,mode,policy):
    model,plan=convergence_workspace
    vadat=(model/'VADAT').read_bytes();saved={}
    def observe(event):
        if event['event']=='auto_action' and event['action']['policy_id']==policy:
            saved['pointer']=(model/'POINT1').read_bytes()
    result=run_plan(plan(mode),observe)
    assert result['status']=='needs_review',result
    assert result['provisional_recovery_rolled_back']==policy
    assert (model/'POINT1').read_bytes()==saved['pointer']
    assert (model/'VADAT').read_bytes()==vadat
    assert not (model/'ADJUST_CORRECTIONS').exists()


def test_unknown_runtime_never_authorizes_population_damping(convergence_workspace):
    model,plan=convergence_workspace
    unidentify(model)
    result=run_plan(plan('tail_relax',max_attempts=4))
    assert not any(a['policy_id']=='population_relaxation' for a in result['actions'])
    assert not (model/'ADJUST_CORRECTIONS').exists()


def test_population_damping_preserves_callers_scoped_controls(convergence_workspace):
    model,plan=convergence_workspace
    text='1 [L_ST]\n1 [L_END]\n1 [RELAX]\n0.1 [T_LIM]\n'
    (model/'ADJUST_CORRECTIONS').write_text(text)
    result=run_plan(plan('tail_relax',max_attempts=2))
    assert not any(a['policy_id']=='population_relaxation' for a in result['actions'])
    assert (model/'ADJUST_CORRECTIONS').read_text()==text


def test_output_only_mode_cannot_be_run_as_main_success(auto_workspace):
    model,make_plan=auto_workspace
    (model/'IN_ITS').write_text((model/'IN_ITS').read_text()+'T [FINAL_OUTPUT_ONLY]\n')
    # build_run_plan returns a reviewable refusal before any native process.
    from cmfgen_viewer.runner_recipe import build_run_plan
    plan=build_run_plan(model,stage='main',cmfgen_root=model.parent/'cmf',atomic_root=model.parent/'atomic')
    assert not plan['ready']
    assert any('output-only native mode' in e for e in plan['errors'])


def test_population_cycle_handles_native_interleaved_depth_chunks(tmp_path):
    path=tmp_path/'STEQ_VALS'
    with path.open('w') as f:
        for value in [.04,-.04,.04]:
            f.write(' STEQ SOLUTION ARRAY\n\n')
            for depth in range(1,26,10):
                for var in range(1,5):
                    row=[-value/100 if var==1 else 1e-8]*min(10,26-depth)
                    f.write(f'{var}({depth:3})# '+' '.join(map(str,row))+'\n')
    result=population_cycle(path,0,4,25,.02)
    assert result['coordinates']==25 and result['depth_end']==25


def test_population_trial_requires_remaining_followup_budget(convergence_workspace):
    model,plan=convergence_workspace
    before=(model/'VADAT').read_bytes()
    result=run_plan(plan('tail_relax',max_iterations=5))
    assert result['status']=='limit_reached',result
    assert not result['actions']
    assert not (model/'ADJUST_CORRECTIONS').exists()
    assert (model/'VADAT').read_bytes()==before


@pytest.mark.parametrize('mode,phase',[('tail_relax','population_relaxation_check'),('tail_grid','transfer_refinement_check')])
def test_interrupted_convergence_trial_restores_accepted_state(convergence_workspace,mode,phase):
    model,plan=convergence_workspace
    before=(model/'VADAT').read_bytes();saved={}
    def interrupt(event):
        if event['event']=='auto_attempt' and event['phase']==phase:
            saved['pointer']=(model/'POINT1').read_bytes()
            raise KeyboardInterrupt()
    result=run_plan(plan(mode),interrupt)
    assert result['status']=='cancelled'
    assert (model/'POINT1').read_bytes()==saved['pointer']
    assert (model/'VADAT').read_bytes()==before
    assert not (model/'ADJUST_CORRECTIONS').exists()


def test_remedy_improvement_cannot_mix_different_xray_sources(tmp_path):
    from cmfgen_viewer.auto_convergence_remedies import _validate
    from cmfgen_viewer.auto_policies import Context
    from cmfgen_viewer.runner_recipe import RunnerError
    context=Context(tmp_path,'success',{}, {}, {}, {'records':[{},{}],'source_changed':True}, [],'iterate',[],'')
    with pytest.raises(RunnerError,match='unchanged structure and source'):
        _validate(context,{})
