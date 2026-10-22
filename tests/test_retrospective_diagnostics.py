"""Legacy model checks never invent invocation provenance or execute recovery."""
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import shutil

import pytest

from test_runner_auto import auto_workspace
from test_main_recommendations import ordinary
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner_recipe import snapshot
from cmfgen_viewer.retrospective_diagnostics import inspect_main_recommendations


@pytest.fixture
def legacy_model(auto_workspace):
    model, make=auto_workspace
    def create(scenario='good'):
        result=run_plan(ordinary(make(scenario)))
        assert result['status']=='succeeded'
        shutil.rmtree(model/'.cmfgen-runs')
        started=(datetime.now()-timedelta(minutes=1)).strftime('%d-%b-%Y %H:%M:%S')
        (model/'OUTGEN').write_text((model/'OUTGEN').read_text().replace('Model started on: now','Model started on: '+started))
        return model
    return create


def test_legacy_candidate_is_screened_not_certified_and_writes_nothing(legacy_model):
    model=legacy_model()
    before={p.relative_to(model):snapshot(p) for p in model.rglob('*')}
    report=inspect_main_recommendations(model)
    assert report['mode']=='retrospective'
    assert report['evidence_status']=='historical_screened', report
    candidate=next(f for f in report['findings'] if f['policy_id']=='verify_candidate')
    assert not candidate['automatic_eligible']
    assert candidate['proposal']['changes']['VADAT']['N_FIX_BA']=='0'
    assert not any(f['policy_id']=='verified_convergence' for f in report['findings'])
    assert {p.relative_to(model):snapshot(p) for p in model.rglob('*')}==before
    assert not (model/'.cmfgen-runs').exists()


def test_legacy_raw_vectors_are_not_treated_as_invocation_aligned(legacy_model):
    model=legacy_model('oscillate')
    report=inspect_main_recommendations(model)
    assert not any(f['policy_id']=='local_relaxation' for f in report['findings'])
    assert any('STEQ_VALS' in text for text in report['limitations'])
    assert any(f['policy_id']=='quality_solver_maximum_change' for f in report['findings'])


@pytest.mark.parametrize('change',['missing_date','stale_counts','bad_checkpoint','edited_controls'])
def test_legacy_untrusted_evidence_cannot_select_numerical_policy(legacy_model,change):
    model=legacy_model()
    if change=='missing_date':
        text=(model/'OUTGEN').read_text().splitlines(keepends=True)
        (model/'OUTGEN').write_text('Model started on: unknown\n'+''.join(text[1:]))
    elif change=='stale_counts':
        os.utime(model/'CORRECTION_SUM',(1,1))
    elif change=='bad_checkpoint':
        (model/'POINT1').write_text('broken')
        (model/'POINT2').write_text('broken')
    else:
        latest=max((model/n).stat().st_mtime for n in ('OUTGEN','MOD_SUM','RVTJ'))
        os.utime(model/'VADAT',(latest+10,latest+10))
    report=inspect_main_recommendations(model)
    assert report['evidence_error']
    assert not any(f['policy_id']=='verify_candidate' for f in report['findings'])


def test_legacy_known_initialization_failure_has_conditional_suggestions(tmp_path):
    (tmp_path/'VADAT').write_text('R [DC_METH]\nT [LIN_INT]\nT [POP_SCALE]\n')
    (tmp_path/'OUTGEN').write_text('Model started on: now\nStarting a new model\nCalling AUTO_ADD_ION\nFortran runtime error: initialization\n#0 scale_pops_\n')
    report=inspect_main_recommendations(tmp_path)
    failure=next(f for f in report['findings'] if f['policy_id']=='initial_population_scaling')
    assert 'DC_METH=POP' in failure['recommendation']
    assert not failure['automatic_eligible']


@pytest.mark.parametrize('options',[[],['--diagnose'],['--diagnose','--json']])
def test_cli_legacy_fallback_and_explicit_recheck_are_read_only(legacy_model,monkeypatch,capsys,options):
    from cmfgen_viewer import runner
    model=legacy_model('never')
    before={p.relative_to(model):snapshot(p) for p in model.rglob('*')}
    monkeypatch.setattr(runner,'run_plan',lambda *a,**kw:pytest.fail('must not run a model'))
    code=runner.main([str(model),'--cmfgen-root',str(model.parent/'cmf'),
        '--atomic-root',str(model.parent/'atomic'),*options])
    assert code==0
    captured=capsys.readouterr()
    if '--json' in options:
        assert json.loads(captured.out)['state']['main_diagnostics']['mode']=='retrospective'
    else:
        assert 'Recomputed model checks:' in captured.out
        assert 'original' in captured.out.lower()
        assert '10%' in captured.out
    assert {p.relative_to(model):snapshot(p) for p in model.rglob('*')}==before


def test_explicit_recheck_bypasses_valid_saved_report(auto_workspace):
    model,make=auto_workspace
    run_plan(ordinary(make()))
    assert inspect_main_recommendations(model)['mode']=='advisory'
    assert inspect_main_recommendations(model,force=True)['mode']=='retrospective'
    assert inspect_main_recommendations(model,force=True,active=True) is None


def test_diagnose_rejects_execution_stage(tmp_path,monkeypatch,capsys):
    from cmfgen_viewer import runner
    monkeypatch.setattr(runner,'run_plan',lambda *a,**kw:pytest.fail('must not execute'))
    assert runner.main([str(tmp_path),'--diagnose','--stage','main'])==2
    assert 'cannot be combined with --stage' in capsys.readouterr().err


def test_workflow_uses_legacy_fallback(legacy_model):
    from cmfgen_viewer.app import create_app
    model=legacy_model('never')
    with create_app(basepath=str(model.parent),read_write_enabled=True).test_client() as client:
        page=client.get('/model-actions/main-computation/model')
        assert page.status_code==200
        assert b'Recomputed model diagnostics' in page.data
        assert b'Auto remedy available' not in page.data


def test_legacy_cache_signature_gets_conditional_remedy(tmp_path):
    (tmp_path/'OUTGEN').write_text('Error - incorrect reading of EDDFACTOR in COMP_J_BLANK\n')
    report=inspect_main_recommendations(tmp_path)
    finding=next(f for f in report['findings'] if f['policy_id']=='radiation_cache')
    assert not finding['automatic_eligible']
    assert finding['proposal']['caches']==['EDDFACTOR','EDDFACTOR_INFO']
    assert 'checkpoint' in finding['recommendation']


def test_legacy_fresh_native_convergence_is_visible_with_quality_warnings(legacy_model):
    import io
    from cmfgen_viewer.app import create_app
    from cmfgen_viewer.runner_output import TerminalOutput
    model = legacy_model()
    log = (model/'OUTGEN').read_text().replace('BA matrix **NOT** computed', 'BA matrix computed')
    (model/'OUTGEN').write_text(log)
    (model/'J_COMP').write_text(
        'Indx Nu J(mom) J(ray) %Diff HBC_CMF J(mom) J(ray) %Diff\n'
        '1 3.49897D-3 1 1 35.2 1 1 1 0\n')
    report = inspect_main_recommendations(model)
    assert report['convergence']['status'] == 'converged'
    assert 'saved outputs' in report['convergence']['detail']
    assert not any(f['policy_id'] == 'verify_candidate' for f in report['findings'])
    assert any(f['policy_id'] == 'quality_boundary_radiation' for f in report['findings'])
    stream = io.StringIO()
    TerminalOutput(stream).recommendations(report)
    assert 'Numerically converged (native criterion)' in stream.getvalue()
    with create_app(basepath=str(model.parent), read_write_enabled=True).test_client() as client:
        page = client.get('/model-actions/main-computation/model')
        assert b'Numerically converged (native criterion)' in page.data
        assert b'Physical-quality warnings are assessed separately' in page.data
        assert b'Fresh-Jacobian verification of a numerical candidate' not in page.data
        assert b'Measured outer-boundary radiation agreement' in page.data


def test_display_native_criterion_does_not_weaken_auto_acceptance():
    from cmfgen_viewer.auto_diagnostics import convergence_status
    evidence = {'candidate': False, 'epsilon_percent': 0.02, 'checkpoint': 272,
                'counts': {'totals': {'0.1%': 0, '0.01%': 213}},
                'records': [dict(global_iteration=271, solver_maximum_change=0.0147,
                                 maximum_increase_percent=0.0172, maximum_decrease_percent=0.0201, ba_computed=True),
                            dict(global_iteration=272, solver_maximum_change=0.0133,
                                 maximum_increase_percent=0.0184, maximum_decrease_percent=0.00785, ba_computed=True)]}
    assert convergence_status(evidence)['status'] == 'converged'
    assert evidence['candidate'] is False
    evidence['records'][-1]['maximum_increase_percent'] = 1.0
    assert convergence_status(evidence)['status'] == 'not_converged'
    evidence['records'][-1]['maximum_increase_percent'] = 0.0184
    evidence['records'][-1]['temperature_fixed'] = True
    assert convergence_status(evidence)['status'] == 'not_converged'
