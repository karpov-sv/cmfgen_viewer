"""Real child-process coverage of automatic decisions, rollback and acceptance."""
import json
from pathlib import Path
import sys
import threading

import pytest

from cmfgen_viewer.runner import main, run_plan
from cmfgen_viewer.runner_auto import configure_auto
from cmfgen_viewer.runner_recipe import RunnerError, build_run_plan
from cmfgen_viewer.auto_diagnostics import oscillating_region, recovery_action, raw_temperature_steps
from cmfgen_viewer.model_activity import model_run_reservation, model_mutation_guard

# The fake executable produces actual text outputs/checkpoint markers; tests do
# not mock run_plan, its output validation, control restoration or subprocesses.
FAKE = r'''
from pathlib import Path
import re,time
p=Path('.')
def get(file,key,default):
 text=(p/file).read_text() if (p/file).exists() else ''
 m=re.search(r'^\s*(\S+)\s+\['+re.escape(key)+r'\]',text,re.M)
 return m[1] if m else default
attempt=int((p/'attempts.txt').read_text())+1 if (p/'attempts.txt').exists() else 1
(p/'attempts.txt').write_text(str(attempt))
mode=(p/'scenario').read_text()
if mode=='cancel':time.sleep(10)
if (mode=='cache' and attempt==1) or mode=='repeat_cache':
 (p/'POINT1').write_text('broken pointer')
 (p/'SCRTEMP').write_bytes(b'broken')
 print('Error - incorrect reading of EDDFACTOR in COMP_J_BLANK',flush=True)
 raise SystemExit(1)
if mode=='unknown':
 (p/'SCRTEMP').write_bytes(b'broken')
 print('Fortran runtime error: unknown issue',flush=True)
 raise SystemExit(1)
count=int(get('IN_ITS','NUM_ITS','2'))
start=int((p/'POINT1').read_text().splitlines()[1].split()[1])+1 if (p/'POINT1').exists() else 1
fresh=get('VADAT','N_FIX_BA','2')=='0' and get('VADAT','FIX_BA','10') in ['0','0.0'] and get('VADAT','COMP_BA','T')=='T'
relaxed=float(get('ADJUST_CORRECTIONS','RELAX','1'))<1
large=mode=='never' or (mode=='oscillate' and not relaxed)
value=10 if large else 0.005
if mode=='raw_high':value=0.5
if mode=='rebound' and attempt==2:value=1
if mode=='stall':value=1
if mode=='decay':value=0.2/attempt**2
out='Model started on: now\n'
with (p/'STEQ_VALS').open('a') as sol:
 for n,it in enumerate(range(start,start+count)):
  out+=f'Current great iteration count is {it}\n'
  out+='BA matrix computed\n' if fresh else 'BA matrix **NOT** computed\n'
  if mode=='lambda':out+='LAMBDA iteration used\nTemperature held fixed at all depths.\n'
  out+=f'Maximum % increase at depth 1 is {value} (BA computed) --- iteration {it}\n'
  out+=f'Maximum % decrease at depth 1 is {value} (BA computed) --- iteration {it}\n'
  out+=f'Maximm changes as returned by SOLVEBA_V13 is {0.001 if mode=="raw_high" else value}\n'
  sol.write(' STEQ SOLUTION ARRAY\n')
  t=0.1*(-1 if n%2 else 1) if large else 0.00001
  sol.write(f' 3( 1)# {t} 0.000001\n')
(p/'OUTGEN').write_text(out)
(p/'MOD_SUM').write_text(f'Model Finalized on: {time.time_ns()}\n')
(p/'MODEL').write_text('2 !Number of depth points\n3 !Total number of variables\n'+str(time.time_ns()))
(p/'RVTJ').write_text('ND: 2\nRadius\n2 1\nVelocity\n20 10\nTemperature\n1 2\nElectron density\n1e10 2e10\n')
if mode!='stale':(p/'CORRECTION_SUM').write_text('NT=3\nDepth 100.0% 10.0% 1.0% 0.1% 0.01% 0.001% 0.0001%\n1 0 0 0 0 0 1 3\n2 0 0 0 0 0 1 3\n')
if mode=='bad_counts':(p/'CORRECTION_SUM').write_text('NT=3\nDepth 100.0% 10.0% 1.0% 0.1% 0.01% 0.001% 0.0001%\n1 1 1 1 1 1 1 3\n2 0 0 0 0 0 1 3\n')
(p/'POINT1').write_text('28-Feb-2004 !Format date\n1 '+str(start+count-1)+' 1 -1000 T\n')
(p/'POINT2').write_bytes((p/'POINT1').read_bytes())
(p/'SCRTEMP').write_bytes(bytes(100)+str(start+count-1).encode())
'''


@pytest.fixture
def auto_workspace(tmp_path):
    model=tmp_path/'model';model.mkdir()
    for name,text in {'VADAT':'1 [RSTAR]\n0.02 [EPS_TERM]\nF [FIX_T]\nMAJOR [SCALE_OPT]\n2 [N_FIX_BA]\n10 [FIX_BA]\nT [COMP_BA]\n',
        'MODEL_SPEC':'2 [ND]\n1 [NC]\n3 [NP]\n','IN_ITS':'5 [NUM_ITS]\n',
        'He2_IN':'helium','GAMMAS_IN':'gamma','batch.sh':'# no base links\n',
        'batch_ins.sh':'ln -sf $ATOMIC/test.dat HYD_L_DATA\n','scenario':'good'}.items():
        (model/name).write_text(text)
    atomic=tmp_path/'atomic';atomic.mkdir();(atomic/'test.dat').write_text('data')
    root=tmp_path/'cmf';(root/'exe').mkdir(parents=True)
    exe=root/'exe/cmfgen_dev.exe';exe.write_text(f'#!{sys.executable}\n'+FAKE);exe.chmod(0o755)
    def plan(scenario='good', **kwargs):
        (model/'scenario').write_text(scenario)
        native=build_run_plan(model,stage='main',cmfgen_root=root,atomic_root=atomic,
                              iterations=kwargs.pop('iterations',3), fresh_start=kwargs.pop('fresh_start',False),
                              lte_initialization=kwargs.pop('lte_initialization',False), t_exc=kwargs.pop('t_exc',1.0),
                              timeout=kwargs.pop('timeout',None))
        assert native['ready'],native['errors']
        return configure_auto(native,cmfgen_root=root,atomic_root=atomic,**kwargs)
    return model,plan


def test_auto_verifies_fresh_matrices_and_keeps_quality_separate(auto_workspace):
    model,plan=auto_workspace
    result=run_plan(plan())
    assert result['status']=='succeeded',result
    assert len(result['attempts'])==2
    assert result['numerical_convergence']=='verified with fresh Jacobians'
    assert result['scientific_acceptance']=='requires separate quality review'
    assert [a['kind'] for a in result['actions']]==['fresh_jacobian']
    assert result['attempts'][-1]['evidence']['fresh_verified']
    assert (model/'IN_ITS').read_text()=='5 [NUM_ITS]\n'
    assert (Path(result['journal'])/'result.json').is_file()
    assert (Path(result['recovery_directory'])/'SCRTEMP').is_file()


def test_cycle_selects_local_relaxation_then_independent_verification(auto_workspace):
    model,plan=auto_workspace
    result=run_plan(plan('oscillate'))
    assert result['status']=='succeeded',result
    assert [a['kind'] for a in result['actions']]==['relaxation','fresh_jacobian']
    assert '0.25' in (model/'ADJUST_CORRECTIONS').read_text()
    assert result['attempts'][0]['evidence']['candidate'] is False


def test_failed_cache_attempt_restores_checkpoint_before_one_retry(auto_workspace):
    model,plan=auto_workspace
    # First create a valid state and then capture its exact checkpoint for retry.
    run_plan(plan())
    (model/'attempts.txt').unlink()
    before=(model/'SCRTEMP').read_bytes()
    (model/'EDDFACTOR').write_bytes(b'bad cache');(model/'EDDFACTOR_INFO').write_text('info')
    result=run_plan(plan('cache'))
    assert result['status']=='succeeded',result
    assert result['attempts'][0]['checkpoint_restored']
    assert result['actions'][0]['kind']=='radiation_cache'
    assert not (model/'EDDFACTOR').exists()
    assert before!=b'broken'


def test_unknown_failure_stops_without_speculative_changes(auto_workspace):
    model,plan=auto_workspace
    run_plan(plan())
    before=(model/'SCRTEMP').read_bytes()
    result=run_plan(plan('unknown'))
    assert result['status']=='needs_review'
    assert (model/'SCRTEMP').read_bytes()==before
    assert not result['actions']


@pytest.mark.parametrize('scenario',['raw_high','stale','lambda','bad_counts'])
def test_no_false_convergence_from_trimmed_metrics_stale_or_fixed_t(auto_workspace,scenario):
    _model,plan=auto_workspace
    result=run_plan(plan(scenario,max_attempts=3))
    assert result['status']!='succeeded'
    assert 'numerical_convergence' not in result


def test_verification_rebound_is_not_accepted(auto_workspace):
    _model,plan=auto_workspace
    result=run_plan(plan('rebound',max_attempts=2))
    assert result['status']=='limit_reached'
    assert not result['attempts'][1]['evidence']['candidate']


def test_shared_timeout_stops_without_retry(auto_workspace):
    _model,plan=auto_workspace
    result=run_plan(plan('cancel',timeout=0.2))
    assert result['status']=='timeout'
    assert len(result['attempts'])==1


def test_total_iteration_budget_reserves_verification(auto_workspace):
    _model,plan=auto_workspace
    result=run_plan(plan(max_iterations=3))
    assert result['status']=='limit_reached'
    assert len(result['attempts'])==1
    assert result['iterations_used']==3


def test_external_edits_are_preserved_and_not_retried(auto_workspace):
    model,plan=auto_workspace
    def edit(item):
        if item['event']=='stage_finished':
            (model/'VADAT').write_text((model/'VADAT').read_text()+'42 [USER_EDIT]\n')
    result=run_plan(plan(),edit)
    assert result['status']=='needs_review'
    assert 'USER_EDIT' in (model/'VADAT').read_text()
    assert len(result['attempts'])==1


def test_cancel_between_attempts_is_journaled(auto_workspace):
    _model,plan=auto_workspace
    def cancel(item):
        if item['event']=='auto_assessment':raise KeyboardInterrupt()
    result=run_plan(plan(),cancel)
    assert result['status']=='cancelled'
    assert len(result['attempts'])==1


def test_changed_adjustment_invalidates_preview(auto_workspace):
    model,plan=auto_workspace
    prepared=plan()
    (model/'ADJUST_CORRECTIONS').write_text('0.5 [RELAX]\n')
    with pytest.raises(RunnerError,match='changed'):
        run_plan(prepared)


def test_reservation_blocks_other_context_between_attempts(auto_workspace):
    model,_plan=auto_workspace
    errors=[]
    def writer():
        try:
            with model_mutation_guard(model):pass
        except ValueError as exc:errors.append(str(exc))
    with model_run_reservation(model):
        thread=threading.Thread(target=writer);thread.start();thread.join()
        with model_mutation_guard(model):pass
    assert errors and 'runner' in errors[0]


def test_cli_plan_is_read_only_and_describes_auto(auto_workspace,capsys):
    model,_plan=auto_workspace
    root=model.parent/'cmf';atomic=model.parent/'atomic'
    args=[str(model),'--stage','main','--auto','--plan','--json','--cmfgen-root',str(root),'--atomic-root',str(atomic)]
    assert main(args)==0
    report=json.loads(capsys.readouterr().out)
    assert report['kind']=='auto' and report['auto']['max_iterations']==500
    assert not (model/'.cmfgen-runs').exists()
    assert not (model/'attempts.txt').exists()


@pytest.mark.parametrize('args',[['--auto'],['--stage','test','--auto'],['--stage','flux','--stage','main','--auto'],['--auto-max-attempts','2']])
def test_cli_rejects_inapplicable_auto_arguments(tmp_path,args,capsys):
    assert main([str(tmp_path),*args,'--json'])==2
    assert json.loads(capsys.readouterr().out)['status']=='preflight_failed'


def test_decay_is_not_mistaken_for_persistent_cycle():
    base={'counts':{'nd':9},'epsilon_percent':0.02,'temperatures':[]}
    assert oscillating_region({**base,'raw_temperature_steps':[[10]*9,[-4]*9,[1]*9]},[]) is None
    assert recovery_action({'passes':[{'diagnostic_tail':'segmentation fault'}]}) is None


def test_failed_attempts_consume_total_budget(auto_workspace):
    _model,plan=auto_workspace
    result=run_plan(plan('cache',max_iterations=3))
    assert result['status']=='limit_reached'
    assert len(result['attempts'])==1
    assert result['iterations_used']==3


def test_repeated_cache_error_is_not_retried_indefinitely(auto_workspace):
    _model,plan=auto_workspace
    result=run_plan(plan('repeat_cache'))
    assert result['status']=='needs_review'
    assert len(result['attempts'])==2
    assert len(result['actions'])==1


def test_explicit_fresh_start_remains_fresh_after_failed_initialization(auto_workspace):
    model,plan=auto_workspace
    run_plan(plan())
    (model/'attempts.txt').unlink()
    result=run_plan(plan('cache',fresh_start=True))
    assert result['status']=='succeeded',result
    assert result['attempts'][1]['evidence']['checkpoint']==3
    assert result['final_checkpoint']==6


def test_does_not_change_scope_of_other_adjustment_controls(auto_workspace):
    model,plan=auto_workspace
    original='2 [MAX_CHNG]\n! Keep this control and comment\n'
    (model/'ADJUST_CORRECTIONS').write_text(original)
    result=run_plan(plan('oscillate'))
    assert result['status']=='needs_review'
    assert (model/'ADJUST_CORRECTIONS').read_text()==original
    assert not result['actions']


def test_single_iteration_batches_cannot_supply_verification_evidence(auto_workspace):
    _model,plan=auto_workspace
    with pytest.raises(RunnerError,match='at least 2 iterations'):
        plan(iterations=1)


def test_temperature_stream_preserves_section_at_append_boundary(tmp_path):
    path=tmp_path/'STEQ_VALS'
    path.write_text('old data\n')
    offset=path.stat().st_size
    with path.open('a') as stream:
        stream.write(' STEQ SOLUTION ARRAY\n 3( 1)# 0.01 -0.02\n')
    assert raw_temperature_steps(path,offset,3,2)==[[-1,2]]


def test_terminal_reports_scientific_warning_after_numerical_success(auto_workspace):
    import io
    from cmfgen_viewer.runner_output import TerminalOutput
    _model,plan=auto_workspace
    result=run_plan(plan())
    result['quality']['checks'].append({'label':'Boundary transfer','level':'warning','detail':'Large error'})
    stream=io.StringIO()
    TerminalOutput(stream,color='never').result(result)
    assert 'Boundary transfer: Large error' in stream.getvalue()
    assert 'verified with fresh Jacobians' in stream.getvalue()


def test_status_recognizes_executed_automatic_parent_journal(auto_workspace):
    from cmfgen_viewer.runner_status import inspect_model_status
    model,plan=auto_workspace
    result=run_plan(plan())
    latest=inspect_model_status(model)['state']['latest_run']
    assert latest['executed']
    assert latest['journal']==result['journal']
    assert latest['status']=='succeeded'


def test_stall_gets_one_matrix_refresh_then_stops_for_review(auto_workspace):
    model,plan=auto_workspace
    result=run_plan(plan('stall'))
    assert result['status']=='needs_review',result
    assert len(result['attempts'])==6
    assert [a['kind'] for a in result['actions']]==['fresh_jacobian']
    assert 'despite fresh matrices' in result['reason']
    assert '[FIX_BA]' in (model/'VADAT').read_text()


def test_decreasing_corrections_continue_without_unnecessary_damping(auto_workspace):
    _model,plan=auto_workspace
    result=run_plan(plan('decay'))
    assert result['status']=='succeeded',result
    assert len(result['attempts'])==5
    assert [a['kind'] for a in result['actions']]==['fresh_jacobian']


@pytest.mark.parametrize('scenario,budget,expected', [('good',None,0),('rebound',2,1)])
def test_cli_executes_auto_and_returns_verification_exit_status(auto_workspace,capsys,scenario,budget,expected):
    model,_plan=auto_workspace
    (model/'scenario').write_text(scenario)
    args=[str(model),'--stage','main','--auto','--iterations','3','--json',
          '--cmfgen-root',str(model.parent/'cmf'),'--atomic-root',str(model.parent/'atomic')]
    if budget:args.extend(['--auto-max-attempts',str(budget)])
    assert main(args)==expected
    report=json.loads(capsys.readouterr().out)
    assert report['kind']=='auto'
    assert (report['status']=='succeeded')==(expected==0)


def test_interrupted_recovery_copy_preserves_committed_snapshot(tmp_path,monkeypatch):
    from cmfgen_viewer import runner_auto
    model=tmp_path/'model';model.mkdir()
    journal=tmp_path/'journal';journal.mkdir()
    (model/'SCRTEMP').write_bytes(b'known state')
    original=runner_auto._capture(model,journal)
    metadata=(journal/'recovery.json').read_bytes()
    def fail(*args):raise OSError('simulated interrupted copy')
    monkeypatch.setattr(runner_auto,'copy_readable',fail)
    with pytest.raises(OSError,match='interrupted copy'):
        runner_auto._capture(model,journal,original)
    assert (journal/'recovery.json').read_bytes()==metadata
    assert (original/'SCRTEMP').read_bytes()==b'known state'
    assert list(journal.glob('recovery-*'))==[original]
