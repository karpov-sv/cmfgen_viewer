import json
from pathlib import Path

from cmfgen_viewer.correction_history import correction_history
from cmfgen_viewer.model_convergence import inspect_model_convergence, _parse_iteration_records


def run(day, rows):
    text=f'Model started on: {day:02}-Jan-2026 00:00:00\n'
    for iteration,value in rows:
        text+=f'Current great iteration count is {iteration}\nBA matrix computed\n'
        text+=f'Maximum % increase at depth 1 is {value} (BA computed) --- iteration {iteration}\n'
        text+=f'Maximm changes as returned by SOLVEBA_V13 is {value}\n'
    return text


def archive(model, name, text, status='succeeded'):
    root=model/'.cmfgen-runs'/name
    (root/'main').mkdir(parents=True)
    (root/'main/OUTGEN').write_text(text)
    (root/'result.json').write_text(json.dumps({'status':status}))
    return root


def test_history_preserves_rewinds_and_rollback_and_deduplicates_sources(tmp_path):
    a='20260101T000000Z-aaaaaaaa';b='20260102T000000Z-bbbbbbbb';c='20260103T000000Z-cccccccc'
    first=run(1,[(1,10),(2,5)]);second=run(2,[(2,20),(3,8)]);current=run(3,[(7,1)])
    (tmp_path/'OUTGEN').write_text(first+current)
    archive(tmp_path,a,first);archive(tmp_path,b,second);archive(tmp_path,c,current)
    auto=tmp_path/'.cmfgen-runs/20260101T000000Z-auto-dddddddd';auto.mkdir()
    (auto/'result.json').write_text(json.dumps({'attempts':[
        {'journal':'/other/machine/'+a,'status':'succeeded','phase':'iterate',
         'evidence':{'records':_parse_iteration_records(first)}},
        {'journal':'/other/machine/'+b,'status':'succeeded','phase':'ba_reuse_check','checkpoint_restored':True,
         'evidence':{'records':_parse_iteration_records(second)}},
        {'journal':'/other/machine/'+c,'status':'succeeded','evidence':{'records':_parse_iteration_records(current)}}]}))
    before={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result=correction_history(tmp_path)
    assert result['run_count']==2
    assert result['record_count']==4
    solver=[t for t in result['data'] if t['name']=='Earlier: Solver maximum change']
    assert sorted(t['x'] for t in solver)==[[1,2],[2,3]]
    assert sum(t['showlegend'] for t in solver)==1
    assert all(t['line']['dash']=='dot' for t in solver)
    assert any(row[1]=='rolled back' for t in solver for row in t['customdata'])
    assert all(7 not in t['x'] for t in result['data'])
    assert before=={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert len(inspect_model_convergence(tmp_path)['iterations'])==1


def test_auto_evidence_survives_log_compaction(tmp_path):
    auto=tmp_path/'.cmfgen-runs/20260101T000000Z-auto-aaaaaaaa';auto.mkdir(parents=True)
    (auto/'result.json').write_text(json.dumps({'attempts':[{
        'journal':'/foreign/model/.cmfgen-runs/20260101T000000Z-bbbbbbbb',
        'phase':'verify','status':'succeeded','evidence':{'records':_parse_iteration_records(run(1,[(1,2),(2,1)]))}}]}))
    assert correction_history(tmp_path)['record_count']==2


def test_failed_run_without_auto_evidence_uses_archived_log(tmp_path):
    name='20260101T000000Z-aaaaaaaa';archive(tmp_path,name,run(1,[(1,10),(2,9)]),'failed')
    auto=tmp_path/'.cmfgen-runs/20260101T000000Z-auto-bbbbbbbb';auto.mkdir()
    (auto/'result.json').write_text(json.dumps({'attempts':[{'journal':'/foreign/'+name,
        'status':'failed','checkpoint_restored':True}]}))
    result=correction_history(tmp_path)
    assert result['record_count']==2
    assert result['data'][0]['customdata'][0][1]=='rolled back'


def test_symlinks_and_malformed_records_are_not_followed(tmp_path):
    model=tmp_path/'model';model.mkdir()
    outside=tmp_path/'outside';outside.write_text(run(1,[(1,1e20),(2,1e19)]))
    root=archive(model,'20260101T000000Z-aaaaaaaa','')
    (root/'main/OUTGEN').unlink();(root/'main/OUTGEN').symlink_to(outside)
    auto=model/'.cmfgen-runs/20260101T000000Z-auto-bbbbbbbb';auto.mkdir()
    (auto/'result.json').write_text(json.dumps({'attempts':[{'journal':'/outside/20260101T000000Z-cccccccc',
        'evidence':{'records':[{'global_iteration':1,'solver_maximum_change':float('inf')},
                               {'global_iteration':2,'solver_maximum_change':10**500}]}}]}))
    assert correction_history(model)['data']==[]


def test_history_is_bounded_and_optional(tmp_path,monkeypatch):
    import cmfgen_viewer.correction_history as module
    assert correction_history(tmp_path)['data']==[]
    archive(tmp_path,'20260101T000000Z-aaaaaaaa',run(1,[(1,20),(2,10)]))
    monkeypatch.setattr(module,'MAX_BYTES',10)
    assert correction_history(tmp_path)['limited']


def test_new_run_keeps_empty_history_plot_available(tmp_path):
    (tmp_path/'OUTGEN').write_text('Model started on: 02-Jan-2026 00:00:00\n')
    state=inspect_model_convergence(tmp_path)
    assert not state['has_iterations']
    assert state['plots'][0]['correction_history']
    assert state['plots'][0]['data']==[]
    assert state['plots'][1]['history_key']=='luminosity_data'
    assert state['plots'][1]['data']==[]


def test_history_route_permissions_and_payload(tmp_path):
    from cmfgen_viewer.app import create_app
    model=tmp_path/'model';model.mkdir()
    (model/'MODEL_SPEC').write_text('2 [ND]\n1 [NC]\n3 [NP]\n')
    (model/'VADAT').write_text('0.02 [EPS_TERM]\n')
    (model/'IN_ITS').write_text('5 [NUM_ITS]\n')
    (model/'OUTGEN').write_text(run(2,[(4,1)]))
    archive(model,'20260101T000000Z-aaaaaaaa',run(1,[(1,3),(2,2)]))
    app=create_app(basepath=str(tmp_path),read_write_enabled=True,secret_key='test')
    client=app.test_client()
    response=client.get('/model-actions/correction-history/model')
    assert response.status_code==200
    assert response.json['run_count']==1
    assert response.headers['Cache-Control']=='no-store'
    page=client.get('/model-actions/main-computation/model')
    assert page.status_code==200
    assert page.data.count(b'data-correction-history-toggle') == 1
    assert page.data.index(b'Show earlier runs') > page.data.index(b'Luminosity difference history')
    assert b'Show earlier runs' in page.data
    assert b'data-history-url="/model-actions/correction-history/model"' in page.data
    assert client.get('/model-actions/correction-history/missing').status_code==404
    readonly=create_app(basepath=str(tmp_path),read_write_enabled=False,secret_key='test')
    assert readonly.test_client().get('/model-actions/correction-history/model').status_code==403


def test_provisional_recipe_rollback_labels_successful_intermediate_steps(tmp_path):
    root=tmp_path/'.cmfgen-runs/20260101T000000Z-auto-aaaaaaaa';root.mkdir(parents=True)
    first=_parse_iteration_records(run(1,[(1,20)]));second=_parse_iteration_records(run(2,[(2,10)]))
    (root/'result.json').write_text(json.dumps({'provisional_recovery_rolled_back':'population_bootstrap',
        'attempts':[{'journal':'/foreign/20260101T000000Z-bbbbbbbb','status':'succeeded',
                    'evidence':{'records':first},'decision':{'policy_id':'population_bootstrap',
                        'kind':'action','steps':[{'name':'bootstrap'},{'name':'check'}]}},
                   {'journal':'/foreign/20260102T000000Z-cccccccc','status':'succeeded',
                    'phase':'bootstrap','evidence':{'records':second}}]}))
    result=correction_history(tmp_path)
    assert result['run_count']==2
    assert all(row[1]=='rolled back' for trace in result['data'] for row in trace['customdata'])


def test_luminosity_history_from_logs_and_compacted_auto_evidence(tmp_path):
    first = run(1, [(1, 10), (2, 5)])
    first += ('Luminosity of star (d=1,ND)(iteration 1) is: 9.0E+04 1.0E+05\n'
              'Luminosity of star (d=1,ND)(iteration 2) is: 1.0E+05 1.0E+05\n')
    archive(tmp_path, '20260101T000000Z-aaaaaaaa', first)
    auto = tmp_path/'.cmfgen-runs/20260102T000000Z-auto-bbbbbbbb'
    auto.mkdir()
    rows = _parse_iteration_records(run(2, [(3, 2), (4, 1)]))
    rows[0]['luminosity_difference_percent'] = 2.5
    rows[1]['luminosity_difference_percent'] = float('inf')
    (auto/'result.json').write_text(json.dumps({'attempts': [{
        'journal': '/foreign/20260102T000000Z-cccccccc',
        'status': 'succeeded', 'evidence': {'records': rows}}]}))
    (tmp_path/'OUTGEN').write_text(run(3, [(5, .5)]))
    result = correction_history(tmp_path)
    assert result['run_count'] == 2
    traces = sorted(result['luminosity_data'], key=lambda t: t['x'][0])
    assert [t['x'] for t in traces] == [[1, 2], [3]]
    assert [t['y'] for t in traces] == [[-10.0, 0.0], [2.5]]
    assert all(t['line']['dash'] == 'dot' for t in traces)
    current = inspect_model_convergence(tmp_path)['plots'][1]
    assert current['history_key'] == 'luminosity_data'
    assert current['data'] == []
