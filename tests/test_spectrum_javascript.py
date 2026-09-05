"""Numerical checks across the browser preview and Python fitting code."""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from cmfgen_viewer.spectrum_transforms import (
    _gaussian_broaden_by_velocity,
    _reddening_scale,
    apply_spectrum_transform,
)

NODE = shutil.which("node")
MODULE = (
    Path(__file__).resolve().parents[1] / "cmfgen_viewer/static/spectrum_transforms.js"
)
pytestmark = pytest.mark.skipif(
    NODE is None, reason="Node.js is required for browser numerical checks"
)


def browser_calculate(operation, **values):
    script = """
const api = require(process.argv[1]);
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const output = input.operation === 'transform'
    ? api.transformSeries(input.x, input.y, input.options)
    : input.operation === 'reddening'
    ? input.x.map(x => api.reddeningScaleAt(x, input.ebv))
    : api.gaussianBroadenByVelocity(input.x, input.y, input.sigma);
process.stdout.write(JSON.stringify(output));
"""
    result = subprocess.run(
        [NODE, "-e", script, str(MODULE)],
        input=json.dumps({"operation": operation, **values}),
        text=True,
        capture_output=True,
        check=True,
    )
    return np.asarray(json.loads(result.stdout))


@pytest.mark.parametrize("ebv", [0.0, 0.2, -0.1, 1.5])
def test_browser_reddening_matches_fitting(ebv):
    wavelength = np.array(
        [900, 1500, 2600, 2700, 4000, 5500, 12000, 240000], dtype=float
    )
    actual = browser_calculate("reddening", x=wavelength.tolist(), ebv=ebv)
    np.testing.assert_allclose(actual, _reddening_scale(wavelength, ebv), rtol=1e-12)


@pytest.mark.parametrize("descending", [False, True])
@pytest.mark.parametrize("sigma", [0, 60, 200])
def test_browser_line_broadening_matches_fitting(descending, sigma):
    wavelength = np.exp(np.linspace(np.log(4900), np.log(5100), 1001))
    flux = 1 - 0.5 * np.exp(-0.5 * ((wavelength - 5000) / 0.8) ** 2)
    if descending:
        wavelength, flux = wavelength[::-1], flux[::-1]
    actual = browser_calculate(
        "broadening", x=wavelength.tolist(), y=flux.tolist(), sigma=sigma
    )
    expected = _gaussian_broaden_by_velocity(wavelength, flux, sigma)
    # The preview and scipy truncate Gaussian kernels at slightly different
    # pixel boundaries; this bound protects line shapes without changing them.
    np.testing.assert_allclose(actual, expected, rtol=3e-5, atol=1e-8)


@pytest.mark.parametrize("mode", ["both", "normalized"])
def test_browser_combined_transform_matches_fitting(mode):
    wavelength = np.exp(np.linspace(np.log(4900), np.log(5100), 1001))
    flux = 1 - 0.5 * np.exp(-0.5 * ((wavelength - 5000) / 0.8) ** 2)
    options = dict(mode=mode, redshift=0.01, distance_kpc=2.0, ebv=0.2, broadening_km_s=60.0, normalization=1.5)
    actual = browser_calculate("transform", x=wavelength.tolist(), y=flux.tolist(), options=options)
    expected = apply_spectrum_transform(wavelength.tolist(), flux.tolist(), **options)
    np.testing.assert_allclose(actual[0], expected[0], rtol=1e-12)
    np.testing.assert_allclose(actual[1][30:-30], expected[1][30:-30], rtol=3e-5, atol=1e-8)
    # At the array edges the existing preview renormalizes the truncated
    # kernel, whereas scipy uses nearest-value padding. Preserve that behavior
    # while bounding the small difference on the reddened continuum slope.
    np.testing.assert_allclose(actual[1], expected[1], rtol=1e-4, atol=1e-8)
