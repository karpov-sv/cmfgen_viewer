"""Restart diagnosis must reuse accepted evidence, never provisional progress."""
from pathlib import Path
import json
import os
import shutil

import pytest

from test_runner_auto import auto_workspace
from test_auto_global_ng import ng_workspace, ng_model, projection_model
from cmfgen_viewer import auto_history
from cmfgen_viewer.runner import run_plan


@pytest.fixture
def accepted(auto_workspace):
    model, make = auto_workspace
    result = run_plan(make())
    assert result['status'] == 'succeeded'
    plan = make()
    assert auto_history.load(model, plan)['usable']
    return model, make, plan, result


def test_candidate_restart_starts_independent_verification_without_ordinary_batch(accepted):
    model, make, _, _ = accepted
    result = run_plan(make())
    assert result['status'] == 'succeeded', result
    assert result['restart_history']['usable']
    assert result['startup_diagnosis']['decision']['policy_id'] == 'verify_candidate'
    assert [a['phase'] for a in result['attempts']] == ['verify']
    assert result['attempts'][0]['evidence']['fresh_verified']


def test_historical_candidate_alone_cannot_certify_convergence(accepted):
    model, make, _, _ = accepted
    stopped = False
    def emit(event):
        nonlocal stopped
        if event['event']=='auto_action':stopped=True
    result=run_plan(make(),emit,stop_requested=lambda:stopped)
    assert result['status']=='stopped' and not result['attempts']
    assert 'numerical_convergence' not in result


@pytest.mark.parametrize('name', ['SCRTEMP','POINT1','VADAT','MODEL_SPEC','GAMMAS_IN'])
def test_changed_checkpoint_or_physics_refuses_history_even_at_same_counter(accepted,name):
    model, _, plan, _ = accepted
    path=model/name;info=path.stat();path.write_bytes(path.read_bytes()+b' ')
    os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns))
    assert not auto_history.load(model,plan)['usable']


def test_changed_executable_or_atomic_data_refuses_history(accepted):
    model, _, plan, _ = accepted
    atomic=Path(plan['links'][0]['target']);atomic.write_text('changed')
    assert not auto_history.load(model,plan)['usable']


def test_copied_model_uses_contents_not_original_paths_or_timestamps(accepted,tmp_path):
    model, _, plan, _ = accepted
    copied=tmp_path/'copy';shutil.copytree(model,copied,symlinks=True)
    for path in copied.iterdir():
        if path.is_file() and not path.is_symlink():os.utime(path,None)
    moved={**plan,'model':str(copied),'inputs':[
        {**r,'path':str(copied/Path(r['path']).name)} if Path(r['path']).parent==model else r
        for r in plan['inputs']]}
    assert auto_history.load(copied,moved)['usable']


def test_stale_radiation_requires_refresh_and_raw_appends_cannot_feed_projection(accepted):
    model, _, plan, _ = accepted
    (model/'OBSFLUX').write_text('discarded partial batch')
    with (model/'STEQ_VALS').open('a') as stream:stream.write('partial attempt\n')
    saved=auto_history.load(model,plan)
    assert saved['usable'] and saved['refresh_required']
    assert all(e['solution_start_offset'] is None and not e['fresh_verified'] for e in saved['history'])


@pytest.mark.parametrize('bad',['corrupt','symlink','gap','transition'])
def test_malformed_or_mixed_history_falls_back_to_fresh_evidence(accepted,bad,tmp_path):
    model, _, plan, _ = accepted
    path=model/'.cmfgen-runs'/auto_history.NAME
    if bad=='corrupt':path.write_text('{')
    elif bad=='symlink':
        target=tmp_path/'receipt';path.rename(target);path.symlink_to(target)
    else:
        value=json.loads(path.read_text())
        if bad=='gap':value['history'][-1]['records'][0]['global_iteration']+=10
        else:value['history'][-1]['source_changed']=True
        path.write_text(json.dumps(value))
    assert not auto_history.load(model,plan)['usable']


def test_global_remedy_selected_before_first_new_full_solve(ng_workspace):
    model,make=ng_workspace
    initial=run_plan(make('ng_good',iterations=2,max_iterations=6,max_attempts=3))
    assert auto_history.load(model,make('ng_good'))['usable'],initial
    before=(model/'SCRTEMP').read_bytes();stopped=False
    def emit(event):
        nonlocal stopped
        if event['event']=='auto_action' and event['action']['kind']=='global_ng':stopped=True
    result=run_plan(make('ng_good',max_iterations=40,max_attempts=12),emit,stop_requested=lambda:stopped)
    assert result['startup_diagnosis']['decision']['policy_id']=='global_ng',result
    assert result['status']=='stopped' and not result['attempts']
    assert result['provisional_recovery_rolled_back']=='global_ng'
    assert (model/'SCRTEMP').read_bytes()==before
    saved=auto_history.load(model,make('ng_good'))
    assert saved['usable'] and saved['actions'][-1]['trial_outcome']=='aborted'


REFRESH = r'''
if get('IN_ITS','FINAL_OUTPUT_ONLY','F')=='T':
 assert get('VADAT','FLUX_CAL_ONLY','F')=='T'
 assert get('VADAT','DO_NG','T')=='F'
 it=int((p/'POINT1').read_text().splitlines()[1].split()[1])
 (p/'MODEL').write_text((p/'MODEL').read_text()+'\nDiagnostic metadata\n')
 (p/'OUTGEN').write_text(f'Model started on: now\nCurrent great iteration count is {it+1}\nLuminosity of star (d=1,ND)(iteration {it+1}) is: 1.12 1\n')
 (p/'OBSFLUX').write_text('Normalized luminosity check (normalized by L[ND])\n1.12 1.12 1.12 1.12 1\nDeparture from Rad Equilibrium Correction\n20 20 20 20 20\n')
 (p/'MEANOPAC').write_text('Depth Tau(Ross)\n'+''.join(f'a {d} {50*d} '+' '.join(['1']*12)+'\n' for d in range(1,6)))
 if (p/'refresh-wait').exists():time.sleep(5)
 if (p/'refresh-fault').exists():(p/'SCRTEMP').write_bytes(b'bad refresh')
 raise SystemExit(0)
'''


@pytest.fixture
def refresh_workspace(ng_workspace):
    model,make=ng_workspace
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    code=exe.read_text();needle="count=int(get('IN_ITS','NUM_ITS','3'))"
    assert needle in code;exe.write_text(code.replace(needle,REFRESH+'\n'+needle))
    result=run_plan(make('ng_good',iterations=2,max_iterations=6,max_attempts=3))
    assert auto_history.load(model,make('ng_good'))['usable'],result
    (model/'OBSFLUX').write_text('discarded radiation output')
    return model,make


def test_output_only_refresh_diagnoses_without_solving_or_applying_a_remedy(refresh_workspace):
    model,make=refresh_workspace;before=(model/'SCRTEMP').read_bytes();stopped=False
    def emit(event):
        nonlocal stopped
        if event['event']=='auto_startup_diagnosis':stopped=True
    result=run_plan(make('ng_good',max_attempts=12,max_iterations=40),emit,stop_requested=lambda:stopped)
    assert result['status']=='stopped',result
    refresh=result['restart_history']['refresh']
    assert refresh['status']=='succeeded' and refresh['solved_iterations']==0
    assert result['startup_diagnosis']['decision']['policy_id']=='global_ng'
    assert not result['attempts'] and not result['actions'] and result['iterations_used']==0
    assert (model/'SCRTEMP').read_bytes()==before
    assert 'FINAL_OUTPUT_ONLY' not in (model/'IN_ITS').read_text()
    assert 'FLUX_CAL_ONLY' not in (model/'VADAT').read_text()
    assert 'T [DO_NG]' in (model/'VADAT').read_text()
    saved=auto_history.load(model,make('ng_good'))
    assert saved['usable'] and not saved['refresh_required']


def test_refresh_that_changes_checkpoint_rolls_back_and_collects_fresh_evidence(refresh_workspace):
    model,make=refresh_workspace;(model/'refresh-fault').write_text('inject')
    stopped=False
    def emit(event):
        nonlocal stopped
        if event['event']=='auto_assessment':stopped=True
    result=run_plan(make('ng_good',max_attempts=12,max_iterations=40),emit,stop_requested=lambda:stopped)
    assert not result['restart_history']['usable'],result
    assert result['restart_history']['refresh']['status']!='succeeded'
    assert result['attempts'][0]['attempt']==2  # Refresh spends one attempt, no iteration credit.
    assert result['attempts'][0]['phase']=='iterate'
    assert result['attempts'][0]['evidence']['checkpoint']==49
    assert result['iterations_used']==3
    assert 'startup_diagnosis' not in result


def test_fresh_initialization_does_not_reuse_history(accepted):
    model, _, plan, _ = accepted
    assert not auto_history.load(model,{**plan,'fresh_start':True})['usable']


def test_changed_executable_refuses_history(accepted):
    model, _, plan, _ = accepted
    exe=Path(plan['executable']);exe.write_text(exe.read_text()+'\n# new executable\n')
    assert not auto_history.load(model,plan)['usable']


def test_nonfinite_json_and_changed_atomic_link_are_not_trusted(accepted,tmp_path):
    model, _, plan, _ = accepted
    name=plan['links'][0]['name'];link=model/name
    replacement=tmp_path/'replacement';replacement.write_bytes(Path(plan['links'][0]['target']).read_bytes())
    link.unlink();link.symlink_to(replacement)
    assert not auto_history.load(model,plan)['usable']
    link.unlink();link.symlink_to(plan['links'][0]['target'])
    path=model/'.cmfgen-runs'/auto_history.NAME
    value=json.loads(path.read_text());value['history'][-1]['records'][0]['solver_maximum_change']=float('nan')
    path.write_text(json.dumps(value))
    assert not auto_history.load(model,plan)['usable']


def test_legacy_journal_requires_matching_recovery_and_input_dependencies(auto_workspace):
    model,make=auto_workspace
    first=run_plan(make('raw_high',max_attempts=2))
    (model/'.cmfgen-runs'/auto_history.NAME).unlink()
    plan=make('raw_high')
    restored=auto_history.load(model,plan)
    assert restored['usable'] and restored['legacy'] and restored['refresh_required'],restored
    assert restored['history'][-1]['checkpoint']==first['attempts'][-1]['evidence']['checkpoint']
    Path(plan['links'][0]['target']).write_text('changed atomic data')
    assert not auto_history.load(model,plan)['usable']


def test_previous_controller_preview_requires_new_review(auto_workspace):
    from cmfgen_viewer.runner_recipe import RunnerError
    model,make=auto_workspace;plan=make();plan['auto']['version']=12
    with pytest.raises(RunnerError,match='prepare a new plan'):run_plan(plan)
    assert not (model/'POINT1').exists()


def test_interrupted_legacy_tail_cannot_erase_or_promote_the_accepted_checkpoint(auto_workspace):
    model,make=auto_workspace
    result=run_plan(make('raw_high',max_attempts=2))
    (model/'.cmfgen-runs'/auto_history.NAME).unlink()
    path=Path(result['journal'])/'result.json';value=json.loads(path.read_text())
    value['status']='running'
    value['attempts'].append({'phase':'iterate','status':'running','checkpoint_restored':True})
    path.write_text(json.dumps(value))
    saved=auto_history.load(model,make('raw_high'))
    assert saved['usable'] and saved['legacy'],saved
    assert saved['history'][-1]['checkpoint']==result['attempts'][-1]['evidence']['checkpoint']


def test_restart_log_explains_reuse_refresh_and_startup_decision():
    import io
    from cmfgen_viewer.runner_output import TerminalOutput
    stream=io.StringIO();output=TerminalOutput(stream)
    output.event({'event':'auto_restart_history','usable':True,'checkpoint':246,'refresh_required':True})
    output.event({'event':'auto_startup_diagnosis','decision':{'policy_id':'global_ng','reason':'slow thermal mode'}})
    assert 'Reusing accepted history at checkpoint 246' in stream.getvalue()
    assert 'refresh radiation diagnostics first' in stream.getvalue()
    assert 'Restart diagnosis: global_ng' in stream.getvalue()


def test_cancel_during_refresh_never_starts_an_ordinary_batch(refresh_workspace):
    model,make=refresh_workspace;before=(model/'SCRTEMP').read_bytes()
    def emit(event):
        if event['event']=='restart_history_refresh':raise KeyboardInterrupt()
    result=run_plan(make('ng_good',max_attempts=12,max_iterations=40),emit)
    assert result['status']=='cancelled',result
    assert not result['attempts'] and not result['actions'] and result['iterations_used']==0
    assert (model/'SCRTEMP').read_bytes()==before
    assert 'FLUX_CAL_ONLY' not in (model/'VADAT').read_text()


def test_timeout_during_refresh_never_starts_an_ordinary_batch(refresh_workspace):
    model,make=refresh_workspace;before=(model/'SCRTEMP').read_bytes()
    (model/'refresh-wait').write_text('inject delay')
    result=run_plan(make('ng_good',max_attempts=12,max_iterations=40,timeout=.2))
    assert result['status']=='timeout',result
    assert not result['attempts'] and not result['actions'] and result['iterations_used']==0
    assert (model/'SCRTEMP').read_bytes()==before
    assert 'FLUX_CAL_ONLY' not in (model/'VADAT').read_text()
