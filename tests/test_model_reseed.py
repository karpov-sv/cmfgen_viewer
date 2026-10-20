"""Text-output restart is explicit, guarded, recoverable, and transactional."""
import json
from pathlib import Path

import pytest

from cmfgen_viewer import model_activity, model_reseed
from cmfgen_viewer.model_cli import main
from cmfgen_viewer.model_reseed import build_reseed_plan, run_reseed_plan
from cmfgen_viewer.recovery_files import RECOVERY_FILE_LIMIT
from test_model_cli import solution, isolated_config


def result(capsys):
    return json.loads(capsys.readouterr().out)


def test_cli_plan_is_read_only_and_execution_seeds_then_retires_checkpoints(solution, capsys):
    (solution / 'POINT2').write_text('fallback')
    (solution / 'GAMMAS_IN').write_text('old gamma')
    assert main(['out2in', str(solution), '--plan', '--json']) == 0
    plan = result(capsys)
    assert plan['ready']
    assert {e['name'] for e in plan['checkpoints']} == {'POINT1', 'POINT2', 'SCRTEMP'}
    assert not (solution / '.cmfgen-viewer-backups').exists()
    assert not (solution / model_activity.LOCK_NAME).exists()
    assert (solution / 'HeI_IN').read_text() == 'old input\n'
    assert main(['out2in', str(solution), '--json']) == 0
    saved = result(capsys)
    archive = Path(saved['result']['archive_path'])
    assert (solution / 'HeI_IN').read_bytes() == (solution / 'HeIOUT').read_bytes()
    assert (solution / 'GREY_SCL_FAC_IN').read_bytes() == (solution / 'GREY_SCL_FACOUT').read_bytes()
    assert (solution / 'GAMMAS_IN').read_bytes() == (solution / 'GAMMAS').read_bytes()
    assert (archive / 'previous/HeI_IN').read_text() == 'old input\n'
    assert (archive / 'previous/GAMMAS_IN').read_text() == 'old gamma'
    assert (archive / 'previous/SCRTEMP').read_text() == 'restart state\n'
    assert (archive / 'operation.json').is_file()
    assert all(not (solution / name).exists() for name in ('POINT1', 'POINT2', 'SCRTEMP'))
    assert (solution / 'MOD_SUM').read_text() == 'old summary\n'
    assert (solution / 'VADAT').read_text() == '1 [LSTAR]\n'
    assert (solution / 'GAMMAS_IN').stat().st_mode & 0o444 == 0o444


@pytest.mark.parametrize('state', ['active', 'unknown'])
def test_reseed_blocks_model_activity(solution, capsys, monkeypatch, state):
    monkeypatch.setattr(model_activity, 'scan_model_processes', lambda *a, **k:
        ([{'pid': 1}], []) if state == 'active' else ([], ['visibility unavailable']))
    assert main(['out2in', str(solution), '--json']) == 2
    assert not result(capsys)['ready']
    assert (solution / 'SCRTEMP').exists()
    assert not (solution / '.cmfgen-viewer-backups').exists()


@pytest.mark.parametrize('missing', ['GAMMAS', 'outputs'])
def test_missing_outputs_do_not_retire_checkpoints(solution, capsys, missing):
    if missing == 'outputs':
        for path in solution.glob('*OUT'):
            path.unlink()
    else:
        (solution / missing).unlink()
    assert main(['out2in', str(solution), '--json']) == 2
    assert result(capsys)['errors']
    assert (solution / 'SCRTEMP').exists()


@pytest.mark.parametrize('name', ['HeIOUT', 'HeI_IN', 'SCRTEMP', '.cmfgen-viewer-backups'])
def test_symlinks_are_rejected_without_touching_targets(solution, tmp_path, capsys, name):
    target = tmp_path / 'external'
    target.write_text('retain')
    path = solution / name
    path.unlink(missing_ok=True)
    path.symlink_to(target)
    assert main(['out2in', str(solution), '--json']) == 2
    assert result(capsys)['errors']
    assert target.read_text() == 'retain'
    assert path.is_symlink()


def test_changed_source_plan_is_rejected(solution):
    plan = build_reseed_plan(solution)
    (solution / 'HeIOUT').write_text('new output')
    with pytest.raises(ValueError, match='changed after planning'):
        run_reseed_plan(plan)
    assert (solution / 'HeI_IN').read_text() == 'old input\n'
    assert (solution / 'SCRTEMP').exists()


def test_failure_retiring_checkpoint_rolls_back_all_inputs(solution, monkeypatch):
    plan = build_reseed_plan(solution)
    original = model_reseed.os.replace
    def fail(source, destination):
        if Path(source) == solution / 'SCRTEMP':
            raise OSError('simulated checkpoint retirement failure')
        return original(source, destination)
    monkeypatch.setattr(model_reseed.os, 'replace', fail)
    with pytest.raises(ValueError, match='simulated'):
        run_reseed_plan(plan)
    assert (solution / 'HeI_IN').read_text() == 'old input\n'
    assert not (solution / 'GAMMAS_IN').exists()
    assert not (solution / 'GREY_SCL_FAC_IN').exists()
    assert (solution / 'POINT1').read_text() == 'restart pointer\n'
    assert (solution / 'SCRTEMP').read_text() == 'restart state\n'
    assert (solution / 'HeIOUT').read_text() == 'helium-state\n'


@pytest.mark.parametrize('keep', [False, True])
def test_recovery_policy_only_compacts_previous_files_after_success(solution, capsys, keep):
    (solution / 'SCRTEMP').write_bytes(b'x' * (RECOVERY_FILE_LIMIT + 1))
    flags = ['--keep-large-files'] if keep else []
    assert main(['out2in', str(solution), '--json', *flags]) == 0
    saved = result(capsys)
    archive = Path(saved['result']['archive_path'])
    assert (archive / 'previous/SCRTEMP').exists() == keep
    assert (archive / 'previous/POINT1').exists()
    assert (solution / 'HeI_IN').read_bytes() == (solution / 'HeIOUT').read_bytes()
    assert not (solution / 'SCRTEMP').exists()


def test_reseed_without_binary_checkpoints_is_supported(solution, capsys):
    (solution / 'POINT1').unlink()
    (solution / 'SCRTEMP').unlink()
    assert main(['out2in', str(solution)]) == 0
    output = capsys.readouterr().out
    assert 'HeIOUT -> HeI_IN' in output and 'Status: succeeded' in output


def test_conflicting_gamma_outputs_do_not_replace_inputs(solution, capsys):
    (solution / 'GAMMASOUT').write_text('ambiguous gamma source')
    assert main(['out2in', str(solution), '--json']) == 2
    assert 'Multiple outputs' in result(capsys)['errors'][0]
    assert (solution / 'SCRTEMP').exists()
    assert not (solution / 'GAMMAS_IN').exists()
