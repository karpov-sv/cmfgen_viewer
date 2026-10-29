from pathlib import Path

import pytest

from cmfgen_viewer.control_files import control_occurrences
from cmfgen_viewer.runner import _write_control, run_plan
from cmfgen_viewer.runner_controls import TemporaryControl, _patch
from cmfgen_viewer.runner_recipe import RunnerError
from test_runner import workspace, SUCCESS


def test_persistent_native_spelling_repair_preserves_other_text():
    text = '! [INCL_DSLDT] comment\r\n  F   [INCL_DSLDT] ! keep [OTHER]\r\n1 [OTHER]\r\n'
    result = _patch(text, {'INCL_DSLDT': 'T'}, key_spellings={'INCL_DSLDT': 'INCL_dSLdT'})
    assert result == text.replace('F   [INCL_DSLDT]', 'T   [INCL_dSLdT]')
    # Ordinary temporary value patches still preserve original key spelling.
    assert _patch(text, {'INCL_DSLDT': 'T'}) == text.replace('F   [INCL_DSLDT]', 'T   [INCL_DSLDT]')


def test_patches_preserve_unrelated_edits_between_passes_and_restore(tmp_path):
    path = tmp_path / 'IN_ITS'
    path.write_bytes(b'2 [NUM_ITS] ! iterations\r\n1 [OTHER]\r\n')
    control = TemporaryControl(path, _write_control)
    control.apply({'NUM_ITS': '0'})
    path.write_bytes(path.read_bytes().replace(b'1 [OTHER]', b'7 [OTHER]') + b'! manual\r\n')
    control.apply({'NUM_ITS': '3'})
    assert b'7 [OTHER]' in path.read_bytes()
    assert control.restore() == []
    assert path.read_bytes() == b'2 [NUM_ITS] ! iterations\r\n7 [OTHER]\r\n! manual\r\n'


@pytest.mark.parametrize('edit', ['9 [NUM_ITS]\n', '', '0 [NUM_ITS]\n9 [NUM_ITS]\n'])
def test_conflicting_values_deletions_and_duplicates_are_preserved(tmp_path, edit):
    path = tmp_path / 'IN_ITS'
    path.write_text('2 [NUM_ITS]\nED [DC_METH]\n')
    control = TemporaryControl(path, _write_control)
    control.apply({'NUM_ITS': '0', 'DC_METH': 'LTE'})
    path.write_text(edit + 'LTE [DC_METH]\n')
    with pytest.raises(RunnerError, match='conflict.*NUM_ITS'):
        control.apply({'NUM_ITS': '3'})
    errors = control.restore()
    assert len(errors) == 1 and '[NUM_ITS]' in errors[0]
    assert path.read_text() == edit + 'ED [DC_METH]\n'


def test_new_control_file_keeps_manual_additions(tmp_path):
    path = tmp_path / 'CMF_FLUX_PARAM'
    control = TemporaryControl(path, _write_control)
    control.apply({'VTURB_FIX': '15'}, seed=b'1 [VTURB_FIX]\n! template comment\n')
    path.write_text(path.read_text() + '7 [CUSTOM]\n')
    assert control.restore() == []
    assert path.read_text() == '! template comment\n7 [CUSTOM]\n'


def test_removed_file_is_not_recreated(tmp_path):
    path = tmp_path / 'IN_ITS'
    path.write_text('2 [NUM_ITS]\n')
    control = TemporaryControl(path, _write_control)
    control.apply({'NUM_ITS': '0'})
    path.unlink()
    assert 'removed' in control.restore()[0]
    assert not path.exists()


def test_comment_added_to_inserted_control_survives_restoration(tmp_path):
    path = tmp_path / 'VADAT'
    path.write_text('1 [RSTAR]\n')
    control = TemporaryControl(path, _write_control)
    control.apply({'T_EXC': '1'})
    path.write_text(path.read_text().replace('[T_EXC]', '[T_EXC] ! manual note'))
    assert control.restore() == []
    assert path.read_text() == '1 [RSTAR]\n! manual note\n'


@pytest.mark.parametrize('conflict', [False, True])
def test_runner_preserves_manual_edits_and_reports_restore_conflicts(workspace, conflict):
    model, make_plan = workspace
    (model / 'VADAT').write_text('1 [RSTAR]\nED [DC_METH]\n')
    edits = "(p/'VADAT').write_text((p/'VADAT').read_text().replace('1 [RSTAR]', '2 [RSTAR]'))\n"
    edits += "(p/'IN_ITS').write_text((p/'IN_ITS').read_text() + '7 [CUSTOM]\\n')\n"
    if conflict:
        edits += "(p/'VADAT').write_text((p/'VADAT').read_text().replace('LTE', 'R'))\n"
    result = run_plan(make_plan(SUCCESS + edits, lte_initialization=True))
    assert result['status'] == ('runner_error' if conflict else 'tested'), result
    assert (model / 'IN_ITS').read_text() == '2 [NUM_ITS]\n7 [CUSTOM]\n'
    text = (model / 'VADAT').read_text()
    assert '2 [RSTAR]' in text and '[T_EXC]' not in text
    assert ('R [DC_METH]' if conflict else 'ED [DC_METH]') in text
    if conflict:
        assert '[DC_METH]' in result['restore_errors'][0]
        assert 'control_restore_conflict' in (Path(result['journal']) / 'events.jsonl').read_text()


def test_runner_stops_before_next_pass_on_conflict(workspace):
    model, make_plan = workspace
    plan = make_plan(SUCCESS)
    plan['passes'].append({'id': 'second', 'overrides': {'NUM_ITS': '3'}})
    def edit(event):
        if event['event'] == 'stage_finished':
            (model / 'IN_ITS').write_text('9 [NUM_ITS]\n')
    result = run_plan(plan, edit)
    assert result['status'] == 'runner_error'
    assert 'conflict' in result['error']
    assert len(result['passes']) == 1
    assert (model / 'IN_ITS').read_text() == '9 [NUM_ITS]\n'


@pytest.mark.parametrize('edit', ['none', 'unrelated', 'owned', 'template', 'failure'])
def test_flux_patches_active_controls_between_passes(workspace, edit):
    import sys
    from cmfgen_viewer.runner_recipe import build_run_plan
    from test_runner import RVTJ_CORE

    model, make_plan = workspace
    make_plan()
    obs = model / 'obs'
    obs.mkdir()
    template = ''.join(f'1 [{key}]\n' for key in (
        'VTURB_FIX', 'VTURB_MIN', 'VTURB_MAX', 'NUM_ES', 'DO_SOB_LINES', 'GLOBAL_LINE'))
    template = template.replace('1 [GLOBAL_LINE]', 'BLANK [GLOBAL_LINE]')
    template = template.replace('1 [DO_SOB_LINES]', 'T [DO_SOB_LINES]')
    template = template.replace('1 [NUM_ES]', '3 [NUM_ES]')
    (obs / 'CMF_FLUX_PARAM_INIT').write_text(template + '1 [CUSTOM]\n! template\n')
    # The previous continuum pass left a different active configuration.
    active = template.replace('BLANK [GLOBAL_LINE]', 'SOB [GLOBAL_LINE]')
    active = active.replace('T [DO_SOB_LINES]', 'F [DO_SOB_LINES]')
    active = active.replace('3 [NUM_ES]', '1 [NUM_ES]')
    active += '7 [CUSTOM]\n9 [ACTIVE_ONLY]\n! active\n'
    (obs / 'CMF_FLUX_PARAM').write_text(active)
    original_mtime = (obs / 'CMF_FLUX_PARAM').stat().st_mtime_ns
    (obs / 'IN_FILE').write_text('../RVTJ [RVTJ]\n1 [MASS]\nF [ONLY_OBS_LINES]\n')
    for name in ('batobs.sh', 'bat_ins.sh'):
        (obs / name).write_text('# reviewed test script\n')
    (model / 'RVTJ').write_text(RVTJ_CORE)
    (model / 'MODEL').write_text('input')
    exe = model.parent / 'cmf/exe/cmf_flux.exe'
    code = "raise SystemExit(9)" if edit == 'failure' else """
from pathlib import Path
Path('OUT_FLUX').write_text('CMF_FLUX has finished')
Path('OBSFRAME').write_text('Continuum Frequencies (2)\\n1 2\\nObserved intensity (Janskys)\\n3 4\\n')
"""
    exe.write_text(f'#!{sys.executable}\n' + code)
    exe.chmod(0o755)
    plan = build_run_plan(model, stage='flux', cmfgen_root=model.parent / 'cmf',
                          atomic_root=model.parent / 'atomic')
    assert plan['ready'], plan['errors']
    def change(event):
        if edit not in {'none', 'failure'} and event['event'] == 'stage_finished' and event['stage'] == 'flux-15':
            path = obs / ('CMF_FLUX_PARAM_INIT' if edit == 'template' else 'CMF_FLUX_PARAM')
            text = path.read_text()
            if edit == 'owned':
                text = text.replace('15.0D0 [VTURB_FIX]', '99 [VTURB_FIX]')
            else:
                text += '8 [MANUAL]\n'
            path.write_text(text)
    result = run_plan(plan, change)
    for record in result['passes']:
        effective = Path(result['journal']) / record['id'] / 'CMF_FLUX_PARAM'
        rows = control_occurrences(effective.read_text())
        continuum = record['id'] == 'continuum'
        assert rows['GLOBAL_LINE'][0]['value'] == ('SOB' if continuum else 'BLANK')
        assert rows['DO_SOB_LINES'][0]['value'] == ('F' if continuum else 'T')
        assert rows['NUM_ES'][0]['value'] == ('1' if continuum else '3')
        assert rows['CUSTOM'][0]['value'] == '1'
        assert 'ACTIVE_ONLY' not in rows
    if edit in {'none', 'failure'}:
        assert result['status'] == ('failed' if edit == 'failure' else 'succeeded'), result
        assert len(result['passes']) == (1 if edit == 'failure' else 4)
        assert (obs / 'CMF_FLUX_PARAM').read_text() == active
        assert (obs / 'CMF_FLUX_PARAM').stat().st_mtime_ns == original_mtime
    elif edit == 'unrelated':
        assert result['status'] == 'succeeded', result
        restored = (obs / 'CMF_FLUX_PARAM').read_text()
        expected_rows = control_occurrences(active + '8 [MANUAL]\n')
        assert {key: rows[0]['value'] for key, rows in control_occurrences(restored).items()} == {
            key: rows[0]['value'] for key, rows in expected_rows.items()}
        assert '! active' in restored
        effective = Path(result['journal']) / 'continuum/CMF_FLUX_PARAM'
        assert '1 [VTURB_FIX]' in effective.read_text()  # previous pass reset
        assert '1 [CUSTOM]' in effective.read_text() and '8 [MANUAL]' in effective.read_text()
    else:
        assert result['status'] == 'runner_error', result
        assert len(result['passes']) == 1
        if edit == 'owned':
            assert '99 [VTURB_FIX]' in (obs / 'CMF_FLUX_PARAM').read_text()
        else:
            assert (obs / 'CMF_FLUX_PARAM').read_text() == active
            assert 'changed during execution' in result['error']


def test_web_result_displays_restore_conflict(workspace):
    from cmfgen_viewer.app import create_app
    from test_detached_jobs import launch, wait_for

    model, make_plan = workspace
    (model / 'VADAT').write_text('1 [RSTAR]\nED [DC_METH]\n')
    code = SUCCESS + "(p/'VADAT').write_text((p/'VADAT').read_text().replace('LTE', 'R'))\n"
    plan = make_plan(code, lte_initialization=True)
    job_id = launch(model, plan)
    job = wait_for(model.parent, job_id, lambda job: not job['active'])
    assert job['status'] == 'runner_error', job
    client = create_app(basepath=str(model.parent), read_write_enabled=True).test_client()
    response = client.get(f'/runner-jobs/{job_id}')
    assert response.status_code == 200
    assert b'[DC_METH] changed during execution; preserving external edit' in response.data
