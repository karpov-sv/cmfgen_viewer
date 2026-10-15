"""Archive access, reviewed control/native recovery, and guarded housekeeping."""
import json
from pathlib import Path
import re
from urllib.parse import urlencode

import pytest

from cmfgen_viewer.app import create_app
from cmfgen_viewer import model_activity, history_restart
from cmfgen_viewer.model_editor import load_model_parameter_file, save_model_parameter_edit, MODEL_INPUT_MODIFIED_MARKER
from cmfgen_viewer.model_history import (HistoryError, list_archives, archive_files, control_versions,
    load_archived_control, preview_housekeeping, apply_housekeeping, safe_path)
from cmfgen_viewer.history_restart import preview_restart, apply_restart
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.recovery_files import RECOVERY_FILE_LIMIT
from test_model_editor import _write_model
from test_runner import workspace, RVTJ_CORE, SUCCESS


@pytest.fixture
def model(tmp_path):
    root = tmp_path / 'model_a'
    _write_model(root)
    return root


@pytest.fixture
def journal(model):
    path = model / '.cmfgen-runs/20260101T120000Z-test'
    (path / 'inputs').mkdir(parents=True)
    (path / 'inputs/VADAT').write_text('0.5 [LSTAR]\nF [DO_HYDRO]\n')
    (path / 'plan.json').write_text(json.dumps({'stage': 'main', 'keep_large_files': True}))
    (path / 'result.json').write_text(json.dumps({'status': 'succeeded', 'finished_at': '2026-01-01T12:00:00+00:00'}))
    (path / 'ES_J_CONV').write_bytes(b'x' * (RECOVERY_FILE_LIMIT + 123))
    (path / 'process.log').write_bytes(b'HEAD\n' + b'x' * RECOVERY_FILE_LIMIT + b'\nTAIL')
    return path


def _app(model, writable=True):
    return create_app(basepath=str(model.parent), read_write_enabled=writable, secret_key='history-test')


def _token(response):
    return re.search(r'name="review_token" value="([^"]+)"', response.data.decode()).group(1)


def test_inventory_files_and_control_versions_include_runner_and_editor(model, journal):
    record = load_model_parameter_file(str(model.parent), model_relpath=model.name, file_relpath='VADAT')
    saved = save_model_parameter_edit(str(model.parent), model_relpath=model.name, file_relpath='VADAT', expected_digest=record['digest'], contents='2 [LSTAR]\n')
    entries, warnings = list_archives(model)
    assert not warnings
    assert {entry['kind'] for entry in entries} == {'Runner journal', 'Editor checkpoint'}
    assert next(entry for entry in entries if entry['kind'] == 'Runner journal')['policy'] == 'Full-size'
    versions = control_versions(model, 'VADAT')
    assert {entry['backup_relpath'] for entry in versions} == {saved['backup_relpath'], str(journal.relative_to(model) / 'inputs/VADAT')}
    entry, files = archive_files(model, str(journal.relative_to(model)))
    assert next(row for row in files if row['path'] == 'inputs/VADAT')['target'] == 'VADAT'
    archived = load_archived_control(model, entry['id'], entry['id'] + '/inputs/VADAT')
    assert '2 [LSTAR]' in archived['diff'] and '0.5 [LSTAR]' in archived['diff']
    assert (model / 'VADAT').read_text() == '2 [LSTAR]\n'


@pytest.mark.parametrize('relative', ['../outside', '/tmp/file', '.cmfgen-runs/../VADAT', 'lte/not-archives/file', 'VADAT'])
def test_archive_paths_are_model_scoped(model, relative):
    with pytest.raises(HistoryError):
        safe_path(model, relative)


def test_symlinks_are_not_followed_and_links_can_be_deleted_without_touching_targets(model, journal, tmp_path):
    external = tmp_path / 'external'
    external.mkdir()
    (external / 'secret').write_text('unchanged')
    (journal / 'linked-dir').symlink_to(external)
    (journal / 'linked-file').symlink_to(external / 'secret')
    _, files = archive_files(model, str(journal.relative_to(model)))
    assert any(row['kind'] == 'link' for row in files)
    assert not any(row['path'].endswith('/secret') for row in files)
    with pytest.raises(HistoryError, match='symlink'):
        safe_path(model, str(journal.relative_to(model) / 'linked-file'))
    review = preview_housekeeping(model, [str(journal.relative_to(model))], 'delete')
    apply_housekeeping(model, review)
    assert (external / 'secret').read_text() == 'unchanged'


def test_compaction_keeps_history_and_working_outputs(model, journal):
    (model / 'ES_J_CONV').write_text('working output')
    archive_id = str(journal.relative_to(model))
    review = preview_housekeeping(model, [archive_id], 'compact')
    assert review['reclaimable'] > RECOVERY_FILE_LIMIT
    assert (journal / 'ES_J_CONV').exists()
    assert not apply_housekeeping(model, review)
    assert not (journal / 'ES_J_CONV').exists()
    assert (journal / 'plan.json').is_file()
    assert (journal / 'process.log').stat().st_size == RECOVERY_FILE_LIMIT
    assert (model / 'ES_J_CONV').read_text() == 'working output'


@pytest.mark.parametrize('state', ['active', 'unknown'])
def test_housekeeping_blocks_active_or_unobservable_models(model, journal, monkeypatch, state):
    review = preview_housekeeping(model, [str(journal.relative_to(model))], 'delete')
    monkeypatch.setattr(model_activity, 'inspect_model_activity', lambda _: {'safe_to_modify': False, 'reason': state})
    with pytest.raises(HistoryError, match=state):
        apply_housekeeping(model, review)
    assert journal.exists()


def test_housekeeping_rejects_changed_archive_and_parent_selection(model, journal):
    review = preview_housekeeping(model, [str(journal.relative_to(model))], 'delete')
    (journal / 'new-file').write_text('new')
    with pytest.raises(HistoryError, match='changed'):
        apply_housekeeping(model, review)
    with pytest.raises(HistoryError, match='recognized'):
        preview_housekeeping(model, ['.cmfgen-runs'], 'delete')
    assert journal.exists()


def test_history_readonly_browse_and_signed_review(model, journal):
    client = _app(model).test_client()
    url = '/model-actions/history/' + model.name
    page = client.get(url + '?' + urlencode({'archive': str(journal.relative_to(model))}))
    assert page.status_code == 200
    assert b'Compare VADAT' in page.data and b'Download' in page.data
    preview = client.post(url, data={'archive_id': str(journal.relative_to(model)), 'cleanup_action': 'delete'})
    assert b'Confirm deletion' in preview.data
    assert journal.exists()
    invalid = client.post(url, data={'action': 'apply', 'review_token': 'forged'})
    assert b'invalid' in invalid.data and journal.exists()
    applied = client.post(url, data={'action': 'apply', 'review_token': _token(preview)})
    assert applied.status_code == 302 and not journal.exists()
    readonly = _app(model, False).test_client()
    assert readonly.get(url).status_code == 200
    assert readonly.post(url, data={'cleanup_action': 'delete'}).status_code == 403


def test_editor_always_shows_history_and_loads_runner_controls_for_review(model, journal):
    client = _app(model).test_client()
    url = '/model-actions/edit/' + model.name
    page = client.get(url + '?file=VADAT')
    assert b'Saved versions (1)' in page.data
    archived = str(journal.relative_to(model) / 'inputs/VADAT')
    loaded = client.get(url + '?' + urlencode({'file': 'VADAT', 'archived_file': archived}))
    assert b'Loaded checkpoint' in loaded.data
    assert b'Save Reviewed Changes' in loaded.data
    assert (model / 'VADAT').read_text().startswith('1.0')
    record = load_model_parameter_file(str(model.parent), model_relpath=model.name, file_relpath='VADAT')
    from cmfgen_viewer.model_editor import review_model_parameter_edit
    review = review_model_parameter_edit(str(model.parent), model_relpath=model.name, file_relpath='VADAT', expected_digest=record['digest'], contents='0.5 [LSTAR]\nF [DO_HYDRO]\n')
    response = client.post(url, data={'action': 'save', 'file_relpath': 'VADAT', 'expected_digest': record['digest'], 'contents': review['contents'], 'reviewed_digest': review['proposed_digest']})
    assert response.status_code == 302
    assert (model / 'VADAT').read_text().startswith('0.5')
    assert list((model / '.cmfgen-viewer-backups').glob('VADAT.*.bak'))
    empty = client.get(url + '?file=IN_ITS')
    assert b'Saved versions (0)' in empty.data and b'No saved versions for this file' in empty.data


@pytest.fixture
def restart_journal(workspace):
    model, make_plan = workspace
    (model / 'POINT1').write_text('1 7 1 -1000\n')
    (model / 'SCRTEMP').write_bytes(b'original checkpoint' * 1000)
    (model / 'MODEL').write_text('original MODEL')
    (model / 'RVTJ').write_text(RVTJ_CORE)
    (model / 'HYD_L_DATA').symlink_to(model.parent / 'atomic/test.dat')
    code = SUCCESS + "\n(p/'POINT1').write_text('1 8 1 -1000\\n')\n(p/'SCRTEMP').write_bytes(b'updated checkpoint' * 1000)\n"
    result = run_plan(make_plan(code, keep_large_files=True))
    assert result['status'] == 'tested', result
    return model, Path(result['journal'])


def test_restart_restore_moves_current_state_and_preserves_source(restart_journal):
    model, journal = restart_journal
    prior = (journal / 'restart-before/SCRTEMP').read_bytes()
    working = (model / 'SCRTEMP').read_bytes()
    review = preview_restart(model, str(journal.relative_to(model)), keep_large_files=True)
    assert review['restart']['pointer']['iterations'] == 7
    assert (model / 'SCRTEMP').read_bytes() == working
    result = apply_restart(model, review)
    assert (model / 'SCRTEMP').read_bytes() == prior
    assert (model / 'POINT1').read_text() == '1 7 1 -1000\n'
    assert (model / result['backup'] / 'before/SCRTEMP').read_bytes() == working
    assert (journal / 'restart-before/SCRTEMP').read_bytes() == prior
    assert (model / MODEL_INPUT_MODIFIED_MARKER).is_file()
    assert not (model / 'MOD_SUM').exists()


@pytest.mark.parametrize('problem', ['missing_scratch', 'controls', 'changed_pointer', 'atomic_link'])
def test_restart_restore_refuses_incomplete_or_incompatible_sources(restart_journal, problem):
    model, journal = restart_journal
    if problem == 'missing_scratch':
        (journal / 'restart-before/SCRTEMP').unlink()
    elif problem == 'controls':
        (model / 'VADAT').write_text('2 [RSTAR]\n')
    elif problem == 'changed_pointer':
        (journal / 'restart-before/POINT1').write_text('1 9 1 -1000\n')
    else:
        (model / 'HYD_L_DATA').unlink()
    with pytest.raises(HistoryError):
        preview_restart(model, str(journal.relative_to(model)))
    assert (model / 'SCRTEMP').read_bytes().startswith(b'updated')


def test_restart_restore_rolls_back_after_marker_failure(restart_journal, monkeypatch):
    model, journal = restart_journal
    before = {name: (model / name).read_bytes() for name in ('POINT1', 'SCRTEMP', 'MODEL', 'RVTJ', 'MOD_SUM')}
    review = preview_restart(model, str(journal.relative_to(model)))
    def fail(*args, **kwargs):
        raise HistoryError('simulated marker failure')
    monkeypatch.setattr(history_restart, 'mark_model_inputs_modified', fail)
    with pytest.raises(HistoryError, match='simulated'):
        apply_restart(model, review)
    assert all((model / name).read_bytes() == data for name, data in before.items())


def test_restart_review_expires_when_current_output_changes(restart_journal):
    model, journal = restart_journal
    review = preview_restart(model, str(journal.relative_to(model)))
    (model / 'MODEL').write_text('changed after preview')
    with pytest.raises(HistoryError, match='changed'):
        apply_restart(model, review)


def test_lte_editor_discovers_parent_workflow_snapshots(model):
    lte = model / 'lte'
    _write_model(lte)
    archive = model / '.cmfgen-viewer-backups/lte-hydro/20260101T120000Z'
    (archive / 'lte').mkdir(parents=True)
    (archive / 'lte/VADAT').write_text('0.5 [LSTAR]\nF [DO_HYDRO]\n')
    client = _app(model).test_client()
    url = '/model-actions/edit/' + model.name + '/lte'
    page = client.get(url + '?file=VADAT')
    assert b'Saved versions (1)' in page.data
    loaded = client.get(url + '?' + urlencode({'file': 'VADAT', 'archived_file': str(archive.relative_to(model) / 'lte/VADAT')}))
    assert loaded.status_code == 200
    assert b'Loaded checkpoint' in loaded.data and b'Save Reviewed Changes' in loaded.data
    assert (lte / 'VADAT').read_text().startswith('1.0')


def test_restart_route_requires_signed_model_scoped_confirmation(restart_journal):
    model, journal = restart_journal
    client = _app(model).test_client()
    url = '/model-actions/history/' + model.name
    archive_id = str(journal.relative_to(model))
    preview = client.post(url, data={'action': 'preview_restart', 'archive': archive_id, 'keep_large_files': '1'})
    assert preview.status_code == 200
    assert b'Restore reviewed restart' in preview.data
    assert (model / 'POINT1').read_text().startswith('1 8')
    response = client.post(url, data={'action': 'restore_restart', 'review_token': _token(preview)})
    assert response.status_code == 302
    assert (model / 'POINT1').read_text().startswith('1 7')


def test_review_token_cannot_delete_another_models_archives(model, journal):
    other = model.parent / 'model_b'
    _write_model(other)
    client = _app(model).test_client()
    preview = client.post('/model-actions/history/' + model.name, data={'archive_id': str(journal.relative_to(model)), 'cleanup_action': 'delete'})
    response = client.post('/model-actions/history/' + other.name, data={'action': 'apply', 'review_token': _token(preview)})
    assert b'another model' in response.data
    assert journal.is_dir()


def test_compacted_archive_label_does_not_claim_full_recovery(model, journal):
    review = preview_housekeeping(model, [str(journal.relative_to(model))], 'compact')
    apply_housekeeping(model, review)
    entries, _ = list_archives(model)
    assert entries[0]['policy'] == 'Compacted'
    assert json.loads((journal / 'plan.json').read_text())['keep_large_files'] is True


def test_native_recovery_is_blocked_during_an_active_run(restart_journal, monkeypatch):
    model, journal = restart_journal
    review = preview_restart(model, str(journal.relative_to(model)))
    monkeypatch.setattr(model_activity, 'inspect_model_activity', lambda _: {'safe_to_modify': False, 'reason': 'active run'})
    with pytest.raises(HistoryError, match='active run'):
        apply_restart(model, review)
    assert (model / 'POINT1').read_text().startswith('1 8')


def test_native_recovery_rolls_back_a_partial_install(restart_journal, monkeypatch):
    model, journal = restart_journal
    before = {name: (model / name).read_bytes() for name in ('POINT1', 'SCRTEMP', 'MODEL', 'RVTJ', 'MOD_SUM')}
    (model / MODEL_INPUT_MODIFIED_MARKER).write_text('{"previous": true}')
    review = preview_restart(model, str(journal.relative_to(model)))
    original = history_restart.os.replace
    failed = False
    def replace(source, target):
        nonlocal failed
        if not failed and Path(source).parent.name == 'staged' and Path(target).name == 'MODEL':
            failed = True
            raise OSError('simulated partial install failure')
        return original(source, target)
    monkeypatch.setattr(history_restart.os, 'replace', replace)
    with pytest.raises(HistoryError, match='simulated partial'):
        apply_restart(model, review)
    assert failed
    assert all((model / name).read_bytes() == data for name, data in before.items())
    assert (model / MODEL_INPUT_MODIFIED_MARKER).read_text() == '{"previous": true}'


def test_native_recovery_removes_a_newer_pointer_that_was_not_in_the_archive(restart_journal):
    model, journal = restart_journal
    (model / 'POINT2').write_text('1 8 1 -1000\n')
    review = preview_restart(model, str(journal.relative_to(model)), keep_large_files=True)
    result = apply_restart(model, review)
    assert not (model / 'POINT2').exists()
    assert (model / result['backup'] / 'before/POINT2').exists()
