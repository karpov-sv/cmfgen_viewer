"""Real native records: conservative local guesses and refusal boundaries."""
import struct
from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest

from cmfgen_viewer.checkpoint_health import RECORD_BYTES, _words
from cmfgen_viewer.checkpoint_physics import checkpoint_physics, compare_physics
from cmfgen_viewer.population_projection import apply_projection, propose_projection, projected_raw_requests
from cmfgen_viewer.population_projection import localized_population_projection
from cmfgen_viewer.auto_policies import Context, Declined
from cmfgen_viewer.runner_recipe import RunnerError


@pytest.fixture
def projection_model(tmp_path):
    tmp_path = tmp_path/'projection-source'
    tmp_path.mkdir()
    (tmp_path/'VADAT').write_text('F [DO_HYDRO]\n')
    (tmp_path/'MODEL_SPEC').write_text('5 [ND]\n1,1,1 [HI_ISF]\n1,1,1 [HeI_ISF]\n')
    (tmp_path/'MODEL').write_text(
        '5 !Number of depth points\n6 !Total number of variables\n\f\n'
        'HI 1 1 1.0 1.0 1.0 1.0 1 1 1 1 ground\n'
        'HeI 1 1 1.0 1.0 1.0 2.0 1 3 2 2 ground\n')
    pointer = '28-Feb-2004 !Format date\n1 1 1 -1000 T\n'
    for name in ['POINT1', 'POINT2']:
        (tmp_path/name).write_text(pointer)
    geo = [6., 5., 4., 3., 2.]+[20.]*5+[0.]*5
    populations = []
    for i in range(5):
        neutral = .9 if i == 2 else .001
        h0, h1 = 1e10*neutral, 1e10*(1-neutral)
        populations.extend([h0, h1, 5e8, 5e8, h1+5e8, 1.])
    def pack(values):
        payload = struct.pack('<'+str(len(values))+'d', *values)
        return payload+bytes(RECORD_BYTES-len(payload))
    # An unselected future record must also be byte-preserved.
    (tmp_path/'SCRTEMP').write_bytes(pack(geo)*3+pack(populations)+pack(geo)+pack(populations))
    return tmp_path


def _pops(model):
    with (model/'SCRTEMP').open('rb') as stream:
        return np.fromiter(_words(stream, 3, 30, '<'), float).reshape(5, 6)


def test_proposal_is_read_only_and_atomic_application_preserves_other_state(projection_model):
    model = projection_model
    original = (model/'SCRTEMP').read_bytes()
    before, pops = checkpoint_physics(model), _pops(model)
    plan = propose_projection(model, 3)
    assert (model/'SCRTEMP').read_bytes() == original
    assert plan['reference_ion'] == 'HI' and plan['contrast'] == pytest.approx(900)
    assert plan['variables'] == [1, 2]
    pointers = [(model/name).read_bytes() for name in ['POINT1', 'POINT2']]
    result = apply_projection(model, plan)
    after = _pops(model)
    assert set(map(tuple, np.argwhere(after != pops))) == {(2, 0), (2, 1), (2, 4)}
    assert after[2, 0] == pytest.approx(1e7)
    assert after[2, 4] == pytest.approx(1.049e10)
    assert (model/'SCRTEMP').read_bytes()[4*RECORD_BYTES:] == original[4*RECORD_BYTES:]
    assert [(model/name).read_bytes() for name in ['POINT1', 'POINT2']] == pointers
    assert result['restart_counter_unchanged']
    checks = compare_physics(before, checkpoint_physics(model), fixed_temperature=True)
    assert checks['element_density_max_relative_change'] < 1e-14
    assert checks['charge_relative_error'] < 1e-14
    assert propose_projection(model, 3) is None


@pytest.mark.parametrize('depth', [1, 2, 4, 5, 0, 6])
def test_boundary_or_nonisolated_depth_does_not_authorize_projection(projection_model, depth):
    assert propose_projection(projection_model, depth) is None


@pytest.mark.parametrize('contrast,accepted', [(49.9, False), (50., True), (81.5, True)])
def test_lower_contrast_spike_boundary_preserves_conservation(projection_model, contrast, accepted):
    model = projection_model
    values = _pops(model)
    # A neutral spike like Bstar3518, with unequal but consistent neighbors.
    peak = .78125
    for depth, fraction in [(1, .0034), (2, peak), (3, peak/contrast)]:
        values[depth, :2] = [1e10*fraction, 1e10*(1-fraction)]
        values[depth, -2] = values[depth, 1]+values[depth, 3]
    with (model/'SCRTEMP').open('r+b') as stream:
        stream.seek(3*RECORD_BYTES)
        stream.write(values.astype('<f8').tobytes())
    before = (model/'SCRTEMP').read_bytes()
    proposal = propose_projection(model, 3)
    assert (proposal is not None) == accepted
    assert (model/'SCRTEMP').read_bytes() == before
    if accepted:
        assert proposal['contrast'] == pytest.approx(contrast)
        baseline = checkpoint_physics(model)
        apply_projection(model, proposal)
        checks = compare_physics(baseline, checkpoint_physics(model), fixed_temperature=True)
        assert checks['element_density_max_relative_change'] < 1e-14
        assert propose_projection(model, 3) is None


@pytest.mark.parametrize('name', ['SCRTEMP', 'MODEL', 'MODEL_SPEC', 'POINT1'])
def test_changed_baseline_is_refused_without_a_checkpoint_write(projection_model, name):
    model = projection_model
    plan = propose_projection(model, 3)
    path = model/name
    if name == 'SCRTEMP':
        data = bytearray(path.read_bytes());data[-1] = 1;path.write_bytes(data)
    elif name == 'POINT1':
        path.write_text(path.read_text().replace('1 1 1', '2 2 1'))
    else:
        path.write_text(path.read_text()+'\n')
    preserved = (model/'SCRTEMP').read_bytes()
    with pytest.raises(RunnerError):
        apply_projection(model, plan)
    assert (model/'SCRTEMP').read_bytes() == preserved


def test_projection_does_not_accept_caller_supplied_population_vectors(projection_model):
    model = projection_model
    plan = propose_projection(model, 3)
    plan.update(populations=[0]*30, variables=[5, 6])
    result = apply_projection(model, plan)
    assert result['variables'] == [1, 2]
    assert _pops(model)[2, 5] == 1.


def test_representable_tiny_levels_survive_normalized_fraction_underflow(projection_model):
    model = projection_model
    old = _pops(model)
    # Add an extremely faint neutral H level, whose normalized fraction
    # underflows even though its absolute population is representable.
    values = np.insert(old, 1, 1e-320, axis=1)
    (model/'MODEL_SPEC').write_text('5 [ND]\n2,2,2 [HI_ISF]\n1,1,1 [HeI_ISF]\n')
    (model/'MODEL').write_text(
        '5 !Number of depth points\n7 !Total number of variables\n\f\n'
        'HI 2 2 1.0 1.0 1.0 1.0 1 1 1 1 faint\n'
        'HeI 1 1 1.0 1.0 1.0 2.0 1 4 2 2 ground\n')
    with (model/'SCRTEMP').open('r+b') as stream:
        stream.seek(3*RECORD_BYTES);stream.write(values.astype('<f8').tobytes())
    plan = propose_projection(model, 3)
    apply_projection(model, plan)
    with (model/'SCRTEMP').open('rb') as stream:
        after = np.fromiter(_words(stream, 3, 35, '<'), float).reshape(5, 7)
    assert after[2, 1] > 0
    assert after[2, 1] == pytest.approx(1e-320, rel=.001, abs=0)


@pytest.mark.parametrize('change', ['thermal', 'density', 'multiple_species', 'charge'])
def test_physical_discontinuities_ambiguous_spikes_and_bad_charge_are_refused(projection_model, change):
    model = projection_model
    values = _pops(model)
    if change == 'thermal':
        values[2, -1] *= 2
    elif change == 'density':
        values[2, :2] *= 10;values[2, -2] = values[2, 1]+values[2, 3]
    elif change == 'multiple_species':
        values[:, 2:4] = [1e6, 999e6]
        values[2, 2:4] = [9e8, 1e8]
        values[:, -2] = values[:, 1]+values[:, 3]
    else:
        values[2, -2] *= 2
    with (model/'SCRTEMP').open('r+b') as stream:
        stream.seek(3*RECORD_BYTES);stream.write(values.astype('<f8').tobytes())
    if change == 'charge':
        with pytest.raises(RunnerError, match='charge'):
            propose_projection(model, 3)
    else:
        assert propose_projection(model, 3) is None


def _solution(raw):
    text = ' STEQ SOLUTION ARRAY\n'
    for variable in range(1, 7):
        values = [0.001]*5
        if variable == 1:
            values[2] = raw
        text += f'{variable}( 1)# '+' '.join(map(str, values))+'\n'
    return text


def test_repaired_raw_coordinates_use_only_complete_new_native_solutions(tmp_path):
    path = tmp_path/'STEQ_VALS'
    path.write_text(_solution(1e6))
    offset = path.stat().st_size
    with path.open('a') as stream:
        stream.write(_solution(.01)+_solution(-.02))
    evidence = {'solution_start_offset': offset, 'counts': {'nt': 6, 'nd': 5},
                'records': [{}, {}]}
    rows = projected_raw_requests(tmp_path, evidence, [1, 2], 3)
    assert [r['nonpositive_unlimited_targets'] for r in rows] == [0, 0]
    assert rows[0]['maximum_decrease_percent'] == 1
    assert rows[1]['maximum_increase_percent'] == 2


@pytest.mark.parametrize('contents', [_solution(1e6)[:-10], _solution(.01).replace('6( 1)#', '5( 1)#'),
                                     _solution(.01).replace('0.01', 'nan'),
                                     _solution(.01)+_solution(.01)])
def test_invalid_truncated_or_unmatched_raw_arrays_cannot_validate_projection(tmp_path, contents):
    (tmp_path/'STEQ_VALS').write_text(contents)
    evidence = {'solution_start_offset': 0, 'counts': {'nt': 6, 'nd': 5}, 'records': [{}]}
    with pytest.raises(RunnerError):
        projected_raw_requests(tmp_path, evidence, [1, 2], 3)


def test_unlimited_negative_population_target_is_reported(tmp_path):
    (tmp_path/'STEQ_VALS').write_text(_solution(1.01))
    evidence = {'solution_start_offset': 0, 'counts': {'nt': 6, 'nd': 5}, 'records': [{}]}
    assert projected_raw_requests(tmp_path, evidence, [1, 2], 3)[0]['nonpositive_unlimited_targets'] == 1


@pytest.fixture
def projection_context(projection_model, monkeypatch):
    from cmfgen_viewer import auto_recovery
    monkeypatch.setattr(auto_recovery, 'repaired_runtime', lambda plan: True)
    (projection_model/'VADAT').write_text('F [DO_HYDRO]\nMAJOR [SCALE_OPT]\nT [INCL_dSLdT]\n0 [N_FIX_BA]\n0 [FIX_BA]\n')
    full = {'ba_computed': True, 'maximum_decrease_percent': 7e7,
            'major_species_minimum_scale': .001, 'maximum_decrease_depth': 3,
            'lambda_iteration': False, 'temperature_fixed': False, 'grey_solution': False}
    evidence = {'solution_start_offset': 0, 'counts': {'nt': 6, 'nd': 5}, 'records': [dict(full, global_iteration=11),
                 dict(full, global_iteration=12, lambda_iteration=True, temperature_fixed=True),
                 dict(full, global_iteration=13)]}
    (projection_model/'STEQ_VALS').write_text(_solution(7e5)+_solution(.01)+_solution(7e5))
    return Context(projection_model, 'success', {'restart': {'mode': 'continuation'}},
                   {}, {}, evidence, [evidence], 'iterate', [], '')


def test_recognized_projection_is_read_only_and_requires_full_followup(projection_context):
    ctx = projection_context
    before = (ctx.model/'SCRTEMP').read_bytes()
    decision = localized_population_projection(ctx)
    assert decision.action == 'localized_population_projection'
    assert decision.evidence['projection']['reference_ion'] == 'HI'
    assert decision.steps[0].iterations == 2 and decision.steps[0].repeat_on_native_fallback
    assert (ctx.model/'SCRTEMP').read_bytes() == before


def test_unrelated_global_maximum_depth_does_not_hide_the_binary_spike(projection_context):
    ctx = projection_context
    evidence = deepcopy(ctx.evidence)
    for record in evidence['records']:
        record['maximum_decrease_depth'] = 4
    decision = localized_population_projection(replace(ctx, evidence=evidence))
    assert decision.evidence['projection']['depth'] == 3


@pytest.mark.parametrize('contrast,accepted', [(81.5, True), (49.9, False)])
def test_lower_contrast_policy_still_requires_the_complete_failure_signature(projection_context, contrast, accepted):
    ctx = projection_context
    values = _pops(ctx.model)
    for depth, fraction in [(1, .0034), (3, .9/contrast)]:
        values[depth, :2] = [1e10*fraction, 1e10*(1-fraction)]
        values[depth, -2] = values[depth, 1]+values[depth, 3]
    with (ctx.model/'SCRTEMP').open('r+b') as stream:
        stream.seek(3*RECORD_BYTES)
        stream.write(values.astype('<f8').tobytes())
    assert (localized_population_projection(ctx) is not None) == accepted
    # Even an eligible geometric peak does not authorize unrelated/small raw targets.
    (ctx.model/'STEQ_VALS').write_text(_solution(.01)*3)
    assert localized_population_projection(ctx) is None


@pytest.mark.parametrize('failure', [None, 'negative_target', 'retained_spike'])
def test_full_response_must_remove_both_the_spike_and_negative_targets(projection_context, monkeypatch, failure):
    from cmfgen_viewer import auto_hydro
    from cmfgen_viewer.population_projection import _projection_response
    ctx = replace(projection_context, evidence={**projection_context.evidence, 'iterations': 3})
    proposal = propose_projection(ctx.model, 3)
    if failure != 'retained_spike':
        apply_projection(ctx.model, proposal)
    monkeypatch.setattr(auto_hydro, 'guard_measurements',
                        lambda *args: {'luminosity_min': .99, 'luminosity_max': 1.1})
    (ctx.model/'STEQ_VALS').write_text(_solution(1.01 if failure == 'negative_target' else .1)*3)
    observed, attempts = [], []
    if failure:
        with pytest.raises(RunnerError, match='nonpositive|spike'):
            _projection_response(ctx, proposal, observed, attempts)
    else:
        checks = _projection_response(ctx, proposal, observed, attempts)
        assert checks['population_projection_check']['remaining_contrast'] == pytest.approx(1)
        assert [r['iteration'] for r in observed] == [11, 13]


@pytest.fixture
def settling_context(projection_context, monkeypatch):
    from cmfgen_viewer import auto_hydro
    ctx = projection_context
    model = ctx.model
    old = _pops(model)
    values = np.empty((5, 15))
    values[:, :10] = old[:, :1]/10
    values[:, 10:] = old[:, 1:]
    for depth, fraction in [(1, .0034), (3, .9/81.5)]:
        values[depth, :10] = 1e9*fraction
        values[depth, 10] = 1e10*(1-fraction)
        values[depth, -2] = values[depth, 10]+values[depth, 12]
    (model/'MODEL_SPEC').write_text('5 [ND]\n10,10,10 [HI_ISF]\n1,1,1 [HeI_ISF]\n')
    (model/'MODEL').write_text(
        '5 !Number of depth points\n15 !Total number of variables\n\f\n'
        'HI 10 10 1.0 1.0 1.0 1.0 1 1 1 1 ground\n'
        'HeI 1 1 1.0 1.0 1.0 2.0 1 12 2 2 ground\n')
    with (model/'SCRTEMP').open('r+b') as stream:
        stream.seek(3*RECORD_BYTES)
        stream.write(values.astype('<f8').tobytes())
    proposal = propose_projection(model, 3)
    assert proposal['contrast'] == pytest.approx(81.5)
    apply_projection(model, proposal)
    monkeypatch.setattr(auto_hydro, 'guard_measurements',
                        lambda *args: {'luminosity_min': .99, 'luminosity_max': 1.1})
    ctx = replace(ctx, evidence={**ctx.evidence, 'iterations': 3, 'counts': {'nt': 15, 'nd': 5}})
    def raw_solutions(bad_variable=1, bad_value=2.1, repeat=False, count=3):
        text = ''
        for solve in range(count):
            text += ' STEQ SOLUTION ARRAY\n'
            for variable in range(1, 16):
                row = [.001]*5
                if variable == bad_variable and (solve == 0 or repeat):
                    row[2] = bad_value
                text += f'{variable}( 1)# '+' '.join(map(str, row))+'\n'
        (model/'STEQ_VALS').write_text(text)
    return ctx, proposal, raw_solutions


@pytest.mark.parametrize('contrast', [81.5, 237.973])
def test_ground_only_settling_never_counts_as_positive_verification(settling_context, contrast):
    from cmfgen_viewer.population_projection import _projection_response
    ctx, proposal, raw_solutions = settling_context
    proposal = {**proposal, 'contrast': contrast}
    raw_solutions()
    checks = _projection_response(ctx, proposal, [], [], settling=True)['population_projection_settling_check']
    assert checks['full_solve_requests'] == []
    assert len(checks['settling_full_requests']) == 2
    with pytest.raises(RunnerError, match='nonpositive'):
        _projection_response(ctx, proposal, [], [])
    raw_solutions(bad_value=.1)
    observed = []
    _projection_response(ctx, proposal, observed, [])
    assert [r['iteration'] for r in observed] == [11, 13]


@pytest.mark.parametrize('variable,value,repeat', [(2, 2.1, False), (14, 2.1, False),
                                                 (1, 10.01, False), (1, 2.1, True)])
def test_settling_refuses_excited_or_electron_failures_large_or_repeated_overshoots(settling_context, variable, value, repeat):
    from cmfgen_viewer.population_projection import _projection_response
    ctx, proposal, raw_solutions = settling_context
    raw_solutions(variable, value, repeat)
    with pytest.raises(RunnerError, match='nonpositive'):
        _projection_response(ctx, proposal, [], [], settling=True)


@pytest.mark.parametrize('second', [1.03, 2., 2.2])
def test_two_settling_batches_require_improving_ground_request_and_never_grant_credit(settling_context, second):
    from cmfgen_viewer.population_projection import _projection_response
    from cmfgen_viewer.auto_policies import VerificationPending
    ctx, proposal, raw_solutions = settling_context
    first = replace(ctx, evidence={**ctx.evidence, 'iterations': 2, 'records': ctx.evidence['records'][:2]})
    raw_solutions(count=2)
    observed, attempts = [], []
    with pytest.raises(VerificationPending) as pending:
        _projection_response(first, proposal, observed, attempts, settling=True)
    assert pending.value.checks['population_projection_settling_check']['full_solve_requests'] == []
    records = [{**r, 'global_iteration': r['global_iteration']+2} for r in first.evidence['records']]
    next_ctx = replace(first, evidence={**first.evidence, 'records': records})
    raw_solutions(bad_value=second, count=2)
    if second > 1.89:
        with pytest.raises(RunnerError, match='nonpositive'):
            _projection_response(next_ctx, proposal, observed, attempts, settling=True)
        return
    checks = _projection_response(next_ctx, proposal, observed, attempts, settling=True)
    check = checks['population_projection_settling_check']
    assert check['full_solve_requests'] == []
    assert [r['iteration'] for r in check['settling_full_requests']] == [11, 13]
    with pytest.raises(RunnerError, match='nonpositive'):
        _projection_response(next_ctx, proposal, [], [])
    with pytest.raises(RunnerError, match='exceeded two'):
        _projection_response(next_ctx, proposal, observed, attempts, settling=True)


@pytest.mark.parametrize('field,value', [('maximum_decrease_percent', None),
    ('maximum_decrease_percent', float('nan')), ('maximum_decrease_percent', 1e5),
    ('major_species_minimum_scale', None), ('major_species_minimum_scale', float('inf')),
    ('major_species_minimum_scale', 0), ('major_species_minimum_scale', 1.01),
    ('ba_computed', False), ('maximum_decrease_depth', 0),
    ('temperature_fixed', True), ('lambda_iteration', True)])
def test_incomplete_or_different_full_step_signature_cannot_authorize_projection(projection_context, field, value):
    ctx = projection_context
    evidence = deepcopy(ctx.evidence)
    evidence['records'][-1][field] = value
    assert localized_population_projection(replace(ctx, evidence=evidence, history=[evidence])) is None


@pytest.mark.parametrize('flag', ['source_changed','hydro_revisions','ng_accelerations','checkpoint_updates'])
def test_native_transitions_cannot_authorize_a_stale_projection(projection_context, flag):
    ctx = projection_context
    evidence = {**ctx.evidence, flag: True}
    assert localized_population_projection(replace(ctx, evidence=evidence, history=[evidence])) is None


@pytest.mark.parametrize('control', ['FIX_T','FIX_NE','FIX_IMP','USE_FIXED_J','INC_GRID','SN_MODEL','USE_J_REL'])
def test_explicit_constraints_and_unvalidated_solver_families_are_preserved(projection_context, control):
    ctx = projection_context
    with (ctx.model/'VADAT').open('a') as stream:
        stream.write(f'T [{control}]\n')
    assert localized_population_projection(ctx) is None


def test_unknown_executable_and_mismatched_grid_decline_projection(projection_context, monkeypatch):
    from cmfgen_viewer import auto_recovery
    ctx = projection_context
    monkeypatch.setattr(auto_recovery, 'repaired_runtime', lambda plan: False)
    with pytest.raises(Declined, match='runtime'):
        localized_population_projection(ctx)
    monkeypatch.setattr(auto_recovery, 'repaired_runtime', lambda plan: True)
    evidence = {**ctx.evidence, 'counts': {'nt': 7, 'nd': 5}}
    with pytest.raises(Declined, match='dimensions'):
        localized_population_projection(replace(ctx, evidence=evidence, history=[evidence]))


def test_grey_output_diagnostic_does_not_replace_an_ordinary_full_solve(projection_context):
    ctx = projection_context
    evidence = deepcopy(ctx.evidence)
    evidence['records'][-1]['grey_solution'] = True
    assert localized_population_projection(replace(ctx, evidence=evidence, history=[evidence])) is not None


def test_peak_in_one_ion_cannot_repair_unrelated_negative_target(projection_context):
    ctx = projection_context
    (ctx.model/'STEQ_VALS').write_text((_solution(7e5)*3).replace('1( 1)#', '2( 1)#'))
    with pytest.raises(Declined):
        localized_population_projection(ctx)
    (ctx.model/'STEQ_VALS').write_text(_solution(.001)*3)
    assert localized_population_projection(ctx) is None
    line = '2( 1)# '+' '.join(['0.001']*5)
    wrong_ion = _solution(.001).replace(line, '2( 1)# 0.001 0.001 700000 0.001 0.001')
    (ctx.model/'STEQ_VALS').write_text(wrong_ion*3)
    assert localized_population_projection(ctx) is None


@pytest.fixture
def production_failure_context(settling_context):
    ctx, _, _ = settling_context
    with (ctx.model/'SCRTEMP').open('r+b') as stream:
        values = np.fromiter(_words(stream, 3, 75, '<'), float).reshape(5, 15)
        values[2, :10] = 9e8
        values[2, 10] = 1e9
        values[2, 13] = values[2, 10]+values[2, 12]
        stream.seek(3*RECORD_BYTES)
        stream.write(values.astype('<f8').tobytes())

    def invocation(specs):
        records, text = [], ''
        for iteration, local, global_max, scale, mode in specs:
            lam = mode == 'lambda'
            records.append({'global_iteration': iteration, 'ba_computed': True,
                            'lambda_iteration': lam, 'temperature_fixed': lam,
                            'maximum_decrease_depth': 3, 'maximum_decrease_percent': global_max,
                            'major_species_minimum_scale': scale})
            text += ' STEQ SOLUTION ARRAY\n'
            for variable in range(1, 16):
                row = [.001]*5
                if mode == 'ground' and variable == 1:
                    row[2] = local/100
                elif mode in {'excited', 'minority'} and 2 <= variable <= (10 if mode == 'excited' else 2):
                    row[2] = local/100
                if variable == 12:
                    row[2] = global_max/100  # Another ion owns the global maximum.
                text += f'{variable}( 1)# '+' '.join(map(str, row))+'\n'
        (ctx.model/'STEQ_VALS').write_text(text)
        e = {**ctx.evidence, 'iterations': len(records), 'records': records}
        return replace(ctx, evidence=e, history=[e])
    return ctx, invocation


def test_production_196_200_uses_ion_targets_despite_larger_other_ion_maximum(production_failure_context):
    base, invocation = production_failure_context
    ctx = invocation([(196, 131730, 1.59e7, .0033962, 'excited'),
                      (197, 0, 9, 1, 'lambda'),
                      (198, 984690, 6.45e6, .021046, 'excited'),
                      (199, 0, 14, 1, 'lambda'),
                      (200, 66400000, 6.64e7, .0011526, 'excited')])
    before = (base.model/'SCRTEMP').read_bytes()
    decision = localized_population_projection(ctx)
    assert decision.evidence['diagnosed_full_iterations'] == [198, 200]
    assert [r['maximum_decrease_percent'] for r in decision.evidence['offending_ion_requests']] == [984690, 66400000]
    assert (base.model/'SCRTEMP').read_bytes() == before


@pytest.mark.parametrize('contrast', [81.5, 237.973])
def test_production_201_204_recognizes_ground_excited_cycle(production_failure_context, contrast):
    base, invocation = production_failure_context
    if contrast > 100:
        with (base.model/'SCRTEMP').open('r+b') as stream:
            values = np.fromiter(_words(stream, 3, 75, '<'), float).reshape(5, 15)
            for depth, fraction in [(1, .0034), (3, .9/contrast)]:
                values[depth, :10] = 1e9*fraction
                values[depth, 10] = 1e10*(1-fraction)
                values[depth, 13] = values[depth, 10]+values[depth, 12]
            stream.seek(3*RECORD_BYTES)
            stream.write(values.astype('<f8').tobytes())
    ctx = invocation([(201, 700.73, 2750, .048336, 'ground'),
                      (202, 0, 74.1, 1, 'lambda'),
                      (203, 1511600, 1.6e6, .034148, 'excited'),
                      (204, 0, 50.7, 1, 'lambda')])
    decision = localized_population_projection(ctx)
    assert decision.evidence['diagnosed_full_iterations'] == [201, 203]
    assert len(decision.steps) == 2  # A ground/excited cycle needs uncredited settling even at high contrast.
    assert decision.steps[-1].name == 'population_projection_full'
    # Historical evidence alone cannot supply the second full observation.
    one = {**ctx.evidence, 'records': ctx.evidence['records'][2:]}
    assert localized_population_projection(replace(ctx, evidence=one)) is None


@pytest.mark.parametrize('latest,expected', [('healthy', None), ('excited', [196, 200])])
def test_weaker_intermediate_full_does_not_hide_failure_but_healthy_latest_blocks_it(production_failure_context, latest, expected):
    _, invocation = production_failure_context
    ctx = invocation([(196, 131730, 1.59e7, .0033962, 'excited'),
                      (198, 0, 100, .1, 'healthy'),
                      (200, 66400000, 6.64e7, .0011526, latest)])
    decision = localized_population_projection(ctx)
    if expected is None:
        assert decision is None
    else:
        assert decision.evidence['diagnosed_full_iterations'] == expected


@pytest.mark.parametrize('local,mode,accepted', [(1e5, 'excited', True), (99999, 'excited', False),
                                               (1e5, 'minority', False), (700, 'ground', False),
                                               (0, 'healthy', False)])
def test_ground_cycle_needs_a_severe_distributed_ion_failure(production_failure_context, local, mode, accepted):
    _, invocation = production_failure_context
    ctx = invocation([(201, 700.73, 2750, .048336, 'ground'),
                      (203, local, max(local, 2750), .034148, mode)])
    assert (localized_population_projection(ctx) is not None) == accepted
