import gzip
from io import BytesIO

import numpy as np
import pytest

from cmfgen_viewer.app import create_app
from cmfgen_viewer.grid_catalog import _discover_grid_fit_candidates
from cmfgen_viewer.grid_config import _grid_fit_source_label
from cmfgen_viewer.grid_fitting import _fit_single_grid_candidate
from cmfgen_viewer.spectrum_options import _normalize_fit_bounds
from cmfgen_viewer.spectrum_fitting import _sample_model_on_observed_grid
from cmfgen_viewer.upload_service import create_upload_bundle
from scripts.import_bosz_spectra import import_grid


@pytest.fixture
def bosz_case(tmp_path):
    source = tmp_path / "download"
    source.mkdir()
    wave = np.linspace(4000, 7000, 501)
    continuum = 1e8 * (5000 / wave) ** 3
    norm = 1 - 0.4 * np.exp(-0.5 * ((wave - 5000) / 30) ** 2)
    np.savetxt(source / "bosz2024_wave_r2000.txt", wave)
    for family, depth in (("ap", 0.4), ("mp", 0.1)):
        flux = continuum * (1 - depth * np.exp(-0.5 * ((wave - 5000) / 30) ** 2))
        name = f"bosz2024_{family}_t8000_g+4.0_m+0.00_a+0.00_c+0.00_v2_r2000_resam.txt.gz"
        with gzip.open(source / name, "wt") as handle:
            np.savetxt(handle, np.column_stack((flux, continuum)))
    root = tmp_path / "bosz"
    import_grid(source, root, log=lambda _: None)
    return root, wave, continuum, norm


def discover(root, **kwargs):
    return _discover_grid_fit_candidates(
        {"bosz_root": str(root)}, fit_source="bosz", mode=kwargs.pop("mode", "normalized"),
        basepath="unused", summary_cache_db="unused", model_name_pattern=kwargs.pop("model_name_pattern", ""),
        **kwargs,
    )


def test_bosz_discovery_preserves_distinct_atmospheres_and_filters(bosz_case):
    root, *_ = bosz_case
    candidates, error = discover(root)
    assert error is None
    assert len(candidates) == 2
    assert {c["grid_metadata"]["atmosphere_family"] for c in candidates} == {"ap", "mp"}
    assert all(c["fit_source"] == "bosz" and c["grid_metadata"]["resolving_power"] == 2000 for c in candidates)
    assert all(c["model_path"].startswith("bosz/") for c in candidates)
    assert len(discover(root, model_name_pattern="*_ap_*")[0]) == 1
    observed = {"observation_type": "photometry", "wavelength": [5000, 9000], "band_width": [100, 100]}
    assert not discover(root, mode="both", observed=observed)[0]
    assert "BOSZ" in discover(root / "missing")[1]


@pytest.mark.parametrize("mode", ["normalized", "both"])
def test_bosz_fit_and_overlay_api(bosz_case, tmp_path, monkeypatch, mode):
    root, wave, continuum, norm = bosz_case
    absolute = mode == "both"
    flux = continuum * norm * 2e-20 if absolute else norm
    stream = BytesIO()
    np.savetxt(stream, np.column_stack((wave, flux)))
    stream.seek(0)
    upload_root = tmp_path / "uploads"
    manifest = create_upload_bundle(
        upload_root, filename="observed.dat", stream=stream,
        flux_mode="absolute" if absolute else "normalized",
    )
    app = create_app(basepath=str(tmp_path), upload_root=str(upload_root), fit_pool_size_max=1)
    app.testing = True
    app.config["CMFGEN_VIEWER"]["bosz_root"] = str(root)
    app.config["CMFGEN_VIEWER"]["summary_cache_db"] = str(tmp_path / "unused.sqlite")

    class InlineThread:
        def __init__(self, *, target, kwargs, daemon):
            self.target, self.kwargs = target, kwargs

        def start(self):
            self.target(**self.kwargs)

    monkeypatch.setattr("cmfgen_viewer.grid_views.Thread", InlineThread)
    client = app.test_client()
    token = manifest["token"]
    page = client.get(f"/uploads/view/{token}?fit_source=bosz").get_data(as_text=True)
    assert 'data-fit-source="bosz"' in page
    assert "R=2000" in page
    query = {"fit_source": "bosz", "mode": mode, "model_name_pattern": ""}
    count = client.get(f"/uploads/fit-grid/match-count/{token}", query_string=query)
    assert count.status_code == 200
    assert count.get_json()["total_models"] == 2
    form = {"fit_source": "bosz"}
    for param in ("redshift", "broadening_km_s", "ebv"):
        form[f"fit_{param}_min"] = "0"
        form[f"fit_{param}_max"] = "0"
    response = client.post(f"/uploads/fit-grid/{token}", data=form)
    assert response.status_code == 200, response.get_json()
    job_id = response.get_json()["job_id"]
    status = client.get(f"/uploads/fit-grid/status/{job_id}").get_json()
    assert status["status"] == "completed", status
    assert status["successful"] == 2
    assert status["fit_source"] == "bosz"
    result = status["result"]
    best = result["best_model"]
    assert "_ap_" in best["model_name"]
    assert best["grid_metadata"]["atmosphere_family"] == "ap"
    assert best["fit_source"] == "bosz"
    assert "tlusty_params" not in best
    assert "grid_confidence" in result
    assert "tlusty_confidence" not in result
    if absolute:
        assert best["fit_params"]["normalization"] == pytest.approx(2e-20, rel=1e-6, abs=0)
        assert "distance_kpc" not in response.get_json()["fit_bounds"]
    overlay = client.get(f"/uploads/fit-grid/overlay/{job_id}?which=final")
    assert overlay.status_code == 200, overlay.get_json()
    trace = overlay.get_json()["trace"]
    assert trace["fit_source"] == "bosz"
    np.testing.assert_allclose(trace["x"], wave)
    np.testing.assert_allclose(trace["y"], flux, rtol=1e-6)
    # Restoring a running search must preserve BOSZ rather than falling back to CMFGEN.
    app.extensions["cmfgen_jobs"]["grid"].update(job_id, status="running")
    reload = client.get(f"/uploads/view/{token}").get_data(as_text=True)
    assert '<option value="bosz" selected' in reload


def test_bosz_bounds_and_cancel(bosz_case):
    root, wave, _, norm = bosz_case
    assert _grid_fit_source_label("bosz") == "BOSZ Grid"
    bounds = _normalize_fit_bounds({}, mode="both", fit_source="bosz")
    assert "distance_kpc" not in bounds
    candidate = discover(root)[0][0]
    fit = _fit_single_grid_candidate(
        fit_source="bosz", candidate=candidate, mode="normalized",
        observed={"wavelength": wave.tolist(), "flux": norm.tolist(), "flux_mode": "normalized"},
        fit_bounds={}, lambda_min=4000, lambda_max=7000, should_cancel=lambda: True,
    )
    assert fit["status"] == "canceled"


def test_bosz_keeps_native_samples(bosz_case, monkeypatch):
    root, *_ = bosz_case
    captured = {}

    def load(**kwargs):
        captured.update(kwargs)
        return None, None, "stop after inspecting preparation"

    monkeypatch.setattr("cmfgen_viewer.grid_fitting._build_tlusty_model_series", load)
    _fit_single_grid_candidate(
        fit_source="bosz", candidate=discover(root)[0][0], mode="both", observed={},
        fit_bounds={}, lambda_min=4000, lambda_max=7000,
    )
    assert captured["max_points"] == 0


def test_bosz_absolute_photometry(bosz_case):
    root, wave, continuum, norm = bosz_case
    centers = np.array([4200, 4500, 5000, 6000, 6600], dtype=float)
    widths = np.full(5, 100.0)
    flux = _sample_model_on_observed_grid(wave, continuum * norm, centers, widths) * 2e-20
    observed = {
        "wavelength": centers.tolist(), "flux": flux.tolist(), "band_width": widths.tolist(),
        "flux_mode": "absolute", "observation_type": "photometry",
    }
    candidates, error = discover(root, mode="both", observed=observed)
    assert error is None
    fits = [
        _fit_single_grid_candidate(
            fit_source="bosz", candidate=candidate, mode="both", observed=observed,
            fit_bounds={"redshift": (0, 0), "broadening_km_s": (0, 0), "ebv": (0, 0)},
            lambda_min=4000, lambda_max=7000,
        ) for candidate in candidates
    ]
    assert all(fit["status"] == "success" for fit in fits)
    best = min((fit["item"] for fit in fits), key=lambda item: item["chi2"])
    assert "_ap_" in best["model_name"]
    assert best["fit_params"]["normalization"] == pytest.approx(2e-20, rel=1e-6, abs=0)
