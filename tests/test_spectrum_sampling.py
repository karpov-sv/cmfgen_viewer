"""Display reduction must never discard the native spectrum or line cores."""

import json
import re
import shutil
import subprocess
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

from cmfgen_viewer import grid_views
from cmfgen_viewer.app import create_app
from cmfgen_viewer.parsers.extended_text import parse_cmf_spectrum, parse_ewdata
from cmfgen_viewer.parsers.obsflux import parse_obsflux
from cmfgen_viewer.upload_service import create_upload_bundle
from cmfgen_viewer.spectrum_plots import (
    build_both_plot,
    build_final_model_series,
    build_normalized_plot,
    build_observed_overlay_trace,
    build_uploaded_spectrum_plot,
)


def test_browser_native_sampling_and_viewport_lifecycle():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for spectrum rendering checks")
    result = subprocess.run(
        [node, str(Path(__file__).with_name("spectrum_sampling.cjs"))],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_model_and_uploaded_payloads_preserve_native_line_profile_and_errors():
    x = np.linspace(4000, 7000, 10007).tolist()
    y = [1.0] * len(x)
    y[5013] = 0.05  # A single native sample that uniform decimation would miss.
    continuum = {"wavelength": x, "flux": [1.0] * len(x)}
    final = {"wavelength": x, "flux": y}
    both = build_both_plot(continuum, final)
    assert all(trace["x"] == x for trace in both["data"])
    normalized = build_normalized_plot(continuum, final)
    assert normalized["data"][0]["x"] == x
    assert normalized["data"][0]["y"] == y
    assert build_final_model_series(continuum, final, mode="normalized") == (x, y)
    assert len(build_final_model_series(continuum, final, mode="normalized", max_points=100)[0]) == 100

    errors = [index / len(x) for index in range(len(x))]
    observed = {"wavelength": x, "flux": y, "flux_err": errors, "flux_mode": "normalized"}
    trace, error = build_observed_overlay_trace(observed, mode="normalized")
    assert error is None
    uploaded, error = build_uploaded_spectrum_plot(observed)
    assert error is None
    for trace in [trace, uploaded["data"][0]]:
        assert trace["x"] == x
        assert trace["y"] == y
        assert trace["error_y"]["array"][1:] == errors[1:]


def test_parsed_spectra_retain_every_sample(tmp_path):
    x = np.linspace(4000, 7000, 6001)
    y = np.linspace(2, 1, x.size)
    y[3013] = 0.01
    path = tmp_path / "OBSFLUX"
    path.write_text(
        f"Continuum Frequencies ({x.size})\n"
        + " ".join(str(2997.92458 / value) for value in x)
        + "\nObserved intensity (Janskys)\n"
        + " ".join(str(value) for value in y) + "\n",
        encoding="utf-8",
    )
    trace = parse_obsflux(path)["plots"][0]["data"][0]
    assert len(trace["x"]) == len(x)
    assert trace["y"] == y.tolist()
    assert trace["line"]["simplify"] is False
    path = tmp_path / "cmf.sed"
    np.savetxt(path, np.column_stack((x, y)))
    trace = parse_cmf_spectrum(path)["plots"][0]["data"][0]
    assert trace["x"] == x.tolist()
    assert trace["y"] == y.tolist()
    path = tmp_path / "ewdata_fin"
    np.savetxt(path, np.column_stack((x, y, y)))
    assert all(len(plot["data"][0]["x"]) == len(x) for plot in parse_ewdata(path)["plots"])


@pytest.mark.parametrize("source", ["cmfgen", "bosz", "phoenix"])
def test_fitted_overlays_broaden_native_samples_before_display(source, tmp_path, monkeypatch):
    x = np.linspace(4000, 7000, 10007)
    continuum = np.linspace(2, 1, len(x))
    y = continuum * (1 - 0.8 * np.exp(-0.5 * ((x - 5000) / 0.4) ** 2))
    upload_root = tmp_path / "uploads"
    stream = BytesIO()
    np.savetxt(stream, np.column_stack((x, y)))
    stream.seek(0)
    manifest = create_upload_bundle(upload_root, filename="observed.dat", stream=stream, flux_mode="absolute")
    config = {"basepath": str(tmp_path), "upload_root": str(upload_root)}
    model = tmp_path / "model_a"
    obs = model / "obs"
    obs.mkdir(parents=True)
    frequencies = " ".join(str(2997.92458 / value) for value in x)
    for name, flux in [("obs_fin", y), ("obs_cont", continuum)]:
        (obs / name).write_text(f"Continuum Frequencies ({x.size})\n{frequencies}\nObserved intensity (Janskys)\n" + " ".join(map(str, flux)) + "\n")
    root = tmp_path / source
    root.mkdir()
    config[source + "_root"] = str(root)
    np.savez_compressed(root / "model.npz", wavelength_angstrom=x, flux_lambda_cgs=y)
    fit_params = {"redshift": 0, "ebv": 0, "distance_kpc": 1, "broadening_km_s": 60}
    entry = {"fit_source": source, "model_name": "test", "model_path": "model_a", "fin": "obs_fin", "spectrum_relpath": "model.npz", "fit_params": fit_params}
    transformed_sizes = []
    original = grid_views.apply_spectrum_transform

    def checked_transform(wavelength, flux, **kwargs):
        transformed_sizes.append(len(wavelength))
        assert kwargs["broadening_km_s"] == 60
        return original(wavelength, flux, **kwargs)

    monkeypatch.setattr(grid_views, "apply_spectrum_transform", checked_transform)
    overlay, error = grid_views._build_upload_grid_overlay_trace(
        config=config, snapshot={"upload_token": manifest["token"], "mode": "both"}, model_entry=entry,
    )
    assert error is None
    assert transformed_sizes == [len(x)]
    assert len(overlay["x"]) == len(x)


def test_spectral_pages_render_native_payloads_and_valid_inline_scripts(tmp_path):
    """Exercise Flask/Jinja integration even when Chromium is unavailable."""
    node = shutil.which("node")
    model = tmp_path / "model_a"
    obs = model / "obs"
    obs.mkdir(parents=True)
    (model / "VADAT").write_text("1 [LSTAR]\n")
    (model / "MODEL_SPEC").write_text("settings\n")
    (model / "RVTJ").write_text("ND: 2\nRadius\n1 2\nVelocity\n10 20\n")
    (model / "MOD_SUM").write_text("ND[2]\nTeff(K)=35000\n")
    values = " ".join(str(0.83 - i / 15000) for i in range(6001))
    flux = " ".join(str(20 - i / 1000) for i in range(6001))
    content = f"Continuum Frequencies (6001)\n{values}\nObserved intensity (Janskys)\n{flux}\n"
    for path in [obs / "obs_fin", obs / "obs_cont", model / "OBSFLUX"]:
        path.write_text(content)
    cmf_sed = model / "cmf.sed"
    np.savetxt(cmf_sed, np.column_stack((np.linspace(4000, 7000, 6001), np.linspace(2, 1, 6001))))
    upload_root = tmp_path / "uploads"
    manifest = create_upload_bundle(upload_root, filename="observed.dat", stream=BytesIO(cmf_sed.read_bytes()), flux_mode="absolute")
    app = create_app(basepath=str(tmp_path), upload_root=str(upload_root))
    app.testing = True
    app.config["CMFGEN_VIEWER"]["summary_cache_db"] = str(tmp_path / "summary.sqlite")
    client = app.test_client()
    pages = ["/spectrum/model_a", "/bulk/spectra/?selected_models=model_a", f"/uploads/view/{manifest['token']}", "/view/model_a/OBSFLUX", "/view/model_a/cmf.sed"]
    for url in pages:
        response = client.get(url)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "spectrum_sampling.js" in html
        assert "spectrum_controls.js" in html
        assert "Line and display settings" in html
        assert "Full resolution in displayed region" in html
        plot_ids = [
            value for value in re.findall(r'\bid="([^"]+)"', html)
            if value.startswith("plotly-") or "spectrum-plot" in value
        ]
        assert len(plot_ids) == len(set(plot_ids)), "Shared components must keep plot IDs unique"
        if not url.startswith("/view/"):
            assert "spectrum_viewer.js" in html
            assert "Reset transformations" in html
        # Verify every rendered inline script parses, including raw combined
        # and separate plot branches and large embedded native vectors.
        scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.S)
        for attrs, code in scripts:
            if 'application/json' in attrs:
                payload = json.loads(code)
                if "plot_data_data" in payload:
                    assert len(payload["plot_data_data"][0]["x"]) == 6001
            elif code.strip() and node:
                result = subprocess.run([node, "--check"], input=code, text=True, capture_output=True)
                assert result.returncode == 0, result.stderr
    for url in ["/view/", "/view/model_a/RVTJ", "/view/model_a/MOD_SUM", "/documentation/spectral-line-overlay"]:
        response = client.get(url)
        assert response.status_code == 200
