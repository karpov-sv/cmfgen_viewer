import json
from pathlib import Path
import re
import subprocess
import sys
import time

import psutil
import pytest

from cmfgen_viewer.app import create_app
from cmfgen_viewer import detached_jobs
from cmfgen_viewer.detached_jobs import launch_job, snapshot_job, cancel_job, fingerprint
from cmfgen_viewer.model_activity import inspect_model_activity
from cmfgen_viewer.runner_recipe import RunnerError
from test_runner import workspace, SUCCESS


def wait_for(base, job_id, predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = snapshot_job(base, job_id)
        if predicate(job):
            return job
        time.sleep(0.05)
    pytest.fail(f'Job did not reach expected state: {job}')


def launch(model, plan):
    return launch_job(model.parent, model, {'stages': [plan['stage']]}, lambda: plan, fingerprint(plan))


def test_job_survives_launching_process_exit(workspace, tmp_path):
    model, make_plan = workspace
    plan = make_plan('import time; time.sleep(1)\n' + SUCCESS)
    payload = tmp_path / 'reviewed-plan.json'
    payload.write_text(json.dumps(plan))
    code = '''from pathlib import Path
import json,sys
from cmfgen_viewer.detached_jobs import launch_job,fingerprint
plan=json.loads(Path(sys.argv[1]).read_text());model=Path(plan['model'])
print(launch_job(model.parent,model,{'stages':[plan['stage']]},lambda:plan,fingerprint(plan)),flush=True)
'''
    launcher = subprocess.run([sys.executable, '-c', code, str(payload)], capture_output=True, text=True)
    assert launcher.returncode == 0, launcher.stderr
    job_id = launcher.stdout.strip()
    job = wait_for(model.parent, job_id, lambda job: not job['active'])
    assert job['status'] == 'tested', job
    assert job['result']['journal']
    assert (model / 'RVTJ').exists()
    assert inspect_model_activity(model)['safe_to_modify']


def test_reservation_blocks_duplicate_launch_and_edits_and_cancel_restores(workspace):
    model, make_plan = workspace
    plan = make_plan('import time; time.sleep(30)\n' + SUCCESS)
    job_id = launch(model, plan)
    try:
        wait_for(model.parent, job_id, lambda job: job['status'] == 'running' and bool(job.get('progress')))
        assert not inspect_model_activity(model)['safe_to_modify']
        with pytest.raises(RunnerError, match='owns this model'):
            launch(model, plan)
        cancel_job(model.parent, job_id)
        job = wait_for(model.parent, job_id, lambda job: not job['active'])
        assert job['status'] == 'cancelled', job
        assert (model / 'IN_ITS').read_text() == '2 [NUM_ITS]\n'
        assert inspect_model_activity(model)['safe_to_modify']
        if job['result']:
            pid = job['result']['passes'][0].get('pid')
            assert not pid or not psutil.pid_exists(pid)
    finally:
        if snapshot_job(model.parent, job_id)['active']:
            cancel_job(model.parent, job_id)


def test_job_recovers_in_new_app_and_tasks_stream(workspace):
    model, make_plan = workspace
    job_id = launch(model, make_plan('import time; time.sleep(30)\n' + SUCCESS))
    try:
        wait_for(model.parent, job_id, lambda job: job['status'] == 'running')
        detached_jobs._CHILDREN.clear()  # No process handles survive an app restart.
        app = create_app(basepath=str(model.parent), read_write_enabled=True)
        client = app.test_client()
        job = client.get(f'/runner-jobs/{job_id}?format=json').json
        assert job['active']
        tasks = client.get('/tasks/status').json
        assert any(task['id'] == job_id for task in tasks['tasks'])
        stream = client.get('/tasks/events', buffered=False)
        assert job_id.encode() in next(stream.response)
        stream.close()
        page = client.get(f'/runner-jobs/{job_id}').get_data(as_text=True)
        token = re.search(r'name="cancel_token" value="([^"]+)"', page)[1]
        assert client.post(f'/runner-jobs/{job_id}/cancel', data={'cancel_token': token}).status_code == 302
        wait_for(model.parent, job_id, lambda job: not job['active'])
    finally:
        if snapshot_job(model.parent, job_id)['active']:
            cancel_job(model.parent, job_id)


def test_review_is_required_and_changed_inputs_rejected(workspace, monkeypatch):
    model, make_plan = workspace
    plan = make_plan()
    app = create_app(basepath=str(model.parent), read_write_enabled=True)
    client = app.test_client()
    monkeypatch.setattr('cmfgen_viewer.runner_job_views.runner_plan', lambda *args: plan)
    assert client.post('/model-actions/run/model', data={'action': 'launch'}).status_code == 200
    assert not (model.parent / detached_jobs.JOB_DIR).exists()
    response = client.post('/model-actions/run/model', data={'action': 'preview', 'stage': 'test'})
    assert response.status_code == 200
    token = re.search(r'name="review_token" value="([^"]+)"', response.get_data(as_text=True))[1]
    plan['inputs'][0]['size'] += 1
    response = client.post('/model-actions/run/model', data={'action': 'launch', 'review_token': token})
    assert b'changed since preview' in response.data
    assert not (model.parent / detached_jobs.JOB_DIR).exists()
    assert create_app(basepath=str(model.parent)).test_client().post('/model-actions/run/model').status_code == 403


def test_stale_pid_is_never_signalled(workspace, monkeypatch):
    model, make_plan = workspace
    job_id = launch(model, make_plan('import time; time.sleep(30)\n' + SUCCESS))
    try:
        wait_for(model.parent, job_id, lambda job: job['status'] == 'running')
        path = detached_jobs.job_directory(model.parent, job_id) / 'process.json'
        identity = json.loads(path.read_text())
        detached_jobs.write_json(path, {**identity, 'create_time': identity['create_time'] - 100})
        with pytest.raises(RunnerError):
            cancel_job(model.parent, job_id)
        detached_jobs.write_json(path, identity)
    finally:
        cancel_job(model.parent, job_id)
        wait_for(model.parent, job_id, lambda job: not job['active'])


def test_filesystem_sequence_holds_reservation_across_stages(tmp_path):
    from test_model_workflow import _write_initializable_workspace_inputs
    from cmfgen_viewer.runner import build_sequence_plan
    model = _write_initializable_workspace_inputs(tmp_path)
    (model / 'BAMAT').write_text('scratch')
    plan = build_sequence_plan(model, ['prepare-lte', 'cleanup'], native_config={},
        configuration_sources={}, timeout=None, iterations=None, fresh_start=False, cleanup_files=['BAMAT'])
    job_id = launch_job(tmp_path, model, {'stages': ['prepare-lte', 'cleanup']}, lambda: plan, fingerprint(plan))
    job = wait_for(tmp_path, job_id, lambda job: not job['active'])
    assert job['status'] == 'succeeded', job
    assert job['result']['completed_stages'] == ['prepare-lte', 'cleanup']
    assert (model / 'lte/HYDRO_PARAMS').exists()
    assert not (model / 'BAMAT').exists()


def test_reviewed_ui_launch_reconnect_and_native_log(workspace, monkeypatch):
    model, make_plan = workspace
    plan = make_plan('import time; time.sleep(0.5); print("native output")\n' + SUCCESS)
    app = create_app(basepath=str(model.parent), read_write_enabled=True)
    client = app.test_client()
    monkeypatch.setattr('cmfgen_viewer.runner_job_views.runner_plan', lambda *args: plan)
    page = client.post('/model-actions/run/model', data={'action': 'preview', 'stage': 'test'})
    token = re.search(r'name="review_token" value="([^"]+)"', page.get_data(as_text=True))[1]
    response = client.post('/model-actions/run/model', data={'action': 'launch', 'review_token': token})
    assert response.status_code == 302
    job_id = response.headers['Location'].rsplit('/', 1)[1]
    wait_for(model.parent, job_id, lambda job: not job['active'])
    recovered = create_app(basepath=str(model.parent), read_write_enabled=True).test_client()
    assert recovered.get(f'/runner-jobs/{job_id}?format=json').json['status'] == 'tested'
    assert b'Run result' in recovered.get(f'/runner-jobs/{job_id}').data
    assert b'native output' in recovered.get(f'/runner-jobs/{job_id}/log?native=1').data
    assert b'run_finished' in recovered.get(f'/runner-jobs/{job_id}/log?events=1').data
