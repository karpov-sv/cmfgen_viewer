"""Ordinary main runs diagnose using the registry without executing remedies."""
import io
import json
from pathlib import Path

import pytest

from test_runner_auto import auto_workspace
from test_auto_lte import lte_workspace
from test_auto_hydro import hydro_workspace
from cmfgen_viewer import auto_policies as policies
from cmfgen_viewer.main_recommendations import current_main_recommendations
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner_output import TerminalOutput


def ordinary(plan):
    return {k: v for k, v in plan.items() if k not in {'kind', 'auto'}}


def test_candidate_is_advisory_persisted_and_visible(auto_workspace):
    model, make = auto_workspace
    controls = (model/'VADAT').read_bytes()
    events = []
    result = run_plan(ordinary(make()), events.append)
    assert result['status'] == 'succeeded'
    report = result['main_diagnostics']
    assert report['evidence_status'] == 'validated', report
    finding = next(f for f in report['findings'] if f['policy_id'] == 'verify_candidate')
    assert finding['automatic_eligible']
    assert finding['proposal']['changes']['VADAT']['N_FIX_BA'] == '0'
    assert (model/'VADAT').read_bytes() == controls
    assert (model/'attempts.txt').read_text() == '1'
    assert json.loads((Path(result['journal'])/'result.json').read_text())['main_diagnostics'] == report
    assert events[-1]['event'] == 'run_finished'
    assert current_main_recommendations(model) == report
    assert current_main_recommendations(model, active=True) is None
    stream = io.StringIO()
    TerminalOutput(stream).result(result)
    assert 'Suggested controls:' in stream.getvalue()
    assert 'no remedy applied' in stream.getvalue()
    (model/'VADAT').write_bytes(controls+b'! changed controls\n')
    assert current_main_recommendations(model) is None


@pytest.mark.parametrize('scenario,rule', [('cache','radiation_cache'), ('unknown',None), ('stale',None)])
def test_failures_and_missing_evidence_are_not_retried(auto_workspace,scenario,rule):
    model, make = auto_workspace
    result = run_plan(ordinary(make(scenario)))
    report = result['main_diagnostics']
    assert (model/'attempts.txt').read_text() == '1'
    if rule:
        assert report['findings'][0]['policy_id'] == rule
        assert report['findings'][0]['automatic_eligible']
    elif scenario == 'stale':
        assert report['evidence_status'] == 'unavailable'
        assert report['evidence_error']
        assert not report['findings']
    else:
        assert 'No supported automatic remedy' in report['summary']
        assert not report['findings']


def test_lte_failure_recommendation_preserves_fresh_controls(lte_workspace):
    model, make = lte_workspace
    original = (model/'VADAT').read_bytes()
    result = run_plan(ordinary(make('lte_scaling')))
    finding = result['main_diagnostics']['findings'][0]
    assert finding['policy_id'] == 'lte_initialization'
    assert finding['automatic_eligible']
    assert len(finding['proposal']['steps']) == 2
    assert (model/'VADAT').read_bytes() == original
    assert (model/'attempts.txt').read_text() == '1'
    from cmfgen_viewer.app import create_app
    app = create_app(basepath=str(model.parent),read_write_enabled=True,secret_key='test')
    with app.test_client() as client:
        page = client.get('/model-actions/main-computation/model')
        assert page.status_code == 200
        assert b'DC_METH=LTE' in page.data
        assert b'Auto remedy available' in page.data
    stream = io.StringIO()
    TerminalOutput(stream).result(result)
    assert 'DC_METH=LTE' in stream.getvalue()


@pytest.mark.parametrize('scenario,eligible',[('hydro',True),('hydro_shallow',False)])
def test_hydro_remedy_requires_same_guard_prerequisites(hydro_workspace,scenario,eligible):
    model, make, original = hydro_workspace
    result = run_plan(ordinary(make(scenario)))
    finding = next(f for f in result['main_diagnostics']['findings'] if f['policy_id'] == 'hydro_bootstrap')
    assert finding['automatic_eligible'] is eligible
    for name, content in original.items():
        assert (model/name).read_bytes() == content
    assert (model/'attempts.txt').read_text() == '1'


def test_stall_requires_three_consecutive_batches_and_resets_on_control_edit(auto_workspace):
    model, make = auto_workspace
    first = run_plan(ordinary(make('stall')))
    second = run_plan(ordinary(make('stall')))
    third = run_plan(ordinary(make('stall')))
    for result in (first,second):
        assert not any(f['policy_id'] == 'stalled_corrections' for f in result['main_diagnostics']['findings'])
    assert third['main_diagnostics']['batches_assessed'] == 3, third['main_diagnostics']
    assert any(f['policy_id'] == 'stalled_corrections' for f in third['main_diagnostics']['findings'])
    (model/'VADAT').write_text((model/'VADAT').read_text()+'! changed\n')
    fourth = run_plan(ordinary(make('stall')))
    assert fourth['main_diagnostics']['batches_assessed'] == 1


def test_fixed_temperature_requires_three_batches(auto_workspace):
    model, make = auto_workspace
    for n in range(3):
        report = run_plan(ordinary(make('lambda')))['main_diagnostics']
        assert report['evidence_status'] == 'validated', report
        assert any(f['policy_id'] == 'fixed_temperature' for f in report['findings']) is (n == 2)


def test_new_registry_rule_appears_without_advisory_branch(auto_workspace,monkeypatch):
    model, make = auto_workspace
    custom = policies.Policy('example',1,'success','Example diagnostic',
        lambda ctx: policies.Decision('action','Example remedy',changes={'VADAT':{'N_FIX_BA':'0'}}))
    monkeypatch.setattr(policies,'POLICIES',(*policies.POLICIES,custom))
    report = run_plan(ordinary(make('never')))['main_diagnostics']
    assert any(f['policy_id'] == 'example' for f in report['findings'])
    assert '2 [N_FIX_BA]' in (model/'VADAT').read_text()


def test_recommendations_render_in_workflow_and_job_templates(auto_workspace):
    from cmfgen_viewer import create_app
    model, make = auto_workspace
    result = run_plan(ordinary(make()))
    app = create_app(basepath=str(model.parent),read_write_enabled=True,secret_key='test')
    with app.test_client() as client:
        page = client.get('/model-actions/main-computation/model')
        assert page.status_code == 200
        assert b'Auto remedy available' in page.data
        assert b'N_FIX_BA=0' in page.data
    with app.test_request_context('/'):
        macro = app.jinja_env.get_template('_main_recommendations.html').module.main_recommendations
        html = macro(result['main_diagnostics'])
        assert 'Conditions and remedies' in html
        assert 'no remedy applied' in html.lower()


def test_local_oscillation_suggests_depth_scoped_relaxation_without_applying_it(auto_workspace):
    model, make = auto_workspace
    report = run_plan(ordinary(make('oscillate')))['main_diagnostics']
    finding = next(f for f in report['findings'] if f['policy_id'] == 'local_relaxation')
    assert finding['proposal']['changes']['ADJUST_CORRECTIONS'] == {
        'L_ST':'1','L_END':'1','RELAX':'0.25','T_LIM':'0.2'}
    assert not (model/'ADJUST_CORRECTIONS').exists()


def test_intervening_output_changes_break_batch_history(auto_workspace):
    model, make = auto_workspace
    run_plan(ordinary(make('stall')))
    (model/'OUTGEN').write_text((model/'OUTGEN').read_text()+'! external run\n')
    report = run_plan(ordinary(make('stall')))['main_diagnostics']
    assert report['batches_assessed'] == 1


def test_unknown_advisory_error_cannot_change_execution_success(auto_workspace,monkeypatch):
    model, make = auto_workspace
    def broken(ctx):
        raise RuntimeError('broken diagnostic extension')
    monkeypatch.setattr(policies,'POLICIES',(policies.Policy('broken',1,'success','Broken rule',broken),))
    result = run_plan(ordinary(make()))
    assert result['status'] == 'succeeded'
    assert result['main_diagnostics']['evidence_status'] == 'unavailable'
    assert 'broken diagnostic extension' in result['main_diagnostics']['evidence_error']


def test_detached_main_job_displays_recommendations(auto_workspace):
    from cmfgen_viewer.app import create_app
    from test_detached_jobs import launch, wait_for
    model, make = auto_workspace
    job_id = launch(model, ordinary(make()))
    job = wait_for(model.parent,job_id,lambda j: not j['active'])
    assert job['result']['main_diagnostics']['evidence_status'] == 'validated', job
    app = create_app(basepath=str(model.parent),read_write_enabled=True,secret_key='test')
    with app.test_client() as client:
        page = client.get(f'/runner-jobs/{job_id}')
        assert page.status_code == 200
        assert b'Auto remedy available' in page.data
        assert b'N_FIX_BA=0' in page.data
