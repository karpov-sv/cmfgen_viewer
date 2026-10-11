import json
from pathlib import Path

import pytest

from cmfgen_viewer import runner
from cmfgen_viewer.runner_preparation import build_preparation_plan
from test_model_workflow import _write_initializable_workspace_inputs


def test_preparation_plan_and_execution(tmp_path, capsys):
    model = _write_initializable_workspace_inputs(tmp_path)
    before = (model / 'VADAT').read_bytes()
    assert runner.main([str(model), '--stage', 'prepare-lte', '--plan', '--json']) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['ready'] and plan['hydro_alignment']['ready']
    assert plan['hydro_alignment']['values']['TEFF'] == '2.5'
    assert not (model / 'lte').exists() and not (model / '.cmfgen-runs').exists()
    events = []
    result = runner.run_plan(plan, events.append)
    assert result['status'] == 'succeeded'
    assert result['preparation']['hydro_initialized']
    assert (model / 'VADAT').read_bytes() == before
    assert (model / 'RVSIG_COL_OLD').read_bytes() == (model / 'RVSIG_COL').read_bytes()
    assert '2.5 [TEFF]' in (model / 'lte/HYDRO_PARAMS').read_text()
    assert json.loads((Path(result['journal']) / 'result.json').read_text()) == result
    assert events[-1]['event'] == 'run_finished'
    assert not build_preparation_plan(model)['ready']


@pytest.mark.parametrize('changed', ['VADAT', 'template'])
def test_preparation_rejects_changed_sources(tmp_path, changed):
    model = _write_initializable_workspace_inputs(tmp_path)
    plan = build_preparation_plan(model)
    source = model / 'VADAT' if changed == 'VADAT' else tmp_path / 'examples/HYDRO_PARAMS'
    source.write_text(source.read_text() + '! changed\n')
    result = runner.run_plan(plan)
    assert result['status'] == 'failed'
    assert 'changed since preflight' in result['passes'][0]['problems'][0]
    assert not (model / 'lte').exists()
    assert not (model / 'RVSIG_COL_OLD').exists()


def test_preparation_custom_templates_and_unsupported_inputs(tmp_path, capsys):
    model = _write_initializable_workspace_inputs(tmp_path)
    templates = tmp_path / 'templates'
    (tmp_path / 'examples').rename(templates)
    hydro = templates / 'HYDRO_PARAMS'
    hydro.write_text(hydro.read_text().replace('F [OLD_V]', 'T [OLD_V]'))
    assert runner.main([str(model), '--stage', 'prepare-lte', '--template-root', str(templates), '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert not result['preparation']['hydro_initialized']
    assert result['preparation']['hydro_initialization_issues']
    assert (model / 'lte/HYDRO_PARAMS').read_bytes() == hydro.read_bytes()


def test_preparation_sequence_rebuilds_lte_after_preparation(tmp_path, monkeypatch):
    model = _write_initializable_workspace_inputs(tmp_path)
    templates = tmp_path / 'examples'
    plan = runner.build_sequence_plan(model, ['prepare-lte', 'lte'], native_config={},
        configuration_sources={}, timeout=None, iterations=None, fresh_start=False,
        cleanup_files=None, template_root=templates)
    assert plan['initial_plan']['stage'] == 'prepare-lte'
    original = runner.run_plan

    def native_plan(model, *, stage, **kwargs):
        assert stage == 'lte' and (model / 'lte/HYDRO_PARAMS').is_file()
        return {'stage': stage, 'ready': True, 'errors': [], 'warnings': []}

    def execute(stage_plan, emit=None):
        if stage_plan['stage'] == 'lte':
            return {'stage': 'lte', 'status': 'succeeded', 'passes': []}
        return original(stage_plan, emit)

    monkeypatch.setattr(runner, 'build_run_plan', native_plan)
    monkeypatch.setattr(runner, 'run_plan', execute)
    result = original(plan)
    assert result['status'] == 'succeeded'
    assert result['completed_stages'] == ['prepare-lte', 'lte']


def test_template_option_requires_preparation_stage(tmp_path, capsys):
    assert runner.main([str(tmp_path), '--stage', 'cleanup', '--template-root', str(tmp_path)]) == 2
    assert '--template-root applies only to prepare-lte' in capsys.readouterr().err


def test_preparation_rejects_changed_template_selection(tmp_path):
    model = _write_initializable_workspace_inputs(tmp_path)
    plan = build_preparation_plan(model)
    (tmp_path / 'examples/GRID_PARAMS').write_text('new preferred template\n')
    result = runner.run_plan(plan)
    assert result['status'] == 'failed'
    assert 'Template selection changed' in result['passes'][0]['problems'][0]
    assert not (model / 'lte').exists()


def test_preparation_human_plan_and_missing_templates(tmp_path, capsys):
    model = _write_initializable_workspace_inputs(tmp_path)
    assert runner.main([str(model), '--stage', 'prepare-lte', '--plan', '--color', 'never']) == 0
    output = capsys.readouterr().out
    assert 'Initialize HYDRO_PARAMS from VADAT:' in output
    assert 'CON_R=' in output and 'Preparation preflight passed' in output
    (tmp_path / 'examples/HYDRO_PARAMS').unlink()
    assert runner.main([str(model), '--stage', 'prepare-lte', '--plan', '--json']) == 2
    plan = json.loads(capsys.readouterr().out)
    assert not plan['ready'] and 'HYDRO_PARAMS' in plan['errors'][0]
    assert not (model / 'lte').exists() and not (model / '.cmfgen-runs').exists()


def test_preparation_never_overwrites_partial_workspace(tmp_path):
    model = _write_initializable_workspace_inputs(tmp_path)
    (model / 'lte').mkdir()
    (model / 'lte/VADAT').write_text('keep existing inputs\n')
    plan = build_preparation_plan(model)
    assert not plan['ready'] and 'incomplete' in plan['errors'][0]
    assert (model / 'lte/VADAT').read_text() == 'keep existing inputs\n'
