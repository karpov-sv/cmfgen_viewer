"""Full maintenance cleanup removes only the intended model's history/data."""
import json
from pathlib import Path

import pytest

from cmfgen_viewer import model_activity, model_full_cleanup
from cmfgen_viewer.model_cli import main
from cmfgen_viewer.model_full_cleanup import build_full_cleanup_plan, run_full_cleanup, FullCleanupError
from cmfgen_viewer.model_editor import MODEL_INPUT_MODIFIED_MARKER
from cmfgen_viewer.detached_jobs import JOB_DIR
from test_model_cli import solution, isolated_config


def _job(base, model, number, status='succeeded'):
    directory = base / JOB_DIR / f'{number:032x}'
    directory.mkdir(parents=True)
    (directory / 'request.json').write_text(json.dumps({'model': str(model),
        'model_relpath': str(model.relative_to(base)), 'created_at': '2026-01-01T00:00:00+00:00',
        'created_epoch': 0, 'stages': ['main']}))
    (directory / 'state.json').write_text(json.dumps({'status': status}))
    return directory


def _populate(model):
    (model / 'BAMAT').write_text('matrix')
    (model / MODEL_INPUT_MODIFIED_MARKER).write_text('{"file": "VADAT"}')
    for workspace in ('', 'lte', 'obs'):
        folder = model / workspace
        folder.mkdir(exist_ok=True)
        if workspace == 'lte':
            for name in ('VADAT', 'MODEL_SPEC', 'RVSIG_COL_NEW', 'ROSSELAND_LTE_TAB', 'OUTLTE', 'HeI_IN', 'POPHYD'):
                (folder / name).write_text(name)
        elif workspace == 'obs':
            (folder / 'fort.63').write_text('scratch')
            (folder / 'obs_fin').write_text('spectrum')
        for archive in ('.cmfgen-runs', '.cmfgen-viewer-backups'):
            path = folder / archive / 'old'
            path.mkdir(parents=True)
            (path / 'data').write_text('old recovery data')


def test_full_plan_is_read_only_and_execution_does_not_create_another_archive(solution, tmp_path, capsys):
    _populate(solution)
    own_job = _job(tmp_path, solution, 1)
    sibling = tmp_path / 'other-model'
    sibling.mkdir()
    other_job = _job(tmp_path, sibling, 2)
    assert main(['cleanup', str(solution), '--full', '--plan', '--json']) == 0
    plan = json.loads(capsys.readouterr().out)
    names = {entry['name'] for entry in plan['entries']}
    assert '.cmfgen-runs' in names and 'lte/.cmfgen-viewer-backups' in names
    assert str(own_job) in names and str(other_job) not in names
    assert (solution / 'BAMAT').exists() and own_job.exists()
    assert main(['cleanup', str(solution), '--full', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'succeeded'
    assert not own_job.exists() and other_job.exists()
    for workspace in ('', 'lte', 'obs'):
        folder = solution / workspace
        assert not (folder / '.cmfgen-runs').exists()
        assert not (folder / '.cmfgen-viewer-backups').exists()
    assert not (solution / MODEL_INPUT_MODIFIED_MARKER).exists()
    assert not (solution / model_activity.LOCK_NAME).exists()
    assert not (solution / 'BAMAT').exists()
    assert not (solution / 'lte/POPHYD').exists()
    assert not (solution / 'obs/fort.63').exists()
    for name in ('VADAT', 'MODEL_SPEC', 'POINT1', 'SCRTEMP', 'HeIOUT', 'GAMMAS'):
        assert (solution / name).exists()
    for name in ('VADAT', 'HeI_IN', 'OUTLTE', 'RVSIG_COL_NEW', 'ROSSELAND_LTE_TAB'):
        assert (solution / 'lte' / name).exists()
    assert (solution / 'obs/obs_fin').exists()
    assert main(['cleanup', str(solution), '--full', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'unchanged'


def test_full_cleanup_never_follows_archive_or_workspace_symlinks(solution, tmp_path):
    external = tmp_path / 'external'
    external.mkdir()
    (external / 'data').write_text('retain')
    (solution / '.cmfgen-runs').symlink_to(external)
    (solution / 'lte').symlink_to(external)
    backup = solution / '.cmfgen-viewer-backups/old'
    backup.mkdir(parents=True)
    (backup / 'nested-link').symlink_to(external)
    plan = build_full_cleanup_plan(solution)
    assert plan['ready']
    result = run_full_cleanup(plan)
    assert not result['failures']
    assert (external / 'data').read_text() == 'retain'
    assert not (solution / '.cmfgen-runs').exists()


@pytest.mark.parametrize('state', ['active', 'unknown'])
def test_full_cleanup_blocks_active_and_uncertain_models(solution, capsys, monkeypatch, state):
    _populate(solution)
    monkeypatch.setattr(model_activity, 'scan_model_processes', lambda *a, **k:
        ([{'pid': 1}], []) if state == 'active' else ([], ['visibility unavailable']))
    assert main(['cleanup', str(solution), '--full', '--json']) == 2
    assert not json.loads(capsys.readouterr().out)['ready']
    assert (solution / '.cmfgen-runs/old/data').exists()
    assert (solution / 'BAMAT').exists()


def test_full_cleanup_blocks_an_active_job_even_if_model_scan_is_idle(solution, tmp_path, monkeypatch):
    _job(tmp_path, solution, 1)
    monkeypatch.setattr(model_full_cleanup, 'snapshot_job', lambda *a, **k: {'active': True})
    plan = build_full_cleanup_plan(solution)
    assert not plan['ready'] and any('still active' in error for error in plan['errors'])


def test_full_cleanup_rejects_changed_archive_or_job_inventory(solution, tmp_path):
    _populate(solution)
    plan = build_full_cleanup_plan(solution)
    _job(tmp_path, solution, 1)
    with pytest.raises(FullCleanupError, match='changed after planning'):
        run_full_cleanup(plan)
    assert (solution / '.cmfgen-runs/old/data').exists()


def test_matching_jobs_are_found_in_ancestor_and_workspace_stores(solution, tmp_path):
    _populate(solution)
    # The immediate ancestor store and a viewer rooted directly in the model.
    ancestor_job = _job(tmp_path, solution, 1)
    local_job = _job(solution, solution, 2)
    workspace_job = _job(solution / 'lte', solution / 'lte', 3)
    plan = build_full_cleanup_plan(solution)
    assert plan['ready'], plan['errors']
    assert not run_full_cleanup(plan)['failures']
    assert not any(job.exists() for job in (ancestor_job, local_job, workspace_job))
    assert not (solution / JOB_DIR).exists()
    assert not (solution / 'lte' / JOB_DIR).exists()


@pytest.mark.parametrize('flags', [['--lte'], ['--file', 'BAMAT']])
def test_full_cleanup_rejects_conflicting_options(solution, capsys, flags):
    assert main(['cleanup', str(solution), '--full', *flags, '--json']) == 2
    assert 'cannot be combined' in json.loads(capsys.readouterr().out)['error']


def test_full_cleanup_ignores_retention_default_and_reports_partial_failures(solution, tmp_path, capsys, monkeypatch):
    _populate(solution)
    original = model_full_cleanup.shutil.rmtree
    def fail(path, *args, **kwargs):
        if Path(path) == solution / '.cmfgen-runs':
            raise PermissionError('simulated deletion failure')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(model_full_cleanup.shutil, 'rmtree', fail)
    assert main(['cleanup', str(solution), '--full', '--json']) == 1
    result = json.loads(capsys.readouterr().out)
    assert 'keep_large_files' not in result
    assert result['result']['failures']
    assert (solution / '.cmfgen-runs/old/data').exists()
    assert not (solution / '.cmfgen-viewer-backups').exists()


def test_full_cleanup_preserves_unidentifiable_job_records(solution, tmp_path):
    directory = tmp_path / JOB_DIR / ('a' * 32)
    directory.mkdir(parents=True)
    (directory / 'request.json').write_text('invalid json')
    plan = build_full_cleanup_plan(solution)
    assert any('left untouched' in warning for warning in plan['warnings'])
    assert directory.exists()


def _client(model):
    from cmfgen_viewer.app import create_app
    app = create_app(basepath=str(model.parent), read_write_enabled=True, secret_key='full-cleanup-tests')
    app.testing = True
    app.config['CMFGEN_VIEWER']['summary_cache_db'] = str(model.parent / 'summary.sqlite')
    return app.test_client()


def _review_token(response):
    import re
    return re.search(r'name="review_token" value="([^"]*)"', response.get_data(as_text=True)).group(1)


def test_ui_full_cleanup_checkbox_previews_then_deletes_after_review(solution, tmp_path):
    _populate(solution)
    own_job = _job(tmp_path, solution, 1)
    client = _client(solution)
    url = '/model-actions/cleanup/' + solution.name
    ordinary = client.get(url)
    assert ordinary.status_code == 200
    assert b'id="full-cleanup"' in ordinary.data
    assert b'name="review_token"' not in ordinary.data
    preview = client.get(url + '?full=1')
    assert preview.status_code == 200
    assert b'Delete All Listed Items' in preview.data
    assert b'editor checkpoints' in preview.data
    assert own_job.exists() and (solution / '.cmfgen-runs').exists()
    unconfirmed = client.post(url, data={'full': '1', 'review_token': _review_token(preview)})
    assert b'Confirm' in unconfirmed.data
    assert (solution / '.cmfgen-runs').exists()
    response = client.post(url, data={'full': '1', 'confirm_cleanup': '1', 'review_token': _review_token(preview)})
    assert response.status_code == 302
    assert not (solution / '.cmfgen-runs').exists() and not own_job.exists()
    assert (solution / 'SCRTEMP').exists() and (solution / 'VADAT').exists()


def test_ui_full_cleanup_rejects_stale_or_forged_preview(solution):
    _populate(solution)
    client = _client(solution)
    url = '/model-actions/cleanup/' + solution.name
    preview = client.get(url + '?full=1')
    (solution / '.cmfgen-runs/old/new-output').write_text('appeared after preview')
    stale = client.post(url, data={'full': '1', 'confirm_cleanup': '1', 'review_token': _review_token(preview)})
    assert b'targets changed' in stale.data
    assert (solution / '.cmfgen-runs/old/data').exists()
    forged = client.post(url, data={'full': '1', 'confirm_cleanup': '1', 'review_token': 'forged'})
    assert b'invalid' in forged.data
    assert (solution / '.cmfgen-runs/old/data').exists()


def test_ui_full_cleanup_preview_is_bound_to_model(solution, tmp_path):
    from test_model_staging import _write_solution
    _populate(solution)
    other = tmp_path / 'other-model'
    _write_solution(other)
    _populate(other)
    client = _client(solution)
    preview = client.get('/model-actions/cleanup/' + solution.name + '?full=1')
    response = client.post('/model-actions/cleanup/' + other.name,
        data={'full': '1', 'confirm_cleanup': '1', 'review_token': _review_token(preview)})
    assert b'another model' in response.data
    assert (solution / '.cmfgen-runs').exists() and (other / '.cmfgen-runs').exists()


def test_ui_full_cleanup_is_blocked_for_readonly_and_active_models(solution, monkeypatch):
    from cmfgen_viewer.app import create_app
    _populate(solution)
    url = '/model-actions/cleanup/' + solution.name
    readonly = create_app(basepath=str(solution.parent)).test_client()
    assert readonly.get(url + '?full=1').status_code == 403
    assert readonly.post(url, data={'full': '1', 'confirm_cleanup': '1'}).status_code == 403
    monkeypatch.setattr(model_activity, 'scan_model_processes', lambda *a, **k: ([{'pid': 1}], []))
    page = _client(solution).get(url + '?full=1')
    assert b'A model calculation is active' in page.data
    assert b'type="submit" disabled>Delete All Listed Items' in page.data
    assert (solution / '.cmfgen-runs').exists()


@pytest.mark.parametrize('workspace', ['', 'lte', 'obs'])
def test_full_cleanup_removes_file_directory_and_broken_links_in_every_workspace(solution, tmp_path, workspace):
    _populate(solution)
    folder = solution / workspace
    target = tmp_path / 'atomic-data'
    target.write_text('retain atomic data')
    target.chmod(0o600)
    directory = tmp_path / 'atomic-directory'
    directory.mkdir(mode=0o700)
    (directory / 'keep').write_text('retain directory contents')
    targets = {'HYD_L_DATA': target, 'He2_IN': target,
               'directory-link': directory, 'broken-link': tmp_path / 'missing'}
    for name, destination in targets.items():
        (folder / name).symlink_to(destination)
    plan = build_full_cleanup_plan(solution)
    planned = {entry['path'] for entry in plan['entries']}
    assert all(str(folder / name) in planned for name in targets)
    assert not run_full_cleanup(plan)['failures']
    assert all(not (folder / name).is_symlink() for name in targets)
    assert target.read_text() == 'retain atomic data' and target.stat().st_mode & 0o777 == 0o600
    assert (directory / 'keep').read_text() == 'retain directory contents'
    assert directory.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize('workspace', ['', 'lte', 'obs'])
def test_full_cleanup_removes_script_metadata_locks_and_temporary_trees(solution, tmp_path, workspace):
    _populate(solution)
    folder = solution / workspace
    for name in (model_activity.LOCK_NAME, model_activity.RUN_LOCK_NAME,
                 MODEL_INPUT_MODIFIED_MARKER, '.cmfgen-edit-leftover', '.cmfgen-promote-leftover',
                 '.runner-control-leftover', '.runner-product-leftover', '.report-leftover',
                 '.diagnostic-leftover', '.recovery-compaction-leftover'):
        (folder / name).write_text('stale')
    temporary = folder / '.cmfgen-lte-leftover'
    temporary.mkdir()
    (temporary / 'scratch').write_text('discard')
    external = tmp_path / 'retain'
    external.write_text('retain')
    (temporary / 'link').symlink_to(external)
    (folder / '.cmfgenrc').write_text('retain configuration')
    (folder / '.unrelated').write_text('retain unrelated data')
    plan = build_full_cleanup_plan(solution)
    assert plan['ready'], plan['errors']
    names = {entry['path'] for entry in plan['entries']}
    assert str(temporary) in names
    assert str(folder / model_activity.LOCK_NAME) in names
    assert not run_full_cleanup(plan)['failures']
    assert {path.name for path in folder.iterdir() if path.name.startswith('.')} == {'.cmfgenrc', '.unrelated'}
    assert external.read_text() == 'retain'
    assert (folder / '.cmfgenrc').exists() and (folder / '.unrelated').exists()
