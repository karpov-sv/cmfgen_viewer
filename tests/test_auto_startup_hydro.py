"""Copied dormant hydro schedules recover only through audited startup steps."""
import json
import sys
from pathlib import Path

import pytest

from test_runner_auto import auto_workspace
from test_auto_recovery import population_workspace, authenticate, unidentify
from test_auto_pop import SOURCE
from test_auto_hydro import BEFORE_SOLVE, AFTER_SOLVE, RVSIG
from cmfgen_viewer.pop_initialization import POP_MARKER
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.auto_diagnostics import control_value
from cmfgen_viewer.auto_hydro import structure_fixed


@pytest.fixture
def startup_hydro_workspace(population_workspace):
    model, make = population_workspace
    for name in ('POINT1','POINT2'):
        (model/name).write_text('28-Feb-2004 !Format date\n1 1 1 -1000 T\n')
    (model/'VADAT').write_text((model/'VADAT').read_text()+
        'POP [DC_METH]\nT [LIN_INT]\nT [POP_SCALE]\nT [DO_HYDRO]\nT [STOP_IF_MW]\n')
    (model/'HYDRO_DEFAULTS').write_text('0 [N_ITS]\n0 [ITS_DONE]\n2 [STRT_ITS]\n10 [FREQ_ITS]\n')
    (model/'MODEL_SPEC').write_text((model/'MODEL_SPEC').read_text()+'0,1,1 [HI_ISF]\n')
    for name in ('He2_IN','HI_IN'): (model/name).write_text(SOURCE)
    (model/'RVSIG_COL').write_text(RVSIG)
    (model/'ROSSELAND_LTE_TAB').write_text('1 !Number of temperatures\n1 !Number of densities\n1 2 3 4 5 6 7 8\n')
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    code=exe.read_text()
    before=BEFORE_SOLVE.replace("'Model started on: now\\nCurrent great iteration count is '",
        "'Model started on: now\\n'+('Starting a new model.\\nSetting ITS_DONE keyword in HYDRO_DEFAULTS to 0\\n' if not (p/'POINT1').exists() else '')+"+repr(POP_MARKER+'\nCurrent great iteration count is '))
    before = before.replace("stop=get", r'''if not (p/'POINT1').exists():
 path=p/'HYDRO_DEFAULTS'
 lines=path.read_text().splitlines()
 for i,line in enumerate(lines):
  if '[ITS_DONE]' in line:
   column=line.index('[ITS_DONE]');lines[i]='0'+' '*(column-1)+line[column:]
 path.write_text('\n'.join(line.rstrip() for line in lines)+'\n')
stop=get''', 1)
    code=code.replace("fresh=get('VADAT'",before+"\nfresh=get('VADAT'")
    code=code.replace("out='Model started on: now\\n'", "out='Model started on: now\\n'+('Starting a new model.\\nSetting ITS_DONE keyword in HYDRO_DEFAULTS to 0\\n' if not (p/'POINT1').exists() else '')+"+repr(POP_MARKER+'\n'))
    code+=AFTER_SOLVE.replace("if stop=='F' and mode!='hydro_no_revision':", "if stop=='F' and start==2 and mode!='hydro_no_revision':")
    exe.write_text(code);authenticate(model)
    return model,make


def fresh(model):
    for name in ('POINT1','POINT2','SCRTEMP','MODEL','RVTJ','MOD_SUM'):
        (model/name).unlink(missing_ok=True)


@pytest.mark.parametrize('is_fresh',[True,False])
def test_rearms_dormant_startup_and_verifies_guarded_followup(startup_hydro_workspace,is_fresh):
    model,make=startup_hydro_workspace
    if is_fresh:fresh(model)
    result=run_plan(make('startup_hydro'))
    assert result['status']=='succeeded',result
    assert result['actions'][0]['policy_id']=='startup_hydro'
    phases=[a['phase'] for a in result['attempts']]
    assert ('hydro_pop_seed' in phases)==is_fresh
    assert 'hydro_bridge' in phases and 'hydro_guarded' in phases
    assert control_value(model,'VADAT','STOP_IF_MW')=='T'
    assert control_value(model,'VADAT','DC_METH')=='POP'
    assert control_value(model,'HYDRO_DEFAULTS','N_ITS')=='0'
    assert control_value(model,'HYDRO_DEFAULTS','ITS_DONE')=='1'
    assert structure_fixed(model)
    if is_fresh:
        seed=next(a for a in result['attempts'] if a['phase']=='hydro_pop_seed')
        assert seed['startup_pop_checkpoint_verified']
        native=json.loads((Path(seed['journal'])/'result.json').read_text())
        assert native['initialization']['method']=='POP'
    trace=[json.loads(l) for l in (model/'guard-trace.jsonl').read_text().splitlines()]
    assert [a['guard'] for a in trace]==(['T','F','F','T','T'] if is_fresh else ['T','F','T','T'])


@pytest.mark.parametrize('scenario',['hydro_crash','hydro_no_revision','hydro_rebound'])
def test_failed_startup_recipe_restores_original_fresh_controls(startup_hydro_workspace,scenario):
    model,make=startup_hydro_workspace;fresh(model)
    old={n:(model/n).read_bytes() for n in ('VADAT','IN_ITS','HYDRO_DEFAULTS','RVSIG_COL')}
    result=run_plan(make(scenario))
    assert result['status']=='needs_review',result
    assert result['provisional_recovery_rolled_back']=='startup_hydro'
    for n,value in old.items():assert (model/n).read_bytes()==value
    assert not (model/'POINT1').exists()


@pytest.mark.parametrize('problem',['negative','severe','not_pop','wrong_schedule','shallow','unidentified'])
def test_unproven_startup_cases_remain_ineligible(startup_hydro_workspace,problem):
    model,make=startup_hydro_workspace;fresh(model)
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    if problem in ('negative','severe'):
        exe.write_text(exe.read_text().replace('low=0.4 if done==0',('low=-0.4' if problem=='negative' else 'low=0.1')+' if done==0'))
    if problem=='not_pop':(model/'VADAT').write_text((model/'VADAT').read_text().replace('POP [DC_METH]','R [DC_METH]'))
    if problem=='wrong_schedule':(model/'HYDRO_DEFAULTS').write_text((model/'HYDRO_DEFAULTS').read_text().replace('2 [STRT_ITS]','5 [STRT_ITS]'))
    authenticate(model)
    if problem=='unidentified':unidentify(model)
    result=run_plan(make('hydro_shallow' if problem=='shallow' else 'startup_hydro'))
    assert result['status']=='needs_review',result
    assert not result['actions']
    assert control_value(model,'HYDRO_DEFAULTS','N_ITS')=='0'
    assert not (model/'POINT1').exists()


def test_startup_cancellation_and_budget_do_not_leave_guard_disabled(startup_hydro_workspace):
    model,make=startup_hydro_workspace;fresh(model)
    result=run_plan(make('startup_hydro',max_iterations=6))
    assert result['status']=='limit_reached' and not result['actions']
    def cancel(event):
        if event['event']=='auto_attempt' and event['phase']=='hydro_bridge':raise KeyboardInterrupt()
    result=run_plan(make('startup_hydro'),cancel)
    assert result['status']=='cancelled'
    assert control_value(model,'VADAT','STOP_IF_MW')=='T'
    assert control_value(model,'HYDRO_DEFAULTS','N_ITS')=='0'
    assert not (model/'POINT1').exists()



def test_fresh_start_can_reset_copied_completed_counter_before_rearming(startup_hydro_workspace):
    model,make=startup_hydro_workspace;fresh(model)
    path=model/'HYDRO_DEFAULTS'
    path.write_text(path.read_text().replace('0 [ITS_DONE]','7 [ITS_DONE]'))
    result=run_plan(make('startup_hydro'))
    assert result['status']=='succeeded',result
    assert result['actions'][0]['changes']['HYDRO_DEFAULTS']=={'N_ITS':'1','ITS_DONE':'0'}
    assert control_value(model,'HYDRO_DEFAULTS','ITS_DONE')=='1'
