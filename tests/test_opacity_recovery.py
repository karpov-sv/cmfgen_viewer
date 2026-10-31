"""Specific native opacity evidence can select a limiter, never opaque crashes."""
from pathlib import Path

import pytest

from test_runner_auto import auto_workspace
from test_auto_recovery import population_workspace
from cmfgen_viewer.native_diagnostics import analyze_main_diagnostics
from cmfgen_viewer.opacity_recovery import SOURCE_FLOOR_MARKER, source_floor_measurements
from cmfgen_viewer.auto_policies import Context, choose
from cmfgen_viewer.auto_diagnostics import control_value
from cmfgen_viewer.runner import run_plan

REPORT = SOURCE_FLOOR_MARKER + '''
ITERATION= 1 DEPTH= 75 FREQUENCY= 4.15375D-1
CHI= -0.05 CHI_CONT= -0.1 CHI_NOSCAT= -0.2
ETA= 0.5 ETA_CONT= 0.2 CHI_SCAT= 0.01
Review NEG_OPAC_OPT=ESEC_CHK; no populations updated by this solve
'''


def test_explicit_diagnostic_is_reported_even_if_completion_is_present(tmp_path):
    for completed in (False, True):
        f=analyze_main_diagnostics(tmp_path,{'OUTGEN':REPORT},completed=completed)
        assert len(f)==1 and f[0]['code']=='source_opacity_floor' and f[0]['severity']=='error'
        assert f[0]['measurements']['DEPTH']==75
    f=analyze_main_diagnostics(tmp_path,{'OUTGEN':SOURCE_FLOOR_MARKER,'process':REPORT})
    assert f[0]['measurements']['DEPTH']==75 and f[0]['path']=='process'
    assert source_floor_measurements(REPORT)['FREQUENCY']==.415375
    assert not analyze_main_diagnostics(tmp_path,{'OUTGEN':'Model started on: old\n'+REPORT+'Model started on: new\n'})


@pytest.mark.parametrize('bad',[
    REPORT.replace('CHI_SCAT= 0.01','CHI_SCAT= NaN'),
    REPORT.replace('CHI_SCAT= 0.01','CHI_SCAT= 0'),
    REPORT.replace('CHI_SCAT= 0.01','CHI_SCAT= 5e-324'),
    REPORT.replace('DEPTH= 75','DEPTH= 91'),
    REPORT.replace('CHI_NOSCAT= -0.2','CHI_NOSCAT= 0.2'),
    REPORT.replace('ETA_CONT= 0.2','ETA_CONT= 0'),
    REPORT.replace('ETA= 0.5','ETA= -0.5'),
    REPORT.replace('CHI= -0.05','CHI= 0.05'),
    REPORT.replace('ETA= 0.5',''),
    REPORT.replace('DEPTH= 75','DEPTH= 1.5'),
    REPORT.replace('CHI_SCAT= 0.01','CHI_SCAT= 0.01 CHI_SCAT= 0.02'),
])
def test_unproven_floor_is_not_automatically_repaired(tmp_path,bad):
    (tmp_path/'VADAT').write_text('SRCE_CHK [NEG_OPAC_OPT]\n')
    (tmp_path/'MODEL_SPEC').write_text('90 [ND]\n')
    findings=analyze_main_diagnostics(tmp_path,{'OUTGEN':bad})
    ctx=Context(tmp_path,'failure',{}, {'passes':[{'diagnostic_findings':findings}]},{},{},[], 'iterate',[],bad)
    decision,trail=choose(ctx)
    assert decision.kind=='stop' and any(t.get('policy_id')=='source_opacity' and t['outcome']=='ineligible' for t in trail)


@pytest.fixture
def opacity_workspace(auto_workspace):
    model,make=auto_workspace
    (model/'VADAT').write_text((model/'VADAT').read_text()+'SRCE_CHK [NEG_OPAC_OPT]\n')
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    # Two-depth executable fixture: use a valid local depth, and fail before
    # any checkpoint write. The real runner must restore and select a remedy.
    report=REPORT.replace('DEPTH= 75','DEPTH= 2')
    injection="""
if mode.startswith('opacity') and (get('VADAT','NEG_OPAC_OPT','')=='SRCE_CHK' or mode=='opacity_repeat'):
 out='Model started on: now\\nStarting a new model.\\nCurrent great iteration count is 1\\n'+%r
 if mode=='opacity_generic':out='Model started on: now\\nSIGILL: opaque failure\\n'
 if mode=='opacity_mixed':out+='The value of DTDR is : NaN\\n'
 (p/'OUTGEN').write_text(out)
 print(out,flush=True)
 raise SystemExit(1)
""" % report
    exe.write_text(exe.read_text().replace("count=int(get('IN_ITS'",injection+"\ncount=int(get('IN_ITS'"))
    return model,make


def test_remedy_restarts_without_reseeding_and_requires_independent_verification(opacity_workspace):
    model,make=opacity_workspace
    (model/'EDDFACTOR').write_bytes(b'old radiation')
    result=run_plan(make('opacity'))
    assert result['status']=='succeeded',result
    assert result['attempts'][0]['status']=='failed'
    action=result['actions'][0]
    assert action['policy_id']=='source_opacity' and action['changes']['VADAT']['NEG_OPAC_OPT']=='ESEC_CHK'
    assert 'EDDFACTOR' in result['attempts'][0]['decision']['caches']
    assert not (model/'EDDFACTOR').exists()
    assert result['attempts'][-1]['phase']=='verify'
    assert result['attempts'][-1]['evidence']['fresh_verified']
    assert control_value(model,'VADAT','NEG_OPAC_OPT')=='ESEC_CHK'
    assert not any(a.get('policy_id') in {'lte_initialization','pop_initialization'} for a in result['actions'])


@pytest.mark.parametrize('scenario',['opacity_generic','opacity_mixed'])
def test_opaque_or_nonfinite_crash_is_not_a_limiter_remedy(opacity_workspace,scenario):
    model,make=opacity_workspace
    result=run_plan(make(scenario))
    assert result['status']=='needs_review',result
    assert not result['actions']
    assert control_value(model,'VADAT','NEG_OPAC_OPT')=='SRCE_CHK'


def test_diagnosed_failure_after_option_changed_stops_instead_of_looping(opacity_workspace):
    model,make=opacity_workspace
    result=run_plan(make('opacity_repeat'))
    assert result['status']=='needs_review',result
    assert len(result['attempts'])==2 and len(result['actions'])==1
    assert result['actions'][0]['policy_id']=='source_opacity'


def test_continuation_recovery_keeps_the_accepted_checkpoint(opacity_workspace):
    import json
    model,make=opacity_workspace
    initial=run_plan(make('good'))
    assert initial['status']=='succeeded'
    checkpoint=initial['final_checkpoint']
    result=run_plan(make('opacity'))
    assert result['status']=='succeeded',result
    retry=json.loads((Path(result['attempts'][1]['journal'])/'plan.json').read_text())
    assert retry['restart']['mode']=='continuation'
    assert retry['restart']['pointer']['iterations']==checkpoint
    assert result['final_checkpoint']>checkpoint
    assert not retry.get('initialization')


@pytest.fixture
def opacity_seed_workspace(population_workspace):
    from test_auto_recovery import authenticate
    model,make=population_workspace
    p=model/'VADAT'
    p.write_text(p.read_text()+'SRCE_CHK [NEG_OPAC_OPT]\nPOP [DC_METH]\nT [LIN_INT]\nT [IT_ON_T]\n')
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    report=REPORT.replace('DEPTH= 75','DEPTH= 2')
    prefix="""
seed=get('IN_ITS','NUM_ITS','2')=='0'
if mode=='population_opacity_seed' and not (p/'bootstrap-seen').exists() and not seed:
 out='Model started on: now\\nStarting a new model.\\n'+%r+'\\nCurrent great iteration count is 1\\n'
 if get('VADAT','NEG_OPAC_OPT','')=='SRCE_CHK':
  out+=%r
  status=1
 else:
  out+='Some normalized luminosities are out by a factor of 2\\n'
  (p/'OBSFLUX').write_text('Normalized luminosity check (normalized by L[ND])\\n-1 1\\n')
  (p/'MEANOPAC').write_text('R I Tau(Ross)\\n2 1 1 '+('0 '*12)+'\\n1 2 80 '+('0 '*12)+'\\n')
  status=0
 (p/'OUTGEN').write_text(out)
 print(out,flush=True)
 raise SystemExit(status)
if seed:
 assert get('VADAT','DC_METH','')=='LTE'
 assert get('VADAT','LIN_INT','')=='F'
 assert get('VADAT','IT_ON_T','')=='F'
 (p/'bootstrap-seen').touch()
""" % (__import__('cmfgen_viewer.pop_initialization',fromlist=['POP_MARKER']).POP_MARKER,report)
    code=exe.read_text().replace("count=int(get('IN_ITS'",prefix+"\ncount=int(get('IN_ITS'")
    code=code.replace("count=int(get('IN_ITS','NUM_ITS','2'))", "count=1 if seed else int(get('IN_ITS','NUM_ITS','2'))")
    code=code.replace("range(start,start+count)","range(start,start+(0 if seed else count))")
    code=code.replace("out='Model started on: now\\n'", "out='Model started on: now\\n'+('Starting a new model.\\nLTE assumed for departure coefficients.\\nLTE charge consistency: iterations=1 residual=0\\n' if seed else '')")
    exe.write_text(code);authenticate(model)
    manifest=model.parent/'cmf/cmfgen-local-build.json'
    import json
    data=json.loads(manifest.read_text());data['capabilities'].append('lte-charge-v1');manifest.write_text(json.dumps(data))
    return model,make


def test_opacity_fresh_seed_initializes_without_counting_a_solve_then_continues(opacity_seed_workspace):
    model,make=opacity_seed_workspace
    events=[]
    result=run_plan(make('population_opacity_seed',fresh_start=True),events.append)
    assert result['status']=='succeeded',result
    assert [a['policy_id'] for a in result['actions'][:2]]==['source_opacity','opacity_lte_seed']
    seed=next(a for a in result['attempts'] if a.get('initialization_only'))
    assert seed['status']=='tested' and seed['charged_iterations']==0
    assert seed['evidence']['initialized_only'] and not seed['evidence']['candidate']
    assert seed['evidence']['records']==[] and seed['evidence']['checkpoint']==1
    assert any(e['event']=='auto_initialized' for e in events)
    assert not any(e['event']=='auto_assessment' and e['attempt']==seed['attempt'] for e in events)
    assert result['attempts'][-1]['phase']=='verify'
    for key,value in [('LIN_INT','T'),('IT_ON_T','T'),('DC_METH','POP')]:
        assert control_value(model,'VADAT',key)==value
    assert control_value(model,'VADAT','T_EXC') is None


def test_clean_stop_after_initialization_restores_provisional_seed(opacity_seed_workspace):
    model,make=opacity_seed_workspace
    original=(model/'POINT1').read_bytes()
    stop=False
    def event(e):
        nonlocal stop
        if e['event']=='auto_initialized':stop=True
    result=run_plan(make('population_opacity_seed',fresh_start=True),event,stop_requested=lambda:stop)
    assert result['status']=='stopped',result
    assert 'numerical_convergence' not in result
    assert len(result['attempts'])==3 and result['attempts'][-1]['charged_iterations']==0
    assert result['attempts'][-1]['evidence']['checkpoint']==1
    assert not result['attempts'][-1]['evidence']['fresh_verified']
    assert result['provisional_recovery_rolled_back']=='opacity_lte_seed'
    assert (model/'POINT1').read_bytes()==original


def test_cancelled_seed_recipe_preserves_pre_seed_checkpoint_and_controls(opacity_seed_workspace):
    model,make=opacity_seed_workspace
    checkpoint=(model/'POINT1').read_bytes()
    def event(e):
        if e['event']=='auto_attempt' and e.get('initialization_only'):raise KeyboardInterrupt()
    result=run_plan(make('population_opacity_seed',fresh_start=True),event)
    assert result['status']=='cancelled',result
    assert result['provisional_recovery_rolled_back']=='opacity_lte_seed'
    assert (model/'POINT1').read_bytes()==checkpoint
    assert control_value(model,'VADAT','LIN_INT')=='T'
    assert control_value(model,'VADAT','DC_METH')=='POP'


@pytest.mark.parametrize('extra',['T [SN_MODEL]\n','T [REVISE_R_GRID]\n',
                                  'T [FLUX_CAL_ONLY]\n','T [USE_FIXED_J]\n',
                                  'F [T_ON_R]\n','T [LTE_EST]\n'])
def test_opacity_seed_declines_unvalidated_initialization_modes(extra):
    from cmfgen_viewer.model_initialization import opacity_lte_seed_controls
    with pytest.raises(ValueError):
        opacity_lte_seed_controls('POP [DC_METH]\nT [LIN_INT]\n'+extra)


def test_opacity_seed_mode_does_not_relax_the_public_lte_flag(opacity_seed_workspace):
    from cmfgen_viewer.runner_recipe import RunnerError,build_run_plan
    model,make=opacity_seed_workspace
    root=model.parent/'cmf';atomic=model.parent/'atomic'
    normal=build_run_plan(model,stage='test',cmfgen_root=root,atomic_root=atomic,
                          lte_initialization=True,fresh_start=True)
    assert not normal['ready'] and any('LIN_INT' in e for e in normal['errors'])
    with pytest.raises(RunnerError,match='zero-iteration'):
        build_run_plan(model,stage='main',cmfgen_root=root,atomic_root=atomic,opacity_lte_seed=True)
    continued=build_run_plan(model,stage='test',cmfgen_root=root,atomic_root=atomic,opacity_lte_seed=True)
    assert not continued['ready'] and any('fresh startup' in e for e in continued['errors'])


def test_lte_seed_is_not_selected_for_a_crash_with_a_guard_message(opacity_seed_workspace):
    from test_auto_recovery import authenticate
    model,make=opacity_seed_workspace
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    exe.write_text(exe.read_text().replace(' status=0\n',' status=1\n'))
    authenticate(model)
    result=run_plan(make('population_opacity_seed',fresh_start=True))
    assert result['status']=='needs_review',result
    assert [a['policy_id'] for a in result['actions']]==['source_opacity']
    assert not any(a.get('initialization_only') for a in result['attempts'])


@pytest.fixture
def structure_seed_workspace(opacity_seed_workspace):
    import shutil
    model,make=opacity_seed_workspace
    extra='1.5 [TEFF]\n2.05 [LOGG]\n84000 [LSTAR]\n6e-7 [MDOT]\n'
    (model/'VADAT').write_text((model/'VADAT').read_text()+extra)
    lte=model/'lte';lte.mkdir()
    (lte/'VADAT').write_bytes((model/'VADAT').read_bytes())
    grid='! Effective temperature (10^4 K) is: 1.5\n2 !Number of depth points\n2 20 0 .1 1\n1 10 0 100 2\n'
    (model/'RVSIG_COL').write_text(grid)
    (lte/'RVSIG_COL_NEW').write_text(grid)
    (lte/'FIN_CAL_GRID').write_text('Index R TAU V T Na Ne/Na Xross Xr/Xes Gam\n'
        '1 2 .1 20 1 1e10 1 1 1 .2\n2 1 100 10 2 2e10 1 1 1 .2\n')
    return model,make


def test_matching_lte_structure_is_preferred_and_temporary_file_is_restored(structure_seed_workspace):
    import json
    model,make=structure_seed_workspace
    original=b'Unrelated original input; preserve exactly\n'
    (model/'FIN_CAL_GRID').write_bytes(original)
    result=run_plan(make('population_opacity_seed',fresh_start=True))
    assert result['status']=='succeeded',result
    seed=next(a for a in result['attempts'] if a.get('initialization_only'))
    native=json.loads((Path(seed['journal'])/'result.json').read_text())
    assert native['initialization']['structure_seed']['depths']==2
    assert native['initialization']['structure_seed']['temperatures']==[1,2]
    assert (Path(seed['journal'])/'effective/FIN_CAL_GRID').read_bytes()==(model/'lte/FIN_CAL_GRID').read_bytes()
    assert (model/'FIN_CAL_GRID').read_bytes()==original
    assert control_value(model,'VADAT','LTE_EST') is None


@pytest.mark.parametrize('change',['grid','depths','physical','stale','nonfinite',
                                   'electron_underflow','linked_hydro_controls','extra_lte_abundance'])
def test_incompatible_lte_structure_is_declined(structure_seed_workspace,change):
    import os
    from cmfgen_viewer.lte_structure_seed import lte_structure_source
    model,_=structure_seed_workspace
    file=model/'lte/FIN_CAL_GRID'
    if change=='grid':file.write_text(file.read_text().replace('1 2 .1','1 3 .1'))
    elif change=='depths':file.write_text('\n'.join(file.read_text().splitlines()[:-1])+'\n')
    elif change=='physical':
        (model/'lte/VADAT').write_text((model/'lte/VADAT').read_text().replace('84000','85000'))
        os.utime(model/'lte/VADAT',ns=(1,1))
    elif change=='stale':os.utime(file,ns=(1,1))
    elif change=='electron_underflow':
        file.write_text(file.read_text().replace('1e10 1','1e-300 1e-300'))
    elif change=='extra_lte_abundance':
        (model/'lte/VADAT').write_text((model/'lte/VADAT').read_text()+'0.1 [He/X]\n')
        os.utime(model/'lte/VADAT',ns=(1,1))
    elif change=='linked_hydro_controls':
        (model/'lte/HYDRO_PARAMS').symlink_to(model/'VADAT')
    else:file.write_text(file.read_text().replace('1e10','NaN'))
    with pytest.raises(ValueError):lte_structure_source(model)


def test_temporary_seed_file_preserves_external_edits(tmp_path):
    from cmfgen_viewer.runner_controls import TemporaryInput
    path=tmp_path/'FIN_CAL_GRID';path.write_bytes(b'original')
    def write(p,data,mode):p.write_bytes(data)
    temp=TemporaryInput(path,write);temp.install(b'reviewed seed')
    path.write_bytes(b'external edit')
    assert temp.restore() and path.read_bytes()==b'external edit'


def test_temporary_seed_file_recovers_a_partial_writer_failure(tmp_path):
    from cmfgen_viewer.runner_controls import TemporaryInput
    path=tmp_path/'FIN_CAL_GRID';path.write_bytes(b'original')
    failed=False
    def write(p,data,mode):
        nonlocal failed
        p.write_bytes(data)
        if not failed:failed=True;raise OSError('after replace')
    temp=TemporaryInput(path,write)
    with pytest.raises(OSError):temp.install(b'reviewed seed')
    assert temp.restore()==[] and path.read_bytes()==b'original'


@pytest.mark.parametrize('phase', ['lambda', 'full'])
def test_seed_recovery_rolls_back_element_loss_in_later_steps(opacity_seed_workspace, phase):
    import json
    from test_auto_recovery import authenticate

    model, make = opacity_seed_workspace
    original = {name: (model/name).read_bytes() for name in ['POINT1', 'POINT2', 'SCRTEMP']}
    exe = model.parent/'cmf/exe/cmfgen_dev.exe'
    condition = 'lam' if phase == 'lambda' else "not lam and (p/'lambda-seen').exists()"
    injection = f"""
if lam and not seed:(p/'lambda-seen').touch()
if not seed and ({condition}):
 v=pack([2e7,1e10,1e10,1., 2e7,2e10,2e10,2.])
"""
    exe.write_text(exe.read_text().replace("(p/'SCRTEMP').write_bytes(g+g+", injection+"\n(p/'SCRTEMP').write_bytes(g+g+"))
    authenticate(model)
    manifest = model.parent/'cmf/cmfgen-local-build.json'
    record = json.loads(manifest.read_text())
    record['capabilities'].append('lte-charge-v1')
    manifest.write_text(json.dumps(record))
    result = run_plan(make('population_opacity_seed', fresh_start=True))
    assert result['status'] == 'needs_review', result
    assert result['provisional_recovery_rolled_back'] == 'opacity_lte_seed'
    assert all((model/name).read_bytes() == data for name, data in original.items())
    assert control_value(model, 'VADAT', 'DC_METH') == 'POP'
    assert control_value(model, 'VADAT', 'FIX_T') == 'F'
    assert control_value(model, 'VADAT', 'MAX_LAM') is None
    assert control_value(model, 'IN_ITS', 'DO_LAM_IT') is None


@pytest.fixture
def lte_thermal_workspace(structure_seed_workspace):
    import json
    from test_auto_recovery import authenticate
    from cmfgen_viewer.pop_initialization import POP_MARKER

    model, make = structure_seed_workspace
    p = model/'VADAT'
    p.write_text(p.read_text().replace('POP [DC_METH]', 'LTE [DC_METH]')
                 .replace('T [LIN_INT]', 'F [LIN_INT]')+'1 [T_EXC]\n')
    exe = model.parent/'cmf/exe/cmfgen_dev.exe'
    code = exe.read_text().replace(repr(POP_MARKER), repr(
        'LTE assumed for departure coefficients.\nLTE charge consistency: iterations=1 residual=0'))
    code = code.replace("if get('VADAT','NEG_OPAC_OPT','')=='SRCE_CHK':", 'if False:')
    exe.write_text(code)
    authenticate(model)
    manifest = model.parent/'cmf/cmfgen-local-build.json'
    data = json.loads(manifest.read_text())
    data['capabilities'].append('lte-charge-v1')
    manifest.write_text(json.dumps(data))
    return model, make


@pytest.mark.parametrize('already_reads_profile', [False, True])
def test_fresh_lte_guard_uses_matching_thermal_seed_and_existing_bootstrap(lte_thermal_workspace, already_reads_profile):
    model, make = lte_thermal_workspace
    if already_reads_profile:
        p = model/'VADAT'
        p.write_text(p.read_text()+'T [LTE_EST]\n')
        (model/'FIN_CAL_GRID').write_bytes((model/'lte/FIN_CAL_GRID').read_bytes())
    original = (model/'VADAT').read_text()
    result = run_plan(make('population_opacity_seed', fresh_start=True))
    assert result['status'] == 'succeeded', result
    assert result['actions'][0]['policy_id'] == 'opacity_lte_seed'
    assert result['actions'][0]['evidence']['initialization_method'] == 'LTE'
    assert not any(a['policy_id'] == 'source_opacity' for a in result['actions'])
    assert [a['phase'] for a in result['attempts'][:4]] == [
        'iterate', 'opacity_lte_seed', 'opacity_population_lambda', 'opacity_population_full']
    assert result['attempts'][1]['charged_iterations'] == 0
    assert result['attempts'][2]['checkpoint_physics']['element_density_max_relative_change'] == 0
    assert result['attempts'][3]['recovery_verified'] == 'opacity_lte_seed'
    for key in ['DC_METH', 'LIN_INT', 'IT_ON_T', 'T_EXC', 'NEG_OPAC_OPT']:
        from cmfgen_viewer.control_files import control_occurrences
        assert control_value(model, 'VADAT', key) == control_occurrences(original)[key][0]['value']
    if already_reads_profile:
        assert control_value(model, 'VADAT', 'LTE_EST') == 'T'
        assert (model/'FIN_CAL_GRID').read_bytes() == (model/'lte/FIN_CAL_GRID').read_bytes()
    else:
        assert control_value(model, 'VADAT', 'LTE_EST') is None
        assert not (model/'FIN_CAL_GRID').exists()


@pytest.mark.parametrize('change', ['no_structure', 'no_lte_marker', 'no_charge_marker',
                                    'already_using_profile', 'interpolated_lte', 'continuation'])
def test_fresh_lte_thermal_recovery_refuses_unproven_or_repeated_seed(lte_thermal_workspace, change):
    import json
    from test_auto_recovery import authenticate

    model, make = lte_thermal_workspace
    exe = model.parent/'cmf/exe/cmfgen_dev.exe'
    if change == 'no_structure':
        (model/'lte/FIN_CAL_GRID').unlink()
        (model/'lte/RVSIG_COL_NEW').unlink()
    elif change in {'no_lte_marker', 'no_charge_marker'}:
        text = 'LTE assumed for departure coefficients.' if change == 'no_lte_marker' else 'LTE charge consistency:'
        exe.write_text(exe.read_text().replace(text, 'Unconfirmed initialization:'))
        authenticate(model)
        manifest = model.parent/'cmf/cmfgen-local-build.json'
        data = json.loads(manifest.read_text())
        data['capabilities'].append('lte-charge-v1')
        manifest.write_text(json.dumps(data))
    elif change == 'already_using_profile':
        p = model/'VADAT'
        p.write_text(p.read_text().replace('T [IT_ON_T]', 'F [IT_ON_T]')+'T [LTE_EST]\n')
        (model/'FIN_CAL_GRID').write_bytes((model/'lte/FIN_CAL_GRID').read_bytes())
    elif change == 'interpolated_lte':
        p = model/'VADAT'
        p.write_text(p.read_text().replace('F [LIN_INT]', 'T [LIN_INT]'))
    result = run_plan(make('population_opacity_seed', fresh_start=change != 'continuation'))
    assert result['status'] == 'needs_review', result
    assert not any(a['policy_id'] == 'opacity_lte_seed' for a in result['actions'])
    if change != 'continuation':
        assert not result['actions']
    assert not any(a.get('initialization_only') for a in result['attempts'])


def test_interrupted_lte_thermal_recovery_restores_original_lte_controls(lte_thermal_workspace):
    model, make = lte_thermal_workspace
    original = {name: (model/name).read_bytes() for name in ['VADAT', 'POINT1', 'POINT2', 'SCRTEMP']}
    stop = False
    def event(item):
        nonlocal stop
        if item['event'] == 'auto_initialized':
            stop = True
    result = run_plan(make('population_opacity_seed', fresh_start=True), event,
                      stop_requested=lambda: stop)
    assert result['status'] == 'stopped', result
    assert result['provisional_recovery_rolled_back'] == 'opacity_lte_seed'
    for name in ['POINT1', 'POINT2', 'SCRTEMP']:
        assert (model/name).read_bytes() == original[name]
    for key, value in [('DC_METH', 'LTE'), ('LIN_INT', 'F'), ('IT_ON_T', 'T'), ('T_EXC', '1')]:
        assert control_value(model, 'VADAT', key) == value
    assert control_value(model, 'VADAT', 'LTE_EST') is None
    assert not (model/'FIN_CAL_GRID').exists()


def test_lte_thermal_recipe_can_apply_typed_opacity_fix_without_reseeding(lte_thermal_workspace):
    import json
    from test_auto_recovery import authenticate

    model, make = lte_thermal_workspace
    exe = model.parent/'cmf/exe/cmfgen_dev.exe'
    report = REPORT.replace('DEPTH= 75', 'DEPTH= 2').replace('ITERATION= 1', 'ITERATION= 2')
    guard = """
if get('IN_ITS','DO_LAM_IT','F')=='T' and get('VADAT','NEG_OPAC_OPT','')=='SRCE_CHK':
 out='Model started on: now\\n'+%r
 (p/'OUTGEN').write_text(out)
 print(out,flush=True)
 raise SystemExit(1)
""" % report
    code = exe.read_text().replace("seed=get('IN_ITS','NUM_ITS','2')=='0'",
                                    "seed=get('IN_ITS','NUM_ITS','2')=='0'\n"+guard)
    exe.write_text(code)
    authenticate(model)
    manifest = model.parent/'cmf/cmfgen-local-build.json'
    data = json.loads(manifest.read_text())
    data['capabilities'].append('lte-charge-v1')
    manifest.write_text(json.dumps(data))
    result = run_plan(make('population_opacity_seed', fresh_start=True))
    assert result['status'] == 'succeeded', result
    assert [a['policy_id'] for a in result['actions'][:2]] == ['opacity_lte_seed', 'source_opacity']
    assert sum(bool(a.get('initialization_only')) for a in result['attempts']) == 1
    failed = next(a for a in result['attempts'] if a.get('decision', {}).get('policy_id') == 'source_opacity')
    assert failed['restored_state'] == 'recovery_step'
    assert failed['phase'] == 'opacity_population_lambda'
    assert control_value(model, 'VADAT', 'DC_METH') == 'LTE'
    assert control_value(model, 'VADAT', 'NEG_OPAC_OPT') == 'ESEC_CHK'
