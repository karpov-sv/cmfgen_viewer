"""Model-local atomic data survive planning, native passes and automatic runs."""
import json
import os
from pathlib import Path

import pytest

from cmfgen_viewer.history_inputs import preview_inputs
from cmfgen_viewer.model_history import HistoryError
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner_recipe import RunnerError
from test_runner import workspace, SUCCESS, RVTJ_CORE
from test_runner_auto import auto_workspace


FLUX_SUCCESS = """
from pathlib import Path
Path('OUT_FLUX').write_text('CMF_FLUX has finished')
Path('OBSFRAME').write_text('Continuum Frequencies (2)\\n1 2\\nObserved intensity (Janskys)\\n3 4\\n')
"""


@pytest.fixture(params=['test', 'flux'])
def atomic_workspace(workspace, request):
    model, make_plan = workspace
    stage = request.param
    cwd = model if stage == 'test' else model/'obs'
    (model/'batch.sh').write_text('ln -sf $ATOMIC/local.dat TWO_PHOT_DATA\n')
    shared = model.parent/'atomic/local.dat'
    shared.write_text('shared data')
    if stage == 'flux':
        cwd.mkdir()
        (cwd/'batobs.sh').write_text('# No additional atomic declarations\n')
        (cwd/'CMF_FLUX_PARAM_INIT').write_text(
            '15 [VTURB_FIX]\n15 [VTURB_MIN]\n250 [VTURB_MAX]\n'
            '1 [NUM_ES]\nT [DO_SOB_LINES]\nCMF [GLOBAL_LINE]\n')
        (cwd/'IN_FILE').write_text('../RVTJ [RVTJ]\n1 [MASS]\nF [ONLY_OBS_LINES]\n')
        (model/'RVTJ').write_text(RVTJ_CORE)
        (model/'MODEL').write_text('atmosphere')

    def plan(expected='local customization'):
        code = ("from pathlib import Path\n"
                "assert not Path('TWO_PHOT_DATA').is_symlink()\n"
                f"assert Path('TWO_PHOT_DATA').read_text() == {expected!r}\n")
        return make_plan(code + (SUCCESS if stage == 'test' else FLUX_SUCCESS), stage=stage)

    return model, cwd, shared, plan


@pytest.mark.parametrize('shared_state', ['identical', 'different', 'missing'])
def test_local_atomic_file_is_used_unchanged(atomic_workspace, shared_state):
    model, cwd, shared, make_plan = atomic_workspace
    content = 'shared data' if shared_state == 'identical' else 'local customization'
    if shared_state == 'missing':
        shared.unlink()
    path = cwd/'TWO_PHOT_DATA'
    path.write_text(content)
    path.chmod(0o444)
    before = path.stat()
    plan = make_plan(content)
    assert plan['ready'], plan['errors']
    assert [entry['name'] for entry in plan['local_atomic_files']] == ['TWO_PHOT_DATA']
    assert not any(link['name'] == 'TWO_PHOT_DATA' for link in plan['links'])
    assert any(row['path'] == str(path) and row['sha256'] for row in plan['inputs'])
    assert any('Using model-local atomic data unchanged' in warning for warning in plan['warnings'])
    result = run_plan(plan)
    assert result['status'] == ('tested' if plan['stage'] == 'test' else 'succeeded'), result
    assert len(result['passes']) == (1 if plan['stage'] == 'test' else 4)
    assert path.read_text() == content and not path.is_symlink()
    after = path.stat()
    assert (before.st_ino, before.st_mode, before.st_mtime_ns) == (after.st_ino, after.st_mode, after.st_mtime_ns)
    assert (cwd/'HYD_L_DATA').is_symlink(), 'Missing atomic destinations still get links'
    if shared_state != 'missing':
        assert shared.read_text() == 'shared data'


@pytest.mark.parametrize('change', ['edit', 'remove', 'directory', 'symlink'])
def test_local_atomic_changes_invalidate_preview(atomic_workspace, change):
    model, cwd, shared, make_plan = atomic_workspace
    path = cwd/'TWO_PHOT_DATA'
    path.write_text('local customization')
    plan = make_plan()
    assert plan['ready'], plan['errors']
    if change == 'edit':
        path.write_text('edited since preview')
    else:
        path.unlink()
        if change == 'directory':
            path.mkdir()
        elif change == 'symlink':
            path.symlink_to(shared)
    with pytest.raises(RunnerError, match='Input changed since preflight'):
        run_plan(plan)
    assert not (model/'.cmfgen-runs').exists()


@pytest.mark.parametrize('kind', ['directory', 'fifo', 'unreadable'])
def test_invalid_local_atomic_destination_is_rejected(atomic_workspace, kind):
    _model, cwd, _shared, make_plan = atomic_workspace
    path = cwd/'TWO_PHOT_DATA'
    if kind == 'directory':
        path.mkdir()
    elif kind == 'fifo':
        os.mkfifo(path)
    else:
        path.write_text('local customization')
        path.chmod(0)
    plan = make_plan()
    assert not plan['ready']
    assert any('Atomic destination is not a readable regular file' in error for error in plan['errors'])


def test_automatic_batches_preserve_local_atomic_files(auto_workspace):
    model, make_plan = auto_workspace
    path = model/'HYD_L_DATA'
    path.write_text('local customization')
    result = run_plan(make_plan())
    assert result['status'] == 'succeeded', result
    assert len(result['attempts']) >= 2
    assert path.read_text() == 'local customization' and not path.is_symlink()


def test_local_atomic_file_is_a_fresh_recovery_dependency(workspace):
    model, make_plan = workspace
    path = model/'HYD_L_DATA'
    path.write_text('local customization')
    result = run_plan(make_plan())
    assert result['status'] == 'tested', result
    archive = Path(result['journal'])
    manifest = json.loads((archive/'fresh-inputs.json').read_text())
    assert manifest['complete']
    assert any(row['path'] == str(path) for row in manifest['dependencies'])
    archive_id = archive.relative_to(model).as_posix()
    # The shared file was not used, so changing it cannot invalidate recovery.
    (model.parent/'atomic/test.dat').write_text('new shared data')
    preview_inputs(model, archive_id)
    path.write_text('changed local data')
    with pytest.raises(HistoryError, match='Atomic dependency changed'):
        preview_inputs(model, archive_id)
