"""Default cleanup covers known workspaces while preserving model history."""
import json
from pathlib import Path

import pytest

from cmfgen_viewer.app import create_app
from cmfgen_viewer.model_cli import main
from cmfgen_viewer.model_staging import plan_model_cleanup, cleanup_model_directory, ModelStagingError
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner_cleanup import build_cleanup_plan
from test_model_cli import solution, isolated_config


def populate(model):
    for workspace in ('', 'lte', 'obs'):
        folder = model / workspace
        folder.mkdir(exist_ok=True)
        for name in ('BAMAT', 'VADAT', 'MODEL_SPEC', 'HeI_IN', 'POINT1', 'SCRTEMP'):
            (folder / name).write_text(name)
        (folder / '.cmfgen-viewer-input-modified.json').write_text('{}')
        for archive in ('.cmfgen-runs', '.cmfgen-viewer-backups'):
            (folder / archive).mkdir(exist_ok=True)
            (folder / archive / 'old').write_text('history')
    (model / 'lte/POPHYD').write_text('temporary population')
    (model / 'lte/HeIOUT').write_text('temporary output')
    (model / 'lte/OUTLTE').write_text('retained result')
    (model / 'obs/obs_fin').write_text('spectrum')
    (model / 'obs/fort.63').write_text('scratch')
    (model / 'lte/nested').mkdir()
    (model / 'lte/nested/POPHYD').write_text('retain')


def test_default_cli_cleans_all_workspaces_and_archives_qualified_paths(solution, tmp_path, capsys):
    populate(solution)
    target = tmp_path / 'atomic'
    target.write_text('retain target')
    for folder in (solution, solution / 'lte', solution / 'obs'):
        (folder / 'atomic-link').symlink_to(target)
        (folder / 'broken-link').symlink_to(tmp_path / 'missing')
    assert main(['cleanup', str(solution), '--plan', '--json']) == 0
    plan = json.loads(capsys.readouterr().out)
    names = {entry['name'] for entry in plan['entries']}
    assert {'BAMAT', 'lte/BAMAT', 'obs/BAMAT', 'lte/POPHYD', 'lte/HeIOUT', 'obs/fort.63'} <= names
    assert (solution / 'lte/POPHYD').exists()
    assert main(['cleanup', str(solution), '--json']) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved['status'] == 'succeeded'
    archive = Path(saved['result']['cleanup']['archive_path'])
    for name in names:
        assert not (solution / name).exists() and not (solution / name).is_symlink()
        if name.endswith(('atomic-link', 'broken-link')):
            assert (archive / name).is_symlink()
        else:
            assert not (archive / name).exists()
    for workspace in ('', 'lte', 'obs'):
        for name in ('VADAT', 'MODEL_SPEC', 'HeI_IN', 'POINT1', 'SCRTEMP',
                     '.cmfgen-viewer-input-modified.json', '.cmfgen-runs/old', '.cmfgen-viewer-backups/old'):
            assert (solution / workspace / name).exists()
    for name in ('HeIOUT', 'lte/OUTLTE', 'lte/nested/POPHYD', 'obs/obs_fin'):
        assert (solution / name).exists()
    assert target.read_text() == 'retain target'
    assert main(['cleanup', str(solution), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'unchanged'


def test_cli_selection_uses_workspace_relative_names(solution, capsys):
    populate(solution)
    assert main(['cleanup', str(solution), '--file', 'lte/BAMAT', '--file', 'obs/fort.63', '--json']) == 0
    saved = json.loads(capsys.readouterr().out)
    assert set(saved['result']['cleanup']['removed_files']) == {'lte/BAMAT', 'obs/fort.63'}
    assert (solution / 'BAMAT').exists() and (solution / 'obs/BAMAT').exists()
    assert (solution / 'lte/POPHYD').exists()


def test_runner_cleanup_stage_uses_same_workspace_policy(solution):
    populate(solution)
    result = run_plan(build_cleanup_plan(solution))
    assert result['status'] == 'succeeded'
    assert {'BAMAT', 'lte/BAMAT', 'obs/BAMAT', 'lte/POPHYD'} <= set(result['cleanup']['removed_files'])
    assert (solution / 'obs/obs_fin').exists()


def test_symlinked_workspaces_are_removed_without_traversing(solution, tmp_path):
    target = tmp_path / 'external'
    target.mkdir()
    (target / 'BAMAT').write_text('retain')
    # The solution fixture already contains a real observer workspace.
    (solution / 'lte').symlink_to(target, target_is_directory=True)
    plan = build_cleanup_plan(solution)
    assert plan['selected_names'] == ['lte']
    result = run_plan(plan)
    assert result['status'] == 'succeeded'
    assert not (solution / 'lte').is_symlink()
    assert (target / 'BAMAT').read_text() == 'retain'


def test_changed_workspace_file_is_rejected_before_any_cleanup(solution):
    populate(solution)
    plan = build_cleanup_plan(solution)
    (solution / 'lte/POPHYD').write_text('changed after preview')
    result = run_plan(plan)
    assert result['status'] == 'failed'
    assert (solution / 'BAMAT').exists() and (solution / 'obs/BAMAT').exists()
    assert (solution / 'lte/POPHYD').exists()


@pytest.mark.parametrize('selection', ['../BAMAT', 'obs/../BAMAT', 'lte/nested/POPHYD', '/tmp/BAMAT'])
def test_cleanup_selection_cannot_escape_the_known_workspace_roots(solution, selection):
    populate(solution)
    with pytest.raises(ModelStagingError, match='invalid file name'):
        cleanup_model_directory(str(solution.parent), model_relpath=solution.name, selected_names=[selection])
    assert (solution / 'BAMAT').exists()


def test_ui_previews_and_removes_candidates_in_all_workspaces(solution):
    populate(solution)
    app = create_app(basepath=str(solution.parent), read_write_enabled=True, secret_key='workspace-cleanup-tests')
    app.testing = True
    app.config['CMFGEN_VIEWER']['summary_cache_db'] = str(solution.parent / 'summary.sqlite')
    browser = app.test_client()
    url = '/model-actions/cleanup/' + solution.name
    preview = browser.get(url)
    assert preview.status_code == 200
    assert b'value="lte/POPHYD"' in preview.data and b'value="obs/fort.63"' in preview.data
    plan = plan_model_cleanup(str(solution.parent), model_relpath=solution.name)
    response = browser.post(url, data={'confirm_cleanup': '1', 'entries': [entry['name'] for entry in plan['entries']]})
    assert response.status_code == 302
    assert not (solution / 'lte/POPHYD').exists() and not (solution / 'obs/fort.63').exists()
    assert (solution / '.cmfgen-runs/old').exists() and (solution / 'lte/.cmfgen-viewer-backups/old').exists()
