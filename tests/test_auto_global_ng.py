"""Eligibility, six-solve acceptance and controller rollback of positive global Ng."""
from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys

import pytest

from test_global_ng import global_model as ng_model
from test_population_projection import projection_model
from test_runner_auto import auto_workspace
from cmfgen_viewer import auto_ng
from cmfgen_viewer.auto_policies import Context, TrialRejected
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner_auto import RECOVERY_NAMES


def recovery_bytes(action):
    journal = Path(action['directory']).parent
    recovery = journal/json.loads((journal/'recovery.json').read_text())['directory']
    return {n: (recovery/n).read_bytes() if (recovery/n).exists() else None
            for n in RECOVERY_NAMES}


def assert_restored(model, saved):
    assert {n: (model/n).read_bytes() if (model/n).exists() else None
            for n in RECOVERY_NAMES} == saved


def evidence(counter=40, values=(3.2,3.19), nd=5):
    return dict(checkpoint=counter, records=[dict(global_iteration=i, solver_maximum_change=v,
                maximum_increase_percent=1., maximum_decrease_percent=v, ba_computed=True,
                major_species_minimum_scale=1,luminosity_generated=1.12-.0001*(i-40),luminosity_target=1.) for i,v in zip(range(counter-1,counter+1),values)],
                full_iterations=2, iterations=2, epsilon_percent=.02, candidate=False,
                counts=dict(nd=nd,nt=6,totals={'10.0%':0,'1.0%':5,'0.1%':10,'0.01%':15}),
                raw_temperature_steps=[[.001]*nd]*2)


@pytest.fixture
def ng_context(ng_model, monkeypatch):
    with (ng_model/'VADAT').open('a') as stream:
        stream.write('T [COMP_BA]\n0 [N_FIX_BA]\n0 [FIX_BA]\nMAJOR [SCALE_OPT]\nF [DO_HYDRO]\n')
    (ng_model/'OBSFLUX').write_text('Departure from Rad Equilibrium Correction\n20 20 20 20 20\n')
    monkeypatch.setattr('cmfgen_viewer.auto_recovery.repaired_runtime',lambda *a,**kw:True)
    monkeypatch.setattr(auto_ng,'guard_measurements',lambda *a:dict(
        luminosity_min=1.,luminosity_max=1.12,inner_tau_ross=100.))
    history = [evidence(36,(3.24,3.23)),evidence(38,(3.22,3.21)),evidence()]
    return Context(ng_model,'success',{}, {},{},history[-1],history,'iterate',[],'',
                   remaining_iterations=20,remaining_attempts=10)


def test_policy_selects_one_six_solve_trial(ng_context):
    decision = auto_ng.global_ng_trial(ng_context)
    assert decision and decision.reversible_trial
    assert [s.iterations for s in decision.steps] == [2,2,2]
    assert decision.evidence['proposal']['alpha'] <= 1
    assert auto_ng.global_ng_trial(replace(ng_context,actions=[{'policy_id':'global_ng','evidence':{'checkpoint':40},'trial_outcome':'accepted'}])) is None
    auto_ng.mark_attempt(ng_context.model,decision.evidence['proposal'],'a', global_trial=True)
    assert auto_ng.global_ng_trial(ng_context) is None


@pytest.mark.parametrize('fault', ['budget','attempts','candidate','phase','fast',
                                  'ng','source','grid','hydro','lambda','fixed_t','old_ba',
                                  'scale','temperature','counter_gap','missing_history',
                                  'missing_metric','nonfinite_metric','nonfinite_epsilon'])
def test_policy_refuses_ineligible_histories(ng_context, fault):
    c = ng_context
    if fault == 'budget':c=replace(c,remaining_iterations=8)
    elif fault == 'attempts':c=replace(c,remaining_attempts=3)
    elif fault == 'candidate':c.evidence['candidate']=True
    elif fault == 'phase':c=replace(c,phase='verify')
    elif fault in ['fast','flat']:
        c.history[0]['records'][0]['maximum_decrease_percent']=6 if fault=='fast' else 3.19
        c.history[0]['records'][0]['solver_maximum_change']=6 if fault=='fast' else 3.19
    elif fault in ['ng','source','grid','hydro']:
        key={'ng':'ng_accelerations','source':'source_changed','grid':'checkpoint_updates','hydro':'hydro_revisions'}[fault]
        c.history[0][key]=[1]
    elif fault in ['lambda','fixed_t','old_ba','scale']:
        key={'lambda':'lambda_iteration','fixed_t':'temperature_fixed','old_ba':'ba_computed','scale':'major_species_minimum_scale'}[fault]
        c.history[0]['records'][0][key]=False if fault=='old_ba' else (.5 if fault=='scale' else True)
    elif fault == 'temperature':c.history[0]['raw_temperature_steps']=[[.2]*5]*2
    elif fault == 'counter_gap':c.history[0]['records'][0]['global_iteration']-=1
    elif fault == 'missing_history':c=replace(c,history=c.history[-2:])
    elif fault == 'missing_metric':c.history[0]['records'][0].pop('solver_maximum_change')
    elif fault == 'nonfinite_metric':c.history[0]['records'][0]['solver_maximum_change']=float('inf')
    elif fault == 'nonfinite_epsilon':c.evidence['epsilon_percent']=float('nan')
    assert auto_ng.global_ng_trial(c) is None


@pytest.mark.parametrize('fault', ['energy','corrections','counts','luminosity','nonsettling',
                                  'source','wrong_counter','old_ba','large_transient'])
def test_final_acceptance_rejects_unhelpful_or_unsafe_trials(ng_context, monkeypatch, fault):
    decision=auto_ng.global_ng_trial(ng_context)
    e=evidence(46,(3.,2.9))
    (ng_context.model/'OBSFLUX').write_text('Departure from Rad Equilibrium Correction\n17 17 17 17 17\n')
    monkeypatch.setattr(auto_ng,'guard_measurements',lambda *a:dict(
        luminosity_min=1.,luminosity_max=1.10,inner_tau_ross=100.))
    if fault=='energy':(ng_context.model/'OBSFLUX').write_text('Departure from Rad Equilibrium Correction\n20 20 20 20 20\n')
    if fault=='corrections':e['records'][-1]['solver_maximum_change']=3.2
    if fault=='counts':e['counts']['totals']['0.1%']=11
    if fault=='nonsettling':e['records'][0]['solver_maximum_change']=2.8;e['records'][0]['maximum_decrease_percent']=2.8
    if fault=='source':e['source_changed']=True
    if fault=='wrong_counter':e['records'][0]['global_iteration']=44
    if fault=='old_ba':e['records'][0]['ba_computed']=False
    if fault=='large_transient':e['records'][0]['solver_maximum_change']=8
    if fault=='luminosity':monkeypatch.setattr(auto_ng,'guard_measurements',lambda *a:dict(luminosity_min=1.,luminosity_max=1.13,inner_tau_ross=100.))
    with pytest.raises(TrialRejected):decision.steps[-1].validate(replace(ng_context,evidence=e))


def test_transient_is_allowed_only_before_final_six_solve_check(ng_context, monkeypatch):
    decision=auto_ng.global_ng_trial(ng_context)
    e=evidence(42,(3.5,3.6))
    assert not decision.steps[0].validate(replace(ng_context,evidence=e))['global_ng_check']['accepted']
    (ng_context.model/'OBSFLUX').write_text('Departure from Rad Equilibrium Correction\n17 17 17 17 17\n')
    monkeypatch.setattr(auto_ng,'guard_measurements',lambda *a:dict(luminosity_min=1.,luminosity_max=1.10,inner_tau_ross=100.))
    result=decision.steps[-1].validate(replace(ng_context,evidence=evidence(46,(3.,2.9))))
    assert result['global_ng_check']['accepted']


NATIVE = r'''
from pathlib import Path
import json,re,struct,sys,time
if sys.argv[1:]==['--version']:
 print('CMFGEN_VIEWER_PATCH 2026-11-02.1');raise SystemExit(0)
p=Path('.')
mode=(p/'scenario').read_text()
def get(file,key,default):
 m=re.search(r'^\s*(\S+)\s+\['+re.escape(key)+r'\]',(p/file).read_text(),re.M)
 return m[1] if m else default
count=int(get('IN_ITS','NUM_ITS','3'))
point=(p/'POINT1').read_text().splitlines()[1].split()
record,iteration=int(point[0]),int(point[1]);size=16376
receipt=p/'.cmfgen-runs/global-ng-trials.json'
seeded=receipt.exists() and get('VADAT','DO_NG','T')=='F'
accepted=0
if receipt.exists():
 for folder in json.loads(receipt.read_text()).values():
  action=Path(folder)/'action.json'
  if action.is_file():accepted+=json.loads(action.read_text()).get('trial_outcome')=='accepted'
if seeded:
 assert get('VADAT','DO_NG','T')=='F'
 assert get('VADAT','FIX_T','T')=='F'
 assert get('IN_ITS','DO_LAM_IT','T')=='F'
 assert get('IN_ITS','DO_T_AUTO','T')=='F'
trial=int((p/'trial-calls').read_text())+1 if (p/'trial-calls').exists() else 1
if seeded:(p/'trial-calls').write_text(str(trial))
if seeded and mode=='ng_crash':print('unrecognized native failure');raise SystemExit(1)
data=(p/'SCRTEMP').read_bytes();geometry=data[:size]
values=list(struct.unpack_from('<30d',data,(3+2*(record-1))*size))
def pack(items):
 b=struct.pack('<'+str(len(items))+'d',*items);return b+bytes(size-len(b))
out='Model started on: now\n'
with (p/'STEQ_VALS').open('a') as sol:
 for n in range(count):
  iteration+=1;record+=1
  if not seeded:
   neutral=-1+1.3*1.005**(40-iteration)
   for d in range(5):values[d*6:d*6+6]=[1e10*neutral,1e10*(1-neutral),5e8,5e8,1e10*(1-neutral)+5e8,1+.001*(1.005**(40-iteration)-1)]
  value=(3.22-.005*(iteration-40)) if not seeded else (3.7-.25*trial-.05*n)
  if seeded and mode=='ng_bad':value=3.5
  out+=f'Current great iteration count is {iteration}\nBA matrix computed\n'
  out+=f'Luminosity of star (d=1,ND)(iteration {iteration}) is: 1.12 1\n'
  out+=f'Maximum % increase at depth 3 is 1.0 (BA computed) --- iteration {iteration}\n'
  out+=f'Maximum % decrease at depth 3 is {value} (BA computed) --- iteration {iteration}\n'
  out+=f'Maximm changes as returned by SOLVEBA_V13 is {value}\n'
  out+='The minimum value of scale for Major species is: 1\n'
  sol.write(' STEQ SOLUTION ARRAY\n')
  for v in range(1,7):sol.write(f'{v}( 1)# '+'.00001 '*5+'\n')
  data=data[:(2+2*(record-1))*size]+geometry+pack(values)
(p/'SCRTEMP').write_bytes(data)
for name in ['POINT1','POINT2']:(p/name).write_text(f'28-Feb-2004 !Format date\n{record} {iteration} 1 10 T\n')
(p/'OUTGEN').write_text(out)
(p/'MODEL').write_text((p/'MODEL').read_text()+'\nNative update '+str(time.time_ns())+'\n')
(p/'MOD_SUM').write_text('Model Finalized on: '+str(time.time_ns())+'\n')
(p/'RVTJ').write_text('ND: 5\nRadius\n6 5 4 3 2\nVelocity\n20 20 20 20 20\nTemperature\n'+' '.join(str(values[i*6+5]) for i in range(5))+'\nElectron density\n'+' '.join(str(values[i*6+4]) for i in range(5))+'\n')
(p/'CORRECTION_SUM').write_text('NT=6\nDepth 100.0% 10.0% 1.0% 0.1% 0.01% 0.001% 0.0001%\n'+''.join(f'{d} 0 0 1 2 3 4 6\n' for d in range(1,6)))
lum=1+.12*.85**(accepted+int(seeded))
energy=20*.85**(accepted+int(seeded))
(p/'OBSFLUX').write_text('Normalized luminosity check (normalized by L[ND])\n'+f'{lum} {lum} {lum} {lum} 1\nDeparture from Rad Equilibrium Correction\n'+(str(energy)+' ')*5+'\n')
(p/'MEANOPAC').write_text('Depth Tau(Ross)\n'+''.join(f'a {d} {50*d} '+' '.join(['1']*12)+'\n' for d in range(1,6)))
'''


@pytest.fixture
def ng_workspace(auto_workspace, ng_model, monkeypatch):
    model,plan=auto_workspace
    for n in ['SCRTEMP','MODEL','MODEL_SPEC','POINT1','POINT2']:
        shutil.copy2(ng_model/n, model/n)
    for n in ['POINT1','POINT2']:(model/n).write_text((model/n).read_text().replace('-1000','10'))
    (model/'MODEL_SPEC').write_text('3 [NUM_BNDS]\n5 [ND]\n1 [NC]\n6 [NP]\n1,1,1 [HI_ISF]\n1,1,1 [HeI_ISF]\n')
    (model/'VADAT').write_text('1 [RSTAR]\n.02 [EPS_TERM]\nF [FIX_T]\nT [INCL_dSLdT]\nMAJOR [SCALE_OPT]\n0 [N_FIX_BA]\n0 [FIX_BA]\nT [COMP_BA]\nF [DO_HYDRO]\nT [DO_NG]\n2 [BW_NG]\n')
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    exe.write_text(f'#!{sys.executable}\n'+NATIVE);exe.chmod(0o755)
    from cmfgen_viewer import auto_policies
    entry=auto_policies.Policy('global_ng',1,'success','Positive global trial',auto_ng.global_ng_trial,3)
    policies=[p for p in auto_policies.POLICIES if p.id!='global_ng']
    policies.insert(next(i for i,p in enumerate(policies) if p.id=='bounded_ng'),entry)
    monkeypatch.setattr(auto_policies,'POLICIES',tuple(policies))
    return model,plan


@pytest.mark.parametrize('mode,outcome', [('ng_good','accepted'),('ng_bad','rejected'),('ng_crash','aborted')])
def test_controller_six_solve_trial_and_atomic_rollback(ng_workspace, mode, outcome):
    model,plan=ng_workspace
    saved={};finished=False
    def emit(event):
        nonlocal finished
        if event['event']=='auto_action' and event['action']['kind']=='global_ng':
            saved['pointer']=(model/'POINT1').read_bytes()
            saved['recovery']=recovery_bytes(event['action'])
        if event['event']=='auto_performance_trial':
            finished=True
            if outcome=='rejected':assert_restored(model,saved['recovery'])
    result=run_plan(plan(mode,max_attempts=8,max_iterations=30),emit,stop_requested=lambda:finished)
    trials=[a for a in result['actions'] if a['kind']=='global_ng']
    assert len(trials)==1,result
    assert trials[0]['trial_outcome']==outcome,result
    assert 'numerical_convergence' not in result
    if outcome=='accepted':
        assert result['attempts'][-1]['global_ng_check']['accepted']
        assert len([a for a in result['attempts'] if a['phase'].startswith('global_ng_')])==3
        assert int((model/'POINT1').read_text().splitlines()[1].split()[1])==52
    else:
        assert_restored(model,saved['recovery'])
        assert (model/'.cmfgen-runs/global-ng-trials.json').exists()
    if mode=='ng_crash':assert result['status']=='needs_review'


def test_controller_cancel_during_second_pair_restores_baseline(ng_workspace):
    model,plan=ng_workspace
    saved={}
    def emit(event):
        if event['event']=='auto_action' and event['action']['kind']=='global_ng':saved.update(recovery_bytes(event['action']))
        if event['event']=='auto_attempt' and event['phase']=='global_ng_settle2':raise KeyboardInterrupt()
    result=run_plan(plan('ng_good',max_attempts=8,max_iterations=30),emit)
    assert result['status']=='cancelled',result
    assert_restored(model,saved)
    assert result['provisional_recovery_rolled_back']=='global_ng'


@pytest.mark.parametrize('boundary', ['after_seed','after_four','receipt_failure','action_directory_failure'])
def test_controller_early_exit_or_receipt_failure_never_accepts_seed(ng_workspace, monkeypatch, boundary):
    model,plan=ng_workspace
    saved={};stop=False
    def fail_receipt(*args,**kwargs):raise OSError('injected receipt ENOSPC')
    if boundary=='receipt_failure':monkeypatch.setattr(auto_ng,'mark_attempt',fail_receipt)
    if boundary=='action_directory_failure':
        from cmfgen_viewer import runner_auto
        original=runner_auto.mkdir_readable
        def fail_directory(path,**kwargs):
            if path.name.startswith('action-'):raise OSError('injected mkdir ENOSPC')
            return original(path,**kwargs)
        monkeypatch.setattr(runner_auto,'mkdir_readable',fail_directory)
    def emit(event):
        nonlocal stop
        if event['event']=='auto_assessment' and event['checkpoint']==46:
            saved.update({n:(model/n).read_bytes() if (model/n).exists() else None for n in RECOVERY_NAMES})
        if event['event']=='auto_action' and event['action']['kind']=='global_ng' and boundary=='after_seed':stop=True
        if event['event']=='auto_assessment' and event['checkpoint']==50 and boundary=='after_four':stop=True
    result=run_plan(plan('ng_good',max_attempts=8,max_iterations=30),emit,stop_requested=lambda:stop)
    assert result['status']==('needs_review' if boundary.endswith('failure') else 'stopped'),result
    assert result['provisional_recovery_rolled_back']=='global_ng'
    assert_restored(model,saved)
    assert 'numerical_convergence' not in result


def test_energy_aggregate_must_be_finite(ng_context):
    (ng_context.model/'OBSFLUX').write_text('Departure from Rad Equilibrium Correction\n'+'1e308 '*5+'\n')
    from cmfgen_viewer.auto_policies import Declined
    with pytest.raises(Declined,match='Unrepresentable'):
        auto_ng.global_ng_trial(ng_context)


@pytest.mark.parametrize('start,outcome,eligible', [(14,'accepted',True),
    (28,'accepted',False),(34,'rejected',False),(30,'rejected',True)])
def test_repeat_requires_cooldown_after_acceptance_or_rejection(ng_context,start,outcome,eligible):
    action={'policy_id':'global_ng','evidence':{'checkpoint':start},'trial_outcome':outcome}
    history=[evidence(34,(3.26,3.25)),*ng_context.history]
    decision=auto_ng.global_ng_trial(replace(ng_context,actions=[action],history=history))
    assert (decision is not None and decision.kind=='action')==eligible


def test_global_acceptance_requires_meaningful_profile_gain(ng_context,monkeypatch):
    decision=auto_ng.global_ng_trial(ng_context)
    (ng_context.model/'OBSFLUX').write_text('Departure from Rad Equilibrium Correction\n17 17 17 17 17\n')
    # Better population and energy metrics cannot excuse a nearly unchanged flux profile.
    monkeypatch.setattr(auto_ng,'guard_measurements',lambda *a:dict(
        luminosity_min=1.,luminosity_max=1.119,inner_tau_ross=100.))
    with pytest.raises(TrialRejected):
        decision.steps[-1].validate(replace(ng_context,evidence=evidence(46,(3.,2.9))))


def test_global_acceptance_rejects_a_small_energy_nudge(ng_context,monkeypatch):
    decision=auto_ng.global_ng_trial(ng_context)
    (ng_context.model/'OBSFLUX').write_text('Departure from Rad Equilibrium Correction\n19 19 19 19 19\n')
    monkeypatch.setattr(auto_ng,'guard_measurements',lambda *a:dict(
        luminosity_min=1.,luminosity_max=1.10,inner_tau_ross=100.))
    with pytest.raises(TrialRejected):
        decision.steps[-1].validate(replace(ng_context,evidence=evidence(46,(3.,2.9))))


def test_global_trial_budget_stops_without_claiming_convergence(ng_context,monkeypatch):
    from cmfgen_viewer import auto_policies
    entry=auto_policies.Policy('global_ng',1,'success','Positive global trial',auto_ng.global_ng_trial,3)
    monkeypatch.setattr(auto_policies,'POLICIES',(entry,))
    old={'policy_id':'global_ng','evidence':{'checkpoint':14},'trial_outcome':'accepted'}
    history=[evidence(34,(3.26,3.25)),*ng_context.history]
    decision,_=auto_policies.choose(replace(ng_context,actions=[old.copy() for _ in range(3)],history=history))
    assert decision.kind=='stop' and 'exhausted' in decision.reason


def test_rejected_global_trial_resumes_from_the_restored_checkpoint(ng_workspace):
    model,plan=ng_workspace;rejected=False;finished=False;restored={}
    def emit(event):
        nonlocal rejected,finished
        if event['event']=='auto_action' and event['action']['kind']=='global_ng':
            restored.update(recovery_bytes(event['action']))
        if event['event']=='auto_performance_trial':
            assert event['outcome']=='rejected'
            assert_restored(model,restored);rejected=True
        if rejected and event['event']=='auto_assessment' and event['checkpoint']==48:finished=True
    result=run_plan(plan('ng_bad',iterations=2,max_attempts=12,max_iterations=40),emit,stop_requested=lambda:finished)
    assert rejected and finished and result['status']=='stopped',result
    assert int((model/'POINT1').read_text().splitlines()[1].split()[1])==48
    assert 'T [DO_NG]' in (model/'VADAT').read_text()
    assert 'numerical_convergence' not in result


def test_controller_can_repeat_a_verified_global_trial_after_cooldown(ng_workspace):
    model,plan=ng_workspace;accepted=[]
    def emit(event):
        if event['event']=='auto_performance_trial':
            assert event['outcome']=='accepted';accepted.append(event)
    result=run_plan(plan('ng_good',max_attempts=25,max_iterations=90),emit,
                    stop_requested=lambda:len(accepted)==2)
    actions=[a for a in result['actions'] if a['kind']=='global_ng']
    assert len(actions)==2 and all(a['trial_outcome']=='accepted' for a in actions),result
    assert actions[1]['evidence']['checkpoint']>=actions[0]['evidence']['checkpoint']+6+8
    assert len(json.loads((model/'.cmfgen-runs/global-ng-trials.json').read_text()))==2
    assert 'T [DO_NG]' in (model/'VADAT').read_text()
    assert 'numerical_convergence' not in result


def test_legacy_affine_trial_cannot_interrupt_global_cooldown(ng_context):
    recent={'policy_id':'global_ng','evidence':{'checkpoint':34},'trial_outcome':'accepted'}
    assert auto_ng.bounded_ng_trial(replace(ng_context,actions=[recent])) is None
    old={'policy_id':'global_ng','evidence':{'checkpoint':14},'trial_outcome':'accepted'}
    history=[evidence(34,(3.26,3.25)),*ng_context.history]
    assert auto_ng.bounded_ng_trial(replace(ng_context,actions=[old],history=history)) is not None


@pytest.mark.parametrize('fault',['missing','fast','changing_target','growing','sign_change'])
def test_global_trial_requires_observed_slow_thermal_progress(ng_context,fault):
    rows=[r for e in ng_context.history for r in e['records']]
    if fault=='missing':rows[0].pop('luminosity_generated')
    if fault=='fast':rows[0]['luminosity_generated']=1.2
    if fault=='changing_target':rows[0]['luminosity_target']=1.01
    if fault=='growing':rows[-1]['luminosity_generated']=1.14
    if fault=='sign_change':rows[-1]['luminosity_generated']=.88
    assert auto_ng.global_ng_trial(ng_context) is None


def test_flat_rounded_population_metric_does_not_hide_a_thermal_stall(ng_context):
    for e in ng_context.history:
        for r in e['records']:r['solver_maximum_change']=r['maximum_decrease_percent']=3.19
    assert auto_ng.global_ng_trial(ng_context) is not None


def test_small_corrections_can_still_have_a_large_slow_thermal_error(ng_context):
    for e in ng_context.history:
        for r in e['records']:
            for key in ['solver_maximum_change','maximum_increase_percent','maximum_decrease_percent']:r[key]*=.125
        e['counts']['totals']['1.0%']=0
    assert auto_ng.global_ng_trial(ng_context) is not None
