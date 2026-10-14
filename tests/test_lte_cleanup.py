"""LTE cleanup preserves results and diagnostics and remains recoverable."""

import os
from pathlib import Path

import pytest

from cmfgen_viewer import lte_cleanup, model_activity, model_workflow
from cmfgen_viewer.app import create_app
from cmfgen_viewer.lte_cleanup import LteCleanupError, archive_lte_temporaries, inspect_lte_cleanup
from cmfgen_viewer.model_workflow import ModelWorkflowError, cleanup_lte_workspace, promote_lte_hydro_results
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner_promotion import build_promotion_plan
from test_runner_promotion import promotable_model


def _temporary_files(lte):
    names = ['HIOUT', 'POPHYD', 'fort.123', 'CFDAT_OUT', 'BA_ASCI_N_D_1', 'LTE_SCRATCH']
    for name in names:
        (lte / name).write_text(name)
    return names


def test_candidate_policy_preserves_results_diagnostics_links_and_nested_files(tmp_path):
    lte = tmp_path / 'lte'
    lte.mkdir()
    names = _temporary_files(lte)
    for name in [*lte_cleanup.RETAINED_FILES, 'README', 'fort.notes', 'user-data.txt', 'POPHYD_IN']:
        (lte / name).write_text('retain')
    (lte / 'POP_DIRECTORY').mkdir()
    (lte / 'POP_DIRECTORY' / 'HIOUT').write_text('nested')
    external = tmp_path / 'external'
    external.write_text('atomic data')
    external.chmod(0o600)
    (lte / 'POPLINK').symlink_to(external)
    os.link(external, lte / 'POPHARDLINK')
    plan = inspect_lte_cleanup(lte)
    assert set(item['name'] for item in plan['entries']) == set(names)
    assert plan['total_size'] == sum(len(name) for name in names)
    result = archive_lte_temporaries(lte, tmp_path / 'archive', expected_entries=plan['entries'])
    assert set(result['removed_files']) == set(names)
    for name in names:
        assert not (lte / name).exists()
        assert (tmp_path / 'archive' / name).read_text() == name
    for name in lte_cleanup.RETAINED_FILES:
        assert (lte / name).read_text() == 'retain'
    assert (lte / 'POP_DIRECTORY' / 'HIOUT').read_text() == 'nested'
    assert (lte / 'POPLINK').is_symlink()
    assert external.stat().st_mode & 0o777 == 0o600
    assert inspect_lte_cleanup(lte)['entry_count'] == 0


@pytest.mark.parametrize('change', ['content', 'new_file', 'symlink'])
def test_cleanup_rejects_changes_since_review_without_moving_files(tmp_path, change):
    lte = tmp_path / 'lte'
    lte.mkdir()
    names = _temporary_files(lte)
    plan = inspect_lte_cleanup(lte)
    if change == 'content':
        (lte / 'HIOUT').write_text('changed')
    elif change == 'new_file':
        (lte / 'NEWOUT').write_text('new')
    else:
        (lte / 'HIOUT').unlink()
        (lte / 'HIOUT').symlink_to(lte / 'POPHYD')
    with pytest.raises(LteCleanupError, match='changed since review'):
        archive_lte_temporaries(lte, tmp_path / 'archive', expected_entries=plan['entries'])
    assert all((lte / name).exists() for name in names)
    assert not (tmp_path / 'archive').exists()


def test_cleanup_restores_files_if_a_move_fails(tmp_path, monkeypatch):
    lte = tmp_path / 'lte'
    lte.mkdir()
    names = _temporary_files(lte)
    original = lte_cleanup.os.replace
    failed = False

    def replace(source, destination):
        nonlocal failed
        if Path(source).name == 'POPHYD' and Path(source).parent == lte and not failed:
            failed = True
            raise OSError('simulated move failure')
        return original(source, destination)

    monkeypatch.setattr(lte_cleanup.os, 'replace', replace)
    with pytest.raises(OSError, match='simulated'):
        archive_lte_temporaries(lte, tmp_path / 'archive')
    assert all((lte / name).read_text() == name for name in names)


def test_runner_promotion_archives_temporary_files_and_keeps_results(promotable_model):
    lte = promotable_model / 'lte'
    names = _temporary_files(lte)
    before = (lte / 'ROSSELAND_LTE_TAB').read_bytes()
    plan = build_promotion_plan(promotable_model)
    assert plan['lte_cleanup']['entry_count'] == len(names)
    result = run_plan(plan)
    assert result['status'] == 'succeeded'
    cleanup = result['promotion']['lte_cleanup']
    assert cleanup['removed_count'] == len(names)
    archive = Path(cleanup['archive_path'])
    assert archive.parent.name == 'lte' and archive.name == 'temporary'
    assert all((archive / name).read_text() == name for name in names)
    assert (lte / 'ROSSELAND_LTE_TAB').read_bytes() == before
    assert model_workflow.inspect_lte_hydro_workflow(str(promotable_model.parent), model_relpath=promotable_model.name)['promoted']


def test_promotion_rejects_changed_cleanup_candidates_before_mutations(promotable_model):
    lte = promotable_model / 'lte'
    _temporary_files(lte)
    plan = build_promotion_plan(promotable_model)
    original = (promotable_model / 'RVSIG_COL').read_bytes()
    (lte / 'HIOUT').write_text('changed since plan')
    result = run_plan(plan)
    assert result['status'] == 'failed'
    assert 'changed since review' in result['passes'][0]['problems'][0]
    assert (promotable_model / 'RVSIG_COL').read_bytes() == original
    assert (promotable_model / 'POINT1').exists()
    assert (lte / 'HIOUT').read_text() == 'changed since plan'


def test_promotion_rolls_back_cleanup_if_marking_solution_fails(promotable_model, monkeypatch):
    lte = promotable_model / 'lte'
    names = _temporary_files(lte)
    before_root = (promotable_model / 'VADAT').read_bytes()
    before_lte = (lte / 'VADAT').read_bytes()

    def fail(*args, **kwargs):
        raise ModelWorkflowError('simulated marker failure')

    monkeypatch.setattr(model_workflow, 'mark_model_inputs_modified', fail)
    with pytest.raises(ModelWorkflowError, match='simulated'):
        promote_lte_hydro_results(str(promotable_model.parent), model_relpath=promotable_model.name)
    assert (promotable_model / 'VADAT').read_bytes() == before_root
    assert (lte / 'VADAT').read_bytes() == before_lte
    assert (promotable_model / 'POINT1').exists()
    assert all((lte / name).read_text() == name for name in names)


@pytest.mark.parametrize('state', ['active', 'unknown'])
def test_independent_cleanup_refuses_non_idle_models(promotable_model, monkeypatch, state):
    names = _temporary_files(promotable_model / 'lte')
    monkeypatch.setattr(model_activity, 'inspect_model_activity', lambda _: {'safe_to_modify': False, 'reason': state})
    with pytest.raises(ModelWorkflowError, match=state):
        cleanup_lte_workspace(str(promotable_model.parent), model_relpath=promotable_model.name)
    assert all((promotable_model / 'lte' / name).exists() for name in names)


def test_cleanup_ui_works_after_promotion_and_is_read_write_gated(promotable_model):
    promote_lte_hydro_results(str(promotable_model.parent), model_relpath=promotable_model.name)
    names = _temporary_files(promotable_model / 'lte')
    app = create_app(basepath=str(promotable_model.parent), read_write_enabled=True, secret_key='test')
    client = app.test_client()
    url = '/model-actions/lte-hydro/' + promotable_model.name
    page = client.get(url)
    assert b'Clean LTE Temporary Files' in page.data
    assert b'HIOUT' in page.data
    response = client.post(url, data={'action': 'cleanup_lte'}, follow_redirects=True)
    assert response.status_code == 200
    assert response.history[0].headers['Location'].endswith('#result-review')
    assert f'Cleaned {len(names)} LTE temporary file(s)'.encode() in response.data
    assert b'Clean LTE Temporary Files' not in response.data
    assert all(not (promotable_model / 'lte' / name).exists() for name in names)
    archive = next((promotable_model / '.cmfgen-viewer-backups/lte-cleanup').iterdir())
    assert all((archive / name).read_text() == name for name in names)
    assert archive.stat().st_mode & 0o777 == 0o755
    read_only = create_app(basepath=str(promotable_model.parent), secret_key='test')
    assert read_only.test_client().post(url, data={'action': 'cleanup_lte'}).status_code == 403


def test_detached_promotion_review_includes_cleanup_candidates(promotable_model):
    from cmfgen_viewer.detached_jobs import fingerprint

    before = build_promotion_plan(promotable_model)
    (promotable_model / 'lte/HIOUT').write_text('new temporary output')
    after = build_promotion_plan(promotable_model)
    assert before['inputs'] == after['inputs']
    assert fingerprint(before) != fingerprint(after)
