"""Compact fresh-input bundles restore a coherent startup without solver state."""
import json
from pathlib import Path
import re

import pytest

from cmfgen_viewer import history_inputs, model_activity
from cmfgen_viewer.app import create_app
from cmfgen_viewer.history_inputs import preview_inputs, apply_inputs, capture_inputs
from cmfgen_viewer.model_editor import MODEL_INPUT_MODIFIED_MARKER
from cmfgen_viewer.model_history import HistoryError, list_archives, preview_housekeeping, apply_housekeeping
from cmfgen_viewer.recovery_files import RECOVERY_FILE_LIMIT, compact_recovery
from cmfgen_viewer.runner import run_plan
from test_runner import workspace, SUCCESS


@pytest.fixture
def bundle(workspace):
    model, make_plan = workspace
    (model / 'He2_IN').write_bytes(b'populations' * (RECOVERY_FILE_LIMIT // 10 + 1))
    (model / 'SMALLOUT').write_text('old calculated output')
    result = run_plan(make_plan(SUCCESS))
    assert result['status'] == 'tested', result
    return model, Path(result['journal']), make_plan


def _id(model, archive):
    return archive.relative_to(model).as_posix()


def test_compact_bundle_retains_large_needed_inputs_and_discards_small_state(bundle):
    model, archive, _ = bundle
    manifest = json.loads((archive / 'fresh-inputs.json').read_text())
    assert manifest['complete']
    assert (archive / 'inputs/He2_IN').stat().st_size > RECOVERY_FILE_LIMIT
    assert not (archive / 'test/MODEL').exists()
    assert not (archive / 'test/RVTJ').exists()
    assert (model / 'SMALLOUT').read_text() == 'old calculated output'
    review = preview_inputs(model, _id(model, archive))
    assert {'He2_IN', 'GAMMAS_IN', 'VADAT', 'MODEL_SPEC', 'IN_ITS'} <= {f['target'] for f in review['files']}
    assert next(a for a in list_archives(model)[0] if a['id'] == _id(model, archive))['fresh_inputs']
    compact_recovery(archive)
    assert preview_inputs(model, _id(model, archive))['files'] == review['files']


def test_restore_inputs_replaces_controls_and_retires_checkpoint_and_old_results(bundle):
    model, archive, _ = bundle
    original = (archive / 'inputs/He2_IN').read_bytes()
    (model / 'VADAT').write_text('4 [RSTAR]\n')
    (model / 'IN_ITS').write_text('100 [NUM_ITS]\n')
    (model / 'He2_IN').write_text('changed populations')
    (model / 'Extra_IN').write_text('belongs to current setup')
    (model / 'POINT1').write_text('checkpoint pointer')
    (model / 'SCRTEMP').write_text('small checkpoint')
    obs = model / 'obs'
    obs.mkdir()
    (obs / 'obs_fin').write_text('old spectrum')
    (obs / 'CMF_FLUX_PARAM_INIT').write_text('observer controls')
    review = preview_inputs(model, _id(model, archive))
    restored = apply_inputs(model, review)
    assert (model / 'VADAT').read_text() == '1 [RSTAR]\n'
    assert (model / 'IN_ITS').read_text() == '2 [NUM_ITS]\n'
    assert (model / 'He2_IN').read_bytes() == original
    for name in ('POINT1', 'SCRTEMP', 'MODEL', 'RVTJ', 'SMALLOUT', 'Extra_IN', 'HYD_L_DATA', 'obs/obs_fin'):
        assert not (model / name).exists() and not (model / name).is_symlink()
    assert (model / MODEL_INPUT_MODIFIED_MARKER).exists()
    assert (obs / 'CMF_FLUX_PARAM_INIT').read_text() == 'observer controls'
    backup = model / restored['backup']
    assert (backup / 'before/VADAT').read_text() == '4 [RSTAR]\n'
    assert not (backup / 'before/SCRTEMP').exists()
    assert (archive / 'inputs/He2_IN').read_bytes() == original


@pytest.mark.parametrize('change', ['source', 'current', 'atomic'])
def test_changed_sources_live_files_and_dependencies_block_restore(bundle, change):
    model, archive, _ = bundle
    review = preview_inputs(model, _id(model, archive))
    if change == 'source':
        (archive / 'inputs/He2_IN').write_text('tampered')
    elif change == 'current':
        (model / 'IN_ITS').write_text('33 [NUM_ITS]')
    else:
        (model.parent / 'atomic/test.dat').write_text('changed atomic environment')
    with pytest.raises((HistoryError, FileNotFoundError), match='changed|incomplete'):
        apply_inputs(model, review)
    assert (model / 'MODEL').exists()


def test_restore_rolls_back_all_inputs_state_and_links_on_failure(bundle, monkeypatch):
    model, archive, _ = bundle
    (model / 'VADAT').write_text('4 [RSTAR]\n')
    (model / 'SCRTEMP').write_text('keep checkpoint')
    link = (model / 'HYD_L_DATA').readlink()
    before = (model / 'MODEL').read_bytes()
    review = preview_inputs(model, _id(model, archive))
    monkeypatch.setattr(history_inputs, 'mark_model_inputs_modified', lambda *a, **k:
                        (_ for _ in ()).throw(OSError('simulated commit failure')))
    with pytest.raises(HistoryError, match='simulated'):
        apply_inputs(model, review)
    assert (model / 'VADAT').read_text() == '4 [RSTAR]\n'
    assert (model / 'SCRTEMP').read_text() == 'keep checkpoint'
    assert (model / 'MODEL').read_bytes() == before
    assert (model / 'HYD_L_DATA').readlink() == link


def test_missing_seed_does_not_make_a_continuation_bundle_restorable(workspace):
    model, make_plan = workspace
    plan = make_plan()
    archive = model / '.cmfgen-runs/missing-seed'
    archive.mkdir(parents=True)
    (archive / 'plan.json').write_text(json.dumps(plan))
    (model / 'He2_IN').unlink()
    capture_inputs(model, archive, plan)
    with pytest.raises(HistoryError, match='incomplete.*He2_IN'):
        preview_inputs(model, _id(model, archive))


def test_symlinked_archived_input_and_path_traversal_are_rejected(bundle, tmp_path):
    model, archive, _ = bundle
    source = archive / 'inputs/He2_IN'
    source.unlink()
    external = tmp_path / 'external'
    external.write_text('retain')
    source.symlink_to(external)
    with pytest.raises(HistoryError):
        preview_inputs(model, _id(model, archive))
    with pytest.raises(HistoryError):
        preview_inputs(model, '../external')
    assert external.read_text() == 'retain'


@pytest.mark.parametrize('state', ['active', 'unknown'])
def test_restore_requires_idle_visible_model(bundle, monkeypatch, state):
    model, archive, _ = bundle
    review = preview_inputs(model, _id(model, archive))
    monkeypatch.setattr(model_activity, 'inspect_model_activity', lambda *_:
                        {'safe_to_modify': False, 'reason': state})
    with pytest.raises(HistoryError, match=state):
        apply_inputs(model, review)
    assert (model / 'MODEL').exists()


def test_history_ui_reviews_restores_and_respects_readonly_and_forged_tokens(bundle):
    model, archive, _ = bundle
    app = create_app(basepath=str(model.parent), read_write_enabled=True, secret_key='fresh-input-tests')
    app.testing = True
    app.config['CMFGEN_VIEWER']['summary_cache_db'] = str(model.parent / 'cache.sqlite')
    client = app.test_client()
    url = '/model-actions/history/' + model.name
    page = client.get(url, query_string={'archive': _id(model, archive)})
    assert b'Preview input restoration' in page.data
    preview = client.post(url, data={'action': 'preview_inputs', 'archive': _id(model, archive)})
    assert b'Restore reviewed inputs' in preview.data
    assert (model / 'MODEL').exists()
    token = re.search(r'name="review_token" value="([^"]+)"', preview.get_data(as_text=True)).group(1)
    forged = client.post(url, data={'action': 'restore_inputs', 'review_token': 'forged'})
    assert b'invalid' in forged.data and (model / 'MODEL').exists()
    response = client.post(url, data={'action': 'restore_inputs', 'review_token': token})
    assert response.status_code == 302 and '/main-computation/' in response.location
    assert not (model / 'MODEL').exists() and (model / MODEL_INPUT_MODIFIED_MARKER).exists()
    app.config['CMFGEN_VIEWER']['read_write_enabled'] = False
    assert client.post(url, data={'action': 'restore_inputs', 'review_token': token}).status_code == 403


def test_synthetic_temperature_link_is_not_a_missing_fresh_input(workspace):
    model, make_plan = workspace
    (model / 'T_IN').symlink_to('He2_IN')
    result = run_plan(make_plan())
    assert result['status'] == 'tested', result
    archive = Path(result['journal'])
    review = preview_inputs(model, _id(model, archive))
    assert 'T_IN' not in {entry['target'] for entry in review['files']}


def test_optional_current_atomic_recipe_is_retired_when_not_in_saved_inputs(bundle):
    model, archive, _ = bundle
    (model / 'atomic_links.json').write_text('{"base": {"WRONG": "different"}}')
    review = preview_inputs(model, _id(model, archive))
    apply_inputs(model, review)
    assert not (model / 'atomic_links.json').exists()
    assert (model / 'batch_ins.sh').read_text().startswith('ln -sf')


def test_missing_or_malformed_archive_is_not_offered_as_a_restore(bundle):
    model, archive, _ = bundle
    (archive / 'inputs/He2_IN').unlink()
    with pytest.raises(HistoryError, match='missing: He2_IN'):
        preview_inputs(model, _id(model, archive))
    path = archive / 'fresh-inputs.json'
    manifest = json.loads(path.read_text())
    manifest['files'] = 'invalid'
    path.write_text(json.dumps(manifest))
    with pytest.raises(HistoryError, match='Malformed'):
        preview_inputs(model, _id(model, archive))


def test_recovery_policy_file_cannot_write_through_an_archived_symlink(tmp_path):
    external = tmp_path / 'external'
    external.write_text('retain')
    archive = tmp_path / 'archive'
    archive.mkdir()
    (archive / '.recovery-policy.json').symlink_to(external)
    compact_recovery(archive)
    assert external.read_text() == 'retain'
    assert not (archive / '.recovery-policy.json').is_symlink()


def test_input_archiving_keeps_working_disk_headroom(workspace, monkeypatch):
    from types import SimpleNamespace
    model, make_plan = workspace
    plan = make_plan()
    archive = model / '.cmfgen-runs/no-room-for-inputs'
    archive.mkdir(parents=True)
    (archive / 'plan.json').write_text(json.dumps(plan))
    monkeypatch.setattr(history_inputs.shutil, 'disk_usage', lambda *_: SimpleNamespace(free=1024**3))
    manifest = capture_inputs(model, archive, plan)
    assert not manifest['complete'] and 'Insufficient space' in manifest['missing'][0]
    assert not list((archive / 'inputs').iterdir())
    assert (model / 'He2_IN').read_text() == 'helium'
