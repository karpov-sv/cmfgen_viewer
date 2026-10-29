"""Patched POP is a bounded fresh-start remedy, not continuation reseeding."""
import io
import json
from pathlib import Path

import pytest

from test_runner_auto import auto_workspace
from test_main_recommendations import ordinary
from cmfgen_viewer.pop_initialization import POP_MARKER, _source_grid, supports_pop
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner_output import TerminalOutput
from cmfgen_viewer.runner_recipe import build_run_plan

SOURCE = '24-FEB-2004 !Format date\n1 1 1 2\n2 1 10 1 0 0 1\n1\n1 1 20 2 0 0 1\n1\n'

PREFIX = r'''
import json
method=get('VADAT','DC_METH','R')
with (p/'pop-trace.jsonl').open('a') as trace:
 trace.write(json.dumps({'method':method,'lin_int':get('VADAT','LIN_INT','unset'),
                        'pop_scale':get('VADAT','POP_SCALE','unset')})+'\n')
if mode=='pop_followup_bad' and (p/'POINT1').exists() and method!='POP':
 (p/'SCRTEMP').write_bytes(b'broken')
 print('Fortran runtime error: unknown continuation problem',flush=True)
 raise SystemExit(1)
if mode=='pop_cancel' and method=='POP':time.sleep(10)
if (mode.startswith('pop_') and not (p/'POINT1').exists() and method!='POP') or mode=='pop_always_bad':
 out='Model started on: now\nStarting a new model.\nCalling AUTO_ADD_ION\n'
 (p/'OUTGEN').write_text(out)
 print(out,flush=True)
 print('Fortran runtime error: population conversion failed\n#0 scale_pops_',flush=True)
 (p/'POINT1').write_text('incomplete')
 (p/'SCRTEMP').write_bytes(b'bad partial checkpoint')
 raise SystemExit(1)
if mode=='pop_invalid_source' and method=='POP':
 print('Population initialization: POP requires contiguous explicit ion stages',flush=True)
 raise SystemExit(1)
'''
SUFFIX = "\nif method=='POP' and mode!='pop_no_marker':\n with (p/'OUTGEN').open('a') as stream:stream.write(" + repr(POP_MARKER+'\n') + ")\n"


@pytest.fixture
def pop_workspace(auto_workspace):
    model, make = auto_workspace
    (model/'VADAT').write_text((model/'VADAT').read_text()+'R [DC_METH]\nT [LIN_INT]\nT [POP_SCALE]\n')
    (model/'MODEL_SPEC').write_text((model/'MODEL_SPEC').read_text()+'0,1,1 [He2_ISF]\n')
    (model/'He2_IN').write_text(SOURCE)
    exe=model.parent/'cmf/exe/cmfgen_dev.exe'
    exe.write_text(exe.read_text().replace("count=int(get('IN_ITS'",PREFIX+"\ncount=int(get('IN_ITS'")+SUFFIX)
    return model,make


def test_pop_trial_then_normal_continuation_and_independent_verification(pop_workspace):
    model, make = pop_workspace
    original=(model/'VADAT').read_bytes()
    result=run_plan(make('pop_good'))
    assert result['status']=='succeeded',result
    assert [a['policy_id'] for a in result['actions']]==['pop_initialization','verify_candidate','verified_convergence']
    assert [a['phase'] for a in result['attempts']]==['iterate','pop_initialization','pop_continuation','verify']
    trace=[json.loads(row) for row in (model/'pop-trace.jsonl').read_text().splitlines()]
    assert [r['method'] for r in trace]==['R','POP','R','R']
    assert all(r['lin_int']=='T' and r['pop_scale']=='T' for r in trace)
    assert result['attempts'][1]['pop_bootstrap_completed']
    assert result['attempts'][2]['pop_recovery_verified']
    # Independent verification restores the caller's starting BA reuse policy.
    assert (model/'VADAT').read_bytes()==original
    assert (model/'He2_IN').read_text()==SOURCE
    native=json.loads((Path(result['attempts'][1]['journal'])/'result.json').read_text())
    assert native['initialization']=={'method':'POP','temporary':True}
    assert 'POP' in (Path(native['journal'])/'effective/VADAT').read_text()


@pytest.mark.parametrize('scenario',['pop_no_marker','pop_followup_bad','pop_invalid_source'])
def test_failed_pop_procedure_restores_original_checkpoint_and_controls(pop_workspace,scenario):
    model, make=pop_workspace
    original=(model/'VADAT').read_bytes()
    result=run_plan(make(scenario))
    assert result['status']=='needs_review',result
    assert [a['policy_id'] for a in result['actions']]==['pop_initialization']
    assert (model/'VADAT').read_bytes()==original
    assert not (model/'POINT1').exists()
    assert not (model/'SCRTEMP').exists()
    if scenario=='pop_invalid_source':
        native=json.loads((Path(result['attempts'][-1]['journal'])/'result.json').read_text())
        assert any(f['code']=='population_initialization_validation' for p in native['passes'] for f in p['diagnostic_findings'])


@pytest.mark.parametrize('problem',['unsupported','missing','wrong_levels','different_grid','pop_scale_off','already_pop'])
def test_ineligible_pop_does_not_reseed_or_toggle_flags(pop_workspace,problem):
    model, make=pop_workspace
    if problem=='unsupported':
        exe=model.parent/'cmf/exe/cmfgen_dev.exe'
        exe.write_text(exe.read_text().replace(POP_MARKER,'unsupported marker'))
        assert not supports_pop(exe)
    elif problem=='missing':
        (model/'MODEL_SPEC').write_text((model/'MODEL_SPEC').read_text()+'0,1,1 [HI_ISF]\n')
    elif problem=='wrong_levels':
        (model/'MODEL_SPEC').write_text((model/'MODEL_SPEC').read_text().replace('0,1,1','0,1,2'))
    elif problem=='different_grid':
        (model/'MODEL_SPEC').write_text((model/'MODEL_SPEC').read_text()+'0,1,1 [HI_ISF]\n')
        (model/'HI_IN').write_text(SOURCE.replace('2 1 10 1','2 1 11 1'))
    elif problem=='pop_scale_off':
        (model/'VADAT').write_text((model/'VADAT').read_text().replace('T [POP_SCALE]','F [POP_SCALE]'))
    else:
        (model/'VADAT').write_text((model/'VADAT').read_text().replace('R [DC_METH]','POP [DC_METH]'))
    original=(model/'VADAT').read_bytes()
    result=run_plan(make('pop_always_bad'))
    assert result['status']=='needs_review',result
    assert not result['actions']
    assert len(result['attempts'])==1
    assert (model/'VADAT').read_bytes()==original
    assert not (model/'POINT1').exists()


def test_nonautomatic_run_recommends_pop_without_applying_it(pop_workspace):
    model, make=pop_workspace
    original=(model/'VADAT').read_bytes()
    result=run_plan(ordinary(make('pop_good')))
    finding=next(f for f in result['main_diagnostics']['findings'] if f['policy_id']=='pop_initialization')
    assert finding['automatic_eligible']
    assert finding['proposal']['steps'][0]['native_options']=={'pop_initialization':True}
    assert (model/'VADAT').read_bytes()==original
    assert (model/'attempts.txt').read_text()=='1'
    stream=io.StringIO();TerminalOutput(stream).result(result)
    assert 'DC_METH=POP' in stream.getvalue()
    assert not any(f['policy_id']=='lte_initialization' for f in result['main_diagnostics']['findings'])
    from cmfgen_viewer.app import create_app
    app=create_app(basepath=str(model.parent),read_write_enabled=True,secret_key='test')
    with app.test_client() as client:
        page=client.get('/model-actions/main-computation/model')
        assert page.status_code==200
        assert b'DC_METH=POP' in page.data
        assert b'Auto remedy available' in page.data


@pytest.mark.parametrize('fmt,coefficient',[('18-Nov-2010','-2'),('10-Dec-2010','-2'),('24-FEB-2004','1.0-100')])
def test_source_reader_accepts_native_coefficient_formats(tmp_path,fmt,coefficient):
    path=tmp_path/'He2_IN'
    path.write_text(SOURCE.replace('24-FEB-2004',fmt).replace('\n1\n','\n'+coefficient+'\n'))
    assert _source_grid(path,1)==[[2,10,1,1],[1,20,2,1]]


def test_pop_does_not_replace_existing_continuation(pop_workspace):
    model, make=pop_workspace
    healthy=run_plan(ordinary(make('good')))
    assert healthy['status']=='succeeded'
    saved={n:(model/n).read_bytes() for n in ('POINT1','POINT2','SCRTEMP','VADAT')}
    result=run_plan(make('pop_always_bad'))
    assert result['status']=='needs_review'
    assert not result['actions']
    for name, content in saved.items():
        assert (model/name).read_bytes()==content
    assert 'fresh startup' in result['reason']


def test_explicit_fresh_pop_failure_restores_preexisting_checkpoint(pop_workspace):
    model, make=pop_workspace
    assert run_plan(ordinary(make('good')))['status']=='succeeded'
    saved={n:(model/n).read_bytes() for n in ('POINT1','POINT2','SCRTEMP','VADAT')}
    result=run_plan(make('pop_followup_bad',fresh_start=True))
    assert result['status']=='needs_review',result
    assert result['actions'][0]['policy_id']=='pop_initialization'
    for name, content in saved.items():
        assert (model/name).read_bytes()==content


def test_pop_procedure_must_fit_remaining_budget(pop_workspace):
    model, make=pop_workspace
    result=run_plan(make('pop_good',max_iterations=6))
    assert result['status']=='limit_reached'
    assert 'complete the selected recovery' in result['reason']
    assert not result['actions']
    assert (model/'attempts.txt').read_text()=='1'


def test_pop_timeout_restores_controls_and_checkpoint(pop_workspace):
    model, make=pop_workspace
    original=(model/'VADAT').read_bytes()
    result=run_plan(make('pop_cancel',timeout=3))
    assert result['status']=='timeout',result
    assert result['actions'][0]['policy_id']=='pop_initialization'
    assert (model/'VADAT').read_bytes()==original
    assert not (model/'POINT1').exists()
    assert not (model/'SCRTEMP').exists()


def test_pop_validation_cannot_accept_generated_or_changed_source_files(pop_workspace):
    from cmfgen_viewer.pop_initialization import pop_source_evidence
    model, make=pop_workspace
    plan=ordinary(make('pop_good'))
    (model/'He2_IN').write_text(SOURCE+'\n')
    with pytest.raises(ValueError,match='unchanged original input'):
        pop_source_evidence(model,plan)
    (model/'He2_IN').write_text(SOURCE)
    plan=ordinary(make('pop_good'))
    plan['inputs']=[p for p in plan['inputs'] if Path(p['path']).name!='He2_IN']
    with pytest.raises(ValueError,match='unchanged original input'):
        pop_source_evidence(model,plan)


def test_pop_temporary_plan_refuses_continuation_and_conflicting_methods(pop_workspace):
    model, make=pop_workspace
    plan=ordinary(make('good'))
    kwargs=dict(stage='main',cmfgen_root=model.parent/'cmf',atomic_root=model.parent/'atomic',iterations=2)
    pop_plan=build_run_plan(model,pop_initialization=True,**kwargs)
    assert pop_plan['ready'],pop_plan['errors']
    stream=io.StringIO();TerminalOutput(stream).plan(pop_plan)
    assert 'DC_METH=POP' in stream.getvalue()
    assert run_plan(plan)['status']=='succeeded'
    assert not build_run_plan(model,pop_initialization=True,**kwargs)['ready']
    with pytest.raises(ValueError,match='only one temporary'):
        build_run_plan(model,pop_initialization=True,lte_initialization=True,**kwargs)


def test_pop_accepts_different_source_and_target_depth_counts(pop_workspace):
    from cmfgen_viewer.pop_initialization import pop_source_evidence
    model, make=pop_workspace
    (model/'MODEL_SPEC').write_text((model/'MODEL_SPEC').read_text().replace('2 [ND]','4 [ND]').replace('3 [NP]','5 [NP]'))
    evidence=pop_source_evidence(model,ordinary(make('pop_good')))
    assert evidence['source_depths']==2
    assert evidence['source_atoms']==['He2_IN']


def test_no_stage_summary_shows_pop_remedy_even_when_next_preflight_is_blocked(pop_workspace,monkeypatch,capsys):
    from cmfgen_viewer import runner
    from cmfgen_viewer.runner_recipe import snapshot
    model, make=pop_workspace
    assert run_plan(ordinary(make('pop_good')))['status']=='failed'
    before={p.relative_to(model):snapshot(p) for p in model.rglob('*')}
    monkeypatch.setattr(runner,'run_plan',lambda *a,**kw: pytest.fail('inspection must not launch a run'))
    assert runner.main([str(model),'--cmfgen-root',str(model.parent/'cmf'),
        '--atomic-root',str(model.parent/'atomic')])==2
    text=capsys.readouterr().out
    assert 'Latest end-of-run check:' in text
    assert 'Recovery step: pop_initialization' in text
    assert 'DC_METH=POP' in text
    assert {p.relative_to(model):snapshot(p) for p in model.rglob('*')}==before
