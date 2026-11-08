"""Completed global-Ng pairs stay provisional until the remaining checks pass."""
from pathlib import Path
import json

import pytest

from test_auto_global_ng import ng_workspace, ng_model, projection_model
from test_runner_auto import auto_workspace
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer import auto_trial_resume


def interrupted(make, pair=2):
    stop=False
    def emit(event):
        nonlocal stop
        if event['event']=='auto_trial_pair_saved' and event['completed_pairs']==pair:stop=True
    return run_plan(make('ng_good',max_attempts=15,max_iterations=50),emit,stop_requested=lambda:stop)


def test_resume_finishes_only_remaining_pair_without_reapplying_seed(ng_workspace):
    model,make=ng_workspace
    first=interrupted(make)
    assert first['status']=='stopped',first
    saved=json.loads((model/'.cmfgen-runs'/auto_trial_resume.NAME).read_text())
    assert saved['completed_pairs']==2
    assert int((model/'POINT1').read_text().splitlines()[1].split()[1])==saved['baseline']['checkpoint']
    receipt=(model/'.cmfgen-runs/global-ng-trials.json').read_bytes()
    done=False
    def emit(event):
        nonlocal done
        if event['event']=='auto_performance_trial' and event['outcome']=='accepted':done=True
    second=run_plan(make('ng_good',max_attempts=8,max_iterations=20),emit,stop_requested=lambda:done)
    assert second['status']=='stopped',second
    assert second['resumed_trial']['completed_pairs']==2
    assert [a['phase'] for a in second['attempts']]==['global_ng_check']
    assert second['iterations_used']==2
    assert second['actions'][0]['trial_outcome']=='accepted'
    assert (model/'.cmfgen-runs/global-ng-trials.json').read_bytes()==receipt
    assert not (model/'.cmfgen-runs'/auto_trial_resume.NAME).exists()
    assert 'numerical_convergence' not in second


def test_resume_first_pair_still_requires_four_full_solves(ng_workspace):
    model,make=ng_workspace;first=interrupted(make,1)
    assert first['status']=='stopped'
    done=False
    def emit(event):
        nonlocal done
        if event['event']=='auto_performance_trial':done=True
    result=run_plan(make('ng_good',max_attempts=8,max_iterations=20),emit,stop_requested=lambda:done)
    assert result['resumed_trial']['completed_pairs']==1
    assert [a['phase'] for a in result['attempts']]==['global_ng_settle2','global_ng_check']
    assert result['iterations_used']==4
    assert result['actions'][0]['trial_outcome']=='accepted'


@pytest.mark.parametrize('fault',['checkpoint','controls','atomic','candidate','budget','counter','owner','manifest','unsafe','policy','evidence','diagnostics','running','validation'])
def test_resume_refuses_changed_or_incomplete_state(ng_workspace,fault):
    model,make=ng_workspace;interrupted(make)
    plan=make('ng_good',max_attempts=8,max_iterations=20)
    path=model/'.cmfgen-runs'/auto_trial_resume.NAME;value=json.loads(path.read_text())
    if fault=='checkpoint':(model/'SCRTEMP').write_bytes((model/'SCRTEMP').read_bytes()+b' ')
    if fault=='controls':(model/'VADAT').write_text((model/'VADAT').read_text()+'! edited\n')
    if fault=='atomic':Path(plan['links'][0]['target']).write_text('new atomic data')
    if fault=='candidate':(model/value['candidate']/'SCRTEMP').write_bytes(b'changed')
    if fault=='budget':plan['auto']['max_iterations']=4
    if fault=='counter':value['resumes']=2;path.write_text(json.dumps(value))
    if fault=='owner':
        owner=model/value['owner']/'result.json';d=json.loads(owner.read_text());d['status']='needs_review';owner.write_text(json.dumps(d))
    if fault=='manifest':value['candidate_hashes'].pop('SCRTEMP');path.write_text(json.dumps(value))
    if fault=='unsafe':value['candidate']='../outside';path.write_text(json.dumps(value))
    if fault=='policy':value['policy_version']+=1;path.write_text(json.dumps(value))
    if fault=='evidence':value['evidence']['ng_accelerations']=[1];path.write_text(json.dumps(value))
    if fault=='diagnostics':value['baseline_diagnostics']={'../VADAT':'bad'};path.write_text(json.dumps(value))
    if fault=='running':
        owner=model/value['owner']/'result.json';d=json.loads(owner.read_text());d['status']='running';owner.write_text(json.dumps(d))
    if fault=='validation':
        owner=model/value['pair_owner']/'result.json';d=json.loads(owner.read_text())
        for a in d['attempts']:a.pop('global_ng_check',None)
        owner.write_text(json.dumps(d))
    before=(model/'SCRTEMP').read_bytes()
    assert not auto_trial_resume.load(model,plan)['usable']
    assert (model/'SCRTEMP').read_bytes()==before


def test_second_interruption_restores_baseline_and_retains_completed_pairs(ng_workspace):
    model,make=ng_workspace;interrupted(make)
    before=(model/'SCRTEMP').read_bytes();stop=False
    def emit(event):
        nonlocal stop
        if event['event']=='auto_trial_resumed':stop=True
    result=run_plan(make('ng_good',max_attempts=8,max_iterations=20),emit,stop_requested=lambda:stop)
    assert result['status']=='stopped' and not result['attempts']
    assert (model/'SCRTEMP').read_bytes()==before
    value=json.loads((model/'.cmfgen-runs'/auto_trial_resume.NAME).read_text())
    assert value['resumes']==1 and value['completed_pairs']==2
    assert auto_trial_resume.load(model,make('ng_good',max_attempts=8,max_iterations=20))['usable']


def test_resumed_trial_rejection_discards_provisional_gain(ng_workspace):
    model,make=ng_workspace;interrupted(make)
    before=(model/'SCRTEMP').read_bytes();rejected=False
    def emit(event):
        nonlocal rejected
        if event['event']=='auto_performance_trial':
            assert event['outcome']=='rejected';rejected=True
    result=run_plan(make('ng_bad',max_attempts=8,max_iterations=20),emit,stop_requested=lambda:rejected)
    assert rejected and result['status']=='stopped',result
    assert result['actions'][0]['trial_outcome']=='rejected'
    assert (model/'SCRTEMP').read_bytes()==before
    assert not (model/'.cmfgen-runs'/auto_trial_resume.NAME).exists()


def test_new_ordinary_progress_is_never_rewound(ng_workspace):
    model,make=ng_workspace;interrupted(make)
    native={k:v for k,v in make('ng_good').items() if k not in {'kind','auto'}}
    result=run_plan(native,diagnose_main=False)
    assert result['status']=='succeeded'
    before=(model/'SCRTEMP').read_bytes()
    offer=auto_trial_resume.load(model,make('ng_good',max_attempts=8,max_iterations=20))
    assert not offer['usable'] and 'baseline changed' in offer['reason']
    assert (model/'SCRTEMP').read_bytes()==before


def test_post_restore_failure_still_rolls_back_owned_controls(ng_workspace,monkeypatch):
    model,make=ng_workspace;interrupted(make)
    before={n:(model/n).read_bytes() if (model/n).exists() else None
            for n in ['SCRTEMP','POINT1','POINT2','VADAT','IN_ITS','OBSFLUX','MEANOPAC']}
    original=auto_trial_resume.activate
    def fail(*args,**kwargs):
        original(*args,**kwargs)
        raise OSError('injected failure after provisional publication')
    monkeypatch.setattr(auto_trial_resume,'activate',fail)
    result=run_plan(make('ng_good',max_attempts=8,max_iterations=20))
    assert result['status']=='needs_review' and not result['attempts'],result
    assert not result.get('recovery_error'),result
    assert {n:(model/n).read_bytes() if (model/n).exists() else None for n in before}==before


def test_resume_snapshot_enospc_keeps_conservative_rollback(ng_workspace,monkeypatch):
    from cmfgen_viewer import runner_auto
    from test_auto_global_ng import recovery_bytes,assert_restored
    model,make=ng_workspace;original=runner_auto._capture;stop=False;baseline={}
    def capture(model,journal,*args,**kwargs):
        if journal.name=='trial-resume':raise OSError('injected resume ENOSPC')
        return original(model,journal,*args,**kwargs)
    monkeypatch.setattr(runner_auto,'_capture',capture)
    def emit(event):
        nonlocal stop
        if event['event']=='auto_action' and event['action']['kind']=='global_ng':baseline.update(recovery_bytes(event['action']))
        if event['event']=='auto_assessment' and event['checkpoint']==50:stop=True
    result=run_plan(make('ng_good',max_attempts=15,max_iterations=50),emit,stop_requested=lambda:stop)
    assert result['status']=='stopped',result
    assert not (model/'.cmfgen-runs'/auto_trial_resume.NAME).exists()
    assert_restored(model,baseline)


def test_resume_log_marks_retained_solves_as_provisional():
    import io
    from cmfgen_viewer.runner_output import TerminalOutput
    stream=io.StringIO();output=TerminalOutput(stream)
    output.event({'event':'auto_trial_resumed','policy_id':'global_ng','completed_pairs':2,'remaining_full_solves':2})
    assert '4 of 6 verification solves retained' in stream.getvalue()
    assert '2 still required' in stream.getvalue()
    assert 'provisional' in stream.getvalue()
