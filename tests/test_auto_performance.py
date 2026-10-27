"""Real controller trials commit only measured safe performance changes."""
import json
from pathlib import Path

import pytest

from test_auto_recovery import population_workspace, authenticate
from test_runner_auto import auto_workspace
from cmfgen_viewer.auto_diagnostics import control_value
from cmfgen_viewer.runner import run_plan


@pytest.fixture
def performance_workspace(population_workspace):
    model, plan = population_workspace
    (model/'attempts.txt').unlink()
    (model/'VADAT').write_text((model/'VADAT').read_text()+'T [STORE_BA]\nF [DO_NG]\n')
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    code=exe.read_text()
    assert "if mode=='raw_high':value=0.5" in code
    code=code.replace("if mode=='raw_high':value=0.5", """if mode.startswith('performance'):
 relax=float(get('ADJUST_CORRECTIONS','RELAX','1'))
 if mode.startswith('performance_relax') and relax<=.25:(p/'settled').touch()
 recovering=mode.startswith('performance_relax') and not (p/'settled').exists()
 large=recovering
 value=10 if recovering else .8/2**max(0,attempt-(2 if mode.startswith('performance_relax') else 1))
 reuse=get('VADAT','N_FIX_BA','0')=='1'
 if mode=='performance_bad' and reuse:value=.8
 if mode=='performance_relax_bad' and not recovering and relax>.25:value=.8
 if mode=='performance_crash' and reuse:
  print('unrecognized native failure',flush=True)
  raise SystemExit(1)
if mode=='raw_high':value=0.5""")
    code=code.replace("out+='BA matrix computed\\n' if fresh else 'BA matrix **NOT** computed\\n'",
        "out+='BA matrix computed\\n' if fresh or (get('VADAT','N_FIX_BA','0')=='1' and n==0) or mode=='performance_no_reuse' else 'BA matrix **NOT** computed\\n'")
    code=code.replace("(p/'CORRECTION_SUM').write_text('NT=3", "(p/'CORRECTION_SUM').write_text('NT=4")
    code=code.replace(' 3( 1)#', ' 4( 1)#')
    code+='''
if mode.startswith('performance'):
 low=.4 if mode=='performance_flux' and get('VADAT','N_FIX_BA','0')=='1' else 1
 (p/'OBSFLUX').write_text('Normalized luminosity check (normalized by L[ND])\\n'+str(low)+' 1\\n')
 (p/'MEANOPAC').write_text('Depth Tau(Ross)\\n'+''.join('a '+str(i)+' '+str(50*i)+' '+' '.join(['1']*12)+'\\n' for i in [1,2]))
 if mode=='performance_missing' and get('VADAT','N_FIX_BA','0')=='1':(p/'MEANOPAC').unlink()
'''
    exe.write_text(code)
    authenticate(model)
    return model, plan


@pytest.mark.parametrize('above_one_percent', [False, True])
def test_guarded_ba_reuse_is_provisional_then_verified(performance_workspace, above_one_percent):
    model,plan=performance_workspace
    if above_one_percent:
        exe = model.parent/'cmf/exe/cmfgen_dev.exe'
        exe.write_text(exe.read_text().replace('else .8/2**', 'else 8/2**'))
        authenticate(model)
    result=run_plan(plan('performance'))
    assert result['status']=='succeeded',result
    trial=next(a for a in result['actions'] if a['kind']=='ba_reuse_trial')
    assert trial['trial_outcome']=='accepted'
    if above_one_percent:
        assert trial['evidence']['correction_metric'] > 1
    attempt=next(a for a in result['attempts'] if a['phase']=='ba_reuse_check')
    assert attempt['performance_trial']['matrix_schedule']==[True,False]
    assert result['attempts'][-1]['phase']=='verify'
    assert result['attempts'][-1]['evidence']['fresh_verified']
    assert control_value(model,'VADAT','N_FIX_BA')=='0'
    assert control_value(model,'VADAT','FIX_BA')=='0.0'
    assert control_value(model,'VADAT','DO_NG')=='F'
    assert json.loads((Path(trial['directory'])/'action.json').read_text())['trial_outcome']=='accepted'


@pytest.mark.parametrize('scenario', ['performance_bad','performance_flux','performance_missing','performance_no_reuse'])
def test_rejected_trial_restores_and_continues_without_retry(performance_workspace, scenario):
    model,plan=performance_workspace
    baseline={}
    def observe(event):
        if event['event']=='auto_action' and event['action']['kind']=='ba_reuse_trial':
            baseline['checkpoint']=(model/'POINT1').read_bytes()
        if event['event']=='auto_performance_trial':
            assert event['outcome']=='rejected'
            assert (model/'POINT1').read_bytes()==baseline['checkpoint']
            assert control_value(model,'VADAT','N_FIX_BA')=='0'
    result=run_plan(plan(scenario),observe)
    assert result['status']=='succeeded',result
    trials=[a for a in result['actions'] if a['kind']=='ba_reuse_trial']
    assert len(trials)==1 and trials[0]['trial_outcome']=='rejected'
    rejected=next(a for a in result['attempts'] if a.get('optimization_rejected'))
    assert rejected['checkpoint_restored']
    assert result['attempts'][-1]['evidence']['fresh_verified']


def test_trial_cancellation_rolls_back(performance_workspace):
    model,plan=performance_workspace
    baseline={}
    def cancel(event):
        if event['event']=='auto_attempt' and event['phase']=='ba_reuse_check':
            baseline['checkpoint']=(model/'POINT1').read_bytes()
            raise KeyboardInterrupt()
    result=run_plan(plan('performance'),cancel)
    assert result['status']=='cancelled'
    assert (model/'POINT1').read_bytes()==baseline['checkpoint']
    assert control_value(model,'VADAT','N_FIX_BA')=='0'
    assert next(a for a in result['actions'] if a['kind']=='ba_reuse_trial')['trial_outcome']=='aborted'


def test_trial_leaves_room_for_verification(performance_workspace):
    model,plan=performance_workspace
    result=run_plan(plan('performance',max_iterations=10))
    assert result['status']=='limit_reached'
    assert not any(a['kind']=='ba_reuse_trial' for a in result['actions'])
    assert control_value(model,'VADAT','N_FIX_BA')=='0'


def test_unknown_trial_failure_still_requires_review(performance_workspace):
    model,plan=performance_workspace
    result=run_plan(plan('performance_crash'))
    assert result['status']=='needs_review',result
    assert control_value(model,'VADAT','N_FIX_BA')=='0'
    assert result['provisional_recovery_rolled_back']=='ba_reuse_trial'


def test_automatic_damping_released_gradually_with_fresh_matrices(performance_workspace):
    model,plan=performance_workspace
    result=run_plan(plan('performance_relax'))
    assert result['status']=='succeeded',result
    trials=[a for a in result['actions'] if a['kind']=='relaxation_release']
    assert [a['changes']['ADJUST_CORRECTIONS']['RELAX'] for a in trials]==['0.5','1.0']
    assert all(a['trial_outcome']=='accepted' for a in trials)
    assert control_value(model,'ADJUST_CORRECTIONS','RELAX')=='1.0'
    assert all(a['performance_trial']['matrix_schedule']==[True,True] for a in result['attempts']
               if a['phase']=='relaxation_release_check')


def test_user_damping_is_not_removed(performance_workspace):
    model,plan=performance_workspace
    (model/'ADJUST_CORRECTIONS').write_text('1 [L_ST]\n1 [L_END]\n0.5 [RELAX]\n0.2 [T_LIM]\n')
    result=run_plan(plan('performance'))
    assert result['status']=='succeeded',result
    assert not any(a['kind']=='relaxation_release' for a in result['actions'])
    assert control_value(model,'ADJUST_CORRECTIONS','RELAX')=='0.5'


def test_damping_release_stops_at_the_users_original_factor(performance_workspace):
    model,plan=performance_workspace
    (model/'ADJUST_CORRECTIONS').write_text('1 [L_ST]\n1 [L_END]\n0.5 [RELAX]\n0.2 [T_LIM]\n')
    result=run_plan(plan('performance_relax'))
    assert result['status']=='succeeded',result
    trials=[a for a in result['actions'] if a['kind']=='relaxation_release']
    assert [a['changes']['ADJUST_CORRECTIONS']['RELAX'] for a in trials]==['0.5']
    assert control_value(model,'ADJUST_CORRECTIONS','RELAX')=='0.5'


def test_rejected_damping_release_is_not_repeated(performance_workspace):
    model,plan=performance_workspace
    result=run_plan(plan('performance_relax_bad'))
    assert result['status']=='succeeded',result
    trials=[a for a in result['actions'] if a['kind']=='relaxation_release']
    assert len(trials)==1 and trials[0]['trial_outcome']=='rejected'
    assert control_value(model,'ADJUST_CORRECTIONS','RELAX')=='0.25'


def test_unidentified_runtime_skips_optional_tuning(performance_workspace):
    model,plan=performance_workspace
    (model.parent/'cmf/cmfgen-local-build.json').unlink()
    result=run_plan(plan('performance'))
    assert result['status']=='succeeded',result
    assert not any(a.get('reversible_trial') for a in result['actions'])


def test_missing_temperature_vectors_skip_tuning_without_blocking_iteration(performance_workspace):
    model,plan=performance_workspace
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    exe.write_text(exe.read_text().replace(' 4( 1)#', ' 3( 1)#'))
    authenticate(model)
    result=run_plan(plan('performance'))
    assert result['status']=='succeeded',result
    assert not any(a.get('reversible_trial') for a in result['actions'])


def test_global_temperature_cycle_blocks_performance_tuning():
    from cmfgen_viewer.auto_diagnostics import oscillating_region
    evidence={'counts':{'nd':3},'epsilon_percent':.02,
              'raw_temperature_steps':[[.1,.1,.1],[-.1,-.1,-.1],[.1,.1,.1]]}
    assert oscillating_region(evidence,[]) is None  # Existing damping remains localized.
    assert oscillating_region(evidence,[],localized_only=False)==[1,3]


@pytest.fixture
def performance_context(tmp_path, monkeypatch):
    from cmfgen_viewer.auto_policies import Context
    from cmfgen_viewer import auto_recovery, checkpoint_physics, auto_performance
    monkeypatch.setattr(auto_recovery, 'repaired_runtime', lambda plan: True)
    monkeypatch.setattr(checkpoint_physics, 'checkpoint_physics', lambda model: {})
    monkeypatch.setattr(checkpoint_physics, 'compare_physics', lambda a, b: {})
    monkeypatch.setattr(auto_performance, 'guard_measurements',
                        lambda model, before: {'luminosity_min': 1, 'luminosity_max': 1})
    (tmp_path/'VADAT').write_text('T [COMP_BA]\nT [STORE_BA]\n0 [N_FIX_BA]\n0 [FIX_BA]\n')
    def batch(value):
        return {'records': [dict(solver_maximum_change=v, maximum_increase_percent=v,
                                maximum_decrease_percent=v) for v in [value*1.1, value]],
                'epsilon_percent': .02, 'iterations': 2, 'full_iterations': 2, 'counts': {
                    'nd': 2, 'nt': 4, 'totals': {'1.0%': 10}},
                'raw_temperature_steps': [[.001, .001], [.0008, .0008]]}
    history = [batch(4.13), batch(1.115)]
    return Context(tmp_path, 'success', {}, {}, {}, history[-1], history,
                   'iterate', [], '', remaining_iterations=20, remaining_attempts=5)


def test_two_improving_batches_above_one_percent_allow_ba_trial(performance_context):
    from cmfgen_viewer.auto_performance import ba_reuse_trial, _baseline
    ctx = performance_context
    decision = ba_reuse_trial(ctx)
    assert decision and decision.reversible_trial
    assert decision.changes['VADAT'] == {'N_FIX_BA': '1', 'FIX_BA': '0.0'}
    assert decision.steps[0].iterations == 2
    assert _baseline(ctx) is None  # Damping still needs three batches.
    ctx.history.insert(0, ctx.history[0])
    assert _baseline(ctx) is None  # Three batches above 1% still cannot release damping.


@pytest.mark.parametrize('condition', ['one_batch', 'weak_decline', 'rebound', 'counts',
    'hydro', 'ng', 'fixed_temperature', 'missing_temperature', 'nonfinite', 'cycling'])
def test_earlier_ba_trial_keeps_progress_and_safety_guards(performance_context, condition):
    from cmfgen_viewer.auto_performance import ba_reuse_trial
    ctx = performance_context
    last = ctx.history[-1]
    if condition == 'one_batch': ctx.history.pop(0)
    if condition in ('weak_decline', 'rebound'):
        value = 4.0 if condition == 'weak_decline' else 5.0
        for row in last['records']:
            for key in ('solver_maximum_change', 'maximum_increase_percent', 'maximum_decrease_percent'):
                row[key] = value
    if condition == 'counts': last['counts']['totals']['1.0%'] = 11
    if condition == 'hydro': last['hydro_revisions'] = [1]
    if condition == 'ng': last['ng_accelerations'] = [1]
    if condition == 'fixed_temperature': last['full_iterations'] = 0
    if condition == 'missing_temperature': last['raw_temperature_steps'] = []
    if condition == 'nonfinite': last['records'][0]['solver_maximum_change'] = float('inf')
    if condition == 'cycling':
        for batch in ctx.history: batch['raw_temperature_steps'] = [[1, 1], [-1, -1]]
    assert ba_reuse_trial(ctx) is None


def test_damping_release_keeps_three_batches_and_one_percent_ceiling(performance_context):
    import copy
    from cmfgen_viewer.auto_performance import _baseline
    ctx = performance_context
    ctx.history.insert(0, copy.deepcopy(ctx.history[0]))
    for batch, value in zip(ctx.history, [.8, .6, .4]):
        for row in batch['records']:
            for key in ('solver_maximum_change', 'maximum_increase_percent', 'maximum_decrease_percent'):
                row[key] = value
    assert _baseline(ctx) is not None
    ctx.history[0]['records'][0]['maximum_increase_percent'] = 1.01
    assert _baseline(ctx) is None
    assert _baseline(ctx, reuse=True) is not None
