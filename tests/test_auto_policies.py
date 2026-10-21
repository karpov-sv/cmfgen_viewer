"""Registry extensions exercise the real loop without adding runner branches."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from test_runner_auto import auto_workspace
from test_auto_hydro import hydro_workspace
from cmfgen_viewer import auto_policies as policies
from cmfgen_viewer.auto_diagnostics import control_value
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner_recipe import RunnerError


def register(monkeypatch, handler, *, steps=False):
    rule=policies.Policy('test_remedy',1,'failure','Regression remedy',handler,1)
    monkeypatch.setattr(policies,'POLICIES',(rule,*policies.POLICIES))


def repair_if_unknown(ctx):
    text='\n'.join(p.get('diagnostic_tail','') for p in ctx.native_result.get('passes',[]))
    if 'unknown issue' in text:
        return policies.Decision('action','Diagnosed test failure',action='test_remedy',
                                 changes={'ADJUST_CORRECTIONS':{'RELAX':'0.5'}})


def make_repairable(model):
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    exe.write_text(exe.read_text().replace("if mode=='unknown':",
                    "if mode=='unknown' and not (p/'ADJUST_CORRECTIONS').exists():"))


def test_new_registered_fix_runs_without_controller_changes(auto_workspace,monkeypatch):
    model,plan=auto_workspace
    make_repairable(model)
    register(monkeypatch,repair_if_unknown)
    result=run_plan(plan('unknown'))
    assert result['status']=='succeeded',result
    assert [a['policy_id'] for a in result['actions']]==['test_remedy','verify_candidate']
    assert result['attempts'][0]['decision']['policy_id']=='test_remedy'
    assert not (Path(result['journal'])/'issue.json').exists()


def test_registered_multistep_fix_is_provisional_until_verified(auto_workspace,monkeypatch):
    model,plan=auto_workspace
    make_repairable(model)
    checked=[]
    def validate(ctx):
        checked.append(ctx.phase)
        return {'extension_check':ctx.phase}
    def handler(ctx):
        decision=repair_if_unknown(ctx)
        return replace(decision,steps=(policies.RecoveryStep('custom_trial',2,validate),
                                      policies.RecoveryStep('custom_verify',2,validate))) if decision else None
    register(monkeypatch,handler)
    result=run_plan(plan('unknown'))
    assert result['status']=='succeeded',result
    assert checked==['custom_trial','custom_verify']
    assert result['attempts'][2]['recovery_verified']=='test_remedy'
    assert control_value(model,'ADJUST_CORRECTIONS','RELAX')=='0.5'


def test_failed_extension_verification_rolls_back_its_changes(auto_workspace,monkeypatch):
    model,plan=auto_workspace
    make_repairable(model)
    def reject(ctx):raise RunnerError('Independent extension verification failed')
    def handler(ctx):
        decision=repair_if_unknown(ctx)
        return replace(decision,steps=(policies.RecoveryStep('custom_trial',2,lambda ctx:{}),
                                      policies.RecoveryStep('custom_verify',2,reject))) if decision else None
    register(monkeypatch,handler)
    result=run_plan(plan('unknown'))
    assert result['status']=='needs_review',result
    assert result['provisional_recovery_rolled_back']=='test_remedy'
    assert not (model/'ADJUST_CORRECTIONS').exists()
    assert not (model/'POINT1').exists()
    issue=json.loads(Path(result['issue_report']).read_text())
    assert 'Independent extension verification failed' in issue['reason']


def test_unknown_problem_leaves_native_evidence_and_policy_trail(auto_workspace):
    _model,plan=auto_workspace
    result=run_plan(plan('unknown'))
    issue=json.loads(Path(result['issue_report']).read_text())
    assert issue['status']=='needs_review'
    assert issue['attempts'][0]['policy_evaluations']
    assert 'unknown issue' in issue['last_native_result']['passes'][0]['diagnostic_tail']
    assert Path(result['issue_report']).with_suffix('.md').exists()


def test_registry_change_invalidates_reviewed_plan(auto_workspace,monkeypatch):
    _model,plan=auto_workspace
    prepared=plan()
    monkeypatch.setattr(policies,'POLICIES',(replace(policies.POLICIES[0],version=2),*policies.POLICIES[1:]))
    with pytest.raises(RunnerError,match='policies changed'):
        run_plan(prepared)


def test_registered_policy_cannot_bypass_convergence_invariants(auto_workspace,monkeypatch):
    _model,plan=auto_workspace
    rule=policies.Policy('bad_acceptance',1,'success','Invalid acceptance',
                         lambda ctx:policies.Decision('converged','Accept without independent verification'))
    monkeypatch.setattr(policies,'POLICIES',(rule,*policies.POLICIES))
    result=run_plan(plan())
    assert result['status']=='needs_review'
    assert 'without independent' in result['reason']


def test_known_cache_fix_composes_with_pending_hydro_recipe(hydro_workspace):
    model,plan,_original=hydro_workspace
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    fault="""
if mode=='hydro_cache_once' and done==1 and not (p/'injected-cache-error').exists():
 (p/'injected-cache-error').touch()
 (p/'POINT1').write_text('broken')
 (p/'SCRTEMP').write_bytes(b'broken')
 print('Error - incorrect reading of EDDFACTOR in COMP_J_BLANK',flush=True)
 raise SystemExit(1)
"""
    exe.write_text(exe.read_text().replace('low=0.4',fault+'\nlow=0.4'))
    result=run_plan(plan('hydro_cache_once'))
    assert result['status']=='succeeded',result
    assert [a['policy_id'] for a in result['actions']]==['hydro_bootstrap','radiation_cache','verify_candidate']
    trace=[json.loads(row) for row in (model/'guard-trace.jsonl').read_text().splitlines()]
    assert sum(row['guard']=='F' for row in trace)==1
    assert result['attempts'][2]['restored_state']=='recovery_step'
    assert not (Path(result['journal'])/'provisional').exists()


def test_slow_consistent_decay_is_not_a_stall(auto_workspace):
    model,plan=auto_workspace
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    exe.write_text(exe.read_text().replace("if mode=='stall':value=1", "if mode=='stall':value=1-0.001*attempt"))
    result=run_plan(plan('stall',max_attempts=5))
    assert result['status']=='limit_reached',result
    assert len(result['attempts'])==5
    assert not result['actions']
