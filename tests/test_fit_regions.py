import numpy as np
import pytest

from cmfgen_viewer.fit_regions import (
    fit_region_mask, format_fit_regions, parse_fit_regions, validate_fit_region_samples,
)
from cmfgen_viewer.spectrum_fitting import fit_model_to_observed


@pytest.mark.parametrize("text", ["line, 1", "nan, 4", "2, inf", "4, 2", "0, 5", "a, b, c"])
def test_invalid_regions_are_rejected(text):
    with pytest.raises(ValueError):
        parse_fit_regions(text)


def test_region_union_exclusions_and_roundtrip():
    regions = parse_fit_regions("first, 1, 4\nsecond, 7, 10", "core, 3, 8")
    assert fit_region_mask(np.arange(1, 11), regions).tolist() == [
        True, True, False, False, False, False, False, False, True, True,
    ]
    assert parse_fit_regions(
        format_fit_regions(regions, "windows"), format_fit_regions(regions, "exclusions"),
    ) == regions
    assert fit_region_mask([1, 2, 3], parse_fit_regions("", "2, 3")).tolist() == [True, False, False]
    with pytest.raises(ValueError, match="overlap"):
        parse_fit_regions("a, 1, 4\nb, 4, 7")
    with pytest.raises(ValueError, match="at least two"):
        validate_fit_region_samples(np.arange(1, 101), parse_fit_regions("1, 50\n200, 220"))


def fit(wave, model, observed, model_wave=None):
    observed = {
        key: value.tolist() if isinstance(value, np.ndarray) else value
        for key, value in observed.items()
    }
    return fit_model_to_observed(
        {}, {}, observed, mode="normalized",
        bounds_override={"redshift": (0, 0), "broadening_km_s": (0, 0)},
        prepared_model=(wave if model_wave is None else model_wave, model),
    )


def test_diagnostics_change_ranking_and_ignore_excluded_contamination():
    wave = np.linspace(4400, 4600, 2001)
    flux = 1 - 0.3 * np.exp(-((wave - 4471) / 2) ** 2) - 0.2 * np.exp(-((wave - 4542) / 2) ** 2)
    regions = parse_fit_regions("He I, 4460, 4480\nHe II, 4530, 4550", "core, 4470, 4472")
    selected = fit_region_mask(wave, regions)
    contaminated = flux.copy()
    contaminated[(wave >= 4470) & (wave <= 4472)] += 10
    observed = {"wavelength": wave, "flux": contaminated, "flux_err": np.full(wave.size, .02),
                "flux_mode": "normalized", "observation_type": "spectrum"}
    good_lines = flux.copy()
    good_lines[~selected] += 0.5
    wrong_lines = contaminated.copy()
    wrong_lines[selected] += .04
    full_good = fit(wave, good_lines, observed)[1]
    full_wrong = fit(wave, wrong_lines, observed)[1]
    assert full_wrong["rmse"] < full_good["rmse"]
    observed["fit_regions"] = regions
    _, metrics, error = fit(wave, good_lines, observed)
    assert error is None
    assert metrics["rmse"] < 1e-10
    assert fit(wave, wrong_lines, observed)[1]["rmse"] > 1
    assert metrics["points"] == np.count_nonzero(selected)
    assert sum(row["points"] for row in metrics["window_scores"]) == metrics["points"]
    assert sum(row["chi2"] for row in metrics["window_scores"]) == pytest.approx(metrics["chi2"])
    assert metrics["dof_eff_method"] == "autocorr_within_selected_segments"
    assert metrics["fit_regions"] == regions


def test_missing_model_coverage_and_empty_selections_fail():
    wave = np.linspace(4400, 4600, 2001)
    observed = {"wavelength": wave, "flux": np.ones(wave.size), "flux_mode": "normalized",
                "fit_regions": parse_fit_regions("first, 4410, 4440\nsecond, 4550, 4590")}
    _, _, error = fit(wave, np.ones(1001), observed, model_wave=wave[:1001])
    assert "every selected" in error
    observed["fit_regions"] = parse_fit_regions("6000, 6100")
    assert "at least 30" in fit(wave, np.ones(wave.size), observed)[2]
    observed["observation_type"] = "photometry"
    assert "only supported for spectra" in fit(wave, np.ones(wave.size), observed)[2]


def test_exclusion_only_fit_starts_with_complete_coverage():
    wave = np.linspace(4400, 4600, 2001)
    flux = 1 - .3 * np.exp(-((wave - 4471) / 2) ** 2)
    observed = {"wavelength": wave.tolist(), "flux": flux.tolist(), "flux_mode": "normalized",
                "fit_regions": parse_fit_regions("", "4500, 4510")}
    # Default redshift initialization is nonzero; identical model/observed
    # endpoints permit only zero shift when complete coverage is required.
    params, metrics, error = fit_model_to_observed(
        {}, {}, observed, mode="normalized", prepared_model=(wave, flux),
    )
    assert error is None
    assert params["redshift"] == 0
    assert metrics["rmse"] < 1e-8
    assert metrics["window_scores"][0]["label"] == "Selected spectrum"
