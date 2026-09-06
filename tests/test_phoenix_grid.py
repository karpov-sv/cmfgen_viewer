from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

from astropy.io import fits
import numpy as np
import pytest

from cmfgen_viewer.app import create_app
from cmfgen_viewer.grid_catalog import _discover_grid_fit_candidates
from cmfgen_viewer.grid_config import _grid_fit_source_label
from cmfgen_viewer.grid_fitting import _fit_single_grid_candidate
from cmfgen_viewer.spectrum_fitting import _sample_model_on_observed_grid
from cmfgen_viewer.spectrum_options import _normalize_fit_bounds
from cmfgen_viewer.upload_service import create_upload_bundle
from scripts.import_phoenix_spectra import FLUX_FACTOR, PRODUCT, import_grid, read_spectrum


def make_fits(teff=6000, *, negative=False, interpolated=False, **headers):
    wave = np.exp(8.006368 + np.arange(212027) * 1e-5)
    flux = (1e15 * (5000 / wave) ** 3 *
            (1 - (0.4 if teff == 6000 else 0.1) * np.exp(-0.5 * ((wave - 5000) / 30) ** 2))).astype("f4")
    if negative:
        flux[700] = -1e10
    hdu = fits.PrimaryHDU(flux)
    hdu.header.update(CRVAL1=8.006368, CDELT1=1e-5, CTYPE1="AWAV-LOG",
                      PHXTEFF=teff, PHXLOGG=4.0, PHXM_H=0.0, PHXALPHA=0.0)
    if interpolated:
        hdu.header["INTERPOL"] = True
    else:
        hdu.header.update(BUNIT="erg/s/cm^2/cm", PHXXI_L=1.73)
    hdu.header.update(headers)
    stream = BytesIO()
    hdu.writeto(stream)
    name = f"lte{teff:05d}-4.00-0.0.{PRODUCT}-HiRes.fits"
    return name, stream.getvalue(), wave, flux.astype(float) * FLUX_FACTOR


@pytest.fixture(scope="module")
def phoenix_case(tmp_path_factory):
    directory = tmp_path_factory.mktemp("phoenix")
    source = directory / "source"
    source.mkdir()
    with ZipFile(source / f"{PRODUCT}_R10000FITS_Z-0.0.zip", "w", ZIP_DEFLATED) as handle:
        for teff, flags in ((6000, {}), (6200, {"interpolated": True}), (6400, {"negative": True})):
            name, payload, _, _ = make_fits(teff, **flags)
            handle.writestr(name, payload)
    root = directory / "converted"
    assert import_grid(source, root, workers=2, log=lambda _: None) == 3
    return root, source


def discover(root, **kwargs):
    return _discover_grid_fit_candidates(
        {"phoenix_root": str(root)}, fit_source="phoenix", mode=kwargs.pop("mode", "both"),
        basepath="unused", summary_cache_db="unused", model_name_pattern=kwargs.pop("model_name_pattern", ""),
        **kwargs,
    )


def fit(candidate, observed, **kwargs):
    return _fit_single_grid_candidate(
        fit_source="phoenix", candidate=candidate, mode=kwargs.pop("mode", "both"), observed=observed,
        fit_bounds={"redshift": (0, 0), "broadening_km_s": (0, 0), "ebv": (0, 0)},
        lambda_min=3000, lambda_max=25000, **kwargs,
    )


def test_import_preserves_sampling_flux_and_provenance(phoenix_case):
    root, source = phoenix_case
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["total_models"] == 3
    assert manifest["fit_eligible_models"] == 2
    assert manifest["flux_conversion_factor"] == FLUX_FACTOR
    assert manifest["wavelength_convention"] == "vacuum"
    assert len(manifest["archives"][0]["sha256"]) == 64
    for row in manifest["models"]:
        name, _, wave, expected = make_fits(row["teff_k"], negative=row["teff_k"] == 6400,
                                          interpolated=row["teff_k"] == 6200)
        assert row["source_member"] == name
        assert row["source_ctype1"] == "AWAV-LOG"
        assert len(row["source_sha256"]) == 64
        with np.load(root / row["spectrum_relpath"]) as arrays:
            assert set(arrays) == {"wavelength_angstrom", "flux_lambda_cgs"}
            np.testing.assert_array_equal(arrays["wavelength_angstrom"], wave)
            np.testing.assert_array_equal(arrays["flux_lambda_cgs"], expected)
        assert row["points"] == 212027
        assert row["wavelength_max_angstrom"] == pytest.approx(24999.9224)
        assert row["negative_flux_points"] == int(row["teff_k"] == 6400)
    assert manifest["models"][1]["source_unit_inferred"] is True
    assert manifest["models"][1]["derived_vturb_km_s"] is None
    with pytest.raises(FileExistsError):
        import_grid(source, root)


@pytest.mark.parametrize("headers", [
    {"CTYPE1": "LINEAR"}, {"CDELT1": 0.1}, {"CRVAL1": 3.0},
    {"BUNIT": "Jy"}, {"BUNIT": ""}, {"PHXTEFF": 7000}, {"PHXALPHA": 0.2},
])
def test_reader_rejects_wrong_products(headers):
    name, payload, *_ = make_fits(**headers)
    with pytest.raises(ValueError):
        read_spectrum(payload, name)


@pytest.mark.parametrize("problem", ["unsafe", "duplicate", "malformed"])
def test_import_failure_never_publishes_or_leaves_staging(tmp_path, problem):
    source = tmp_path / "source"
    source.mkdir()
    name, payload, *_ = make_fits()
    if problem == "unsafe":
        name = "../" + name
    with ZipFile(source / f"{PRODUCT}_R10000FITS_Z-0.0.zip", "w") as handle:
        handle.writestr(name, payload if problem != "malformed" else b"invalid FITS")
    if problem == "duplicate":
        with ZipFile(source / f"{PRODUCT}_R10000FITS_Z+0.5.zip", "w") as handle:
            handle.writestr(name, payload)
    with pytest.raises((ValueError, OSError)):
        import_grid(source, tmp_path / "output", log=lambda _: None)
    assert not (tmp_path / "output").exists()
    assert not list(tmp_path.glob(".output-import-*"))


def test_discovery_quality_modes_and_coverage(phoenix_case):
    root, _ = phoenix_case
    candidates, error = discover(root)
    assert error is None and len(candidates) == 2
    assert all(c["fit_source"] == "phoenix" for c in candidates)
    assert all(c["grid_params"]["vturb_km_s"] is None for c in candidates)
    assert candidates[0]["grid_metadata"]["derived_vturb_km_s"] == 1.73
    assert candidates[1]["grid_metadata"]["interpolated"] is True
    assert len(discover(root, model_name_pattern="lte06000*")[0]) == 1
    assert not discover(root, model_name_pattern="lte06400*")[0]
    assert "no continua" in discover(root, mode="normalized")[1]
    assert "PHOENIX index is missing" in discover(root / "absent")[1]
    observed = {"observation_type": "photometry", "wavelength": [12500, 16500, 22000],
                "band_width": [1000, 1000, 1000]}
    assert len(discover(root, observed=observed)[0]) == 2
    observed["wavelength"][-1] = 26000
    assert not discover(root, observed=observed)[0]
    assert _grid_fit_source_label("phoenix") == "PHOENIX Grid"
    assert "distance_kpc" not in _normalize_fit_bounds({}, mode="both", fit_source="phoenix")


def test_worker_keeps_native_sampling_and_rejects_normalized(phoenix_case, monkeypatch):
    root, _ = phoenix_case
    candidate = discover(root)[0][0]
    captured = {}

    def load(**kwargs):
        captured.update(kwargs)
        return None, None, "stop"

    monkeypatch.setattr("cmfgen_viewer.grid_fitting._build_tlusty_model_series", load)
    assert fit(candidate, {}, mode="normalized")["status"] == "failed"
    assert not captured
    fit(candidate, {})
    assert captured["max_points"] == 0


def test_photometry_fit_and_cancel(phoenix_case):
    root, _ = phoenix_case
    _, _, wave, flux = make_fits()
    centers = np.array([4200, 5000, 6600, 12500, 22000], dtype=float)
    widths = np.full(5, 100.0)
    observed = {
        "wavelength": centers.tolist(), "band_width": widths.tolist(),
        "flux": (_sample_model_on_observed_grid(wave, flux, centers, widths) * 2e-20).tolist(),
        "flux_mode": "absolute", "observation_type": "photometry",
    }
    candidates = discover(root, observed=observed)[0]
    results = [fit(candidate, observed) for candidate in candidates]
    assert all(result["status"] == "success" for result in results)
    best = min((result["item"] for result in results), key=lambda item: item["chi2"])
    assert best["grid_params"]["teff_k"] == 6000
    assert best["fit_params"]["normalization"] == pytest.approx(2e-20, rel=1e-6, abs=0)
    assert fit(candidates[0], observed, should_cancel=lambda: True)["status"] == "canceled"
    bad = dict(candidates[0])
    bad["spectrum_path_str"] = bad["spectrum_path_str"].replace("lte06000", "lte06400")
    assert fit(bad, observed)["status"] == "failed"


@pytest.mark.parametrize("normalized", [False, True])
def test_fit_overlay_api_and_mode_guard(phoenix_case, tmp_path, monkeypatch, normalized):
    root, _ = phoenix_case
    _, _, wave, flux = make_fits()
    stream = BytesIO()
    np.savetxt(stream, np.column_stack((wave[::100], flux[::100] * 2e-20)))
    stream.seek(0)
    upload_root = tmp_path / "uploads"
    manifest = create_upload_bundle(upload_root, filename="observed.dat", stream=stream,
                                    flux_mode="normalized" if normalized else "absolute")
    app = create_app(basepath=str(tmp_path), upload_root=str(upload_root), fit_pool_size_max=1)
    app.testing = True
    app.config["CMFGEN_VIEWER"].update(phoenix_root=str(root), summary_cache_db=str(tmp_path / "unused.sqlite"))

    class InlineThread:
        def __init__(self, *, target, kwargs, daemon):
            self.target, self.kwargs = target, kwargs

        def start(self):
            self.target(**self.kwargs)

    monkeypatch.setattr("cmfgen_viewer.grid_views.Thread", InlineThread)
    client = app.test_client()
    token = manifest["token"]
    page = client.get(f"/uploads/view/{token}?fit_source=phoenix").get_data(as_text=True)
    assert 'data-fit-source="phoenix"' in page and "R=10000" in page
    assert ('disabled title="PHOENIX' in page) == normalized
    form = {"fit_source": "phoenix", "mode": "both"}  # Cannot override actual normalized upload mode.
    for param in ("redshift", "broadening_km_s", "ebv"):
        form[f"fit_{param}_min"] = form[f"fit_{param}_max"] = "0"
    response = client.post(f"/uploads/fit-grid/{token}", data=form)
    if normalized:
        assert response.status_code == 400
        assert "no continua" in str(response.get_json())
        return
    assert response.status_code == 200, response.get_json()
    job_id = response.get_json()["job_id"]
    status = client.get(f"/uploads/fit-grid/status/{job_id}").get_json()
    assert status["status"] == "completed" and status["successful"] == 2
    assert status["fit_source"] == "phoenix"
    best = status["result"]["best_model"]
    assert best["grid_params"]["teff_k"] == 6000
    assert best["grid_metadata"]["wavelength_convention"] == "vacuum"
    assert best["fit_params"]["normalization"] == pytest.approx(2e-20, rel=1e-6, abs=0)
    assert "grid_confidence" in status["result"] and "tlusty_confidence" not in status["result"]
    overlay = client.get(f"/uploads/fit-grid/overlay/{job_id}?which=final")
    assert overlay.status_code == 200, overlay.get_json()
    trace = overlay.get_json()["trace"]
    assert trace["fit_source"] == "phoenix"
    np.testing.assert_allclose(trace["y"], np.interp(trace["x"], wave, flux) * 2e-20, rtol=1e-6)
    app.extensions["cmfgen_jobs"]["grid"].update(job_id, status="running")
    page = client.get(f"/uploads/view/{token}").get_data(as_text=True)
    assert 'name="fit_source" value="phoenix"' in page
