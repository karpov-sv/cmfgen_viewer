"""Preset bounds and fit-window selection remain in uploaded coordinates."""

import shutil
import subprocess
from pathlib import Path

import pytest

from cmfgen_viewer.fit_regions import parse_fit_regions


def test_diagnostic_presets():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for preset checks")
    result = subprocess.run(
        [node, str(Path(__file__).with_name("diagnostic_presets.cjs"))],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_preset_windows_follow_backend_interval_rules():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for preset checks")
    script_root = Path(__file__).resolve().parents[1] / "cmfgen_viewer" / "static"
    program = """
const fs=require('fs'), vm=require('vm'); const window={};
const runtime=vm.createContext({window});
for (const name of ['spectral_lines.js','diagnostic_presets.js']) vm.runInContext(fs.readFileSync(process.argv[1]+'/'+name,'utf8'),runtime);
const api=window.CmfgenDiagnosticPresets;
const selection=api.plan('optical-combined',{halfWidth:3000,redshift:.001,medium:'air',coverage:[3000,9000]});
process.stdout.write(api.append('',selection).text);
"""
    result = subprocess.run([node, "-e", program, str(script_root)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    regions = parse_fit_regions(result.stdout)
    assert len(regions["windows"]) == 5
