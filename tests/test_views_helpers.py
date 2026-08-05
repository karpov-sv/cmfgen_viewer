from __future__ import annotations

from pathlib import Path

from flask import Flask

from cmfgen_viewer import documentation, views


def test_markdown_and_basic_normalizers() -> None:
    source = "Heading\n1) first\n2) second\n"
    normalized = documentation.normalize_markdown_lists(source)
    assert "1. first" in normalized
    assert "\n\n1. first" in normalized

    assert views._normalize_spectrum_mode("normalized") == "normalized"
    assert views._normalize_spectrum_mode("bad") == "both"
    assert views._normalize_grid_fit_source("TLUSTY") == "tlusty"
    assert views._grid_fit_source_label("tlusty") == "TLUSTY Grid"
    assert views._grid_fit_source_label("other") == "Cached CMFGEN Models"


def test_collection_and_summary_parsing_helpers() -> None:
    token_a = "Token_0001"
    token_b = "Token_0002"
    tokens = views._collect_obs_tokens([f"{token_a},bad,{token_b}", token_a])
    assert tokens == [token_a, token_b]

    rel_paths = views._collect_rel_paths(["/a/b/", "a/b", "x/y"])
    assert rel_paths == ["a/b", "x/y"]

    assert views._parse_summary_float("3.2D+01") == 32.0
    assert views._parse_summary_float("3.2-02") == 0.032
    assert views._parse_summary_float("x") is None
    assert views._format_summary_value("1.0e5") == "1.0000e+05"


def test_transform_fit_and_wavelength_helpers() -> None:
    params = views._normalize_transform_params(
        {
            "z": "0.001",
            "sigma": "15",
            "ebv": "0.2",
            "distance": "2.5",
        }
    )
    assert params["redshift"] == 0.001
    assert params["broadening_km_s"] == 15.0
    assert params["ebv"] == 0.2
    assert params["distance_kpc"] == 2.5

    bounds = views._normalize_fit_bounds(
        {
            "fit_redshift_min": "0.01",
            "fit_redshift_max": "-0.01",
            "fit_distance_kpc_min": "0",
            "fit_distance_kpc_max": "2",
        },
        mode="both",
    )
    assert bounds["redshift"] == (-0.01, 0.01)
    assert bounds["distance_kpc"][0] > 0.0

    tlusty_bounds = views._normalize_fit_bounds(
        {
            "fit_redshift_min": "0.01",
            "fit_redshift_max": "-0.01",
            "fit_distance_kpc_min": "0.1",
            "fit_distance_kpc_max": "2",
        },
        mode="both",
        fit_source="tlusty",
    )
    assert tlusty_bounds["redshift"] == (-0.01, 0.01)
    assert "distance_kpc" not in tlusty_bounds

    fit_range, error = views._normalize_fit_wavelength_range(
        {"fit_lambda_min": "1200", "fit_lambda_max": "5000"},
        configured_min=1000,
        configured_max=10000,
    )
    assert error is None
    assert fit_range == (1200.0, 5000.0)

    fit_range_none, error_text = views._normalize_fit_wavelength_range(
        {"fit_lambda_min": "bad"},
        configured_min=1000,
        configured_max=10000,
    )
    assert fit_range_none is None
    assert error_text == "Fit wavelength minimum must be a positive number."

    assert views._format_query_float(float("inf")) == "0"

    query: list[tuple[str, str]] = []
    views._append_transform_query(query, None)
    assert query == []

    query = []
    views._append_transform_query(query, {"redshift": 0.01})
    assert ("redshift", "0.01") in query


def test_view_url_helpers_and_selection_resolution(tmp_path: Path) -> None:
    app = Flask(__name__)
    app.secret_key = "x"
    app.register_blueprint(views.bp)

    with app.test_request_context("/"):
        spectrum_url = views._spectrum_url(
            "models/model_a",
            fin="obs_fin",
            mode="both",
            obs_tokens=["Token_0001", "invalid token"],
            transform_params={"redshift": 0.1},
            fit_wavelength_inputs={"min": "1200", "max": "5000"},
            upload_error="e",
            fit_notice="n",
        )
        assert "fin=obs_fin" in spectrum_url
        assert "obs=Token_0001" in spectrum_url
        assert "invalid+token" not in spectrum_url
        assert "fit_lambda_min=1200" in spectrum_url

        bulk_url = views._bulk_spectra_url(
            "models",
            selected_models=["models/model_a", "models/model_b"],
            mode="normalized",
            obs_tokens=["Token_0001"],
        )
        assert "selected_models=models%2Fmodel_a" in bulk_url
        assert "mode=normalized" in bulk_url

    current_dir = tmp_path / "models"
    current_dir.mkdir()
    inside = current_dir / "model_a"
    inside.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    valid, skipped = views._resolve_selected_model_dirs(
        str(tmp_path),
        current_dir,
        ["models/model_a", "outside", "missing"],
    )
    assert len(valid) == 1 and valid[0][0] == "models/model_a"
    reasons = {item[1] for item in skipped}
    assert "Outside current folder" in reasons
    assert "Not found" in reasons


def test_spectrum_lambda_bounds_and_summary_row() -> None:
    assert views._spectrum_lambda_bounds({"lambda_min_angstrom": "900", "lambda_max_angstrom": "700"}) == (700.0, 900.0)

    model = {
        "name": "model_x",
        "params": {"T*(K)": 35000, "R_/Rsun": 12.3, "Log_g": 3.2},
        "vadat": {"LSTAR": "1.0E+05", "MDOT": "1.0D-6", "CL_P_1": "0.1"},
    }
    row = views._build_summary_row(model, mod_sum_mtime=1_700_000_000.0)
    assert row[0] == "model_x"
    assert row[1] == "1.0000e+05"
    assert row[-1] == "2023-11-14 22:13:20"


def test_tlusty_confidence_uses_strict_delta_chi2_for_well_fit_weighted_photometry() -> None:
    best_model = {
        "chi2": 17.0,
        "points": 21,
        "dof": 17,
        "dof_eff": 17,
        "dof_eff_method": "nominal_photometry",
        "chi2_weighting": "photometry_flux_err_weighted",
        "photometry_error_weighting": "flux_err_or_2pct_fallback",
        "tlusty_params": {
            "teff_k": 24000,
            "log_g": 2.5,
            "z_over_zsun": 0.0,
            "vturb_km_s": 2,
        },
    }
    profiles = views._empty_tlusty_confidence_profiles()
    teff_profile = profiles.get("teff_k")
    assert isinstance(teff_profile, dict)
    teff_profile[23000] = {"chi2": 19.5, "points": 21}
    teff_profile[24000] = {"chi2": 17.0, "points": 21}
    teff_profile[25000] = {"chi2": 17.7, "points": 21}

    summary = views._summarize_tlusty_confidence_profiles(
        best_model=best_model,
        profiles=profiles,
        mode="both",
    )
    assert summary["method"] == "profile_delta_chi2_known_variance"
    chi2_info = summary["chi2"]
    assert chi2_info["sigma2_hat"] == 1.0
    assert chi2_info["sigma2_hat_nominal"] == 1.0
    teff_ranges = summary["parameters"]["teff_k"]["intervals"]
    assert teff_ranges["68%"]["min_value"] == 24000
    assert teff_ranges["68%"]["max_value"] == 25000


def test_tlusty_confidence_uses_profile_jitter_for_misspecified_weighted_photometry() -> None:
    best_model = {
        "chi2": 1142.0,
        "points": 21,
        "dof": 17,
        "dof_eff": 17,
        "dof_eff_method": "nominal_photometry",
        "chi2_weighting": "photometry_flux_err_weighted",
        "photometry_error_weighting": "flux_err_or_2pct_fallback",
        "tlusty_params": {
            "teff_k": 24000,
            "log_g": 2.5,
            "z_over_zsun": 0.0,
            "vturb_km_s": 2,
        },
    }
    profiles = views._empty_tlusty_confidence_profiles()
    teff_profile = profiles.get("teff_k")
    assert isinstance(teff_profile, dict)
    teff_profile[23000] = {"chi2": 1200.0, "points": 21}
    teff_profile[24000] = {"chi2": 1142.0, "points": 21}
    teff_profile[25000] = {"chi2": 1150.0, "points": 21}

    summary = views._summarize_tlusty_confidence_profiles(
        best_model=best_model,
        profiles=profiles,
        mode="both",
    )
    assert summary["method"] == "profile_delta_chi2_profile_jitter"
    teff_ranges = summary["parameters"]["teff_k"]["intervals"]
    assert teff_ranges["68%"]["min_value"] == 23000
    assert teff_ranges["68%"]["max_value"] == 25000
