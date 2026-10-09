"""Opt-in Chromium checks: CMFGEN_BROWSER_TESTS=1 python3 -m pytest -q -s tests/test_browser_smoke.py."""

import os
import csv
import json
import re
import shutil
import subprocess
from io import BytesIO
from pathlib import Path
from threading import Thread

import pytest
import numpy as np
from werkzeug.serving import make_server

from cmfgen_viewer.app import create_app
from cmfgen_viewer.upload_service import create_upload_bundle


@pytest.mark.skipif(
    os.environ.get("CMFGEN_BROWSER_TESTS") != "1", reason="Opt-in browser smoke check"
)
def test_spectrum_pages_in_chromium(tmp_path):
    chromium, node = shutil.which("chromium"), shutil.which("node")
    if not chromium or not node:
        pytest.skip("Chromium and Node.js are required")
    plotly = pytest.importorskip("plotly.offline")
    for name in ("model_a", "model_b"):
        model = tmp_path / name
        obs = model / "obs"
        obs.mkdir(parents=True)
        (model / "VADAT").write_text("1.0 [LSTAR]\n", encoding="utf-8")
        (model / "MODEL_SPEC").write_text("2 [ND]\n1 [NC]\n3 [NP]\n")
        (model / "batch.sh").write_text("#!/bin/sh\ncd obs\n./batobs.sh\n")
        (model / "batch.sh").chmod(0o755)
        (model / "MOD_SUM").write_text(
            "Model Started on: example\nND[2]\nTeff(K)=35000\n", encoding="utf-8"
        )
        (model / "RVTJ").write_text(
            "ND: 2\nRadius\n1 2\nVelocity\n10 20\n", encoding="utf-8"
        )
        # CMFGEN frequencies are in 10^15 Hz: cover the optical lines in
        # descending frequency order without triggering short-wave floor trim.
        values = " ".join(str(0.83 - i / 500) for i in range(201))
        flux = " ".join(str(20 - i / 20) for i in range(201))
        contents = f"Continuum Frequencies (201)\n{values}\nObserved intensity (Janskys)\n{flux}\n"
        for path in (obs / "obs_fin", obs / "obs_cont", model / "OBSFLUX"):
            path.write_text(contents, encoding="utf-8")
    upload_root = tmp_path / "uploads"
    wave = np.linspace(4000, 7000, 201)
    continuum = np.full(wave.size, 1e8)
    normalized = 1 - 0.4 * np.exp(-0.5 * ((wave - 5000) / 50) ** 2)
    model_flux = continuum * normalized
    observed_stream = BytesIO()
    np.savetxt(observed_stream, np.column_stack((wave, model_flux * 1e-20)))
    observed_stream.seek(0)
    manifest = create_upload_bundle(
        upload_root,
        filename="observed.dat",
        stream=observed_stream,
        flux_mode="absolute",
    )
    app = create_app(
        basepath=str(tmp_path), upload_root=str(upload_root), fit_pool_size_max=1,
        read_write_enabled=True,
    )
    app.config["CMFGEN_VIEWER"]["summary_cache_db"] = str(tmp_path / "summary.sqlite")
    bosz_root = tmp_path / "bosz"
    bosz_root.mkdir()
    app.config["CMFGEN_VIEWER"]["bosz_root"] = str(bosz_root)
    np.savez_compressed(
        bosz_root / "test.npz", wavelength_angstrom=wave, flux_lambda_cgs=model_flux,
        continuum_lambda_cgs=continuum, normalized_flux_candidate=normalized,
    )
    row = {
        "grid": "bosz", "model_name": "bosz2024_ap_test", "spectrum_relpath": "test.npz",
        "teff_k": 8000, "log_g": 4, "z_over_zsun": 1, "vturb_km_s": 2,
        "atmosphere_family": "ap", "resolving_power": 2000,
        "wavelength_min_angstrom": 4000, "wavelength_max_angstrom": 7000,
        "available_arrays": json.dumps(["flux_lambda_cgs", "normalized_flux_candidate"]),
    }
    with (bosz_root / "models.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)

    phoenix_root = tmp_path / "phoenix"
    phoenix_root.mkdir()
    app.config["CMFGEN_VIEWER"]["phoenix_root"] = str(phoenix_root)
    np.savez_compressed(phoenix_root / "test.npz", wavelength_angstrom=wave, flux_lambda_cgs=model_flux)
    row.update(grid="phoenix", model_name="lte06000_test", atmosphere_family="phoenix_aces",
               resolving_power=10000, vturb_km_s="", derived_vturb_km_s=1.73, interpolated="true",
               fit_eligible="true", wavelength_convention="vacuum",
               available_arrays=json.dumps(["flux_lambda_cgs"]))
    with (phoenix_root / "models.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)

    @app.route("/test-plotly.js")
    def local_plotly():
        return app.response_class(
            plotly.get_plotlyjs(), mimetype="application/javascript"
        )

    @app.after_request
    def local_assets(response):
        # Exercise real Plotly without requiring CDN access. Bootstrap/Font
        # Awesome cosmetics are omitted; application CSS and JS remain intact.
        if response.mimetype == "text/html":
            html = response.get_data(as_text=True).replace(
                "https://cdn.plot.ly/plotly-2.35.2.min.js", "/test-plotly.js"
            )
            html = re.sub(r'<link[^>]+href="https://[^>]+>', "", html)
            html = re.sub(r'<script src="https://[^>]+></script>', "", html)
            response.set_data(html)
        return response

    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [
                node,
                str(Path(__file__).with_name("browser_smoke.mjs")),
                f"http://127.0.0.1:{server.server_port}",
                str(manifest["token"]),
                chromium,
            ],
            text=True,
            capture_output=True,
            timeout=90,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
