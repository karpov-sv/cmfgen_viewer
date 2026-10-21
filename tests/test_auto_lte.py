"""Automatic temporary LTE fallback only for confirmed fresh initialization failures."""
import json
from pathlib import Path

import pytest

from test_runner_auto import auto_workspace
from cmfgen_viewer.auto_diagnostics import control_value
from cmfgen_viewer.runner import run_plan

PREFIX = r'''
import json
method=get('VADAT','DC_METH','ED')
with (p/'initialization-trace.jsonl').open('a') as trace:
 trace.write(json.dumps({'method':method,'t_exc':get('VADAT','T_EXC','unset'),
                        'count':get('IN_ITS','NUM_ITS','unset')})+'\n')
fail=(mode.startswith('lte_') and method!='LTE' and not (p/'POINT1').exists()) or mode=='lte_always' or mode=='lte_existing'
if mode=='lte_followup_bad' and method!='LTE' and (p/'POINT1').exists():
 (p/'SCRTEMP').write_bytes(b'poisoned')
 print('Fortran runtime error: independent continuation failed',flush=True)
 raise SystemExit(1)
if method=='LTE' and mode=='lte_timeout':time.sleep(10)
if fail:
 out='Model started on: now\nStarting a new model.\nCalling AUTO_ADD_ION\n'
 if mode=='lte_after_iteration':out+='Current great iteration count is 1\n'
 (p/'OUTGEN').write_text(out)
 print(out,flush=True)
 if mode=='lte_opaque':
  print('SIGSEGV: opaque initialization crash',flush=True)
 elif mode=='lte_zero_rgu':
  print('Error in SETPOP_WLD_V3 -- zero RGU',flush=True)
 else:
  print('Fortran runtime error: population conversion failed',flush=True)
  print('#0 cnvt_fr_dc_' if mode=='lte_conversion' else '#0 scale_pops_',flush=True)
 if mode=='lte_other_error':print('Some normalized luminosities are out by a factor of 2',flush=True)
 # A failed fresh attempt can leave incomplete checkpoints. They must not
 # turn the LTE retry into an accidental continuation.
 (p/'POINT1').write_text('incomplete')
 (p/'SCRTEMP').write_bytes(b'bad partial checkpoint')
 raise SystemExit(0 if mode=='lte_zero_rgu' else 1)
'''


@pytest.fixture
def lte_workspace(auto_workspace):
    model,make=auto_workspace
    (model/'VADAT').write_text((model/'VADAT').read_text()+'ED [DC_METH]\nF [LIN_INT]\nF [LTE_EST]\n')
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    exe.write_text(exe.read_text().replace("count=int(get('IN_ITS'", PREFIX+"\ncount=int(get('IN_ITS'"))
    return model,make


@pytest.mark.parametrize('scenario',['lte_scaling','lte_zero_rgu','lte_conversion'])
def test_confirmed_fresh_failure_gets_lte_then_normal_continuation(lte_workspace,scenario):
    model,plan=lte_workspace
    result=run_plan(plan(scenario))
    assert result['status']=='succeeded',result
    assert [a['policy_id'] for a in result['actions']]==['lte_initialization','verify_candidate']
    assert [a['phase'] for a in result['attempts']]==['iterate','lte_initialization','lte_continuation','verify']
    trace=[json.loads(row) for row in (model/'initialization-trace.jsonl').read_text().splitlines()]
    assert [r['method'] for r in trace]==['ED','LTE','ED','ED']
    assert trace[1]['t_exc']=='1' and trace[1]['count']=='2'
    assert result['attempts'][1]['lte_bootstrap_completed']
    assert result['attempts'][2]['lte_recovery_verified']
    assert result['attempts'][2]['recovery_verified']=='lte_initialization'
    assert control_value(model,'VADAT','DC_METH')=='ED'
    assert control_value(model,'VADAT','T_EXC') is None
    assert (model/'IN_ITS').read_text()=='5 [NUM_ITS]\n'
    native=json.loads((Path(result['attempts'][1]['journal'])/'result.json').read_text())
    assert native['initialization']=={'method':'LTE','t_exc':1.0,'temporary':True}
    assert 'LTE' in (Path(native['journal'])/'effective/VADAT').read_text()


def test_existing_excitation_temperature_is_used_and_restored(lte_workspace):
    model,plan=lte_workspace
    (model/'VADAT').write_text((model/'VADAT').read_text()+'0.8 [T_EXC] ! keep chosen value\n')
    result=run_plan(plan('lte_scaling'))
    assert result['status']=='succeeded',result
    assert result['attempts'][1]['lte_t_exc']==0.8
    assert '0.8 [T_EXC] ! keep chosen value' in (model/'VADAT').read_text()


@pytest.mark.parametrize('scenario',['lte_opaque','lte_after_iteration','lte_other_error'])
def test_suspected_late_or_mixed_failures_do_not_select_lte(lte_workspace,scenario):
    model,plan=lte_workspace
    original=(model/'VADAT').read_bytes()
    result=run_plan(plan(scenario))
    assert result['status']=='needs_review',result
    assert len(result['attempts'])==1
    assert not result['actions']
    assert (model/'VADAT').read_bytes()==original
    assert not (model/'POINT1').exists()


@pytest.mark.parametrize('extra',['T [LIN_INT]\n','T [LTE_EST]\n','0 [T_EXC]\n','NaN [T_EXC]\n'])
def test_incompatible_or_invalid_initialization_is_not_rewritten(lte_workspace,extra):
    model,plan=lte_workspace
    key=extra.split('[')[1].split(']')[0]
    text=(model/'VADAT').read_text()
    text=''.join(row for row in text.splitlines(keepends=True) if f'[{key}]' not in row)+extra
    (model/'VADAT').write_text(text)
    result=run_plan(plan('lte_scaling'))
    assert result['status']=='needs_review',result
    assert not result['actions']
    assert (model/'VADAT').read_text()==text


def test_lte_already_used_is_not_retried(lte_workspace):
    model,plan=lte_workspace
    (model/'VADAT').write_text((model/'VADAT').read_text().replace('ED [DC_METH]','LTE [DC_METH]')+'1 [T_EXC]\n')
    result=run_plan(plan('lte_always'))
    assert result['status']=='needs_review'
    assert not result['actions']
    assert 'already in use' in result['reason']


def test_explicit_temporary_lte_is_not_retried(lte_workspace):
    model,plan=lte_workspace
    result=run_plan(plan('lte_always',lte_initialization=True))
    assert result['status']=='needs_review'
    assert not result['actions']
    assert control_value(model,'VADAT','DC_METH')=='ED'


def test_failed_normal_followup_rolls_back_the_provisional_lte_checkpoint(lte_workspace):
    model,plan=lte_workspace
    original=(model/'VADAT').read_bytes()
    result=run_plan(plan('lte_followup_bad'))
    assert result['status']=='needs_review',result
    assert [a['policy_id'] for a in result['actions']]==['lte_initialization']
    assert result['provisional_recovery_rolled_back']=='lte_initialization'
    assert not (model/'POINT1').exists()
    assert not (model/'SCRTEMP').exists()
    assert (model/'VADAT').read_bytes()==original


def test_continuation_failure_never_reseeds_a_healthy_checkpoint(lte_workspace):
    model,plan=lte_workspace
    run_plan(plan('good'))
    checkpoint=(model/'SCRTEMP').read_bytes()
    pointer=(model/'POINT1').read_bytes()
    result=run_plan(plan('lte_existing'))
    assert result['status']=='needs_review'
    assert not result['actions']
    assert 'preserving the continuation checkpoint' in result['reason']
    assert (model/'SCRTEMP').read_bytes()==checkpoint
    assert (model/'POINT1').read_bytes()==pointer


def test_explicit_fresh_start_retains_original_checkpoint_for_failed_lte_recovery(lte_workspace):
    model,plan=lte_workspace
    run_plan(plan('good'))
    checkpoint=(model/'SCRTEMP').read_bytes()
    pointer=(model/'POINT1').read_bytes()
    result=run_plan(plan('lte_always',fresh_start=True))
    assert result['status']=='needs_review',result
    assert len(result['actions'])==1
    assert (model/'SCRTEMP').read_bytes()==checkpoint
    assert (model/'POINT1').read_bytes()==pointer
    assert control_value(model,'VADAT','DC_METH')=='ED'


def test_lte_recipe_is_not_started_without_verification_budget(lte_workspace):
    model,plan=lte_workspace
    result=run_plan(plan('lte_scaling',max_iterations=6))
    assert result['status']=='limit_reached'
    assert len(result['attempts'])==1
    assert not result['actions']
    assert not (model/'POINT1').exists()


def test_timeout_restores_temporary_lte_controls(lte_workspace):
    model,plan=lte_workspace
    original=(model/'VADAT').read_bytes()
    result=run_plan(plan('lte_timeout',timeout=2))
    assert result['status']=='timeout',result
    assert (model/'VADAT').read_bytes()==original
    assert not (model/'POINT1').exists()


def test_cancellation_after_lte_bootstrap_rolls_back(lte_workspace):
    model,plan=lte_workspace
    original=(model/'VADAT').read_bytes()
    def cancel(item):
        if item['event']=='auto_assessment' and item['attempt']==2:raise KeyboardInterrupt()
    result=run_plan(plan('lte_scaling'),cancel)
    assert result['status']=='cancelled'
    assert (model/'VADAT').read_bytes()==original
    assert not (model/'POINT1').exists()
