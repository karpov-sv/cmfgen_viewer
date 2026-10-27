"""Graceful native finalization retains an accepted checkpoint without more stages."""
from pathlib import Path

import pytest

from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner_restart import read_pointer
from cmfgen_viewer.detached_jobs import launch_job, snapshot_job, fingerprint, stop_after_iteration_job, cancel_job
from cmfgen_viewer.app import create_app
from test_runner_auto import auto_workspace
from test_detached_jobs import wait_for
from test_auto_performance import performance_workspace
from test_auto_recovery import population_workspace


def slow_native(model, make_plan):
    # The fake rereads NUM_ITS at a boundary, then does one final output step,
    # mirroring CMFGEN's documented minimum final-iteration behavior.
    plan = make_plan('stall', iterations=5)
    exe = Path(plan['executable'])
    code = exe.read_text().replace("count=int(get('IN_ITS','NUM_ITS','2'))", """count=int(get('IN_ITS','NUM_ITS','2'))
(p/'native-running').touch()
for tick in range(100):
 time.sleep(.05)
 if get('IN_ITS','NUM_ITS','2')=='1':
  count=2
  break
else: raise RuntimeError('No clean-stop request received')
""")
    exe.write_text(code)
    # Rebuild after changing executable; preflight fingerprints must match.
    return make_plan('stall', iterations=5)


def request_during_progress(model, events):
    requested = False
    def emit(event):
        nonlocal requested
        events.append(event)
        if event['event'] == 'progress':
            requested = True
    return emit, lambda: requested


@pytest.mark.parametrize("override_iterations", [True, False])
def test_native_clean_stop_restores_controls_and_retains_outputs(auto_workspace, override_iterations):
    model, make_plan = auto_workspace
    auto = slow_native(model, make_plan)
    native = {**auto, 'kind': 'native'}
    if not override_iterations:
        native['passes'][0]['overrides'] = {}
    original = (model/'IN_ITS').read_bytes()
    events = []
    emit, requested = request_during_progress(model, events)
    result = run_plan(native, emit, stop_requested=requested)
    assert result['status'] == 'stopped', result
    assert result['passes'][0]['status'] == 'succeeded'
    assert result['stop_after_iteration']
    assert read_pointer(model/'POINT1')['iterations'] == 2
    assert (model/'IN_ITS').read_bytes() == original
    assert any(e['event'] == 'iteration_stop_requested' for e in events)
    assert result['main_diagnostics']['evidence_status'] == 'validated'


def test_auto_clean_stop_keeps_partial_batch_and_starts_no_further_attempt(auto_workspace):
    model, make_plan = auto_workspace
    plan = slow_native(model, make_plan)
    events = []
    emit, requested = request_during_progress(model, events)
    result = run_plan(plan, emit, stop_requested=requested)
    assert result['status'] == 'stopped', result
    assert len(result['attempts']) == 1
    assert result['final_checkpoint'] == 2
    assert result['iterations_used'] == 2
    assert read_pointer(model/'POINT1')['iterations'] == 2
    assert (model/'IN_ITS').read_text() == '5 [NUM_ITS]\n'
    assert not result['attempts'][0].get('checkpoint_restored')


def test_detached_clean_stop_route_is_authenticated_and_persistent(auto_workspace):
    model, make_plan = auto_workspace
    plan = slow_native(model, make_plan)
    options = {'stages': ['main'], 'automatic': True}
    job_id = launch_job(model.parent, model, options, lambda: plan, fingerprint(plan))
    try:
        job = wait_for(model.parent, job_id, lambda j: j['can_stop_after_iteration'] and (model/'native-running').exists())
        app = create_app(basepath=str(model.parent), read_write_enabled=True)
        client = app.test_client()
        url = f'/runner-jobs/{job_id}/stop-after-iteration?format=json'
        assert client.post(url).status_code == 409
        page = client.get(f'/runner-jobs/{job_id}').get_data(as_text=True)
        assert 'Stop after this iteration' in page
        token = client.get(f'/runner-jobs/{job_id}?format=json').json['cancel_token']
        assert client.post(url, data={'cancel_token': token}).status_code == 200
        stop_after_iteration_job(model.parent, job_id)  # Idempotent.
        job = wait_for(model.parent, job_id, lambda j: not j['active'])
        assert job['status'] == 'stopped', job
        assert job['stop_after_iteration_pending']
        assert not job['can_stop_after_iteration']
        assert read_pointer(model/'POINT1')['iterations'] == 2
        assert client.post(url, data={'cancel_token': token}).status_code == 409
        readonly = create_app(basepath=str(model.parent), read_write_enabled=False)
        assert readonly.test_client().post(url, data={'cancel_token': token}).status_code == 403
    finally:
        if snapshot_job(model.parent, job_id)['active']:
            cancel_job(model.parent, job_id)


def test_clean_stop_in_provisional_trial_restores_conservative_checkpoint(performance_workspace):
    model, make_plan = performance_workspace
    stop = False
    baseline = None
    def emit(event):
        nonlocal stop, baseline
        if event['event'] == 'auto_attempt' and event['phase'] == 'ba_reuse_check':
            baseline = (model/'POINT1').read_bytes()
            stop = True
    result = run_plan(make_plan('performance'), emit, stop_requested=lambda: stop)
    assert result['status'] == 'stopped', result
    assert result['provisional_recovery_rolled_back'] == 'ba_reuse_trial'
    assert (model/'POINT1').read_bytes() == baseline
    assert result['actions'][-1]['trial_outcome'] == 'aborted'
    assert result['attempts'][-1]['checkpoint_restored']


def test_clean_stop_skips_queued_spectra(auto_workspace, monkeypatch):
    from cmfgen_viewer import runner
    from test_runner_sequence import _sequence
    model, make_plan = auto_workspace
    auto = slow_native(model, make_plan)
    def build(sequence, stage, **options):
        assert stage == 'main', 'Spectra must not even be preflighted after a clean stop'
        return auto
    monkeypatch.setattr(runner, '_sequence_stage_plan', build)
    events = []
    emit, requested = request_during_progress(model, events)
    # Sequence progress precedes native launch: request only after a native main event.
    def forward(event):
        if event.get('stage') == 'main' and event['event'] == 'progress':
            emit(event)
    result = runner._run_sequence_plan(_sequence(model, ['main', 'flux']), forward,
                                       stop_requested=requested)
    assert result['status'] == 'stopped', result
    assert len(result['stage_results']) == 1
    assert result['remaining_stages'] == ['flux']
    assert read_pointer(model/'POINT1')['iterations'] == 2


def test_invalid_output_on_clean_stop_is_not_accepted(auto_workspace):
    model, make_plan = auto_workspace
    plan = slow_native(model, make_plan)
    exe = Path(plan['executable'])
    exe.write_text(exe.read_text()+"\n(p/'RVTJ').write_text('invalid output')\n")
    plan = make_plan('stall', iterations=5)
    emit, requested = request_during_progress(model, [])
    result = run_plan(plan, emit, stop_requested=requested)
    assert result['status'] == 'needs_review', result
    assert result['attempts'][-1]['checkpoint_restored']
    assert not (model/'POINT1').exists()
