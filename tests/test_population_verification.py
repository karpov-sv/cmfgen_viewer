"""Native Lambda fallback defers full verification without accepting it as full."""
import io
import json
from pathlib import Path

import pytest

from test_runner_auto import auto_workspace
from test_auto_recovery import population_workspace, authenticate
from cmfgen_viewer.auto_diagnostics import control_value
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner_output import TerminalOutput


@pytest.fixture
def fallback_workspace(population_workspace):
    model, make = population_workspace
    exe = model.parent/'cmf/exe/cmfgen_dev.exe'
    code = exe.read_text()
    code = code.replace(" if mode=='population_fail' and", """ native_fallback=False
 if mode.startswith('population_fallback') and not lam and (p/'bootstrap-seen').exists():
  path=p/'verification-batches'
  verification_batch=int(path.read_text())+1 if path.exists() else 1
  path.write_text(str(verification_batch))
  native_fallback=verification_batch==1 or mode=='population_fallback_always'
  value=100 if native_fallback else .005
 if mode=='population_fail' and""")
    code = code.replace("  if mode=='lambda' or (mode.startswith('population') and lam):",
                        "  if mode=='lambda' or (mode.startswith('population') and lam) or (native_fallback and n==1):")
    code = code.replace("if fresh else 'BA matrix **NOT** computed",
        "if fresh and not (mode=='population_fallback_bad_ba' and native_fallback and n==1) else 'BA matrix **NOT** computed")
    code = code.replace("v=pack([1e7,1e10,1e10,1., 1e7,2e10,2e10,2.])", """v=pack([1e7,1e10,1e10,1., 1e7,2e10,2e10,2.])
if mode=='population_fallback_bad_physics' and native_fallback:
 v=pack([9e6,9e9,9e9,1., 9e6,18e9,18e9,2.])
if mode=='population_fallback_cumulative' and (p/'bootstrap-seen').exists() and not lam:
 f=1-7e-7*verification_batch
 v=pack([1e7*f,1e10*f,1e10*f,1., 1e7*f,2e10*f,2e10*f,2.])""")
    exe.write_text(code); authenticate(model)
    return model,make


def test_native_fallback_repeats_then_requires_full_and_independent_verification(fallback_workspace):
    model,make=fallback_workspace
    path=model/'IN_ITS';path.write_text(path.read_text()+'T [DO_LAM_AUTO]\n')
    events=[]
    result=run_plan(make('population_fallback'),events.append)
    assert result['status']=='succeeded',result
    checks=[a for a in result['attempts'] if a['phase']=='population_full']
    assert len(checks)==2
    assert checks[0]['verification_pending']
    assert checks[0]['verification_full_steps']==1
    assert 'validation_error' not in checks[0]
    assert 'recovery_verified' not in checks[0]
    assert [r['lambda_iteration'] for r in checks[0]['evidence']['records']]==[False,True]
    assert checks[1]['recovery_verified']=='population_bootstrap'
    assert all(not r['lambda_iteration'] and not r['temperature_fixed'] and r['ba_computed']
               for r in checks[1]['evidence']['records'][-2:])
    assert checks[0]['checkpoint_physics']['element_density_max_relative_change']==0
    assert result['attempts'][-1]['phase']=='verify'
    assert result['attempts'][-1]['evidence']['fresh_verified']
    assert sum(a['policy_id']=='population_bootstrap' for a in result['actions'])==1
    notices=[e for e in events if e['event']=='auto_verification_pending']
    assert len(notices)==1
    output=io.StringIO();TerminalOutput(output).event(notices[0])
    assert 'continue verification' in output.getvalue()
    assert control_value(model,'IN_ITS','DO_LAM_AUTO')=='T'


def test_persistent_fallback_spends_shared_budget_then_rolls_back(fallback_workspace):
    model,make=fallback_workspace
    result=run_plan(make('population_fallback_always',max_iterations=10))
    assert result['status']=='limit_reached',result
    checks=[a for a in result['attempts'] if a['phase']=='population_full']
    assert len(checks)==2 and all(a['verification_pending'] for a in checks)
    assert result['iterations_used']==10
    assert result['provisional_recovery_rolled_back']=='population_bootstrap'
    assert not any(a.get('recovery_verified') for a in result['attempts'])
    assert int((model/'POINT1').read_text().splitlines()[1].split()[1])==result['attempts'][0]['evidence']['checkpoint']
    assert control_value(model,'VADAT','FIX_T')=='F'
    assert control_value(model,'VADAT','MAX_LAM') is None
    issue=json.loads(Path(result['issue_report']).read_text())
    assert any(a.get('verification_pending') for a in issue['attempts'])


@pytest.mark.parametrize('scenario,reason',[('population_fallback_bad_physics','abundance'),
                                          ('population_fallback_bad_ba','fresh-BA')])
def test_fallback_cannot_hide_physical_or_matrix_failure(fallback_workspace,scenario,reason):
    model,make=fallback_workspace
    result=run_plan(make(scenario))
    assert result['status']=='needs_review',result
    checks=[a for a in result['attempts'] if a['phase']=='population_full']
    assert len(checks)==1 and 'verification_pending' not in checks[0]
    assert reason in checks[0]['validation_error']
    assert result['provisional_recovery_rolled_back']=='population_bootstrap'


def test_cancellation_while_verification_pending_restores_recipe_baseline(fallback_workspace):
    model,make=fallback_workspace
    seen=0
    def cancel(event):
        nonlocal seen
        if event['event']=='auto_attempt' and event['phase']=='population_full':
            seen+=1
            if seen==2:raise KeyboardInterrupt()
    result=run_plan(make('population_fallback'),cancel)
    assert result['status']=='cancelled',result
    assert result['provisional_recovery_rolled_back']=='population_bootstrap'
    assert control_value(model,'VADAT','FIX_T')=='F'
    assert control_value(model,'IN_ITS','DO_LAM_IT') is None


def test_repeated_checks_use_original_physical_baseline(fallback_workspace):
    model,make=fallback_workspace
    result=run_plan(make('population_fallback_cumulative'))
    assert result['status']=='needs_review',result
    checks=[a for a in result['attempts'] if a['phase']=='population_full']
    assert len(checks)==2 and checks[0]['verification_pending']
    assert 'abundance' in checks[1]['validation_error']
    assert result['provisional_recovery_rolled_back']=='population_bootstrap'
