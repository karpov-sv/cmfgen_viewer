"""Coupled structure edits must retain provenance and require reviewed installation."""
import io
import json
from pathlib import Path

import pytest

from cmfgen_viewer.app import create_app
from cmfgen_viewer.model_editor import (ModelEditorError, load_model_parameter_file,
    review_model_parameter_edit, save_model_parameter_edit)
from cmfgen_viewer.model_preflight import inspect_model_preflight
from cmfgen_viewer.model_cli import main
from cmfgen_viewer.structure_update import (STATE_FILE, apply_structure_plan, build_structure_plan,
    inspect_structure_update, parse_grid)

GRID = '4 !Number of depth points\n\n4 40 0 1\n3 30 0 2\n2 20 0 3\n1 10 0 4\n'


@pytest.fixture
def model(tmp_path):
    model = tmp_path / 'model'
    model.mkdir()
    (model/'VADAT').write_text('RVSIG_COL [VEL_OPT]\n1 [RSTAR]\n4 [RMAX]\n40 [VINF]\n'
        '1 [BETA]\n1D-6 [MDOT]\n1D4 [LSTAR]\n3.5 [LOGG]\n1 [HYD/X]\n')
    (model/'MODEL_SPEC').write_text('4 [ND]\n1 [NC]\n5 [NP]\n')
    (model/'IN_ITS').write_text('2 [NUM_ITS]\n')
    (model/'batch.sh').write_text('#!/bin/sh\n')
    (model/'RVSIG_COL').write_text(GRID)
    return model


def edit(model, filename='VADAT', old='1D-6', new='2D-6'):
    record = load_model_parameter_file(str(model.parent), model_relpath=model.name, file_relpath=filename)
    contents = record['contents'].replace(old, new)
    args = dict(model_relpath=model.name, file_relpath=filename, expected_digest=record['digest'], contents=contents)
    review = review_model_parameter_edit(str(model.parent), **args)
    save_model_parameter_edit(str(model.parent), **args)
    return review


@pytest.mark.parametrize('filename,old,new,key', [
    ('VADAT','1D-6','2D-6','MDOT'), ('VADAT','1 [RSTAR]','2 [RSTAR]','RSTAR'),
    ('VADAT','1 [BETA]','2 [BETA]','BETA'), ('VADAT','40 [VINF]','50 [VINF]','VINF'),
    ('MODEL_SPEC','4 [ND]','5 [ND]','ND'),
])
def test_edits_warn_track_and_block_preflight(model, filename, old, new, key):
    original = (model/filename).read_text()
    review = edit(model, filename, old, new)
    assert any('RVSIG_COL structure update required' in warning for warning in review['warnings'])
    status = inspect_structure_update(model)
    assert status['required'] and key in status['changes']
    baseline = json.loads((model/STATE_FILE).read_text())['baseline']
    assert baseline[filename] == original and baseline['RVSIG_COL'] == GRID
    assert any(issue['code']=='structure-update-required' for issue in inspect_model_preflight(model)['issues'])


@pytest.mark.parametrize('old,new', [('1 [HYD/X]','0.8 [HYD/X]'), ('3.5 [LOGG]','3.6 [LOGG]'),
                                   ('1D-6','0.000001')])
def test_unrelated_and_notation_only_changes_do_not_require_structure(model, old, new):
    review = edit(model, old=old, new=new)
    assert not any('structure update required' in warning for warning in review['warnings'])
    assert not inspect_structure_update(model)['required']


def test_baseline_survives_multiple_edits_and_reverts(model):
    original = (model/'VADAT').read_text()
    edit(model)
    edit(model, old='1 [RSTAR]', new='2 [RSTAR]')
    assert json.loads((model/STATE_FILE).read_text())['baseline']['VADAT'] == original
    assert set(inspect_structure_update(model)['changes']) == {'MDOT','RSTAR'}
    edit(model, old='2D-6', new='1D-6')
    edit(model, old='2 [RSTAR]', new='1 [RSTAR]')
    assert not inspect_structure_update(model)['required']


def test_analytic_velocity_model_does_not_require_rvsig_update(model):
    (model/'VADAT').write_text((model/'VADAT').read_text().replace('RVSIG_COL','STAR'))
    edit(model)
    assert not (model/STATE_FILE).exists()


def test_review_does_not_mutate_and_apply_archives_checkpoints(model):
    edit(model)
    for name in ('SCRTEMP','POINT1','BAMAT'):
        (model/name).write_bytes(b'old checkpoint')
    original = {p.name:p.read_bytes() for p in model.iterdir() if p.is_file()}
    candidate = GRID.replace('4 40', '5 40')
    plan = build_structure_plan(model, candidate=candidate)
    assert original == {p.name:p.read_bytes() for p in model.iterdir() if p.is_file()}
    assert '5 [RMAX]' in plan['replacements']['VADAT']
    result = apply_structure_plan(model, plan)
    assert (model/'RVSIG_COL').read_text() == candidate
    assert not inspect_structure_update(model)['required']
    for name in ('SCRTEMP','POINT1','BAMAT'):
        assert not (model/name).exists()
        assert (Path(result['archive_path'])/name).read_bytes() == b'old checkpoint'
    assert (Path(result['archive_path'])/'RVSIG_COL').read_text() == GRID


@pytest.mark.parametrize('name', ['VADAT','MODEL_SPEC','RVSIG_COL','SCRTEMP','IN_ITS'])
def test_apply_refuses_changes_since_review(model, name):
    edit(model)
    plan = build_structure_plan(model, candidate=GRID)
    with (model/name).open('a') as stream:
        stream.write('\n! external change\n')
    with pytest.raises(ValueError, match='changed after review'):
        apply_structure_plan(model, plan)
    assert inspect_structure_update(model)['required']


def test_apply_rolls_back_when_installation_fails(model, monkeypatch):
    from cmfgen_viewer import model_editor
    edit(model)
    (model/'SCRTEMP').write_bytes(b'checkpoint')
    plan = build_structure_plan(model, candidate=GRID)
    original = {n:(model/n).read_bytes() for n in ('RVSIG_COL','VADAT',STATE_FILE,'SCRTEMP')}
    atomic = model_editor._atomic_replace
    def fail(path, data, **kwargs):
        if path.name == STATE_FILE:
            raise OSError('simulated metadata failure')
        return atomic(path,data,**kwargs)
    monkeypatch.setattr(model_editor, '_atomic_replace', fail)
    with pytest.raises(ValueError, match='simulated'):
        apply_structure_plan(model, plan)
    assert original == {n:(model/n).read_bytes() for n in original}


@pytest.mark.parametrize('candidate', [GRID.replace('4 !Number','5 !Number'),
    GRID.replace('3 30','4 30'), GRID.replace('2 20','2 NaN'), GRID.replace('1 10 0','1 10 -2')])
def test_invalid_candidate_is_rejected(model, candidate):
    with pytest.raises(ValueError):
        build_structure_plan(model, candidate=candidate)


def test_symlinks_and_missing_baseline_are_refused(model, tmp_path):
    with pytest.raises(ValueError, match='No saved pre-edit baseline'):
        build_structure_plan(model)
    (model/'SCRTEMP').symlink_to(tmp_path/'elsewhere')
    with pytest.raises(ValueError, match='symlink'):
        build_structure_plan(model, candidate=GRID)


def test_editor_notice_and_candidate_route(model):
    edit(model)
    app=create_app(basepath=str(model.parent), read_write_enabled=True, secret_key='test')
    client=app.test_client()
    page=client.get('/model-actions/edit/model')
    assert b'Structure update required' in page.data
    assert b'/model-actions/structure/model' in page.data
    response=client.post('/model-actions/structure/model', data={
        'action':'preview', 'candidate':(io.BytesIO(GRID.encode()),'candidate')})
    assert response.status_code==200 and b'Structure update review' in response.data
    assert inspect_structure_update(model)['required']
    token=next(iter(app.extensions['structure_reviews']))
    response=client.post('/model-actions/structure/model', data={'action':'apply','review_token':token})
    assert response.status_code==302
    assert not inspect_structure_update(model)['required']
    assert client.post('/model-actions/structure/model', data={
        'action':'apply','review_token':token}).status_code==200
    readonly=create_app(basepath=str(model.parent), read_write_enabled=False)
    assert readonly.test_client().get('/model-actions/structure/model').status_code==403


def test_cli_tracks_and_applies_review(model, tmp_path, capsys):
    assert main(['set',str(model),'MDOT=2D-6','--json'])==0
    result=json.loads(capsys.readouterr().out)
    assert any('structure update required' in w for w in result['warnings'])
    candidate=tmp_path/'candidate'
    candidate.write_text(GRID)
    review=tmp_path/'review.json'
    assert main(['structure',str(model),'--candidate',str(candidate),'--review-file',str(review),'--json'])==0
    assert json.loads(capsys.readouterr().out)['status']=='review_required'
    assert main(['structure',str(model),'--apply',str(review),'--json'])==0
    assert json.loads(capsys.readouterr().out)['status']=='succeeded'
    assert not inspect_structure_update(model)['required']


def test_native_adapter_runs_in_scratch_and_preserves_live_inputs(model, tmp_path):
    import sys
    native = tmp_path/'native'
    (native/'exe').mkdir(parents=True)
    executable = native/'exe/rev_rvsig.exe'
    # A protocol fixture, not a replacement implementation of the velocity laws.
    executable.write_text(f'#!{sys.executable}\n' + '''
from pathlib import Path
import sys
answers=sys.stdin.read().splitlines()
assert answers[:3]==['RVSIG_COL_OLD','F','MDOT']
assert answers[3:9]==['1e-06','2e-06','2','40.0','1.0','50.0']
assert answers[9:]==['RVSIG_COL_NEW','/null','E','E']
assert not Path('VADAT').exists()
assert not Path('SCRTEMP').exists()
Path('RVSIG_COL_NEW').write_text(Path('RVSIG_COL_OLD').read_text())
print('validated native input protocol')
''')
    executable.chmod(0o755)
    edit(model)
    original=(model/'RVSIG_COL').read_bytes()
    plan=build_structure_plan(model, cmfgen_root=native, velocity_type=2, connection_velocity=50)
    assert plan['native_runs'][0]['mode']=='MDOT'
    assert 'validated native input protocol' in plan['native_runs'][0]['log']
    assert (model/'RVSIG_COL').read_bytes()==original
    assert inspect_structure_update(model)['required']


def test_native_adapter_preserves_answers_across_buffered_input_readers(model, tmp_path):
    import sys
    native = native_root(tmp_path)
    executable = native/'exe/rev_rvsig.exe'
    # Reproduce GEN_IN buffering stdin before Giza reads the device with C stdio.
    # With a pipe, the first reader consumes the graphics answers as read-ahead.
    executable.write_text(f'#!{sys.executable}\n' + '''
import ctypes
from pathlib import Path
import sys
assert sys.stdin.isatty()
answers = [sys.stdin.readline().rstrip('\\n') for _ in range(10)]
assert answers[:3] == ['RVSIG_COL_OLD', 'F', 'MDOT']
assert answers[-1] == 'RVSIG_COL_NEW'
libc = ctypes.CDLL(None)
libc.fgets.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
libc.fgets.restype = ctypes.c_void_p
buffer = ctypes.create_string_buffer(256)
assert libc.fgets(buffer, len(buffer), ctypes.c_void_p.in_dll(libc, 'stdin'))
assert buffer.value == b'/null\\n'
assert sys.stdin.read().splitlines() == ['E', 'E']
Path('RVSIG_COL_NEW').write_text(Path('RVSIG_COL_OLD').read_text())
print('x' * 70000)
print('mixed input readers completed')
''')
    edit(model)
    original = {p.name: p.read_bytes() for p in model.iterdir() if p.is_file()}
    plan = build_structure_plan(model, cmfgen_root=native, connection_velocity=50)
    log = plan['native_runs'][0]['log']
    assert log.endswith('mixed input readers completed\n')
    assert len(log.encode()) == 65536
    assert original == {p.name: p.read_bytes() for p in model.iterdir() if p.is_file()}


def test_guided_update_rejects_incompatible_inputs(model, tmp_path):
    import sys
    native=tmp_path/'native'
    (native/'exe').mkdir(parents=True)
    exe=native/'exe/rev_rvsig.exe'
    exe.write_text(f'#!{sys.executable}\nraise SystemExit(9)\n')
    exe.chmod(0o755)
    edit(model)
    with pytest.raises(ValueError, match='safely inside'):
        build_structure_plan(model, cmfgen_root=native, connection_velocity=0.1)
    with pytest.raises(ValueError, match='failed'):
        build_structure_plan(model, cmfgen_root=native, connection_velocity=50)
    assert inspect_structure_update(model)['required']
    (model/'RVSIG_COL').write_text(GRID+'\n')
    with pytest.raises(ValueError, match='changed since the baseline'):
        build_structure_plan(model, cmfgen_root=native, connection_velocity=50)


def test_unknown_metadata_and_candidate_without_original_structure(model):
    (model/STATE_FILE).write_text('[]')
    assert inspect_structure_update(model)['required']
    (model/STATE_FILE).unlink()
    (model/'RVSIG_COL').unlink()
    plan=build_structure_plan(model, candidate=GRID)
    apply_structure_plan(model, plan)
    assert parse_grid((model/'RVSIG_COL').read_text())==parse_grid(GRID)


def test_resolved_tracking_does_not_flag_later_native_hydro_updates(model):
    edit(model)
    apply_structure_plan(model, build_structure_plan(model, candidate=GRID))
    # Native hydro owns these coupled changes after the reviewed update.
    hydro_vadat=(model/'VADAT').read_text().replace('1 [RSTAR]', '2 [RSTAR]')
    (model/'VADAT').write_text(hydro_vadat)
    hydro_grid=GRID.replace('1 10 0','2 10 0').replace('2 20 0','2.5 20 0')
    (model/'RVSIG_COL').write_text(hydro_grid)
    assert not inspect_structure_update(model)['required']
    edit(model, old='2D-6', new='3D-6')
    baseline=json.loads((model/STATE_FILE).read_text())['baseline']
    assert baseline['VADAT']==hydro_vadat
    assert baseline['RVSIG_COL']==hydro_grid
    assert inspect_structure_update(model)['changes']==['MDOT']


def test_pending_baseline_is_copied_with_model_and_preserved_by_cleanup(model):
    from cmfgen_viewer.model_staging import plan_model_from_solution
    from cmfgen_viewer.model_full_cleanup import build_full_cleanup_plan
    edit(model)
    (model/'GAMMAS').write_text('gamma input\n')
    (model/'HI_OUT').write_text('population output\n')
    plan=plan_model_from_solution(str(model.parent), source_relpath='model', destination_relpath='new')
    assert STATE_FILE in {item['destination_name'] for item in plan['entries']}
    cleanup=build_full_cleanup_plan(model)
    assert STATE_FILE not in {item['name'] for item in cleanup['entries']}


def test_depth_update_includes_required_ray_count_in_review(model):
    edit(model, 'MODEL_SPEC', '4 [ND]', '5 [ND]')
    candidate=('5 !Number of depth points\n\n4 40 0 1\n3.5 35 0 2\n'
               '3 30 0 3\n2 20 0 4\n1 10 0 5\n')
    plan=build_structure_plan(model, candidate=candidate)
    assert '6 [NP]' in plan['replacements']['MODEL_SPEC']
    assert 'MODEL_SPEC' in plan['diffs']
    result=apply_structure_plan(model, plan)
    assert '6 [NP]' in (model/'MODEL_SPEC').read_text()
    assert '5 [NP]' in (Path(result['archive_path'])/'MODEL_SPEC').read_text()
    assert not inspect_structure_update(model)['required']


def test_candidate_indices_and_extra_columns_are_validated(model):
    with pytest.raises(ValueError, match='sequential depth indices'):
        build_structure_plan(model, candidate=GRID.replace('2 20 0 3','2 20 0 2'))
    density_grid='4 !Number of depth points\n\n'+''.join(
        f'{r} {v} {s} 1e-10 1.0 {i}\n' for i,(r,v,s) in enumerate(parse_grid(GRID),1))
    plan=build_structure_plan(model, candidate=density_grid)
    apply_structure_plan(model, plan)
    assert not any(issue['code']=='structure-row-count' for issue in inspect_model_preflight(model)['issues'])
    with pytest.raises(ValueError, match='Nonfinite additional'):
        build_structure_plan(model, candidate=density_grid.replace('1e-10','NaN',1))


def test_switching_away_and_back_retains_original_mass_loss_baseline(model):
    original=(model/'VADAT').read_text()
    edit(model)
    edit(model, old='RVSIG_COL [VEL_OPT]', new='STAR [VEL_OPT]')
    assert not inspect_structure_update(model)['required']
    edit(model, old='STAR [VEL_OPT]', new='RVSIG_COL [VEL_OPT]')
    assert inspect_structure_update(model)['required']
    assert json.loads((model/STATE_FILE).read_text())['baseline']['VADAT']==original


def native_root(tmp_path):
    root=tmp_path/'native-grid-tools'
    (root/'exe').mkdir(parents=True)
    exe=root/'exe/rev_rvsig.exe'
    exe.write_text('#!/bin/sh\nexit 1\n')
    exe.chmod(0o755)
    return root


@pytest.mark.parametrize('operation,options,mode,answers,rad', [
    ('new_nd', {'new_depths':5}, 'NEW_ND', [5], [4,3.5,3,2,1]),
    ('new_nd', {'new_depths':3}, 'NEW_ND', [3], [4,2.5,1]),
    ('insert', {'start_depth':1,'end_depth':3,'points':1}, 'NINS', [1,1,3], [4,3.5,3,2.5,2,1]),
    ('outer', {'points':2}, 'FGOB', [2], [4,3.88891111,3.6667,3,2,1]),
    ('radii', {'radii':'3.5, 1.5'}, 'ADDR', [2,3.5,1.5], [4,3.5,3,2,1.5,1]),
    ('sigma', {}, 'SIGU', [], [4,3,2,1]),
])
def test_standalone_grid_operations_review_and_apply(model,tmp_path,monkeypatch,operation,options,mode,answers,rad):
    from cmfgen_viewer import structure_update as updates
    root=native_root(tmp_path)
    output=f'{len(rad)} !Number of depth points\n\n'+''.join(
        f'{r} {r*10} 0 {i}\n' for i,r in enumerate(rad,1))
    def fixture(executable,folder,rows,requested_mode,requested_answers,logs):
        assert requested_mode==mode and requested_answers==answers
        assert rows==parse_grid(GRID)
        logs.append({'mode':mode,'answers':answers,'returncode':0,'log':'protocol fixture'})
        return parse_grid(output),output
    monkeypatch.setattr(updates,'_native',fixture)
    original={p.name:p.read_bytes() for p in model.iterdir()}
    plan=build_structure_plan(model,cmfgen_root=root,operation=operation,**options)
    assert plan['operation']==operation and plan['summary']['depths']==len(rad)
    assert original=={p.name:p.read_bytes() for p in model.iterdir()}
    assert not (model/STATE_FILE).exists()
    assert plan['summary']['impact_parameters']==max(5,len(rad)+1)
    apply_structure_plan(model,plan)
    assert len(parse_grid((model/'RVSIG_COL').read_text()))==len(rad)
    assert updates.value((model/'MODEL_SPEC').read_text(),'ND')==str(len(rad))
    assert not inspect_structure_update(model)['required']


@pytest.mark.parametrize('operation,options', [
    ('new_nd',{'new_depths':4}), ('new_nd',{'new_depths':2}), ('new_nd',{'new_depths':5001}),
    ('new_nd',{'new_depths':'NaN'}), ('insert',{'start_depth':0}),
    ('insert',{'start_depth':2,'end_depth':2}), ('insert',{'points':5000}),
    ('outer',{'points':0}), ('outer',{'points':5000}), ('radii',{'radii':''}),
    ('radii',{'radii':'3.5,3.5'}), ('radii',{'radii':'1.5,3.5'}), ('radii',{'radii':'4'}),
    ('radii',{'radii':'3'}), ('radii',{'radii':'1'}), ('radii',{'radii':'NaN'}),
])
def test_grid_operation_validates_before_native_execution(model,tmp_path,monkeypatch,operation,options):
    from cmfgen_viewer import structure_update as updates
    root=native_root(tmp_path)
    def must_not_run(*args,**kwargs):
        pytest.fail('Invalid input reached native utility')
    monkeypatch.setattr(updates,'_native',must_not_run)
    with pytest.raises(ValueError):
        build_structure_plan(model,cmfgen_root=root,operation=operation,**options)
    assert (model/'RVSIG_COL').read_text()==GRID


def test_grid_operation_does_not_bypass_pending_parameters(model,tmp_path):
    edit(model)
    with pytest.raises(ValueError,match='pending parameter-driven'):
        build_structure_plan(model,cmfgen_root=native_root(tmp_path),operation='sigma')
    with pytest.raises(ValueError,match='cannot be combined'):
        build_structure_plan(model,candidate=GRID,operation='sigma')


def test_cli_grid_operation_records_native_choice(model,tmp_path,monkeypatch,capsys):
    from cmfgen_viewer import structure_update as updates
    root=native_root(tmp_path)
    def fixture(executable,folder,rows,mode,answers,logs):
        assert mode=='SIGU' and answers==[]
        return parse_grid(GRID),GRID
    monkeypatch.setattr(updates,'_native',fixture)
    assert main(['structure',str(model),'--operation','sigma','--cmfgen-root',str(root),'--json'])==0
    report=json.loads(capsys.readouterr().out)
    assert report['operation']=='Recalculate sigma from the velocity profile'
    assert report['status']=='review_required'


def test_structure_form_retains_selected_grid_operation(model):
    app=create_app(basepath=str(model.parent),read_write_enabled=True,secret_key='test')
    app.config['CMFGEN_VIEWER']['summary_cache_db']=str(model.parent/'summary.sqlite')
    client=app.test_client()
    response=client.post('/model-actions/structure/model',data={
        'action':'preview','operation':'new_nd','new_depths':'135'})
    assert response.status_code==200
    assert b'value="new_nd" selected' in response.data
    assert b'name="new_depths" value="135"' in response.data
    assert b'data-structure-form' in response.data


def test_cli_execute_generates_native_update_and_archives_checkpoint(model, tmp_path, capsys):
    import sys
    native = native_root(tmp_path)
    exe = native/'exe/rev_rvsig.exe'
    exe.write_text(f'#!{sys.executable}\n' + '''
from pathlib import Path
import sys
answers=sys.stdin.read().splitlines()
assert answers[:3]==['RVSIG_COL_OLD','F','MDOT']
assert not Path('VADAT').exists()
Path('RVSIG_COL_NEW').write_text(Path('RVSIG_COL_OLD').read_text())
print('native structure generation completed')
''')
    edit(model)
    (model/'SCRTEMP').write_bytes(b'old checkpoint')
    original = (model/'RVSIG_COL').read_bytes()
    assert main(['structure',str(model),'--execute','--cmfgen-root',str(native),
                 '--connection-velocity','50','--json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'succeeded'
    archive = Path(report['result']['archive_path'])
    assert (archive/'SCRTEMP').read_bytes() == b'old checkpoint'
    assert (archive/'RVSIG_COL').read_bytes() == original
    assert not (model/'SCRTEMP').exists()
    assert not inspect_structure_update(model)['required']
    plan = json.loads((archive/'operation.json').read_text())
    assert plan['native_runs'][0]['mode'] == 'MDOT'
    assert 'native structure generation completed' in plan['native_runs'][0]['log']


def test_cli_execute_grid_operation_updates_coupled_dimensions(model, tmp_path, capsys):
    import sys
    root = native_root(tmp_path)
    output = '5 !Number of depth points\n\n4 40 0 1\n3.5 35 0 2\n3 30 0 3\n2 20 0 4\n1 10 0 5\n'
    (root/'exe/rev_rvsig.exe').write_text(f'#!{sys.executable}\n' +
        'from pathlib import Path\nimport sys\na=sys.stdin.read().splitlines()\n'
        'assert a[:4]==["RVSIG_COL_OLD","F","NEW_ND","5"]\n'
        f'Path("RVSIG_COL_NEW").write_text({output!r})\n')
    assert main(['structure',str(model),'--execute','--operation','new_nd',
                 '--new-depths','5','--cmfgen-root',str(root),'--json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'succeeded'
    assert len(parse_grid((model/'RVSIG_COL').read_text())) == 5
    spec = (model/'MODEL_SPEC').read_text()
    assert '5 [ND]' in spec and '6 [NP]' in spec
    assert (Path(report['result']['archive_path'])/'MODEL_SPEC').is_file()


def test_cli_execute_candidate_can_also_save_review(model, tmp_path, capsys):
    edit(model)
    candidate, review = tmp_path/'candidate', tmp_path/'review.json'
    candidate.write_text(GRID)
    assert main(['structure',str(model),'--execute','--candidate',str(candidate),
                 '--review-file',str(review),'--json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'succeeded'
    assert report['review_file'] == str(review)
    assert json.loads(review.read_text()) == json.loads(
        (Path(report['result']['archive_path'])/'operation.json').read_text())


@pytest.mark.parametrize('conflict', [['--plan'], ['--apply','unused.json']])
def test_cli_execute_rejects_conflicting_modes_before_mutation(model, conflict):
    original = {p.name:p.read_bytes() for p in model.iterdir()}
    with pytest.raises(SystemExit) as exc:
        main(['structure',str(model),'--execute',*conflict])
    assert exc.value.code == 2
    assert original == {p.name:p.read_bytes() for p in model.iterdir()}


def test_cli_execute_still_rejects_changes_after_generation(model, tmp_path, monkeypatch, capsys):
    from cmfgen_viewer import model_cli
    edit(model)
    backups_before = set((model/'.cmfgen-viewer-backups').iterdir())
    candidate = tmp_path/'candidate';candidate.write_text(GRID)
    (model/'SCRTEMP').write_bytes(b'checkpoint')
    original = (model/'RVSIG_COL').read_bytes()
    build = model_cli.build_structure_plan
    def changed(*args, **kwargs):
        plan = build(*args, **kwargs)
        with (model/'VADAT').open('a') as stream: stream.write('! concurrent edit\n')
        return plan
    monkeypatch.setattr(model_cli,'build_structure_plan',changed)
    assert main(['structure',str(model),'--execute','--candidate',str(candidate),'--json']) == 1
    report = json.loads(capsys.readouterr().out)
    assert 'changed after review' in report['error']
    assert (model/'RVSIG_COL').read_bytes() == original
    assert (model/'SCRTEMP').read_bytes() == b'checkpoint'
    assert (model/'VADAT').read_text().endswith('! concurrent edit\n')
    assert set((model/'.cmfgen-viewer-backups').iterdir()) == backups_before


def test_cli_execute_invalid_candidate_leaves_model_unchanged(model, tmp_path, capsys):
    candidate = tmp_path/'candidate';candidate.write_text(GRID.replace('2 20','2 NaN'))
    original = {p.name:p.read_bytes() for p in model.iterdir()}
    assert main(['structure',str(model),'--execute','--candidate',str(candidate),'--json']) == 2
    assert json.loads(capsys.readouterr().out)['status'] == 'blocked'
    assert original == {p.name:p.read_bytes() for p in model.iterdir()}
