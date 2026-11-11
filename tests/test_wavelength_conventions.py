from io import BytesIO

import numpy as np
import pytest

from cmfgen_viewer.app import create_app
from cmfgen_viewer.observed_spectrum import parse_uploaded_spectrum, read_upload_manifest
from cmfgen_viewer.spectrum_fitting import fit_model_to_observed
from cmfgen_viewer.spectrum_transforms import _apply_transform_arrays, PreparedSpectrumTransform
from cmfgen_viewer.upload_service import create_upload_bundle
from cmfgen_viewer.wavelengths import air_to_vacuum, vacuum_to_air, to_upload_medium
from cmfgen_viewer.grid_jobs import _grid_search_job_create


def test_air_vacuum_roundtrip_and_flux_density():
    assert vacuum_to_air(6564.614) == pytest.approx(6562.801, abs=.003)
    wave = np.linspace(4000, 10000, 50001)
    np.testing.assert_allclose(air_to_vacuum(vacuum_to_air(wave)), wave, atol=1e-9, rtol=1e-12)
    flux = 2 + np.sin(wave / 1000)
    air_wave, air_flux = to_upload_medium(wave, flux, medium="air", absolute=True)
    assert np.trapezoid(air_flux, air_wave) == pytest.approx(np.trapezoid(flux, wave), rel=1e-9)
    np.testing.assert_array_equal(vacuum_to_air([1000, 1500]), [1000, 1500])
    np.testing.assert_array_equal(air_to_vacuum([0, 1000, 1500]), [0, 1000, 1500])


@pytest.mark.parametrize("mode", ["normalized", "both"])
def test_prepared_air_sampling_matches_full_transform(mode):
    wave = np.exp(np.linspace(np.log(4900), np.log(5100), 2001))
    flux = 1 - .5 * np.exp(-((wave - 5000) / 1.5)**2)
    prepared = PreparedSpectrumTransform(wave, flux, mode, "air")
    params = dict(redshift=.002, broadening_km_s=0, ebv=.15, distance_kpc=1.4)
    native = _apply_transform_arrays(wave, flux, mode=mode, wavelength_medium="air", **params)
    full = prepared(**params)
    np.testing.assert_allclose(full, native, rtol=1e-12)
    x = np.linspace(native[0][50], native[0][-50], 800)
    fast = prepared.sample_unbroadened(x, redshift=.002, ebv=.15, distance_kpc=1.4)
    np.testing.assert_allclose(fast, np.interp(x, *native), rtol=1e-12)


def test_fit_recovers_physical_redshift_without_moving_air_samples():
    wave = np.linspace(4900, 5100, 8001)
    flux = 1 - .5 * np.exp(-((wave - 5000) / .7)**2) - .3 * np.exp(-((wave - 5050) / .9)**2)
    true_z = .0013
    x, y = _apply_transform_arrays(wave, flux, mode="normalized", redshift=true_z,
        broadening_km_s=20, ebv=0, distance_kpc=1, wavelength_medium="air")
    observed_x = np.linspace(4960, 5080, 2000)
    observed = {"wavelength": observed_x.tolist(), "flux": np.interp(observed_x, x, y).tolist(),
                "flux_mode": "normalized", "wavelength_medium": "air", "flux_err": [.01]*2000,
                "require_full_coverage": True}
    original = {key: value.copy() for key, value in observed.items() if isinstance(value, list)}
    bounds = {"redshift": (.0005, .002), "broadening_km_s": (20, 20)}
    params, metrics, error = fit_model_to_observed({}, {}, observed, mode="normalized",
        prepared_model=(wave, flux), bounds_override=bounds, initial_params={"redshift": .0012})
    assert error is None
    assert params["redshift"] == pytest.approx(true_z, abs=1e-7)
    assert metrics["wavelength_medium"] == "air"
    for key, value in original.items():
        assert observed[key] == value
    # Without the conversion, the optimizer would absorb the wavelength-medium
    # mismatch into the source velocity.
    wrong, _, error = fit_model_to_observed({}, {}, {**observed, "wavelength_medium": "vacuum"},
        mode="normalized", prepared_model=(wave, flux), bounds_override=bounds,
        initial_params={"redshift": .001})
    assert error is None
    assert abs(wrong["redshift"] - true_z) > .0002


def test_upload_medium_default_edit_and_cached_parsing(tmp_path):
    root = tmp_path / "uploads"
    manifest = create_upload_bundle(root, filename="star.dat", stream=BytesIO(b"4000 1\n5000 .5\n6000 1\n"), flux_mode="normalized")
    assert manifest["wavelength_medium"] == "air"
    token = manifest["token"]
    source = root / token / manifest["stored_name"]
    original = source.read_bytes()
    before = parse_uploaded_spectrum(source)
    assert before["require_full_coverage"] is True
    before["fit_regions"] = {"windows": []}
    app = create_app(basepath=str(tmp_path), upload_root=str(root))
    client = app.test_client()
    response = client.post(f"/uploads/wavelengths/{token}", data={"wavelength_medium": "vacuum"})
    assert response.status_code == 302
    assert read_upload_manifest(root, token)["wavelength_medium"] == "vacuum"

    after = parse_uploaded_spectrum(source)
    assert after["wavelength_medium"] == "vacuum"
    assert "fit_regions" not in after
    assert after["wavelength"] == before["wavelength"]
    assert source.read_bytes() == original
    client.post(f"/uploads/wavelengths/{token}", data={"wavelength_medium": "invalid"})
    assert read_upload_manifest(root, token)["wavelength_medium"] == "vacuum"
    page = client.get(f"/uploads/view/{token}").get_data(as_text=True)
    assert "Save wavelength convention" in page
    assert '<option value="vacuum" selected' in page
    store = app.extensions["cmfgen_jobs"]["grid"]
    _grid_search_job_create(store, upload_token=token, fit_source="tlusty", mode="normalized",
        fit_bounds={}, fit_wavelength_range=None, model_name_pattern="", total_models=1,
        wavelength_medium="vacuum")
    client.post(f"/uploads/wavelengths/{token}", data={"wavelength_medium": "air"})
    assert read_upload_manifest(root, token)["wavelength_medium"] == "vacuum"


def test_full_window_requires_identical_samples_without_named_diagnostics():
    wave = np.linspace(4000, 6000, 300)
    observed_x = np.linspace(3900, 6100, 300)
    observed = {"wavelength": observed_x.tolist(), "flux": [1.0]*300, "flux_mode":"normalized",
                "wavelength_medium":"vacuum", "require_full_coverage":True}
    params, metrics, error = fit_model_to_observed({}, {}, observed, mode="normalized",
        prepared_model=(wave, np.ones(wave.size)),
        bounds_override={"redshift": (0, 0), "broadening_km_s":(0, 0)})
    assert params is None and metrics is None
    assert "every selected spectral sample" in error


@pytest.mark.parametrize("medium", ["air", "vacuum"])
def test_upload_form_persists_medium(tmp_path, medium):
    app = create_app(basepath=str(tmp_path), upload_root=str(tmp_path / "uploads"))
    client = app.test_client()
    response = client.post("/uploads/upload", data={
        "observed_file": (BytesIO(b"4000 1\n5000 .5\n6000 1\n"), "star.dat"),
        "flux_mode": "normalized", "wavelength_medium": medium,
    })
    assert response.status_code == 302
    from cmfgen_viewer.observed_spectrum import list_upload_manifests
    entries = list_upload_manifests(tmp_path / "uploads")
    assert len(entries) == 1 and entries[0]["wavelength_medium"] == medium


def test_vizier_points_appended_to_air_photometry_are_converted(tmp_path, monkeypatch):
    from cmfgen_viewer.upload_views import _query_vizier_photometry_rows_from_form
    from cmfgen_viewer.vizier_photometry import VizierPhotometryPoint

    monkeypatch.setattr("cmfgen_viewer.upload_views.query_vizier_photometry_points",
        lambda **kwargs: [VizierPhotometryPoint(5000, 100, 1, .1, "catalog point")])
    app = create_app(basepath=str(tmp_path), upload_root=str(tmp_path / "uploads"))
    with app.test_request_context("/", method="POST", data={"vizier_center": "120 -20", "vizier_catalog": ["panstarrs_dr1"]}):
        rows = _query_vizier_photometry_rows_from_form("air")
    values = rows.split("#")[0].split()
    assert float(values[0]) == pytest.approx(float(vacuum_to_air(5000)), abs=.001)
    assert float(values[2]) == pytest.approx(float(vacuum_to_air(5000, flux_jacobian=True)), rel=1e-8)


def test_mixed_overlay_conventions_are_not_silently_combined(tmp_path):
    import json
    import re

    obs = tmp_path / "model" / "obs"
    obs.mkdir(parents=True)
    for name in ("obs_cont", "obs_fin"):
        (obs / name).write_text("Continuum Frequencies (3)\n.75 .6 .5\nObserved intensity (Janskys)\n1 1 1\n")
    root = tmp_path / "uploads"
    tokens = {}
    for name, medium, flux in (("air", "air", "normalized"), ("vac", "vacuum", "normalized"), ("abs", "air", "absolute")):
        manifest = create_upload_bundle(root, filename=name+".dat", stream=BytesIO(b"4000 1\n5000 .5\n6000 1\n"),
            flux_mode=flux, wavelength_medium=medium)
        tokens[name] = manifest["token"]
    client = create_app(basepath=str(tmp_path), upload_root=str(root)).test_client()
    for names, expected_medium, mixed in ((["air", "vac"], "air", True), (["abs", "vac"], "vacuum", False)):
        page = client.get("/spectrum/model", query_string={"mode":"normalized", "obs":[tokens[name] for name in names]}).get_data(as_text=True)
        assert ("Observed overlays must share" in page) is mixed
        configs = [json.loads(text) for text in re.findall(r'<script type="application/json">(.*?)</script>', page, re.S)]
        traces = next(item["plot_data_data"] for item in configs if "plot_data_data" in item)
        observed = [trace for trace in traces if trace.get("meta", {}).get("transform_target") == "observed"]
        assert len(observed) == 1 and observed[0]["meta"]["wavelength_medium"] == expected_medium
