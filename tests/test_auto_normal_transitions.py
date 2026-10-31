"""Normal native transitions must defer acceptance rather than terminate progress."""
from pathlib import Path

import pytest

from test_runner_auto import auto_workspace
from test_auto_stall import _evidence, _context
from test_auto_convergence_remedies import convergence_workspace
from test_auto_performance import performance_workspace
from test_auto_recovery import population_workspace
from cmfgen_viewer import auto_policies as policies
from cmfgen_viewer.auto_hydro import capture_controls, native_updates
from cmfgen_viewer.auto_native_events import grid_revisions, checkpoint_updates
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner_recipe import RunnerError


def record(counter=1, value=25, *, lam=False):
    return (f'Current great iteration count is {counter}\nBA matrix computed\n'+
            ('LAMBDA iteration used\nTemperature held fixed at all depths.\n' if lam else '')+
            f'Maximm changes as returned by SOLVEBA_V13 is {value}\n')


def test_temperature_release_uses_in_its(auto_workspace):
    model, plan = auto_workspace
    (model/'VADAT').write_text((model/'VADAT').read_text().replace('F [FIX_T]', 'T [FIX_T]'))
    (model/'IN_ITS').write_text('5 [NUM_ITS]\nT [DO_T_AUTO]\n')
    assert plan()['ready']
    before = capture_controls(model)
    (model/'VADAT').write_text((model/'VADAT').read_text().replace('T [FIX_T]', 'F [FIX_T]'))
    assert 'VADAT' in native_updates(model, record(), before)
    (model/'IN_ITS').write_text('5 [NUM_ITS]\nF [DO_T_AUTO]\n')
    before['IN_ITS'] = (model/'IN_ITS').read_text()
    with pytest.raises(RunnerError, match='Unexpected VADAT'):
        native_updates(model, record(), before)


@pytest.mark.parametrize('diagnostic', ['counts', 'populations', 'temperature'])
def test_uncapped_maximum_does_not_hide_progress(tmp_path, diagnostic):
    history = []
    for n in range(3):
        e = _evidence(count=50-n if diagnostic == 'counts' else 50,
                      increase=100-n if diagnostic == 'populations' else 100,
                      temperature=200-n if diagnostic == 'temperature' else 200)
        e['records'][0]['solver_maximum_change'] = 1
        history.append(e)
    decision, _ = policies.choose(_context(tmp_path, history))
    assert decision.kind == 'continue'
    assert decision.evidence['improving_diagnostics']


@pytest.mark.parametrize('progressing,automatic,expected', [(True, True, 'continue'),
    (False, True, 'stop'), (True, False, 'stop')])
def test_lambda_only_startup_needs_progress_and_automatic_release(tmp_path, progressing, automatic, expected):
    history = []
    for n in range(3):
        e = _evidence()
        e['full_iterations'] = 0
        e['records'][0].update(lambda_iteration=True, temperature_fixed=True,
                              solver_maximum_change=1000/(n+1) if progressing else 1000)
        history.append(e)
    ctx = _context(tmp_path, history)
    (tmp_path/'IN_ITS').write_text(f"{'T' if automatic else 'F'} [DO_LAM_AUTO]\n")
    decision, _ = policies.choose(ctx)
    assert decision.kind == expected
    assert decision.kind != 'converged'


@pytest.mark.parametrize('old,new,text', [
    ('T [INC_ADV]\n0.1 [ADV_RELAX]\n', 'T [INC_ADV]\n0.2 [ADV_RELAX]\n',
     'Have adjusted advection relaxation parameter to: 0.2\n'),
    ('T [TRT_NON_TE]\nT [GAMMA_SLOW]\n0.001 [DECNRG_SCLFAC_BEG]\n',
     'T [TRT_NON_TE]\nT [GAMMA_SLOW]\n0.1 [DECNRG_SCLFAC_BEG]\n',
     'Have adjusted radioactivity decay energy scale factor\nNew scale factor is 0.1\n'),
    ('T [INC_SHOCK_POWER]\nT [ADD_SHOCK_POWER_SLOWLY]\n0.01 [SHOCK_POWER_FAC_BEG]\n',
     'T [INC_SHOCK_POWER]\nT [ADD_SHOCK_POWER_SLOWLY]\n0.1 [SHOCK_POWER_FAC_BEG]\n',
     'Have adjusted SHOCK POWERscale factor\nNew scale factor is 0.1\n'),
])
def test_native_ramps_require_matching_enabled_algorithm_and_log(tmp_path, old, new, text):
    (tmp_path/'VADAT').write_text(old)
    (tmp_path/'IN_ITS').write_text('T [DO_LAM_IT]\n')
    before = capture_controls(tmp_path)
    (tmp_path/'VADAT').write_text(new)
    adopted = native_updates(tmp_path, record(lam=True)+text, before)
    assert adopted['VADAT']['native_transitions']
    with pytest.raises(RunnerError):
        native_updates(tmp_path, record(lam=True), before)
    (tmp_path/'VADAT').write_text(new+'1 [UNRELATED]\n')
    with pytest.raises(RunnerError, match='Unexpected VADAT'):
        native_updates(tmp_path, record(lam=True)+text, before)


@pytest.mark.parametrize('flag,key,enable', [('GAMMA_SLOW', 'DECNRG_SCLFAC_BEG', 'TRT_NON_TE'),
    ('ADD_SHOCK_POWER_SLOWLY', 'SHOCK_POWER_FAC_BEG', 'INC_SHOCK_POWER')])
def test_completed_source_ramp_needs_eligible_lambda_evidence(tmp_path, flag, key, enable):
    old = f'T [{enable}]\nT [{flag}]\n1 [{key}]\n'
    (tmp_path/'VADAT').write_text(old)
    (tmp_path/'IN_ITS').write_text('T [DO_LAM_IT]\n')
    before = capture_controls(tmp_path)
    (tmp_path/'VADAT').write_text(old.replace(f'T [{flag}]', f'F [{flag}]'))
    assert native_updates(tmp_path, record(lam=True), before)['VADAT']['native_transitions']
    with pytest.raises(RunnerError):
        native_updates(tmp_path, record(value=101, lam=True), before)


def test_gradual_xrays_require_both_logged_components_and_native_scaling(tmp_path):
    old = 'T [INC_XRAYS]\nT [XSLOW]\n10 [XSCL_FAC]\n0.1 [FIL_FAC_1]\n0.2 [FIL_FAC_2]\n0.001 [XFI1_BEG]\n0.002 [XFI2_BEG]\n'
    (tmp_path/'VADAT').write_text(old)
    (tmp_path/'IN_ITS').write_text('T [DO_LAM_IT]\n')
    before = capture_controls(tmp_path)
    (tmp_path/'VADAT').write_text(old.replace('0.001 [XFI1_BEG]', '0.01 [XFI1_BEG]').replace('0.002 [XFI2_BEG]', '0.02 [XFI2_BEG]'))
    log = 'Have adjusted X-ray values closer to the desired values\nCurrent filling factor is (1st component) 0.01\nCurrent filling factor is (2nd component) 0.02\n'
    assert native_updates(tmp_path, record(lam=True), before, process_text=log)['VADAT']['native_transitions'] == ['xray_ramp']
    with pytest.raises(RunnerError):
        native_updates(tmp_path, record(lam=True), before, process_text=log.replace('0.02', '0.03'))


@pytest.mark.parametrize('kind', ['average', 'undo', 'grid', 'grey'])
def test_checkpoint_only_updates_continue_without_charging_extra_solves(auto_workspace, kind):
    model, plan = auto_workspace
    control = {'average': 'T [DO_AV]\n', 'undo': 'T [DO_UNDO]\n',
               'grid': 'T [REV_RGRID]\n', 'grey': 'T [USE_FIXED_J]\n'}[kind]
    (model/'VADAT').write_text((model/'VADAT').read_text()+control)
    if kind == 'grid':
        (model/'ADJUST_R_DEFAULTS').write_text('2 [N_ITS]\n')
    if kind == 'grey':
        (model/'IN_ITS').write_text('5 [NUM_ITS]\nT [DO_LAM_IT]\nT [DO_GT_AUTO]\n')
    exe = model.parent/'cmf/exe/cmfgen_dev.exe'
    code = exe.read_text().replace(' for n,it in enumerate(range(start,start+count)):',
        ' for n,it in enumerate(range(start,start+count)):\n  if attempt==1 and n>0:it+=1')
    message = {'average': 'Averaging of oscilating populations performed on iteration 1',
               'undo': 'Last corrections undone for depths 1 to 2', 'grid': '',
               'grey': 'LAMBDA iteration used\nIteration 1 --- Largest correction to T in GREY initialization loop is 1%'}[kind]
    code = code.replace("  sol.write(' STEQ SOLUTION ARRAY\\n')",
        f"  if attempt==1 and n==0:out+={message!r}+'\\n'\n  sol.write(' STEQ SOLUTION ARRAY\\n')")
    code = code.replace('str(start+count-1)', 'str(start+count-1+int(attempt==1))')
    if kind == 'grid':
        code += "\nif attempt==1:\n (p/'ADJUST_R_DEFAULTS').write_text('1 [N_ITS]\\n')\n print('Entering ADJUST_R_GRID_V4\\nMain counter: 1\\nAdjusted R grid in ADJUST_R_GRID_V4')\n"
    if kind == 'grey':
        code += "\nif attempt==1:(p/'VADAT').write_text((p/'VADAT').read_text().replace('T [USE_FIXED_J]','F [USE_FIXED_J]'))\n"
    exe.write_text(code)
    result = run_plan(plan())
    assert result['status'] == 'succeeded', result
    first = result['attempts'][0]
    assert first['charged_iterations'] == 3 and first['evidence']['checkpoint'] == 4
    assert len(first['evidence']['checkpoint_updates']) == 1
    assert result['attempts'][-1]['phase'] == 'verify'
    if kind == 'grey':
        assert first['evidence']['source_changed'] and not first['evidence']['candidate']


@pytest.mark.parametrize('text', ['Adjusted R grid in ADJUST_R_GRID_V4\n',
    'Main counter: 1\nAdjusted R grid in ADJUST_R_GRID_V4\nAdjusted R grid in ADJUST_R_GRID_V4\n'])
def test_grid_completion_without_unique_counter_is_rejected(text):
    with pytest.raises(RunnerError):
        grid_revisions(text)


@pytest.mark.parametrize('kind', ['average', 'undo'])
def test_checkpoint_update_marker_needs_enabled_control_and_completed_solve(tmp_path, kind):
    (tmp_path/'VADAT').write_text('F [DO_AV]\nF [DO_UNDO]\n')
    message = ('Averaging of oscilating populations performed on iteration 1\n' if kind == 'average'
               else 'Last corrections undone for depths 1 to 2\n')
    with pytest.raises(RunnerError):
        checkpoint_updates(tmp_path, record()+message)


@pytest.mark.parametrize('mode,attempt', [('tail_relax', 2), ('tail_grid', 4)])
def test_convergence_remedy_defers_native_lambda_fallback(convergence_workspace, mode, attempt):
    model, plan = convergence_workspace
    exe = model.parent/'cmf/exe/cmfgen_dev.exe'
    code = exe.read_text().replace("  sol.write(' STEQ SOLUTION ARRAY\\n')",
        f"  if attempt=={attempt} and n==count-1:out+='LAMBDA iteration used\\nTemperature held fixed at all depths.\\n'\n  sol.write(' STEQ SOLUTION ARRAY\\n')")
    exe.write_text(code)
    result = run_plan(plan(mode))
    assert result['status'] == 'succeeded', result
    fallback = result['attempts'][attempt-1]
    assert fallback['verification_pending']
    assert not fallback.get('recovery_verified')
    assert result['attempts'][attempt]['recovery_verified']
    assert result['attempts'][-1]['phase'] == 'verify'


def test_gradual_xray_completion_can_release_lambda_above_fifty(tmp_path):
    old = 'T [INC_XRAYS]\nT [XSLOW]\n10 [XSCL_FAC]\n0.1 [FIL_FAC_1]\n0.2 [FIL_FAC_2]\n0.1 [XFI1_BEG]\n0.2 [XFI2_BEG]\n'
    (tmp_path/'VADAT').write_text(old)
    (tmp_path/'IN_ITS').write_text('T [DO_LAM_IT]\n')
    before = capture_controls(tmp_path)
    (tmp_path/'VADAT').write_text(old.replace('T [XSLOW]', 'F [XSLOW]'))
    (tmp_path/'IN_ITS').write_text('F [DO_LAM_IT]\n')
    adopted = native_updates(tmp_path, record(1, 80, lam=True)+record(2, 10), before)
    assert adopted['VADAT']['native_transitions'] == ['xray_ramp']
    assert 'IN_ITS' in adopted


@pytest.mark.parametrize('mode,attempt', [('tail_relax', 2), ('tail_grid', 4)])
@pytest.mark.parametrize('source_value', [.01, 0])
def test_convergence_remedy_waits_for_stable_source_and_rebases_comparison(convergence_workspace, mode, attempt, source_value):
    model, plan = convergence_workspace
    (model/'VADAT').write_text((model/'VADAT').read_text()+
        'T [INC_XRAYS]\nT [SCL_XLUM]\nF [XSLOW]\n1 [FIL_FAC_1]\n2 [FIL_FAC_2]\n')
    exe = model.parent/'cmf/exe/cmfgen_dev.exe'
    code = exe.read_text().replace("out='Model started on: now\\n'",
        f"if attempt=={attempt}:value={source_value}\nout='Model started on: now\\n'")
    code += f'''
if attempt=={attempt}:
 text=(p/'VADAT').read_text().replace('1 [FIL_FAC_1]','0.5 [FIL_FAC_1]').replace('2 [FIL_FAC_2]','1.0 [FIL_FAC_2]')
 (p/'VADAT').write_text(text)
 with (p/'OUTGEN').open('a') as f:f.write('XRAY_NORMALIZATION_FACTOR: 0.5\\n')
'''
    exe.write_text(code)
    result = run_plan(plan(mode))
    assert result['status'] == 'succeeded', result
    changed = result['attempts'][attempt-1]
    assert changed['verification_pending'] and changed['source_comparison_reset']
    assert changed['comparison_raw_maximum_percent'] == source_value
    assert not changed['evidence']['candidate']
    assert result['attempts'][attempt]['recovery_verified']
    assert result['attempts'][-1]['phase'] == 'verify'


def test_fixed_temperature_full_startup_can_progress_with_lambda_auto_disabled(tmp_path):
    history = []
    for value in [100, 80, 60]:
        e = _evidence()
        e['full_iterations'] = 0
        e['records'][0].update(temperature_fixed=True, solver_maximum_change=value)
        history.append(e)
    ctx = _context(tmp_path, history)
    with (tmp_path/'VADAT').open('a') as f:
        f.write('T [FIX_T]\n')
    (tmp_path/'IN_ITS').write_text('F [DO_LAM_AUTO]\nT [DO_T_AUTO]\n')
    assert policies.choose(ctx)[0].kind == 'continue'


def test_source_transition_during_remedy_cannot_bypass_luminosity_guard(convergence_workspace):
    model, plan = convergence_workspace
    (model/'VADAT').write_text((model/'VADAT').read_text()+
        'T [INC_XRAYS]\nT [SCL_XLUM]\nF [XSLOW]\n1 [FIL_FAC_1]\n2 [FIL_FAC_2]\n')
    exe = model.parent/'cmf/exe/cmfgen_dev.exe'
    exe.write_text(exe.read_text()+'''
if attempt==2:
 text=(p/'VADAT').read_text().replace('1 [FIL_FAC_1]','0.5 [FIL_FAC_1]').replace('2 [FIL_FAC_2]','1.0 [FIL_FAC_2]')
 (p/'VADAT').write_text(text)
 with (p/'OUTGEN').open('a') as f:f.write('XRAY_NORMALIZATION_FACTOR: 0.5\\n')
 (p/'OBSFLUX').write_text('Normalized luminosity check (normalized by L[ND])\\n0.1 1\\n')
''')
    result = run_plan(plan('tail_relax'))
    assert result['status'] == 'needs_review', result
    assert result['provisional_recovery_rolled_back'] == 'population_relaxation'
    assert result['attempts'][-1]['checkpoint_restored']
    assert '1 [FIL_FAC_1]' in (model/'VADAT').read_text()


def test_round_trip_normalization_still_records_source_transition(tmp_path):
    original = 'T [INC_XRAYS]\nT [SCL_XLUM]\nF [XSLOW]\n1 [FIL_FAC_1]\n2 [FIL_FAC_2]\n'
    (tmp_path/'VADAT').write_text(original)
    before = capture_controls(tmp_path)
    text = record(1)+ 'XRAY_NORMALIZATION_FACTOR: 0.5\n'+record(2)+'XRAY_NORMALIZATION_FACTOR: 2\n'
    adopted = native_updates(tmp_path, text, before)
    assert adopted['VADAT']['xray_normalization']['factors'] == [.5, 2]
    assert adopted['VADAT']['before'] == adopted['VADAT']['after']


def test_ramp_recognition_uses_temporary_lambda_probe_controls(tmp_path):
    original = 'T [TRT_NON_TE]\nT [GAMMA_SLOW]\n0.01 [DECNRG_SCLFAC_BEG]\n'
    (tmp_path/'VADAT').write_text(original)
    (tmp_path/'IN_ITS').write_text('F [DO_LAM_IT]\n')
    before = capture_controls(tmp_path)
    (tmp_path/'VADAT').write_text(original.replace('0.01 [DECNRG_SCLFAC_BEG]', '0.1 [DECNRG_SCLFAC_BEG]'))
    text = record(lam=True)+'Have adjusted radioactivity decay energy scale factor\nNew scale factor is 0.1\n'
    assert native_updates(tmp_path, text, before, iteration_overrides={'DO_LAM_IT': 'T'})['VADAT']['native_transitions']
    with pytest.raises(RunnerError):
        native_updates(tmp_path, text, before)


def test_failed_averaging_can_cancel_an_undo_checkpoint_update(tmp_path):
    (tmp_path/'VADAT').write_text('T [DO_AV]\nT [DO_UNDO]\n')
    text = record()+'Last corrections undone for depths 1 to 2\nError performing AV acceleration.\n'
    assert checkpoint_updates(tmp_path, text) == []


def test_grey_release_is_distinguished_from_earlier_hydro_grey_iterations(tmp_path):
    (tmp_path/'VADAT').write_text('T [DO_HYDRO]\n')
    grey = 'Iteration 1 --- Largest correction to T in GREY initialization loop is 1%\n'
    text = (record(1, lam=True)+'Revised hydrostatic structure and output new RVSIG_COL file\n'+grey+
            record(3, lam=True)+grey+record(5))
    assert checkpoint_updates(tmp_path, text, grey_release=True) == [
        {'after_iteration': 3, 'kind': 'grey_release'}]
    # Two unexplained grey increments cannot both be a single fixed-J release.
    with pytest.raises(RunnerError, match='Ambiguous fixed-J'):
        checkpoint_updates(tmp_path, text.replace('count is 3', 'count is 4').replace('count is 5', 'count is 6'),
                           grey_release=True)


@pytest.mark.parametrize('fault', ['duplicate', 'counter', 'unsolved'])
def test_averaging_counter_requires_unique_matching_completed_evidence(tmp_path, fault):
    (tmp_path/'VADAT').write_text('T [DO_AV]\n')
    message = 'Averaging of oscilating populations performed on iteration 1\n'
    text = record()+message
    if fault == 'duplicate':
        text += message
    elif fault == 'counter':
        text = text.replace('on iteration 1', 'on iteration 2')
    else:
        text = 'Current great iteration count is 1\n'+message
    with pytest.raises(RunnerError, match='averaging'):
        checkpoint_updates(tmp_path, text)


@pytest.mark.parametrize('remaining,expected', [(None, False), (1, False), (0, True)])
def test_fixed_geometry_remedies_wait_for_native_grid_schedule(tmp_path, remaining, expected):
    from cmfgen_viewer.auto_hydro import structure_fixed
    (tmp_path/'VADAT').write_text('F [DO_HYDRO]\nT [REV_RGRID]\n')
    if remaining is not None:
        (tmp_path/'ADJUST_R_DEFAULTS').write_text(f'{remaining} [N_ITS]\n')
    assert structure_fixed(tmp_path) is expected


def test_native_ramp_does_not_hide_unrelated_comment_edit(tmp_path):
    original = 'T [INC_ADV]\n0.1 [ADV_RELAX]\n! original note\n'
    (tmp_path/'VADAT').write_text(original)
    before = capture_controls(tmp_path)
    (tmp_path/'VADAT').write_text(original.replace('0.1', '0.2').replace('original note', 'user edit'))
    with pytest.raises(RunnerError, match='Unexpected edit'):
        native_updates(tmp_path, record()+'Have adjusted advection relaxation parameter to: 0.2\n', before)


def test_grid_logs_without_native_entry_cannot_authorize_a_checkpoint(tmp_path):
    with pytest.raises(RunnerError, match='Ambiguous radial-grid'):
        grid_revisions('Main counter: 1\nAdjusted R grid in ADJUST_R_GRID_V4\n')


@pytest.mark.parametrize('indent', ['', '  '])
def test_native_iteration_cycle_replays_rotation_and_grid_requests(indent):
    from cmfgen_viewer.auto_native_cycle import replay
    before = f'{indent}! cycle\n{indent}REVISE_R\n{indent}FULL 2\nLAM 1\n'
    after = f"{'LAM 1'}\n! cycle\nREVISE_R\n{'FULL':<20}{2:4d}\n"
    assert replay(before, after, [1, 2]) == {1: 2}
    with pytest.raises(RunnerError, match='outside its native'):
        replay(before, after.replace('LAM 1', 'LAM 2'), [1, 2])


def test_native_grid_rescheduling_by_iteration_cycle_matches_completed_work(tmp_path):
    old_cycle = 'REVISE_R\nFULL 1\n'
    # After one non-final solve, the native cycle rotates back to REVISE_R.
    new_cycle = f"REVISE_R\n{'FULL':<20}{1:4d}\n"
    (tmp_path/'VADAT').write_text('T [REV_RGRID]\n')
    (tmp_path/'ADJUST_R_DEFAULTS').write_text('1 [N_ITS]\n1 [STRT_ITS]\n1 [FREQ_ITS]\n')
    (tmp_path/'IT_SPECIFIER').write_text(old_cycle)
    before = capture_controls(tmp_path)
    # Revisions on solves 1 and 3; the first solve's saved counter is 2.
    text = record(1)+record(3)
    process_text = ('Entering ADJUST_R_GRID_V4\nMain counter: 1\nAdjusted R grid in ADJUST_R_GRID_V4\n'
                    'Entering ADJUST_R_GRID_V4\nMain counter: 3\nAdjusted R grid in ADJUST_R_GRID_V4\n')
    (tmp_path/'IT_SPECIFIER').write_text(new_cycle)
    (tmp_path/'ADJUST_R_DEFAULTS').write_text('0 [N_ITS]\n3 [STRT_ITS]\n1 [FREQ_ITS]\n')
    adopted = native_updates(tmp_path, text, before, process_text=process_text)
    assert adopted['ADJUST_R_DEFAULTS']['grid_revisions'] == [1, 3]
    assert 'IT_SPECIFIER' in adopted
    (tmp_path/'ADJUST_R_DEFAULTS').write_text('0 [N_ITS]\n4 [STRT_ITS]\n1 [FREQ_ITS]\n')
    with pytest.raises(RunnerError, match='Radial-grid counters'):
        native_updates(tmp_path, text, before, process_text=process_text)


@pytest.mark.parametrize('cycle,lambda_it,expected', [('LAM 20\nFULL 3\n', False, True),
    ('LAM 20\nNORM\nFULL 3\n', False, False), ('LAM 20\nFULL(FIXT) 3\n', False, False),
    ('LAM 20\nFULL 3\n', True, False)])
def test_scripted_temperature_release_must_be_reachable_and_not_overridden(tmp_path, cycle, lambda_it, expected):
    from cmfgen_viewer.auto_native_cycle import allows_full
    (tmp_path/'IN_ITS').write_text(f"{'T' if lambda_it else 'F'} [DO_LAM_IT]\nF [DO_LAM_AUTO]\n")
    (tmp_path/'IT_SPECIFIER').write_text(cycle)
    assert allows_full(tmp_path) == expected


def test_scripted_full_can_authorize_fixed_temperature_startup(auto_workspace):
    model, plan = auto_workspace
    (model/'VADAT').write_text((model/'VADAT').read_text().replace('F [FIX_T]', 'T [FIX_T]'))
    (model/'IN_ITS').write_text('5 [NUM_ITS]\nF [DO_LAM_IT]\nF [DO_LAM_AUTO]\n')
    (model/'IT_SPECIFIER').write_text('LAM 3\nFULL 3\n')
    assert plan()['ready']
    (model/'IT_SPECIFIER').write_text('NORM\nFULL 3\n')
    with pytest.raises(RunnerError, match='DO_T_AUTO'):
        plan()
