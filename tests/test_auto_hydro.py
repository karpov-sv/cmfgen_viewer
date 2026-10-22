"""Bstar3500 guard-before-scheduled-hydro recovery, without real model runs."""
import json
from pathlib import Path
import sys

import pytest

from test_runner_auto import auto_workspace, FAKE
from cmfgen_viewer.auto_diagnostics import control_value
from cmfgen_viewer.auto_hydro import native_updates
from cmfgen_viewer.runner import main, run_plan
from cmfgen_viewer.runner_recipe import RunnerError

RVSIG = '2 !Number of depth points\n2 20 0 0.1 1\n1 10 0 100 2\n'

BEFORE_SOLVE = r'''
import json
stop=get('VADAT','STOP_IF_MW','T')
done=int(get('HYDRO_DEFAULTS','ITS_DONE','0'))
with (p/'guard-trace.jsonl').open('a') as trace:
 trace.write(json.dumps({'guard':stop,'count':count,'start':start})+'\n')
low=0.4 if done==0 or mode=='hydro_rebound' else 0.97
if mode=='hydro_unphysical' and done:low=0.3
(p/'OBSFLUX').write_text('Normalized luminosity check (normalized by L[ND])\n\n'+str(low)+' 1.0\n\n')
tau=10 if mode=='hydro_shallow' else 100
(p/'MEANOPAC').write_text('R I Tau(Ross)\n2 1 0.1 '+'0 '*12+'\n1 2 '+str(tau)+' '+'0 '*12+'\n')
if mode=='hydro_missing_tau':(p/'MEANOPAC').unlink(missing_ok=True)
if mode=='hydro_partial_obs':(p/'OBSFLUX').write_text('Normalized luminosity check (normalized by L[ND])\n\n0.4\n\n')
if mode=='hydro_stale_obs':
 (p/'OBSFLUX').write_text((p/'old-obs').read_text())
 import os
 old=json.loads((p/'old-obs-stat').read_text())
 os.utime(p/'OBSFLUX',ns=(old['atime'],old['mtime']))
if (done==0 or mode=='hydro_rebound') and stop=='T':
 (p/'OUTGEN').write_text('Model started on: now\nCurrent great iteration count is '+str(start)+'\n')
 print('Some normalized luminosities are out by a factor of 2',flush=True)
 if mode=='hydro_combined':print('This model does not extend sufficiently deeply to guarantee the accuracy of',flush=True)
 raise SystemExit(0)
if stop=='F' and mode=='hydro_cancel':time.sleep(10)
if stop=='F' and mode=='hydro_crash':
 print('Fortran runtime error: bridge failed',flush=True)
 raise SystemExit(1)
'''

AFTER_SOLVE = r'''
if stop=='F' and mode!='hydro_no_revision':
 def patch(file,key,value):
  text=(p/file).read_text()
  pattern=r'^\s*\S+\s+\['+key+r'\].*$'
  text=re.sub(pattern,value+' ['+key+']',text,flags=re.M) if re.search(pattern,text,re.M) else text+value+' ['+key+']\n'
  (p/file).write_text(text)
 patch('VADAT','RSTAR','1.1')
 patch('VADAT','RMAX','2')
 patch('VADAT','MASS','10')
 patch('HYDRO_DEFAULTS','N_ITS','0')
 patch('HYDRO_DEFAULTS','ITS_DONE','1')
 (p/'RVSIG_COL').write_text('2 !Number of depth points\n2.2 20 0 0.1 1\n1.1 10 0 100 2\n')
 with (p/'OUTGEN').open('a') as stream:
  stream.write(' Revised hydrostatic structure and output new RVSIG_COL file\n')
 pointer=(p/'POINT1').read_text().splitlines()
 words=pointer[1].split();words[1]=str(int(words[1])+1)
 pointer[1]=' '.join(words)
 for name in ['POINT1','POINT2']:(p/name).write_text('\n'.join(pointer)+'\n')
if mode=='hydro_wrong_counter' and stop=='F':
 for name in ['POINT1','POINT2']:
  text=(p/name).read_text().replace('1 3 1 -1000 T','1 4 1 -1000 T')
  (p/name).write_text(text)
'''


@pytest.fixture
def hydro_workspace(auto_workspace):
    model,make=auto_workspace
    # A pre-existing, reviewed iteration-1 restart, as in the report.
    (model/'VADAT').write_text((model/'VADAT').read_text()+'T [DO_HYDRO]\nT [STOP_IF_MW]\n')
    (model/'HYDRO_DEFAULTS').write_text('1 [N_ITS]\n0 [ITS_DONE]\n2 [STRT_ITS]\n10 [FREQ_ITS]\n')
    (model/'ROSSELAND_LTE_TAB').write_text('1 !Number of temperatures\n1 !Number of densities\n1 2 3 4 5 6 7 8\n')
    (model/'RVSIG_COL').write_text(RVSIG)
    for name in ('POINT1','POINT2'):
        (model/name).write_text('28-Feb-2004 !Format date\n1 1 1 -1000 T\n')
    (model/'SCRTEMP').write_bytes(b'checkpoint'+bytes(100))
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    code=FAKE.replace("fresh=get('VADAT'",BEFORE_SOLVE+"\nfresh=get('VADAT'")+AFTER_SOLVE
    exe.write_text(f'#!{sys.executable}\n'+code)
    original={n:(model/n).read_bytes() for n in ('VADAT','HYDRO_DEFAULTS','RVSIG_COL','POINT1','POINT2','SCRTEMP')}
    return model,make,original


def test_opt_in_bridges_one_iteration_then_runs_with_guard_restored(hydro_workspace):
    model,plan,_original=hydro_workspace
    result=run_plan(plan('hydro'))
    assert result['status']=='succeeded',result
    assert [a['kind'] for a in result['actions']]==['hydro_bootstrap','fresh_jacobian']
    assert [a['phase'] for a in result['attempts']]==['iterate','hydro_bridge','hydro_guarded','verify']
    bridge=result['attempts'][1]
    assert bridge['requested_iterations']==1
    assert bridge['evidence']['iterations']==1
    assert bridge['evidence']['checkpoint']==3
    assert bridge['evidence']['hydro_revisions']==[2]
    assert result['attempts'][2]['hydro_recovery_verified']
    assert control_value(model,'VADAT','STOP_IF_MW')=='T'
    assert control_value(model,'VADAT','RSTAR')=='1.1'
    assert control_value(model,'HYDRO_DEFAULTS','ITS_DONE')=='1'
    trace=[json.loads(line) for line in (model/'guard-trace.jsonl').read_text().splitlines()]
    assert [r['guard'] for r in trace]==['T','F','T','T']
    assert trace[2]['start']==4
    assert (Path(bridge['journal'])/'effective/VADAT').read_text().count('[STOP_IF_MW]')==1
    assert 'F [STOP_IF_MW]' in (Path(bridge['journal'])/'effective/VADAT').read_text()
    recovery=Path(result['recovery_directory'])
    for name in ('VADAT','RVSIG_COL','HYDRO_DEFAULTS'):
        assert (recovery/name).read_bytes()==(model/name).read_bytes()


def test_default_auto_selects_hydro_remedy_without_extra_flags(hydro_workspace):
    model,plan,original=hydro_workspace
    result=run_plan(plan('hydro'))
    assert result['status']=='succeeded',result
    assert result['actions'][0]['policy_id']=='hydro_bootstrap'
    assert control_value(model,'VADAT','STOP_IF_MW')=='T'



@pytest.mark.parametrize('scenario',['hydro_shallow','hydro_missing_tau','hydro_partial_obs','hydro_combined'])
def test_bridge_requires_complete_evidence_and_adequate_optical_depth(hydro_workspace,scenario):
    model,plan,original=hydro_workspace
    result=run_plan(plan(scenario))
    assert result['status']=='needs_review',result
    assert len(result['attempts'])==1
    assert any(t['outcome']=='ineligible' for t in result['attempts'][0]['policy_evaluations'])
    assert not result['actions']
    for name,data in original.items():assert (model/name).read_bytes()==data


@pytest.mark.parametrize('scenario',['hydro_crash','hydro_no_revision','hydro_wrong_counter','hydro_rebound','hydro_unphysical'])
def test_failed_bridge_or_guarded_followup_restores_coupled_state(hydro_workspace,scenario):
    model,plan,original=hydro_workspace
    result=run_plan(plan(scenario))
    assert result['status']=='needs_review',result
    assert [a['kind'] for a in result['actions']]==['hydro_bootstrap']
    assert control_value(model,'VADAT','STOP_IF_MW')=='T'
    for name,data in original.items():assert (model/name).read_bytes()==data
    assert len(result['attempts']) <= 3


def test_uncompleted_guarded_check_is_rolled_back(hydro_workspace):
    model,plan,original=hydro_workspace
    def stop(item):
        if item['event']=='auto_assessment' and item['attempt']==2:raise KeyboardInterrupt()
    result=run_plan(plan('hydro'),stop)
    assert result['status']=='cancelled',result
    assert control_value(model,'VADAT','STOP_IF_MW')=='T'
    for name,data in original.items():assert (model/name).read_bytes()==data


def test_cannot_spend_budget_on_bridge_without_guarded_check(hydro_workspace):
    model,plan,original=hydro_workspace
    result=run_plan(plan('hydro',max_iterations=5))
    assert result['status']=='limit_reached'
    assert len(result['attempts'])==1
    assert not result['actions']
    for name,data in original.items():assert (model/name).read_bytes()==data


def test_unknown_hydro_schedule_is_not_guessed(hydro_workspace):
    model,plan,_original=hydro_workspace
    (model/'HYDRO_DEFAULTS').write_text('1 [N_ITS]\n0 [ITS_DONE]\n')
    result=run_plan(plan('hydro'))
    assert result['status']=='needs_review'
    assert 'explicitly scheduled' in result['reason']
    assert not result['actions']


def test_hydro_option_requires_auto(tmp_path,capsys):
    assert main([str(tmp_path),'--auto-hydro-recovery','--json'])==2
    assert 'requires --auto' in json.loads(capsys.readouterr().out)['error']


def test_stale_guard_evidence_cannot_authorize_a_bridge(hydro_workspace):
    model,plan,_original=hydro_workspace
    text='Normalized luminosity check (normalized by L[ND])\n\n0.4 1.0\n\n'
    (model/'OBSFLUX').write_text(text)
    info=(model/'OBSFLUX').stat()
    (model/'old-obs').write_text(text)
    (model/'old-obs-stat').write_text(json.dumps({'atime':info.st_atime_ns,'mtime':info.st_mtime_ns}))
    result=run_plan(plan('hydro_stale_obs'))
    assert result['status']=='needs_review',result
    assert not result['actions']
    assert 'fresh OBSFLUX' in result['reason']


def test_timeout_restores_guard_and_original_state(hydro_workspace):
    model,plan,original=hydro_workspace
    result=run_plan(plan('hydro_cancel',timeout=2))
    assert result['status']=='timeout',result
    assert control_value(model,'VADAT','STOP_IF_MW')=='T'
    for name,data in original.items():assert (model/name).read_bytes()==data


def test_ordinary_hydro_continuation_also_accepts_native_updates(hydro_workspace):
    model,plan,_original=hydro_workspace
    # Exercise the native handoff without bypassing the guard: change the fake
    # executable's probe trigger, while leaving the actual model guard enabled.
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    code=exe.read_text().replace("(done==0 or mode=='hydro_rebound') and stop=='T'",'False')
    code=code.replace("if stop=='F' and mode!='hydro_no_revision':", "if done==0:")
    # Put the revision after solver iteration 2, so the next radiation pass
    # uses counter 4. Counter 3 describes only the hydro/grey adjustment.
    code=code.replace("  out+=f'Current great iteration count is {it}\\n'",
                      "  if done==0 and n==1:out+=' Revised hydrostatic structure and output new RVSIG_COL file\\n'\n"
                      "  if done==0 and n>=1:it+=1\n"
                      "  out+=f'Current great iteration count is {it}\\n'")
    code=code.replace("stream.write(' Revised hydrostatic structure and output new RVSIG_COL file\\n')", "stream.write('')")
    exe.write_text(code)
    result=run_plan(plan('hydro_ordinary',iterations=2))
    assert result['status']=='succeeded',result
    assert not any(a['kind']=='hydro_bootstrap' for a in result['actions'])
    assert result['attempts'][0]['evidence']['checkpoint']==4
    assert [r['global_iteration'] for r in result['attempts'][0]['evidence']['records']]==[2,4]
    assert result['attempts'][0]['native_control_updates']


def test_fixed_t_requires_explicit_native_auto_release(auto_workspace):
    model,plan=auto_workspace
    (model/'VADAT').write_text((model/'VADAT').read_text().replace('F [FIX_T]','T [FIX_T]'))
    with pytest.raises(RunnerError,match='DO_T_AUTO'):
        plan()
    (model/'VADAT').write_text((model/'VADAT').read_text()+'T [DO_T_AUTO]\n')
    prepared=plan()
    before={n:(model/n).read_text() if (model/n).exists() else None for n in ('VADAT','RVSIG_COL','HYDRO_DEFAULTS')}
    (model/'VADAT').write_text((model/'VADAT').read_text().replace('T [FIX_T]','F [FIX_T]'))
    evidence='Current great iteration count is 1\nMaximm changes as returned by SOLVEBA_V13 is 1\n'
    assert 'VADAT' in native_updates(model,evidence,before)
    assert prepared['kind']=='auto'
