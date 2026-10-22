"""Ng checkpoint increments must not trigger a rollback of valid CMFGEN work."""
import sys

import pytest

from test_runner_auto import FAKE, auto_workspace
from cmfgen_viewer.auto_diagnostics import ng_accelerations
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner_recipe import RunnerError


@pytest.fixture
def ng_workspace(auto_workspace):
    model, plan = auto_workspace
    code = FAKE.replace(
        "mode=(p/'scenario').read_text()",
        "mode=(p/'scenario').read_text()\nng=attempt==1 and mode.startswith('ng_')")
    code = code.replace(
        ' for n,it in enumerate(range(start,start+count)):',
        ''' for n,it in enumerate(range(start,start+count)):
  ng_after=count-1 if mode=='ng_final' else 0
  if ng and n>ng_after and mode!='ng_no_gap':it+=1''')
    code = code.replace(
        "  sol.write(' STEQ SOLUTION ARRAY\\n')",
        '''  if ng and n==ng_after and mode!='ng_unexplained':
   out+=' NG Acceleration performed using NG_BAND= 10\\n'
   if mode=='ng_duplicate':out+=' NG Acceleration performed using NG_BAND= 10\\n'
  sol.write(' STEQ SOLUTION ARRAY\\n')''')
    code = code.replace('str(start+count-1)',
                        "str(start+count-1+int(ng and mode!='ng_wrong_pointer'))")
    exe = model.parent/'cmf/exe/cmfgen_dev.exe'
    exe.write_text(f'#!{sys.executable}\n'+code)
    return model, plan


def test_successful_ng_step_preserves_checkpoint_and_reaches_fresh_verification(ng_workspace):
    model, plan = ng_workspace
    result = run_plan(plan('ng_success'))
    assert result['status'] == 'succeeded', result
    assert len(result['attempts']) == 2
    first = result['attempts'][0]
    assert first['evidence']['ng_accelerations'] == [1]
    assert [r['global_iteration'] for r in first['evidence']['records']] == [1, 3, 4]
    assert first['evidence']['checkpoint'] == 4
    # Ng advances the saved counter, not the radiation-iteration allowance.
    assert first['charged_iterations'] == first['evidence']['iterations'] == 3
    assert not first.get('checkpoint_restored')
    assert result['attempts'][-1]['evidence']['fresh_verified']
    assert (model/'POINT1').read_text().splitlines()[1].split()[1] == '7'


def test_ng_after_final_solve_cannot_establish_convergence(ng_workspace):
    _model, plan = ng_workspace
    result = run_plan(plan('ng_final'))
    assert result['status'] == 'succeeded', result
    first = result['attempts'][0]['evidence']
    assert first['checkpoint'] == 4
    assert first['ng_accelerations'] == [3]
    assert not first['candidate']
    assert len(result['attempts']) == 3
    assert result['attempts'][-1]['evidence']['fresh_verified']


def test_ng_between_last_two_solves_requires_more_full_steps(ng_workspace):
    _model, plan = ng_workspace
    result = run_plan(plan('ng_success', iterations=2))
    assert result['status'] == 'succeeded', result
    first = result['attempts'][0]['evidence']
    assert [r['global_iteration'] for r in first['records']] == [1, 3]
    assert not first['candidate']
    assert len(result['attempts']) == 3
    assert result['attempts'][-1]['evidence']['fresh_verified']


@pytest.mark.parametrize('scenario', ['ng_unexplained', 'ng_wrong_pointer',
                                     'ng_duplicate', 'ng_no_gap'])
def test_ng_near_matches_still_reject_inconsistent_checkpoints(ng_workspace, scenario):
    model, plan = ng_workspace
    # Establish a usable baseline, then reset the fake's invocation counter.
    assert run_plan(plan())['status'] == 'succeeded'
    (model/'attempts.txt').unlink()
    before = {n: (model/n).read_bytes() for n in ('POINT1', 'POINT2', 'SCRTEMP')}
    result = run_plan(plan(scenario))
    assert result['status'] == 'needs_review', result
    assert result['attempts'][0]['checkpoint_restored']
    assert all((model/n).read_bytes() == content for n, content in before.items())


@pytest.mark.parametrize('text', [
    ' NG Acceleration performed using NG_BAND= 10\n',
    'Current great iteration count is 73\n NG Acceleration performed using NG_BAND= 10\n',
    'Current great iteration count is 73\nMaximm changes as returned by SOLVEBA_V13 is NaN\n'
    ' NG Acceleration performed using NG_BAND= 10\n',
])
def test_ng_marker_requires_preceding_completed_population_solve(text):
    with pytest.raises(RunnerError, match='Ambiguous native Ng'):
        ng_accelerations(text)


def test_failed_ng_attempt_does_not_explain_a_counter_increment():
    text = ('Current great iteration count is 73\n'
            'Maximm changes as returned by SOLVEBA_V13 is 0.838\n'
            'Error performing NG acceleration.\nWill try again in 8 iterations.\n')
    assert ng_accelerations(text) == []
