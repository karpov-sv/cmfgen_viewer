"""Standalone maintenance uses the UI's staging, cleanup, and parameter rules."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from cmfgen_viewer import model_cli, model_activity, model_staging
from cmfgen_viewer.model_cli import main
from cmfgen_viewer.model_editor import MODEL_INPUT_MODIFIED_MARKER
from cmfgen_viewer.recovery_files import RECOVERY_FILE_LIMIT
from test_model_staging import _write_solution
from test_model_editor import _scaling_model


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: home))
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def solution(tmp_path):
    model = tmp_path / 'source model'
    _write_solution(model)
    return model


def report(capsys):
    return json.loads(capsys.readouterr().out)


def test_show_and_set_plan_leave_the_model_untouched(tmp_path, capsys):
    model, original, _, _ = _scaling_model(tmp_path)
    assert main(['show', str(model), '--json']) == 0
    shown = report(capsys)
    assert next(field for field in shown['parameters'] if field['key'] == 'LSTAR')['value'] == '1.0D5'
    assert main(['set', str(model), 'LSTAR=4D5', '--keep-teff-logg', '--plan', '--json']) == 0
    planned = report(capsys)
    assert planned['ready'] and planned['changed']
    assert planned['resulting_values']['RSTAR'] == '140'
    assert planned['resulting_values']['MASS'] == '40'
    assert (model / 'VADAT').read_bytes() == original.encode()
    assert not (model / '.cmfgen-viewer-backups').exists()
    assert not (model / MODEL_INPUT_MODIFIED_MARKER).exists()


def test_set_coupled_luminosity_creates_checkpoint_and_preserves_file_layout(tmp_path, capsys):
    model, original, _, _ = _scaling_model(tmp_path)
    assert main(['set', str(model), 'LSTAR=4D5', '--keep-teff-logg', '--json']) == 0
    saved = report(capsys)
    expected = original.replace('1.0D5', '4D5').replace('70.0', '140').replace('10.0', '40')
    assert (model / 'VADAT').read_bytes() == expected.encode()
    assert Path(saved['backup']).read_bytes() == original.encode()
    assert (model / MODEL_INPUT_MODIFIED_MARKER).is_file()
    assert any('discrepancy' in warning for warning in saved['warnings'])


def test_set_iteration_controls_and_noop(tmp_path, capsys):
    model, _, _, _ = _scaling_model(tmp_path)
    assert main(['set', str(model), '--file', 'IN_ITS', 'NUM_ITS=12', '--json']) == 0
    saved = report(capsys)
    assert (model / 'IN_ITS').read_text() == '12 [NUM_ITS]\n'
    backups = list((model / '.cmfgen-viewer-backups').glob('*.bak'))
    assert main(['set', str(model), '--file', 'IN_ITS', 'NUM_ITS=12', '--json']) == 0
    assert report(capsys)['status'] == 'unchanged'
    assert list((model / '.cmfgen-viewer-backups').glob('*.bak')) == backups
    assert main(['show', str(model), '--file', 'IN_ITS']) == 0
    assert 'NUM_ITS=12' in capsys.readouterr().out


@pytest.mark.parametrize('assignments,flag', [
    (['LSTAR=4e5', 'lstar=5e5'], []), (['TEFF=3.5'], []), (['LSTAR=nan'], []),
    (['LSTAR'], []), (['LSTAR='], []), (['MDOT=2e-6'], ['--keep-teff-logg']),
    (['LSTAR=4e5', 'MASS=20'], ['--keep-teff-logg']),
    (['LSTAR=0'], ['--keep-teff-logg']),
])
def test_invalid_edits_never_write(tmp_path, capsys, assignments, flag):
    model, original, _, _ = _scaling_model(tmp_path)
    assert main(['set', str(model), *assignments, *flag, '--json']) == 2
    assert report(capsys)['error']
    assert (model / 'VADAT').read_bytes() == original.encode()
    assert not (model / '.cmfgen-viewer-backups').exists()


def test_copy_stages_new_inputs_without_old_restart_files(solution, tmp_path, capsys):
    destination = tmp_path / 'destination model'
    assert main(['copy', str(solution), str(destination), '--plan', '--json']) == 0
    planned = report(capsys)
    assert planned['ready'] and not destination.exists()
    mappings = {entry['source_name']: entry['destination_name'] for entry in planned['entries']}
    assert mappings['GAMMAS'] == 'GAMMAS_IN'
    assert mappings['HeIOUT'] == 'HeI_IN'
    assert 'SCRTEMP' not in mappings and 'POINT1' not in mappings
    assert main(['copy', str(solution), str(destination), '--json']) == 0
    assert report(capsys)['status'] == 'succeeded'
    assert (destination / 'HeI_IN').read_text() == (solution / 'HeIOUT').read_text()
    assert (destination / 'GAMMAS_IN').read_text() == (solution / 'GAMMAS').read_text()
    assert (solution / 'HeIOUT').exists()
    assert not (destination / 'SCRTEMP').exists()
    assert not (destination / 'lte').exists()
    assert main(['copy', str(solution), str(destination), '--json']) == 2
    assert 'already exists' in report(capsys)['error']


def test_copy_refuses_destination_inside_source(solution, capsys):
    assert main(['copy', str(solution), str(solution / 'nested'), '--json']) == 2
    assert 'inside' in report(capsys)['error']
    assert not (solution / 'nested').exists()


def test_copy_reads_template_root_from_shared_rc(solution, tmp_path, capsys):
    templates = tmp_path / 'templates'
    templates.mkdir()
    (templates / 'IN_ITS').write_text('99 [NUM_ITS]\n')
    (solution / 'IN_ITS').unlink()
    (tmp_path / '.cmfgenrc').write_text('template_root = templates\n')
    destination = tmp_path / 'new'
    assert main(['copy', str(solution), str(destination), '--json']) == 0
    report(capsys)
    assert (destination / 'IN_ITS').read_text() == '99 [NUM_ITS]\n'


@pytest.mark.parametrize('keep', [False, True])
def test_cleanup_preserves_working_products_and_uses_retention_policy(solution, capsys, keep):
    scratch = solution / 'BAMAT'
    scratch.write_bytes(b'x' * (RECOVERY_FILE_LIMIT + 1))
    original_checkpoint = (solution / 'SCRTEMP').read_bytes()
    flags = ['--keep-large-files'] if keep else []
    assert main(['cleanup', str(solution), '--file', 'BAMAT', '--plan', '--json', *flags]) == 0
    assert report(capsys)['entry_count'] == 1
    assert scratch.exists() and not (solution / '.cmfgen-runs').exists()
    assert main(['cleanup', str(solution), '--file', 'BAMAT', '--json', *flags]) == 0
    cleaned = report(capsys)
    journal = Path(cleaned['result']['journal'])
    assert not scratch.exists()
    assert (journal / 'removed/BAMAT').exists() == keep
    assert (journal / 'result.json').exists()
    assert (solution / 'SCRTEMP').read_bytes() == original_checkpoint
    assert (solution / 'HeIOUT').exists()


def test_cleanup_lte_preserves_controls_and_results_and_rechecks_candidates(solution, capsys, monkeypatch):
    lte = solution / 'lte'
    lte.mkdir()
    for name in ['VADAT', 'MODEL_SPEC', 'OUTLTE', 'RVSIG_COL_NEW', 'HeI_IN', 'POPHYD']:
        (lte / name).write_text(name)
    assert main(['cleanup', str(solution), '--lte', '--plan', '--json']) == 0
    assert report(capsys)['entry_count'] == 1
    original = model_cli.cleanup_lte_workspace
    def changed(*args, **kwargs):
        (lte / 'POPNEW').write_text('appeared after plan')
        return original(*args, **kwargs)
    monkeypatch.setattr(model_cli, 'cleanup_lte_workspace', changed)
    assert main(['cleanup', str(solution), '--lte', '--json']) == 1
    assert 'changed since review' in report(capsys)['error']
    assert (lte / 'POPHYD').exists()
    monkeypatch.setattr(model_cli, 'cleanup_lte_workspace', original)
    assert main(['cleanup', str(solution), '--lte', '--json']) == 0
    cleaned = report(capsys)
    assert (Path(cleaned['result']['archive_path']) / 'POPHYD').exists()
    for name in ['VADAT', 'MODEL_SPEC', 'OUTLTE', 'RVSIG_COL_NEW', 'HeI_IN']:
        assert (lte / name).exists()


def test_cleanup_noop_unknown_selection_and_rc_override(solution, tmp_path, capsys):
    assert main(['cleanup', str(solution), '--json']) == 0
    assert report(capsys)['status'] == 'unchanged'
    assert not (solution / '.cmfgen-runs').exists()
    assert main(['cleanup', str(solution), '--file', 'SCRTEMP', '--json']) == 2
    assert 'Not a current cleanup candidate' in report(capsys)['errors'][0]
    (solution / 'BAMAT').write_text('scratch')
    (tmp_path / '.cmfgenrc').write_text('keep_large_files = true\n')
    assert main(['cleanup', str(solution), '--plan', '--json']) == 0
    assert report(capsys)['keep_large_files'] is True
    assert main(['cleanup', str(solution), '--plan', '--json', '--no-keep-large-files']) == 0
    assert report(capsys)['keep_large_files'] is False


@pytest.mark.parametrize('command', ['copy', 'cleanup', 'set'])
@pytest.mark.parametrize('state', ['active', 'unknown'])
def test_all_mutations_refuse_active_or_unobservable_models(solution, tmp_path, capsys, monkeypatch, command, state):
    monkeypatch.setattr(model_activity, 'scan_model_processes', lambda *args, **kwargs:
        ([{'pid': 123}], []) if state == 'active' else ([], ['visibility unavailable']))
    (solution / 'BAMAT').write_text('scratch')
    if command == 'copy':
        args = ['copy', str(solution), str(tmp_path / 'destination')]
    elif command == 'set':
        args = ['set', str(solution), 'LSTAR=2']
    else:
        args = ['cleanup', str(solution)]
    assert main([*args, '--json']) == 2
    assert not report(capsys)['ready']
    assert not (solution / '.cmfgen-runs').exists()
    assert not (solution / '.cmfgen-viewer-backups').exists()
    assert not (tmp_path / 'destination').exists()
    assert (solution / 'BAMAT').exists()


def test_set_rejects_concurrent_edit_before_saving(tmp_path, capsys, monkeypatch):
    model, _, _, _ = _scaling_model(tmp_path)
    original = model_cli.save_quick_model_parameter_edit
    def changed(*args, **kwargs):
        (model / 'VADAT').write_text('2 [LSTAR]\n')
        return original(*args, **kwargs)
    monkeypatch.setattr(model_cli, 'save_quick_model_parameter_edit', changed)
    assert main(['set', str(model), 'LSTAR=4e5', '--json']) == 1
    assert 'changed' in report(capsys)['error']
    assert (model / 'VADAT').read_text() == '2 [LSTAR]\n'
    assert not (model / '.cmfgen-viewer-backups').exists()


def test_copy_execution_failure_is_structured(solution, tmp_path, monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise model_staging.ModelStagingError('simulated filesystem failure')
    monkeypatch.setattr(model_cli, 'create_model_from_solution', fail)
    assert main(['copy', str(solution), str(tmp_path / 'new'), '--json']) == 1
    assert report(capsys)['status'] == 'failed'


def test_standalone_entry_point_help():
    script = Path(__file__).resolve().parents[1] / 'cmfgen_model.py'
    result = subprocess.run([sys.executable, str(script), '--help'], capture_output=True, text=True)
    assert result.returncode == 0
    assert '{show,get,copy,cleanup,out2in,set}' in result.stdout


def test_get_prints_only_the_raw_value_and_never_mutates(tmp_path, capsys, monkeypatch):
    model, original, _, _ = _scaling_model(tmp_path)
    monkeypatch.setattr(model_activity, 'scan_model_processes', lambda *a, **k: ([], ['unavailable']))
    assert main(['get', str(model), 'lstar']) == 0
    captured = capsys.readouterr()
    assert captured.out == '1.0D5\n' and captured.err == ''
    # Read-only get includes controls that are not exposed by the quick editor.
    assert main(['get', str(model), 'TEFF']) == 0
    assert capsys.readouterr().out == '3.0\n'
    assert main(['get', str(model), 'NUM_ITS', '--file', 'IN_ITS']) == 0
    assert capsys.readouterr().out == '10\n'
    assert (model / 'VADAT').read_bytes() == original.encode()
    assert not (model / '.cmfgen-viewer-backups').exists()
    assert not (model / MODEL_INPUT_MODIFIED_MARKER).exists()


def test_get_json_keeps_provenance_and_raw_value(tmp_path, capsys):
    model, _, _, _ = _scaling_model(tmp_path)
    assert main(['get', str(model), 'LOGG', '--json']) == 0
    value = report(capsys)
    assert value['key'] == 'LOGG' and value['value'] == '3.50D0'
    assert value['file'] == 'VADAT' and value['model'] == str(model)


@pytest.mark.parametrize('content', ['', '1 [LSTAR]\n2 [LSTAR]\n', '   [LSTAR]\n'])
def test_get_missing_or_ambiguous_values_fail_without_polluting_stdout(tmp_path, capsys, content):
    model, _, _, _ = _scaling_model(tmp_path)
    (model / 'VADAT').write_text(content)
    assert main(['get', str(model), 'LSTAR']) == 2
    captured = capsys.readouterr()
    assert captured.out == '' and 'ERROR:' in captured.err
    assert main(['get', str(model), 'LSTAR', '--json']) == 2
    assert report(capsys)['error']


def test_get_preserves_zero_boolean_and_vector_values(solution, capsys):
    (solution / 'VADAT').write_text('0 [ZERO] ! comment\nF [DO_CL]\n1, 2, 3 [VECTOR]\n')
    for key, expected in [('ZERO', '0'), ('DO_CL', 'F'), ('VECTOR', '1, 2, 3')]:
        assert main(['get', str(solution), key]) == 0
        assert capsys.readouterr().out == expected + '\n'
