import os
from pathlib import Path

import pytest

from cmfgen_viewer.hydro_lte_alignment import preview_lte_hydro_alignment
from cmfgen_viewer.model_workflow import align_hydro_lte_composition, ModelWorkflowError
from cmfgen_viewer.app import create_app


@pytest.fixture
def workspace(tmp_path):
    from tests.test_model_workflow import _write_model, _write_templates, _make_outputs_fresh
    from cmfgen_viewer.model_workflow import prepare_lte_hydro_workspace
    model = _write_model(tmp_path)
    _write_templates(tmp_path)
    prepare_lte_hydro_workspace(str(tmp_path), model_relpath=model.name)
    _make_outputs_fresh(model)
    target = model / 'lte/HYDRO_PARAMS'
    target.write_text(target.read_text().replace('1.30563 [MU_ATOM]', '1.4062 [MU_ATOM]'))
    return model


def test_viewer_applies_lte_composition_and_preserves_lte(workspace):
    model = workspace
    target = model / 'lte/HYDRO_PARAMS'
    table = model / 'lte/ROSSELAND_LTE_TAB'
    before = table.read_bytes(), table.stat().st_mtime_ns
    original = target.read_bytes()
    preview = preview_lte_hydro_alignment(model)
    assert preview['ready'] and preview['changed']
    assert preview['proposed'] == 1.30563
    client = create_app(basepath=str(model.parent), read_write_enabled=True).test_client()
    page = client.get('/model-actions/lte-hydro/' + model.name)
    assert b'Apply LTE parameters' in page.data
    response = client.post('/model-actions/lte-hydro/' + model.name,
        data={'action': 'align_lte_composition', 'expected_digest': preview['digest']})
    assert response.status_code == 302
    assert b'1.30563' in target.read_bytes()
    assert (model / 'lte/RVSIG_COL_NEW').stat().st_mtime_ns < target.stat().st_mtime_ns
    assert (table.read_bytes(), table.stat().st_mtime_ns) == before
    backup = next((model / '.cmfgen-viewer-backups/lte-composition').glob('*/HYDRO_PARAMS'))
    assert backup.read_bytes() == original
    assert not preview_lte_hydro_alignment(model)['changed']


@pytest.mark.parametrize('header', ['', '! Mean atomic weight (atoms/ions only) NaN',
    '! Mean atomic weight (atoms/ions only) 0',
    '! Mean atomic weight (atoms/ions only) 1.3\n! Mean atomic weight (atoms/ions only) 1.4'])
def test_reject_invalid_metadata(workspace, header):
    table = workspace / 'lte/ROSSELAND_LTE_TAB'
    lines = table.read_text().splitlines()
    table.write_text(header + '\n' + '\n'.join(lines[1:]) + '\n')
    assert not preview_lte_hydro_alignment(workspace)['ready']


@pytest.mark.parametrize('changed', ['ROSSELAND_LTE_TAB', 'HYDRO_PARAMS', 'VADAT'])
def test_reject_changed_preview(workspace, changed):
    preview = preview_lte_hydro_alignment(workspace)
    target = workspace / 'lte/HYDRO_PARAMS'
    path = workspace / 'lte' / changed
    path.write_text(path.read_text() + '\n! changed\n')
    before = target.read_bytes()
    with pytest.raises(ModelWorkflowError):
        align_hydro_lte_composition(str(workspace.parent), model_relpath=workspace.name,
                                   expected_digest=preview['digest'])
    assert target.read_bytes() == before


def test_reject_stale_table(workspace):
    table = workspace / 'lte/ROSSELAND_LTE_TAB'
    os.utime(table, ns=(1, 1))
    assert 'stale' in ' '.join(preview_lte_hydro_alignment(workspace)['issues'])


def test_alignment_refuses_active_workspace(workspace, monkeypatch):
    from cmfgen_viewer import model_activity
    preview = preview_lte_hydro_alignment(workspace)
    before = (workspace / 'lte/HYDRO_PARAMS').read_bytes()
    monkeypatch.setattr(model_activity, 'inspect_model_activity',
                        lambda _: {'safe_to_modify': False, 'reason': 'active model'})
    with pytest.raises(ModelWorkflowError, match='active model'):
        align_hydro_lte_composition(str(workspace.parent), model_relpath=workspace.name,
                                   expected_digest=preview['digest'])
    assert (workspace / 'lte/HYDRO_PARAMS').read_bytes() == before


def test_read_only_viewer_refuses_alignment(workspace):
    client = create_app(basepath=str(workspace.parent)).test_client()
    response = client.post('/model-actions/lte-hydro/' + workspace.name,
                           data={'action': 'align_lte_composition'})
    assert response.status_code == 403
