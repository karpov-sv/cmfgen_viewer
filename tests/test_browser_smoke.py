"""Opt-in Chromium checks: CMFGEN_BROWSER_TESTS=1 python3 -m pytest -q -s tests/test_browser_smoke.py."""

import os
import re
import shutil
import subprocess
from io import BytesIO
from pathlib import Path
from threading import Thread

import pytest
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
        (model / "MOD_SUM").write_text(
            "Model Started on: example\nND[2]\nTeff(K)=35000\n", encoding="utf-8"
        )
        (model / "RVTJ").write_text(
            "ND: 2\nRadius\n1 2\nVelocity\n10 20\n", encoding="utf-8"
        )
        values = " ".join(str(1 + i / 200) for i in range(201))
        flux = " ".join(str(10 + i / 20) for i in range(201))
        contents = f"Continuum Frequencies (201)\n{values}\nObserved intensity (Janskys)\n{flux}\n"
        for path in (obs / "obs_fin", obs / "obs_cont", model / "OBSFLUX"):
            path.write_text(contents, encoding="utf-8")
    upload_root = tmp_path / "uploads"
    manifest = create_upload_bundle(
        upload_root,
        filename="observed.dat",
        stream=BytesIO(b"1500 1e-12\n2000 2e-12\n2500 3e-12\n3000 2e-12\n"),
    )
    app = create_app(
        basepath=str(tmp_path), upload_root=str(upload_root), fit_pool_size_max=1
    )
    app.config["CMFGEN_VIEWER"]["summary_cache_db"] = str(tmp_path / "summary.sqlite")

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
