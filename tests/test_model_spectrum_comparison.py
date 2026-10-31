"""The Models comparison loads only selected spectra and shares spectrum math."""

import shutil
import subprocess
from pathlib import Path

import pytest

from cmfgen_viewer.app import create_app
from cmfgen_viewer.model_summary import ModelSummary
from cmfgen_viewer.summary_cache import upsert_model_summary


@pytest.fixture
def comparison(tmp_path):
    model = tmp_path / "grid" / "star"
    obs = model / "obs"
    obs.mkdir(parents=True)
    prefix = "Continuum Frequencies (4)\n1 .8 .6 .4\nObserved intensity (Janskys)\n"
    (obs / "obs_cont").write_text(prefix + "20 15 10 5\n")
    (obs / "obs_fin2").write_text(prefix + "10 7.5 5 2.5\n")
    (obs / "obs_fin10").write_text(prefix + "20 15 10 5\n")
    app = create_app(basepath=str(tmp_path), upload_root=str(tmp_path / "uploads"))
    app.config["TESTING"] = True
    db = str(tmp_path / "summary.sqlite")
    app.config["CMFGEN_VIEWER"]["summary_cache_db"] = db
    upsert_model_summary(db, basepath=str(tmp_path), relpath="grid/star", model_dir=model,
                         model_name="star", summary=ModelSummary(name="star"),
                         vadat_mtime=1.0, mod_sum_mtime=2.0)
    return app, app.test_client(), obs


def test_summary_has_lazy_comparison_without_altering_table_columns(comparison, monkeypatch):
    _, client, _ = comparison
    def unexpected(*args, **kwargs):
        raise AssertionError("The Models page must not parse spectra before selection")
    monkeypatch.setattr("cmfgen_viewer.spectrum_views.load_obs_spectrum", unexpected)
    response = client.get("/models/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'class="form-check-input me-2 comparison-model" value="grid/star"' in html
    assert 'data-spectrum-url="/models/spectrum-data"' in html
    assert 'id="comparison-select-visible"' in html
    assert html.count('id="model-comparison-plot"') == 1
    assert 'data-col0="star"' in html
    assert 'data-model-path="grid/star"' in html
    assert 'id="summary-name-filter"' in html
    assert 'aria-controls="summary-table"' in html


def test_comparison_normalizes_native_samples_and_chooses_first_fin(comparison):
    _, client, _ = comparison
    response = client.get("/models/spectrum-data", query_string={"model": "grid/star"})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    data = response.get_json()
    assert data["fin"] == "obs_fin2"
    assert data["plot"]["data"][0]["y"] == [0.5] * 4
    absolute = client.get("/models/spectrum-data?model=grid/star&mode=both").get_json()["plot"]
    assert len(absolute["data"]) == 2
    assert absolute["data"][0]["x"] == data["plot"]["data"][0]["x"]
    assert absolute["data"][0]["y"] == [v * 0.5 for v in absolute["data"][1]["y"]]


@pytest.mark.parametrize("path", ["../outside", "/etc", "grid/missing", "grid/star/obs/obs_fin2"])
def test_comparison_rejects_invalid_model_paths(comparison, path):
    _, client, _ = comparison
    response = client.get("/models/spectrum-data", query_string={"model": path})
    assert response.status_code == 404
    assert response.is_json


def test_comparison_reports_missing_and_unusable_data(comparison):
    _, client, obs = comparison
    assert client.get("/models/spectrum-data?model=grid/star&mode=invalid").status_code == 400
    (obs / "obs_fin2").write_text("incomplete spectrum\n")
    assert client.get("/models/spectrum-data?model=grid/star").status_code == 422
    (obs / "obs_cont").unlink()
    response = client.get("/models/spectrum-data?model=grid/star")
    assert response.status_code == 404
    assert "compute spectra first" in response.get_json()["error"]


def test_comparison_honors_configured_wavelength_range(comparison):
    app, client, _ = comparison
    app.config["CMFGEN_VIEWER"]["lambda_min_angstrom"] = 4000.0
    data = client.get("/models/spectrum-data?model=grid/star").get_json()
    assert len(data["plot"]["data"][0]["x"]) == 2
    assert min(data["plot"]["data"][0]["x"]) >= 4000


def test_model_comparison_javascript():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for comparison UI checks")
    result = subprocess.run([node, str(Path(__file__).with_name("model_spectrum_comparison.cjs"))],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
