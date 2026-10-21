"""Automatic main runs through reviewed and inline detached UI launch paths."""
import copy
import json
import re

import pytest
from werkzeug.datastructures import MultiDict

from test_runner_auto import auto_workspace
from test_detached_jobs import wait_for
from cmfgen_viewer.app import create_app
from cmfgen_viewer.detached_jobs import fingerprint, snapshot_job, cancel_job
from cmfgen_viewer.runner_job_views import parse_options


def client_for(model):
    return create_app(basepath=str(model.parent), read_write_enabled=True, secret_key='auto-ui',
        cmfgen_root=str(model.parent/'cmf'), atomic_root=str(model.parent/'atomic')).test_client()


def auto_token(client):
    page=client.get('/model-actions/main-computation/model').get_data(as_text=True)
    return re.search(r'data-inline-automatic data-start-token="([^"]+)"',page)[1]


def test_reviewed_automatic_run_finishes_and_renders_verification(auto_workspace):
    model,make=auto_workspace
    make()
    client=client_for(model)
    url='/model-actions/run/model'
    page=client.post(url,data={'action':'preview','stage_sequence':'main','automatic':'1',
        'iterations':'3','auto_max_attempts':'10','auto_max_iterations':'30'})
    assert page.status_code==200
    text=page.get_data(as_text=True)
    assert 'Automatic main convergence' in text
    assert '10 attempts and 30 total iterations' in text
    assert 'Iterations per batch: 3' in text
    token=re.search(r'name="review_token" value="([^"]+)"',text)[1]
    launched=client.post(url,data={'action':'launch','review_token':token})
    assert launched.status_code==302
    job_id=launched.location.rsplit('/',1)[-1]
    job=wait_for(model.parent,job_id,lambda j:not j['active'])
    assert job['status']=='succeeded',job
    assert job['automatic']
    assert job['sequence_label']=='Automatic main computation'
    assert job['result']['numerical_convergence']=='verified with fresh Jacobians'
    assert len(job['result']['attempts'])==2
    result=client.get(launched.location)
    assert result.status_code==200
    assert b'verified with fresh Jacobians' in result.data
    assert b'Automatic adjustments and recovery' in result.data
    assert b'charged iterations' in result.data
    # Reconnecting through a new app reads the same independently owned job.
    assert client_for(model).get(launched.location+'?format=json').json['result']==job['result']


def test_inline_auto_is_bound_to_mode_and_uses_default_budgets(auto_workspace):
    model,make=auto_workspace
    make()
    client=client_for(model)
    page=client.get('/model-actions/main-computation/model').get_data(as_text=True)
    manual=re.search(r'name="start_token" value="([^"]+)"',page)[1]
    token=auto_token(client)
    url='/model-actions/run/model?format=json'
    assert client.post(url,data={'action':'start','stage_sequence':'main','automatic':'1','start_token':manual}).status_code==409
    assert client.post(url,data={'action':'start','stage_sequence':'main','start_token':token}).status_code==409
    launched=client.post(url,data={'action':'start','stage_sequence':'main','automatic':'1','start_token':token,'iterations':'2'})
    assert launched.status_code==200,launched.json
    job_id=launched.json['job_id']
    job=wait_for(model.parent,job_id,lambda j:not j['active'])
    assert job['status']=='succeeded',job
    plan=json.loads((model.parent/'.cmfgen-runner-jobs'/job_id/'plan.json').read_text())
    assert plan['kind']=='auto'
    assert plan['auto']['batch_iterations']==2
    assert plan['auto']['max_attempts']==100
    assert plan['auto']['max_iterations']==500
    assert job['auto_attempt']==2
    assert job['auto_phase']=='verify'
    assert job['progress_label'].startswith('Attempt 2 · verify · ')


@pytest.mark.parametrize('scenario,status',[('unknown','needs_review'),('never','limit_reached')])
def test_automatic_review_and_budget_stops_are_visible(auto_workspace,scenario,status):
    model,make=auto_workspace
    make(scenario)
    client=client_for(model)
    response=client.post('/model-actions/run/model?format=json',data={
        'action':'start','stage_sequence':'main','automatic':'1','start_token':auto_token(client),
        'iterations':'3','auto_max_iterations':'6','auto_max_attempts':'5'})
    assert response.status_code==200,response.json
    job=wait_for(model.parent,response.json['job_id'],lambda j:not j['active'])
    assert job['status']==status,job
    assert job['status_class']=='bg-warning text-dark'
    page=client.get('/runner-jobs/'+job['job_id'])
    assert page.status_code==200
    assert b'Investigation report:' in page.data
    assert job['result']['reason'].encode() in page.data


def test_inline_auto_cancel_restores_controls_and_releases_reservation(auto_workspace):
    model,make=auto_workspace
    make('cancel')
    original=(model/'VADAT').read_bytes()
    client=client_for(model)
    response=client.post('/model-actions/run/model?format=json',data={
        'action':'start','stage_sequence':'main','automatic':'1','start_token':auto_token(client)})
    job_id=response.json['job_id']
    try:
        wait_for(model.parent,job_id,lambda j:j.get('auto_attempt')==1 and j.get('native_log') and j['can_cancel'])
        assert snapshot_job(model.parent,job_id)['progress_label'].startswith('Attempt 1')
        token=client.get('/runner-jobs/'+job_id+'?format=json').json['cancel_token']
        assert client.post('/runner-jobs/'+job_id+'/cancel?format=json',data={'cancel_token':token}).status_code==200
        job=wait_for(model.parent,job_id,lambda j:not j['active'])
        assert job['status']=='cancelled',job
        assert (model/'VADAT').read_bytes()==original
        assert (model/'IN_ITS').read_text()=='5 [NUM_ITS]\n'
        assert not (model/'POINT1').exists()
    finally:
        if snapshot_job(model.parent,job_id)['active']:
            cancel_job(model.parent,job_id)
            wait_for(model.parent,job_id,lambda j:not j['active'])


@pytest.mark.parametrize('values',[
    {'stage_sequence':'flux,main','automatic':'1'},
    {'stage_sequence':'test','automatic':'1'},
    {'stage_sequence':'main','auto_max_attempts':'10'},
    {'stage_sequence':'main','automatic':'1','iterations':'1'},
    {'stage_sequence':'main','automatic':'1','auto_max_iterations':'1'},
    {'stage_sequence':'main','automatic':'1','auto_max_attempts':'NaN'},
])
def test_ui_rejects_incompatible_automatic_options(values):
    with pytest.raises(ValueError):
        parse_options(MultiDict(values),['main'])


def test_automatic_review_fingerprint_includes_budget_and_policy_manifest(auto_workspace):
    model,make=auto_workspace
    plan=make()
    for key in ('max_attempts','max_iterations'):
        changed=copy.deepcopy(plan);changed['auto'][key]+=1
        assert fingerprint(plan)!=fingerprint(changed)
    changed=copy.deepcopy(plan);changed['auto']['policies'][0]['version']+=1
    assert fingerprint(plan)!=fingerprint(changed)


def add_spectra(model):
    import sys
    (model/'atomic_links.json').write_text(json.dumps({'base':{'HYD_L_DATA':'test.dat'},'ions':{},'obs':{}}))
    obs=model/'obs';obs.mkdir()
    (obs/'CMF_FLUX_PARAM_INIT').write_text(''.join(f'1 [{key}]\n' for key in (
        'VTURB_FIX','VTURB_MIN','VTURB_MAX','NUM_ES','DO_SOB_LINES','GLOBAL_LINE')))
    (obs/'IN_FILE').write_text('../RVTJ [RVTJ]\n1 [MASS]\nF [ONLY_OBS_LINES]\n')
    exe=model.parent/'cmf/exe/cmf_flux.exe'
    exe.write_text(f'#!{sys.executable}\n'+'''from pathlib import Path
p=Path('.')
assert (p/'../POINT1').is_file()
(p/'flux-started').write_text((p/'../POINT1').read_text())
(p/'OUT_FLUX').write_text('CMF_FLUX has finished')
(p/'OBSFRAME').write_text('Continuum Frequencies (2)\\n1 2\\nObserved intensity (Janskys)\\n3 4\\n')
''')
    exe.chmod(0o755)
    return obs


@pytest.mark.parametrize('scenario,status',[('good','succeeded'),('unknown','needs_review'),('never','limit_reached')])
def test_checkbox_applies_to_inline_main_and_spectra(auto_workspace,scenario,status):
    model,make=auto_workspace
    make(scenario)
    obs=add_spectra(model)
    client=client_for(model)
    text=client.get('/model-actions/main-computation/model').get_data(as_text=True)
    assert 'name="automatic"' in text
    assert '>Automatic mode</label>' in text
    assert 'Run automatically</button>' not in text
    token=re.search(r'data-inline-token="[^"]+" data-inline-auto-token="([^"]+)" data-inline-label="main \+ spectra"',text)[1]
    response=client.post('/model-actions/run/model?format=json',data={
        'action':'start','stage_sequence':'main,flux','automatic':'1','start_token':token,
        'iterations':'3','auto_max_iterations':'12' if scenario=='good' else '6'})
    assert response.status_code==200,response.json
    job=wait_for(model.parent,response.json['job_id'],lambda j:not j['active'])
    assert job['status']==status,job
    result=job['result']
    assert result['stage_results'][0]['kind']=='auto'
    assert job['sequence_label']=='Automatic main computation → spectra'
    if status=='succeeded':
        assert result['completed_stages']==['main','flux']
        assert result['stage_results'][0]['numerical_convergence']=='verified with fresh Jacobians'
        assert all((obs/name).is_file() for name in ('obs_fin_15','obs_fin_10','obs_fin_20','obs_cont'))
        assert 'auto_attempt' not in job  # Flux progress must not retain a main-attempt prefix.
    else:
        assert result['remaining_stages']==['flux']
        assert not (obs/'flux-started').exists()
    page=client.get('/runner-jobs/'+job['job_id'])
    assert page.status_code==200
    assert b'charged iterations' in page.data


def test_reviewed_auto_main_plus_spectra_preview(auto_workspace):
    model,make=auto_workspace;make();add_spectra(model)
    page=client_for(model).post('/model-actions/run/model',data={
        'action':'preview','stage_sequence':'main,flux','automatic':'1','auto_max_iterations':'30'})
    assert page.status_code==200
    assert b'Automatic main convergence' in page.data
    assert b'30 total iterations' in page.data
    assert b'Spectra start only after verified main convergence' in page.data
    assert b'name="review_token"' in page.data


def test_cli_auto_flag_supports_main_then_spectra(auto_workspace,capsys):
    from cmfgen_viewer.runner import main
    model,make=auto_workspace;make();obs=add_spectra(model)
    assert main([str(model),'--stage','main','--stage','flux','--auto','--iterations','3',
        '--auto-max-iterations','12','--cmfgen-root',str(model.parent/'cmf'),
        '--atomic-root',str(model.parent/'atomic'),'--json'])==0
    result=json.loads(capsys.readouterr().out)
    assert result['stage_results'][0]['numerical_convergence']=='verified with fresh Jacobians'
    assert (obs/'obs_cont').is_file()


def test_automatic_sequence_rejects_changes_after_preview(auto_workspace):
    from cmfgen_viewer.runner import build_sequence_plan, run_plan
    from cmfgen_viewer.runner_auto import configure_auto
    model,make=auto_workspace;make();obs=add_spectra(model)
    root=model.parent/'cmf';atomic=model.parent/'atomic'
    sequence=build_sequence_plan(model,['main','flux'],native_config={'cmfgen_root':root,'atomic_root':atomic},
        configuration_sources={},timeout=None,iterations=3,fresh_start=False,cleanup_files=None)
    sequence=configure_auto(sequence,cmfgen_root=root,atomic_root=atomic)
    (model/'VADAT').write_text((model/'VADAT').read_text()+'! external change\n')
    with pytest.raises(ValueError,match='Input changed since automatic sequence preview'):
        run_plan(sequence)
    assert not (obs/'flux-started').exists()
