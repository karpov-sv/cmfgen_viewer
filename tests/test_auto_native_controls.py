"""Native lambda release must survive auto boundaries without hiding edits."""
from pathlib import Path

import pytest

from test_runner_auto import auto_workspace
from test_auto_hydro import hydro_workspace
from cmfgen_viewer.auto_diagnostics import control_value
from cmfgen_viewer.auto_hydro import capture_controls, native_updates
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner_recipe import RunnerError


TRANSITION = (
    'Current great iteration count is 16\nLAMBDA iteration used\n'
    'Maximm changes as returned by SOLVEBA_V13 is 28.68\n'
    'Current great iteration count is 17\nBA matrix computed\n'
    'Maximm changes as returned by SOLVEBA_V13 is 10000000\n'
    'Current great iteration count is 18\nLAMBDA iteration used\n'
    'Maximm changes as returned by SOLVEBA_V13 is 70054\n'
)


@pytest.mark.parametrize('automatic', ['T [DO_LAM_AUTO]\n', ''])
def test_native_lambda_release_accepts_rebound_and_native_formatting(tmp_path, automatic):
    original = '20 [NUM_ITS]  \n   T    [DO_LAM_IT] ! lambda   \n' + automatic
    current = '20 [NUM_ITS]\nF       [DO_LAM_IT] ! lambda\n' + automatic
    path = tmp_path/'IN_ITS'
    path.write_text(original)
    before = capture_controls(tmp_path)
    path.write_text(current)

    adopted = native_updates(tmp_path, TRANSITION, before)

    assert adopted == {'IN_ITS': {'before': original, 'after': current}}
    assert path.read_text() == current


@pytest.mark.parametrize('fault', [
    'auto_disabled', 'no_lambda', 'no_full', 'threshold', 'missing_metric',
    'counter_gap', 'extra_value', 'extra_comment', 'duplicate', 'reverse',
])
def test_native_lambda_release_rejects_unproven_or_unrelated_edits(tmp_path, fault):
    original = '20 [NUM_ITS]\nT [DO_LAM_IT]\nT [DO_LAM_AUTO]\nT [DO_T_AUTO]\n'
    if fault == 'auto_disabled':
        original = original.replace('T [DO_LAM_AUTO]', 'F [DO_LAM_AUTO]')
    if fault == 'reverse':
        original = original.replace('T [DO_LAM_IT]', 'F [DO_LAM_IT]')
    path = tmp_path/'IN_ITS'
    path.write_text(original)
    before = capture_controls(tmp_path)
    current = original.replace('T [DO_LAM_IT]', 'F [DO_LAM_IT]')
    text = TRANSITION
    if fault == 'no_lambda':
        text = text.replace('LAMBDA iteration used', 'BA matrix computed')
    elif fault == 'no_full':
        text = text.replace('BA matrix computed', 'LAMBDA iteration used')
    elif fault == 'threshold':
        text = text.replace('28.68', '50.0')
    elif fault == 'missing_metric':
        text = text.replace('10000000', 'NaN')
    elif fault == 'counter_gap':
        text = text.replace('count is 17', 'count is 19')
    elif fault == 'extra_value':
        current = current.replace('T [DO_T_AUTO]', 'F [DO_T_AUTO]')
    elif fault == 'extra_comment':
        current += '! unrelated user comment\n'
    elif fault == 'duplicate':
        current += 'F [DO_LAM_IT]\n'
    elif fault == 'reverse':
        current = current.replace('F [DO_LAM_IT]', 'T [DO_LAM_IT]')
    path.write_text(current)

    with pytest.raises(RunnerError, match='IN_ITS|Ambiguous controls'):
        native_updates(tmp_path, text, before)
    assert path.read_text() == current


@pytest.fixture
def switching_workspace(auto_workspace):
    model, plan = auto_workspace
    (model/'IN_ITS').write_text('20 [NUM_ITS]\nT [DO_LAM_IT]\nT [DO_LAM_AUTO]\nT [DO_T_AUTO]\n')
    exe = model.parent/'cmf/exe/cmfgen_dev.exe'
    code = exe.read_text().replace("if mode=='lambda':", "if get('IN_ITS','DO_LAM_IT','F')=='T' and n==0:")
    code += """
with (p/'input-trace').open('a') as trace:
 trace.write(get('IN_ITS','DO_LAM_IT','F')+'\\n')
if attempt==1:
 text=(p/'IN_ITS').read_text().replace('T [DO_LAM_IT]','F [DO_LAM_IT]')
 (p/'IN_ITS').write_text(text)
"""
    exe.write_text(code)
    return model, plan, exe


def test_native_lambda_release_continues_and_independently_verifies(switching_workspace):
    model, plan, _exe = switching_workspace

    result = run_plan(plan())

    assert result['status'] == 'succeeded', result
    assert [a['phase'] for a in result['attempts']] == ['iterate', 'verify']
    update = result['attempts'][0]['native_control_updates']['IN_ITS']
    assert '20 [NUM_ITS]' in update['before'] and 'T [DO_LAM_IT]' in update['before']
    assert '20 [NUM_ITS]' in update['after'] and 'F [DO_LAM_IT]' in update['after']
    assert (model/'input-trace').read_text().splitlines() == ['T', 'F']
    assert control_value(model, 'IN_ITS', 'NUM_ITS') == '20'
    assert control_value(model, 'IN_ITS', 'DO_LAM_IT') == 'F'
    assert (Path(result['recovery_directory'])/'IN_ITS').read_bytes() == (model/'IN_ITS').read_bytes()
    assert result['attempts'][-1]['evidence']['fresh_verified']


def test_full_solve_rebound_does_not_turn_native_release_into_convergence(switching_workspace):
    model, plan, exe = switching_workspace
    code = exe.read_text().replace('and n==0:', 'and n in (0,2):')
    code = code.replace("  out+=f'Current great iteration count is {it}\\n'",
                        "  if attempt==1:value=[28.68,10000000,70054][n]\n"
                        "  out+=f'Current great iteration count is {it}\\n'")
    exe.write_text(code)

    result = run_plan(plan())

    assert result['status'] == 'succeeded', result
    assert [a['phase'] for a in result['attempts']] == ['iterate', 'iterate', 'verify']
    first = result['attempts'][0]
    assert first['native_control_updates']['IN_ITS']
    assert not first['evidence']['candidate']
    assert [r['lambda_iteration'] for r in first['evidence']['records']] == [True, False, True]
    assert first['evidence']['records'][-1]['solver_maximum_change'] == 70054
    assert (model/'input-trace').read_text().splitlines() == ['T', 'F', 'F']


def test_unrelated_edit_alongside_native_release_still_stops_auto(switching_workspace):
    model, plan, exe = switching_workspace
    with exe.open('a') as stream:
        stream.write("with (p/'IN_ITS').open('a') as stream:stream.write('! user edit\\n')\n")

    result = run_plan(plan())

    assert result['status'] == 'needs_review', result
    assert 'Unexpected IN_ITS edit' in result['reason']
    assert len(result['attempts']) == 1
    assert '! user edit' in (model/'IN_ITS').read_text()


def test_failed_provisional_followup_restores_iteration_controls(hydro_workspace):
    model, plan, _original = hydro_workspace
    original = '20 [NUM_ITS]\nT [DO_LAM_IT]\nT [DO_LAM_AUTO]\n'
    (model/'IN_ITS').write_text(original)
    exe = model.parent/'cmf/exe/cmfgen_dev.exe'
    code = exe.read_text().replace("if mode=='lambda':", "if mode=='lambda' or (done and stop=='T' and n==0):")
    code += """
if done and stop=='T':
 (p/'IN_ITS').write_text((p/'IN_ITS').read_text().replace('T [DO_LAM_IT]','F [DO_LAM_IT]'))
"""
    exe.write_text(code)

    result = run_plan(plan('hydro_unphysical'))

    assert result['status'] == 'needs_review', result
    assert result['attempts'][-1]['native_control_updates']['IN_ITS']
    assert result['provisional_recovery_rolled_back'] == 'hydro_bootstrap'
    assert (model/'IN_ITS').read_text() == original
    assert (Path(result['recovery_directory'])/'IN_ITS').read_text() == original
