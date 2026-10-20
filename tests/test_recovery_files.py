"""Input-based recovery preserves full rollback until an operation commits."""
from pathlib import Path

import pytest

from cmfgen_viewer import model_workflow
from cmfgen_viewer.recovery_files import RECOVERY_FILE_LIMIT, compact_recovery, copy_recovery, retire_recovery
from cmfgen_viewer.model_workflow import cleanup_lte_workspace, promote_lte_hydro_results, ModelWorkflowError
from cmfgen_viewer.runner import run_plan
from test_runner import workspace, SUCCESS
from test_runner_promotion import promotable_model

LARGE = b'BEGIN\n' + b'x' * RECOVERY_FILE_LIMIT + b'\nEND'


def test_compact_keeps_history_and_small_files_and_excerpts_logs(tmp_path):
    (tmp_path / 'ES_J_CONV').write_bytes(LARGE)
    (tmp_path / 'OUTGEN').write_bytes(LARGE)
    (tmp_path / 'process.log').write_bytes(LARGE)
    (tmp_path / 'events.jsonl').write_bytes(LARGE)
    (tmp_path / 'VADAT').write_text('controls')
    external = tmp_path.parent / 'external-data'
    external.write_bytes(LARGE)
    (tmp_path / 'cache-link').symlink_to(external)
    summary = compact_recovery(tmp_path)
    assert summary['discarded_files'] == ['ES_J_CONV']
    assert set(summary['excerpted_logs']) == {'OUTGEN', 'process.log'}
    for name in summary['excerpted_logs']:
        data = (tmp_path / name).read_bytes()
        assert len(data) == RECOVERY_FILE_LIMIT
        assert data.startswith(b'BEGIN\n') and data.endswith(b'\nEND')
        assert b'middle of large diagnostic log omitted' in data
    assert (tmp_path / 'events.jsonl').read_bytes() == LARGE
    assert external.read_bytes() == LARGE
    assert (tmp_path / 'VADAT').read_text() == 'controls'
    assert summary['bytes_released'] > len(LARGE)


def test_copy_and_retire_follow_explicit_policy(tmp_path):
    source = tmp_path / 'ES_J_CONV'
    source.write_bytes(LARGE)
    copied = tmp_path / 'copy'
    copy_recovery(source, copied)
    assert source.read_bytes() == LARGE
    assert copied.exists() is False
    retired = tmp_path / 'retired'
    retire_recovery(source, retired)
    assert not source.exists()
    assert retired.exists() is False


def test_retire_readable_shared_log_does_not_require_ownership(tmp_path, monkeypatch):
    source = tmp_path / 'OUT_FLUX'
    source.write_text('previous flux log')
    source.chmod(0o666)
    destination = tmp_path / 'before' / source.name
    destination.parent.mkdir()

    def deny_chmod(*args, **kwargs):
        raise PermissionError('Only the owner may change permissions')

    monkeypatch.setattr(Path, 'chmod', deny_chmod)
    retire_recovery(source, destination)
    assert not source.exists()
    assert destination.read_text() == 'previous flux log'
    assert destination.stat().st_mode & 0o777 == 0o666


def test_native_run_keeps_working_output_with_optional_journal_copy(workspace):
    model, make_plan = workspace
    code = SUCCESS + "\n(p/'MODEL').write_bytes(b'x' * (2 * 1024 * 1024 + 10))\n"
    result = run_plan(make_plan(code))
    assert result['status'] == 'tested', result
    assert (model / 'MODEL').stat().st_size > RECOVERY_FILE_LIMIT
    archived = list(Path(result['journal']).rglob('MODEL'))
    assert bool(archived) is False


def test_lte_cleanup_retention(promotable_model):
    (promotable_model / 'lte/POPHYD').write_bytes(LARGE)
    result = cleanup_lte_workspace(str(promotable_model.parent), model_relpath=promotable_model.name)
    assert not (promotable_model / 'lte/POPHYD').exists()
    assert (Path(result['archive_path']) / 'POPHYD').exists() is False
    assert result['recovery']['policy'] == 'fresh-inputs'


def test_failed_promotion_preserves_full_rollback_files(promotable_model, monkeypatch):
    (promotable_model / 'lte/POPHYD').write_bytes(LARGE)
    (promotable_model / 'ES_J_CONV').write_bytes(LARGE)
    def fail(*args, **kwargs):
        raise ModelWorkflowError('simulated commit failure')
    monkeypatch.setattr(model_workflow, 'mark_model_inputs_modified', fail)
    with pytest.raises(ModelWorkflowError, match='simulated'):
        promote_lte_hydro_results(str(promotable_model.parent), model_relpath=promotable_model.name)
    assert (promotable_model / 'lte/POPHYD').read_bytes() == LARGE
    assert (promotable_model / 'ES_J_CONV').read_bytes() == LARGE


def test_successful_promotion_compacts_only_new_backup(promotable_model):
    old = promotable_model / '.cmfgen-viewer-backups/lte-hydro/old'
    old.mkdir(parents=True)
    (old / 'ES_J_CONV').write_bytes(LARGE)
    (promotable_model / 'ES_J_CONV').write_bytes(LARGE)
    (promotable_model / 'lte/POPHYD').write_bytes(LARGE)
    result = promote_lte_hydro_results(str(promotable_model.parent), model_relpath=promotable_model.name)
    backup = promotable_model / result['backup_relpath']
    assert (backup / 'ES_J_CONV').exists() is False
    assert (backup / 'lte/temporary/POPHYD').exists() is False
    assert (old / 'ES_J_CONV').read_bytes() == LARGE
    assert (promotable_model / 'RVSIG_COL').exists()



def test_flux_retires_large_caches_before_each_pass_without_trimming_final_output(workspace):
    from test_runner import RVTJ_CORE
    model, make_plan = workspace
    make_plan()
    obs = model / 'obs'
    obs.mkdir()
    (obs / 'CMF_FLUX_PARAM_INIT').write_text(''.join(f'1 [{key}]\n' for key in ('VTURB_FIX', 'VTURB_MIN', 'VTURB_MAX', 'NUM_ES', 'DO_SOB_LINES', 'GLOBAL_LINE')))
    (obs / 'IN_FILE').write_text('../RVTJ [RVTJ]\n1 [MASS]\nF [ONLY_OBS_LINES]\n')
    for name in ('batobs.sh', 'bat_ins.sh'):
        (obs / name).write_text('# fixture: no additional atomic links\n')
    (obs / 'ES_J_CONV').write_bytes(LARGE)
    (model / 'RVTJ').write_text(RVTJ_CORE)
    (model / 'MODEL').write_text('input')
    code = """
from pathlib import Path
assert not Path('ES_J_CONV').exists(), 'stale cache reused'
Path('ES_J_CONV').write_bytes(b'x' * (2 * 1024 * 1024 + 10))
Path('OUT_FLUX').write_text('CMF_FLUX has finished')
Path('OBSFRAME').write_text('Continuum Frequencies (2)\\n1 2\\nObserved intensity (Janskys)\\n3 4\\n')
"""
    result = run_plan(make_plan(code, stage='flux'))
    assert result['status'] == 'succeeded', result
    assert (obs / 'ES_J_CONV').stat().st_size > RECOVERY_FILE_LIMIT
    assert (obs / 'obs_cont').is_file()
    journal = Path(result['journal'])
    assert (journal / 'flux-15/before/ES_J_CONV').exists() is False
    assert (journal / 'flux-10/before/ES_J_CONV').exists() is False
    assert bool(list(journal.rglob('ES_J_CONV'))) is False


def test_failed_compaction_keeps_artifact_and_reports_warning(tmp_path, monkeypatch):
    cache = tmp_path / 'ES_J_CONV'
    cache.write_bytes(LARGE)
    original = Path.unlink
    def unlink(path, *args, **kwargs):
        if path == cache:
            raise PermissionError('simulated permission denial')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', unlink)
    result = compact_recovery(tmp_path)
    assert result['warnings'] and 'simulated' in result['warnings'][0]
    assert cache.read_bytes() == LARGE
    assert result['bytes_released'] == 0




def test_compact_retains_needed_large_inputs_but_drops_even_small_solver_state(tmp_path):
    (tmp_path / 'He2_IN').write_bytes(LARGE)
    for name in ('POINT1', 'SCRTEMP', 'MODEL', 'RVTJ', 'POPHYD', 'BAMAT'):
        (tmp_path / name).write_text('small, but not a fresh input')
    result = compact_recovery(tmp_path)
    assert (tmp_path / 'He2_IN').read_bytes() == LARGE
    assert set(result['discarded_files']) == {'POINT1', 'SCRTEMP', 'MODEL', 'RVTJ', 'POPHYD', 'BAMAT'}
    assert (tmp_path / '.recovery-policy.json').is_file()


@pytest.mark.parametrize('flag', ['--keep-large-files', '--no-keep-large-files'])
def test_removed_recovery_flags_are_rejected(flag, tmp_path):
    from cmfgen_viewer.cli import build_parser
    from cmfgen_viewer.model_cli import main as model_main
    from cmfgen_viewer.runner import main as runner_main
    with pytest.raises(SystemExit) as viewer_error:
        build_parser().parse_args([flag])
    assert viewer_error.value.code == 2
    with pytest.raises(SystemExit) as runner_error:
        runner_main([str(tmp_path), '--plan', '--stage', 'main', flag])
    assert runner_error.value.code == 2
    with pytest.raises(SystemExit) as maintenance_error:
        model_main(['out2in', str(tmp_path), flag])
    assert maintenance_error.value.code == 2


def test_removed_recovery_rc_setting_is_rejected(tmp_path, monkeypatch):
    from cmfgen_viewer.runner_config import _read_rc
    from cmfgen_viewer.runner_recipe import RunnerError
    config = tmp_path / '.cmfgenrc'
    config.write_text('keep_large_files = true\n')
    with pytest.raises(RunnerError, match='supported viewer/runner setting'):
        _read_rc(config)
