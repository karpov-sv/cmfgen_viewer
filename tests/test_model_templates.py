from pathlib import Path
import shutil

import pytest

from cmfgen_viewer.app import create_app
from cmfgen_viewer.model_staging import create_model_from_solution, plan_model_from_solution
from cmfgen_viewer.model_templates import resolve_model_template
from cmfgen_viewer.runner_preparation import build_preparation_plan
from cmfgen_viewer.runner import run_plan
from test_model_staging import _write_solution
from test_model_workflow import _write_initializable_workspace_inputs


def _template(root, relative, contents):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    return path


def test_template_priority_and_independent_fallback(tmp_path):
    model = tmp_path / 'grid/model'
    model.mkdir(parents=True)
    explicit = tmp_path / 'custom'
    outer = _template(tmp_path / 'templates', 'lte/GRID_PARAMS', 'outer')
    inner = _template(model.parent / 'templates', 'lte/GRID_PARAMS', 'inner')
    chosen = _template(explicit, 'lte/GRID_PARAMS', 'explicit')
    assert resolve_model_template(model, 'lte/GRID_PARAMS')['path'] == str(inner)
    assert resolve_model_template(model, 'lte/GRID_PARAMS', template_root=explicit)['path'] == str(chosen)
    own = model / 'lte/GRID_PARAMS'
    own.parent.mkdir()
    own.write_text('own')
    assert resolve_model_template(model, 'lte/GRID_PARAMS', template_root=explicit)['origin'] == 'source model'
    own.unlink()
    inner.unlink()
    assert resolve_model_template(model, 'lte/GRID_PARAMS')['path'] == str(outer)
    assert resolve_model_template(model, 'lte/HYDRO_PARAMS', template_root=explicit)['origin'] == 'packaged templates'
    outer.unlink()
    assert resolve_model_template(model, 'lte/GRID_PARAMS')['origin'] == 'packaged templates'


def test_examples_directory_is_not_an_alias(tmp_path):
    model = tmp_path / 'model'
    model.mkdir()
    _template(tmp_path / 'examples', 'lte/GRID_PARAMS', 'do not use')
    result = resolve_model_template(model, 'lte/GRID_PARAMS')
    assert result['origin'] == 'packaged templates'


@pytest.mark.parametrize('path', ['/absolute', '../outside'])
def test_template_paths_cannot_escape_layout(tmp_path, path):
    with pytest.raises(ValueError):
        resolve_model_template(tmp_path, path)


def test_packaged_preparation_without_tree_templates_or_cleanup(tmp_path):
    model = _write_initializable_workspace_inputs(tmp_path)
    shutil.rmtree(tmp_path / 'templates')
    (model / 'clean.sh').unlink()
    plan = build_preparation_plan(model)
    assert plan['ready'] and plan['hydro_alignment']['ready']
    support = [item for item in plan['copies'] if item.get('origin')]
    assert len(support) == 4
    assert all(item['origin'] == 'packaged templates' for item in support)
    events = []
    result = run_plan(plan, events.append)
    assert result['status'] == 'succeeded' and result['preparation']['hydro_initialized']
    for name in ('GRID_PARAMS', 'ltebat.sh', 'HYDRO_PARAMS', 'clean.sh'):
        assert (model / 'lte' / name).is_file()
    assert not (model / 'clean.sh').exists()
    assert (model / 'lte/ltebat.sh').is_file()
    assert (model / 'lte/ltebat.sh').stat().st_mode & 0o111


def test_viewer_uses_explicit_root_and_shows_provenance(tmp_path):
    model = _write_initializable_workspace_inputs(tmp_path)
    explicit = tmp_path / 'custom'
    _template(explicit, 'lte/GRID_PARAMS', 'explicit grid')
    app = create_app(basepath=str(tmp_path), template_root=str(explicit), read_write_enabled=True)
    client = app.test_client()
    page = client.get('/model-actions/lte-hydro/model_a')
    assert page.status_code == 200 and b'explicit templates' in page.data
    response = client.post('/model-actions/lte-hydro/model_a', data={'action': 'prepare'})
    assert response.status_code == 302
    assert (model / 'lte/GRID_PARAMS').read_text() == 'explicit grid'


def test_copy_fills_setup_from_templates_without_fabricating_physical_inputs(tmp_path):
    model = tmp_path / 'source'
    _write_solution(model)
    shutil.rmtree(model / 'obs')
    for name in ('batch.sh', 'IN_ITS', 'clean.sh'):
        (model / name).unlink()
    explicit = tmp_path / 'custom'
    batch = _template(explicit, 'batch.sh', '#!/bin/sh\n# configured batch\n')
    batch.chmod(0o750)
    _template(explicit, 'IN_ITS', '2 [NUM_ITS]\n')
    _template(explicit, 'obs/batobs.sh', '#!/bin/sh\n')
    _template(explicit, 'obs/CMF_FLUX_PARAM_INIT', 'F [FLUX_CAL_ONLY]\n')
    _template(explicit, 'VADAT', 'must not be used')
    _template(explicit, 'MODEL_SPEC', 'must not be used')
    plan = plan_model_from_solution(str(tmp_path), source_relpath='source', destination_relpath='copy', template_root=str(explicit))
    assert plan['ready'] and plan['observer_setup']
    cleanup = next(item for item in plan['entries'] if item['destination_name'] == 'clean.sh')
    assert cleanup['origin'] == 'packaged templates'
    create_model_from_solution(str(tmp_path), source_relpath='source', destination_relpath='copy', template_root=str(explicit))
    assert (tmp_path / 'copy/batch.sh').read_bytes() == batch.read_bytes()
    assert (tmp_path / 'copy/batch.sh').stat().st_mode & 0o777 == 0o755
    assert (tmp_path / 'copy/obs/CMF_FLUX_PARAM_INIT').is_file()
    assert (tmp_path / 'copy/VADAT').read_bytes() == (model / 'VADAT').read_bytes()
    assert not (tmp_path / 'copy/lte').exists()
    (model / 'GAMMAS').unlink()
    _template(explicit, 'GAMMAS', 'must not be used')
    blocked = plan_model_from_solution(str(tmp_path), source_relpath='source', destination_relpath='another', template_root=str(explicit))
    assert not blocked['ready'] and 'GAMMAS' in blocked['missing_required']
