"""UI out2in shares maintenance semantics and requires a current review."""
import re

import pytest

from cmfgen_viewer.app import create_app
from cmfgen_viewer import model_activity
from test_model_cli import solution, isolated_config
from test_model_staging import _write_solution


def client(model, *, writable=True):
    app = create_app(basepath=str(model.parent), read_write_enabled=writable, secret_key='out2in-ui-tests')
    app.testing = True
    app.config['CMFGEN_VIEWER'].update(summary_cache_db=str(model.parent / 'summary.sqlite'))
    return app.test_client()


def token(response):
    return re.search(r'name="review_token" value="([^"]*)"', response.get_data(as_text=True)).group(1)


def test_preview_and_confirmed_execution(solution):
    browser = client(solution)
    url = '/model-actions/out2in/' + solution.name
    preview = browser.get(url)
    assert preview.status_code == 200
    assert b'HeIOUT' in preview.data and b'HeI_IN' in preview.data
    assert b'aria-current="page" href="/model-actions/out2in/' in preview.data
    assert b'Prepare inputs (out2in)' in preview.data
    assert (solution / 'SCRTEMP').exists()
    assert not (solution / '.cmfgen-viewer-backups').exists()
    post = {'review_token': token(preview)}
    unconfirmed = browser.post(url, data=post)
    assert b'Confirm replacing' in unconfirmed.data
    assert (solution / 'SCRTEMP').exists()
    response = browser.post(url, data={**post, 'confirm_out2in': '1'})
    assert response.status_code == 302
    assert '/model-actions/main-computation/' in response.location
    assert '?' not in response.location
    assert (solution / 'HeI_IN').read_bytes() == (solution / 'HeIOUT').read_bytes()
    assert (solution / 'GAMMAS_IN').read_bytes() == (solution / 'GAMMAS').read_bytes()
    assert not (solution / 'SCRTEMP').exists()
    assert list((solution / '.cmfgen-viewer-backups/out2in').glob('*/operation.json'))


@pytest.mark.parametrize('mutation', ['output', 'checkpoint'])
def test_rejects_changed_review(solution, mutation):
    browser = client(solution)
    url = '/model-actions/out2in/' + solution.name
    preview = browser.get(url)
    data = {'review_token': token(preview), 'confirm_out2in': '1'}
    (solution / ('HeIOUT' if mutation == 'output' else 'SCRTEMP')).write_text('changed')
    response = browser.post(url, data=data)
    assert response.status_code == 200 and b'changed' in response.data
    assert (solution / 'HeI_IN').read_text() == 'old input\n'
    assert (solution / 'SCRTEMP').exists()
    assert not (solution / '.cmfgen-viewer-backups').exists()


def test_forged_and_other_model_reviews_are_rejected(solution, tmp_path):
    other = tmp_path / 'another'
    _write_solution(other)
    browser = client(solution)
    preview = browser.get('/model-actions/out2in/' + solution.name)
    url = '/model-actions/out2in/' + other.name
    for review in ('forged', token(preview)):
        response = browser.post(url, data={'review_token': review, 'confirm_out2in': '1'})
        assert response.status_code == 200
        assert b'invalid' in response.data or b'another model' in response.data
        assert (other / 'SCRTEMP').exists()


def test_ui_has_one_fixed_recovery_policy(solution):
    browser = client(solution)
    preview = browser.get('/model-actions/out2in/' + solution.name)
    assert b'Previous initial inputs are retained in full' in preview.data
    assert b'name="keep_large_files"' not in preview.data
    assert (solution / 'SCRTEMP').exists()
    assert not (solution / '.cmfgen-viewer-backups').exists()


@pytest.mark.parametrize('method', ['get', 'post'])
def test_readonly_ui_cannot_use_out2in(solution, method):
    assert getattr(client(solution, writable=False), method)('/model-actions/out2in/' + solution.name).status_code == 403


@pytest.mark.parametrize('state', ['active', 'unknown'])
def test_active_or_uncertain_model_is_blocked(solution, monkeypatch, state):
    browser = client(solution)
    url = '/model-actions/out2in/' + solution.name
    preview = browser.get(url)
    monkeypatch.setattr(model_activity, 'scan_model_processes', lambda *a, **k:
        ([{'pid': 1}], []) if state == 'active' else ([], ['Process visibility unavailable']))
    response = browser.get(url)
    assert b'type="submit" disabled>Prepare inputs' in response.data
    response = browser.post(url, data={'review_token': token(preview), 'confirm_out2in': '1'})
    assert response.status_code == 200
    assert (solution / 'SCRTEMP').exists()
    assert not (solution / '.cmfgen-viewer-backups').exists()


def test_nonmodel_page_is_rejected(solution, tmp_path):
    (tmp_path / 'other').mkdir()
    assert client(solution).get('/model-actions/out2in/other').status_code == 404
