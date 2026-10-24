"""Bstar3502 remedies: real controller rollback, temporary controls and binary audits."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from test_runner_auto import auto_workspace
from cmfgen_viewer import auto_policies as policies
from cmfgen_viewer.auto_diagnostics import control_value
from cmfgen_viewer.auto_recovery import ng_cadence, ray_refinement, repaired_runtime
from cmfgen_viewer.checkpoint_physics import checkpoint_physics, compare_physics
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner_recipe import RunnerError


def authenticate(model):
    root=model.parent/'cmf'
    exe=root/'exe/cmfgen_dev.exe'
    (root/'cmfgen-local-build.json').write_text(json.dumps({
        'capabilities':['line-jacobian-v1','ba-restart-v1'],
        'executables':{'cmfgen_dev.exe':{'sha256':hashlib.sha256(exe.read_bytes()).hexdigest()}}}))


@pytest.fixture
def population_workspace(auto_workspace):
    model,plan=auto_workspace
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    code=exe.read_text()
    code=code.replace("if mode=='stall':value=1", """if mode.startswith('population'):
 lam=get('IN_ITS','DO_LAM_IT','F')=='T'
 if lam:(p/'bootstrap-seen').touch()
 value=1e24 if not (p/'bootstrap-seen').exists() else 0.005
 if mode=='population_fail' and (p/'bootstrap-seen').exists() and not lam:
  print('unknown issue',flush=True)
  raise SystemExit(1)
 with (p/'control-trace').open('a') as stream:
  stream.write(get('VADAT','FIX_T','F')+' '+get('VADAT','MAX_LAM','10000')+' '+get('IN_ITS','DO_LAM_IT','F')+' '+get('VADAT','DO_NG','T')+'\\n')
""")
    code=code.replace("  if mode=='lambda':", "  if mode=='lambda' or (mode.startswith('population') and lam):")
    code=code.replace("  out+=f'Maximum % increase", "  if mode.startswith('population') and lam:value=[1e24,1e12,32][n]\n  out+=f'Maximum % increase")
    # Emit a genuine recognized two-depth/four-variable checkpoint with a
    # complete H I/terminal H II table, exact charge and constant element sums.
    code=code.replace("(p/'SCRTEMP').write_bytes(bytes(100)+str(start+count-1).encode())", """
import struct
def pack(v):
 b=struct.pack('<'+str(len(v))+'d',*v)
 return b+bytes(16376-len(b))
g=pack([2.,1.,20.,10.,0.,0.])
v=pack([1e7,1e10,1e10,1., 1e7,2e10,2e10,2.])
(p/'SCRTEMP').write_bytes(g+g+(g+v)*(start+count-1))
(p/'MODEL').write_text('2 !Number of depth points\\n4 !Total number of variables\\n\\f\\nHI 1 1 1.0 1.0 1.0 1.0 1 1 1 1 ground\\n')
""")
    exe.write_text(code)
    authenticate(model)
    assert run_plan(plan())['status']=='succeeded'
    return model,plan


def test_population_recipe_restores_controls_and_checks_conservation(population_workspace):
    model,plan=population_workspace
    before={n:control_value(model,'VADAT',n) for n in ['FIX_T','MAX_LAM','DO_NG']}
    result=run_plan(plan('population'))
    assert result['status']=='succeeded',result
    assert [a['policy_id'] for a in result['actions']]==['population_bootstrap','verify_candidate']
    assert [x['phase'] for x in result['attempts']]==['iterate','population_lambda','population_full','verify']
    check=result['attempts'][1]['checkpoint_physics']
    assert check['element_density_max_relative_change']==check['charge_relative_error']==0
    assert {n:control_value(model,'VADAT',n) for n in before}==before
    assert control_value(model,'IN_ITS','DO_LAM_IT') is None
    assert 'T 1.0D12 T F' in (model/'control-trace').read_text()
    assert checkpoint_physics(model)['charge_relative_error']==0


def test_failed_full_check_rolls_back_entire_bootstrap(population_workspace):
    model,plan=population_workspace
    old={n:(model/n).read_bytes() for n in ['POINT1','POINT2','SCRTEMP','VADAT','IN_ITS']}
    result=run_plan(plan('population_fail'))
    assert result['status']=='needs_review',result
    assert result['provisional_recovery_rolled_back']=='population_bootstrap'
    # The accepted initial full batch precedes the provisional recipe; its
    # checkpoint remains the recovery source, and normal controls survive.
    for name in ['VADAT','IN_ITS']:assert (model/name).read_bytes()==old[name]
    assert control_value(model,'VADAT','FIX_T')=='F'
    assert checkpoint_physics(model)['charge_relative_error']==0


def test_bootstrap_declines_unidentified_binary(auto_workspace):
    model,plan=auto_workspace
    authenticate(model)
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    assert repaired_runtime({'executable':str(exe)})
    exe.write_text(exe.read_text()+'\n# changed binary\n')
    assert not repaired_runtime({'executable':str(exe)})


def test_conservation_loss_and_temperature_changes_are_rejected(population_workspace):
    model,_=population_workspace
    a=checkpoint_physics(model)
    b={**a,'element_densities':{k:[x*.9 for x in v] for k,v in a['element_densities'].items()}}
    with pytest.raises(RunnerError,match='abundance'):compare_physics(a,b)
    with pytest.raises(RunnerError,match='temperature'):
        compare_physics(a,{**a,'temperature':[2,3]},fixed_temperature=True)


def test_temperature_coupling_precedes_local_damping(auto_workspace):
    model,plan=auto_workspace
    (model/'VADAT').write_text((model/'VADAT').read_text().replace('T [INCL_dSLdT]','F [INCL_dSLdT]'))
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    exe.write_text(exe.read_text().replace("large=mode=='never' or (mode=='oscillate' and not relaxed)",
        "large=mode=='never' or (mode=='oscillate' and get('VADAT','INCL_dSLdT','F')!='T')"))
    result=run_plan(plan('oscillate'))
    assert result['status']=='succeeded',result
    assert [a['policy_id'] for a in result['actions']]==['superlevel_temperature','verify_candidate']
    assert not (model/'ADJUST_CORRECTIONS').exists()
    assert control_value(model,'VADAT','INCL_dSLdT')=='T'


def test_ng_cadence_extends_contiguous_batch_and_honors_budget(auto_workspace):
    model,plan=auto_workspace
    (model/'VADAT').write_text((model/'VADAT').read_text()+'T [DO_NG]\n1 [IBEG_NG]\n10 [BEG_NG]\n')
    result=run_plan(plan('decay',max_attempts=5,max_iterations=50))
    assert result['attempts'][2]['requested_iterations']==8,result
    assert result['actions'][0]['policy_id']=='ng_cadence'
    assert result['iterations_used']<=50
    # Start another auto invocation with too little budget for the extension.
    result=run_plan(plan('stall',max_iterations=7))
    assert result['status']=='limit_reached'
    assert result['iterations_used']==6
    assert not result['actions']


def ray_context(model, minimum=-1):
    (model/'VADAT').write_text('F [DO_HYDRO]\n20000 [VFRAC_FG]\n20000 [VFRAC_MOM]\n')
    (model/'MODEL_SPEC').write_text('2 [ND]\n')
    (model/'OBSFLUX').write_text('Normalized luminosity check (normalized by L[ND])\n'+str(minimum)+' 1\n')
    return policies.Context(model,'failure',{'restart':{'mode':'continuation'}},
        {'passes':[{'diagnostic_findings':[{'code':'inner_flux_accuracy','severity':'error'}]}]},
        {'OBSFLUX':{}},{},[],'iterate',[],'')


def test_ray_refinement_requires_negative_fresh_profile_and_original_moment_grid(tmp_path):
    ctx=ray_context(tmp_path)
    decision=ray_refinement(ctx)
    assert decision.changes['VADAT']['VFRAC_FG']=='0.1'
    assert 'VFRAC_MOM' not in decision.changes['VADAT']
    assert decision.steps[0].iterations==2
    assert ray_refinement(ray_context(tmp_path,.4)) is None
    ctx=ray_context(tmp_path)
    (tmp_path/'VADAT').write_text('0.5 [VFRAC_MOM]\n')
    with pytest.raises(policies.Declined,match='moment grids'):ray_refinement(ctx)
    ctx=ray_context(tmp_path)
    from cmfgen_viewer.runner_recipe import snapshot
    with pytest.raises(policies.Declined,match='refreshed'):
        ray_refinement(replace(ctx,before={'OBSFLUX':snapshot(tmp_path/'OBSFLUX')}))


def add_guard_stop(model):
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    s=exe.read_text().replace("if mode=='population_fail' and", "if mode in ['population_fail','population_guard_fail'] and")
    s=s.replace("count=int(get('IN_ITS','NUM_ITS','2'))", "count=int(get('IN_ITS','NUM_ITS','2'))\nif mode.startswith('population_guard') and not (p/'bootstrap-seen').exists() and get('IN_ITS','DO_LAM_IT','F')!='T':count=1")
    s+='''
if mode.startswith('population_guard') and not (p/'bootstrap-seen').exists():
 with (p/'OUTGEN').open('a') as stream:
  stream.write('Error - bad initial population guesses.\\nPredicted changes are too large.\\nNew populations written to SCRTEMP file.\\nEdit POINT1 file to recover older populations.\\n')
 (p/'MOD_SUM').unlink()
 print('STOP',flush=True)
'''
    exe.write_text(s)
    authenticate(model)


def test_explicit_guard_checkpoint_is_only_provisional_until_full_verification(population_workspace):
    model,plan=population_workspace
    add_guard_stop(model)
    result=run_plan(plan('population_guard'))
    assert result['status']=='succeeded',result
    assert result['attempts'][0]['status']=='invalid_output'
    assert result['attempts'][0]['checkpoint_provisional']
    assert not result['attempts'][0]['checkpoint_restored']
    assert result['actions'][0]['policy_id']=='population_guard'
    assert result['attempts'][2]['recovery_verified']=='population_guard'
    assert result['attempts'][-1]['phase']=='verify'


def test_failed_provisional_guard_recovery_restores_pre_failure_checkpoint(population_workspace):
    model,plan=population_workspace
    add_guard_stop(model)
    old={n:(model/n).read_bytes() for n in ['POINT1','POINT2','SCRTEMP','VADAT','IN_ITS']}
    result=run_plan(plan('population_guard_fail'))
    assert result['status']=='needs_review',result
    assert result['provisional_recovery_rolled_back']=='population_guard'
    assert all((model/n).read_bytes()==v for n,v in old.items())


def test_guard_trial_never_leaves_provisional_state_on_insufficient_budget(population_workspace):
    model,plan=population_workspace
    add_guard_stop(model)
    old={n:(model/n).read_bytes() for n in ['POINT1','POINT2','SCRTEMP','VADAT','IN_ITS']}
    result=run_plan(plan('population_guard',max_iterations=4))
    assert result['status']=='limit_reached',result
    assert result['attempts'][0]['checkpoint_provisional_rolled_back']
    assert all((model/n).read_bytes()==v for n,v in old.items())


@pytest.mark.parametrize('scenario,expected', [('rays','succeeded'),('rays_bad','needs_review')])
def test_guarded_ray_recipe_and_failed_followup_rollback(auto_workspace,scenario,expected):
    model,plan=auto_workspace
    assert run_plan(plan())['status']=='succeeded'
    (model/'VADAT').write_text((model/'VADAT').read_text()+'F [DO_HYDRO]\n20000 [VFRAC_FG]\n20000 [VFRAC_MOM]\n')
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    s=exe.read_text().replace("if mode=='cancel':", """if mode.startswith('rays') and float(get('VADAT','VFRAC_FG','20000'))>0.1:
 (p/'OBSFLUX').write_text('Normalized luminosity check (normalized by L[ND])\\n-1 1\\n')
 (p/'OUTGEN').write_text('Model started on: now\\nSome normalized luminosities are out by a factor of 2\\n')
 print('Some normalized luminosities are out by a factor of 2\\nSTOP',flush=True)
 raise SystemExit(0)
if mode=='cancel':""")
    s+='''
if mode.startswith('rays'):
 low=0.4 if mode=='rays_bad' else 1
 (p/'OBSFLUX').write_text('Normalized luminosity check (normalized by L[ND])\\n'+str(low)+' 1\\n')
 (p/'MEANOPAC').write_text('Depth Tau(Ross)\\n'+''.join('a '+str(i)+' '+str(50*i)+' '+' '.join(['1']*12)+'\\n' for i in [1,2]))
'''
    exe.write_text(s)
    old={n:(model/n).read_bytes() for n in ['POINT1','POINT2','SCRTEMP','VADAT']}
    result=run_plan(plan(scenario))
    assert result['status']==expected,result
    assert result['actions'][0]['policy_id']=='ray_refinement'
    if expected=='succeeded':
        assert result['attempts'][1]['recovery_verified']=='ray_refinement'
        assert control_value(model,'VADAT','VFRAC_FG')=='0.1'
    else:
        assert result['provisional_recovery_rolled_back']=='ray_refinement'
        assert all((model/n).read_bytes()==v for n,v in old.items())


def test_nonautomatic_guard_advice_is_read_only(population_workspace):
    model,plan=population_workspace
    add_guard_stop(model)
    p=plan('population_guard');p.pop('kind');p.pop('auto')
    result=run_plan(p)
    assert result['status']=='invalid_output'
    finding=next(x for x in result['main_diagnostics']['findings'] if x['policy_id']=='population_guard')
    assert finding['automatic_eligible']
    assert finding['proposal']['retain_failed_checkpoint']
    assert control_value(model,'VADAT','MAX_LAM') is None
    assert control_value(model,'IN_ITS','DO_LAM_IT') is None


@pytest.mark.parametrize('value',[None,float('inf'),float('nan'),-1])
def test_incomplete_population_extrema_do_not_trigger_recovery(tmp_path,value):
    from cmfgen_viewer.auto_recovery import population_bootstrap
    evidence={'records':[{'ba_computed':True,'maximum_increase_percent':value}]*2}
    ctx=policies.Context(tmp_path,'success',{}, {}, {}, evidence, [],'iterate',[],'')
    assert population_bootstrap(ctx) is None
