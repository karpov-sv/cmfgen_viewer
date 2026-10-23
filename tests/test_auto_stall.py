"""Distinguish capped solver metrics and changing structures from a plateau."""
import json

import pytest

from test_runner_auto import auto_workspace
from test_auto_hydro import hydro_workspace
from cmfgen_viewer import auto_policies as policies
from cmfgen_viewer.runner import run_plan


def _evidence(*, increase=1000, decrease=2000, temperature=200, count=50):
    return {
        'records': [{'global_iteration': 1, 'lambda_iteration': False, 'temperature_fixed': False,
                     'solver_maximum_change': 1e7, 'maximum_increase_percent': increase,
                     'maximum_decrease_percent': decrease}],
        'counts': {'nt': 100, 'nd': 3, 'totals': {'100.0%': count, '0.001%': 200}},
        'raw_temperature_steps': [[temperature, 0, 0]], 'temperatures': [1, 2, 3],
        'hydro_revisions': [], 'epsilon_percent': 0.02, 'full_iterations': 1,
        'candidate': False, 'fresh_verified': False,
    }


def _context(model, history, *, fresh=True):
    (model/'VADAT').write_text(f"{0 if fresh else 2} [N_FIX_BA]\n0 [FIX_BA]\nMAJOR [SCALE_OPT]\n")
    return policies.Context(model, 'success', {}, {}, {}, history[-1], history, 'iterate', [], '')


@pytest.mark.parametrize('diagnostic,values', [
    ('increase', [1000, 999, 998]),
    ('decrease', [2000, 1999, 1998]),
    ('temperature', [219.34, 182.29, 148.06]),
    ('count', [50, 49, 48]),
    ('increase', [1000, 950, 980]),
])
def test_saturated_metric_cannot_hide_uncapped_progress(tmp_path, diagnostic, values):
    history = [_evidence(**{diagnostic: value}) for value in values]

    decision, _ = policies.choose(_context(tmp_path, history))

    assert decision.kind == 'continue'
    assert decision.policy_id == 'stalled_corrections'
    assert decision.evidence['saturated_solver_metric']
    assert decision.evidence['improving_diagnostics']
    assert decision.evidence['solver_maximum_changes'] == [1e7]*3


@pytest.mark.parametrize('fresh,kind', [(True, 'stop'), (False, 'action')])
def test_saturated_plateau_still_requires_refresh_or_review(tmp_path, fresh, kind):
    history = [_evidence() for _ in range(3)]

    decision, _ = policies.choose(_context(tmp_path, history, fresh=fresh))

    assert decision.kind == kind
    assert decision.evidence['saturated_solver_metric']
    assert not decision.evidence['improving_diagnostics']
    if not fresh:
        assert decision.action == 'fresh_jacobian'


@pytest.mark.parametrize('bad', [None, float('nan'), float('inf'), -1])
def test_saturation_without_valid_raw_extrema_cannot_prove_a_stall(tmp_path, bad):
    history = [_evidence() for _ in range(3)]
    history[1]['records'][-1]['maximum_decrease_percent'] = bad

    decision, _ = policies.choose(_context(tmp_path, history))

    assert decision.kind == 'continue'
    assert decision.policy_id == 'continue'


def test_counts_from_different_final_iteration_modes_cannot_show_progress(tmp_path):
    history = [_evidence(count=count) for count in [50, 40, 30]]
    history[0]['records'].append({'lambda_iteration': True, 'temperature_fixed': True})

    decision, _ = policies.choose(_context(tmp_path, history))

    assert decision.kind == 'stop'
    assert not any(key.startswith('count_above_') for key in decision.evidence['correction_trends'])


def test_counts_below_convergence_tolerance_do_not_mask_a_plateau(tmp_path):
    history = [_evidence() for _ in range(3)]
    for evidence, count in zip(history, [200, 150, 100]):
        evidence['counts']['totals']['0.001%'] = count

    decision, _ = policies.choose(_context(tmp_path, history))

    assert decision.kind == 'stop'


@pytest.mark.parametrize('revision_batch', [0, 1, 2])
def test_hydro_batches_cannot_establish_a_comparable_plateau(tmp_path, revision_batch):
    history = [_evidence() for _ in range(3)]
    history[revision_batch]['hydro_revisions'] = [1]

    decision, _ = policies.choose(_context(tmp_path, history))

    assert decision.kind == 'continue'


def test_different_grid_sizes_cannot_establish_a_plateau(tmp_path):
    history = [_evidence() for _ in range(3)]
    history[0]['counts']['nd'] = 4

    decision, _ = policies.choose(_context(tmp_path, history))

    assert decision.kind == 'continue'


def test_older_advisory_summary_without_counts_defers_stall_assessment(tmp_path):
    history = [_evidence() for _ in range(3)]
    del history[0]['counts']

    decision, _ = policies.choose(_context(tmp_path, history))

    assert decision.kind == 'continue'


def test_mixed_hydro_batch_cannot_trigger_local_relaxation(tmp_path):
    history = [_evidence() for _ in range(3)]
    history[-1]['hydro_revisions'] = [1]
    history[-1]['raw_temperature_steps'] = [[1, 0, 0], [-1, 0, 0], [1, 0, 0]]

    decision, _ = policies.choose(_context(tmp_path, history))

    assert decision.kind == 'continue'


def test_recorded_bstar3010_progress_is_not_a_stall(tmp_path):
    history = [_evidence(increase=inc, decrease=dec, temperature=temp, count=count)
               for inc, dec, temp, count in [(7310, 1280, 219.34, 10481),
                                             (4630, 39200, 182.29, 8100),
                                             (3070, 8730, 148.06, 6520)]]
    for evidence in history:
        evidence['counts'].update(nt=2233, nd=125)
        evidence['raw_temperature_steps'][-1].extend([0]*122)
        evidence['temperatures'] = [1]*125
    # First assess the capped values alone, independent of the hydro barrier.
    decision, _ = policies.choose(_context(tmp_path, history))
    assert decision.kind == 'continue'
    assert 'maximum_increase_percent' in decision.evidence['improving_diagnostics']
    assert 'raw_temperature_maximum_percent' in decision.evidence['improving_diagnostics']
    history[0]['hydro_revisions'] = [22]
    history[2]['hydro_revisions'] = [32]
    decision, _ = policies.choose(_context(tmp_path, history))
    assert decision.kind == 'continue'


@pytest.mark.parametrize('decaying,fresh,expected,attempts', [
    (True, True, 'limit_reached', 5),
    (False, True, 'needs_review', 3),
    (False, False, 'needs_review', 6),
])
def test_capped_native_batches_continue_or_stop_from_raw_trends(auto_workspace, decaying, fresh, expected, attempts):
    model, plan = auto_workspace
    if fresh:
        (model/'VADAT').write_text((model/'VADAT').read_text().replace('2 [N_FIX_BA]', '0 [N_FIX_BA]').replace('10 [FIX_BA]', '0 [FIX_BA]'))
    exe = model.parent/'cmf/exe/cmfgen_dev.exe'
    code = exe.read_text().replace("if mode=='stall':value=1",
                                   "if mode=='stall':value=" + ('200/attempt' if decaying else '200'))
    code = code.replace('0.001 if mode=="raw_high" else value', '10000000 if mode=="stall" else value')
    exe.write_text(code)

    result = run_plan(plan('stall', max_attempts=5 if decaying else 8))

    assert result['status'] == expected, result
    assert len(result['attempts']) == attempts
    assert len(result['actions']) == (0 if fresh else 1)
    decision = result['attempts'][-1]['decision']
    assert decision['evidence']['saturated_solver_metric']
    assert bool(decision['evidence']['improving_diagnostics']) == decaying
    assert not result['attempts'][-1]['evidence']['candidate']


def test_native_hydro_restarts_batch_history_before_stall_detection(hydro_workspace):
    model, plan, _original = hydro_workspace
    (model/'VADAT').write_text((model/'VADAT').read_text().replace('2 [N_FIX_BA]', '0 [N_FIX_BA]').replace('10 [FIX_BA]', '0 [FIX_BA]'))
    (model/'HYDRO_DEFAULTS').write_text('1 [N_ITS]\n0 [ITS_DONE]\n10 [STRT_ITS]\n10 [FREQ_ITS]\n')
    exe = model.parent/'cmf/exe/cmfgen_dev.exe'
    code = exe.read_text().replace("(done==0 or mode=='hydro_rebound') and stop=='T'", 'False')
    code = code.replace("low=0.4 if done==0 or mode=='hydro_rebound' else 0.97", 'low=0.97')
    code = code.replace("if stop=='F' and mode!='hydro_no_revision':", 'if attempt==3:')
    exe.write_text(code)
    events = []

    result = run_plan(plan('stall', max_attempts=10, max_iterations=15), events.append)

    assert result['status'] == 'limit_reached', result
    assert len(result['attempts']) == 5
    assert result['iterations_used'] == 15
    assert not result['actions']
    resets = [e for e in events if e['event'] == 'auto_history_reset']
    assert len(resets) == 1 and resets[0]['attempt'] == 3
    assert resets[0]['hydro_revisions'] == [10]
    saved = [json.loads(row) for row in (model/'.cmfgen-runs'/result['run_id']/'events.jsonl').read_text().splitlines()]
    assert resets == [e for e in saved if e['event'] == 'auto_history_reset']
