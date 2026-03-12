from __future__ import annotations

from pathlib import Path

from cmfgen_viewer import final_spectrum as fs


def test_discover_final_spectrum_files_finds_and_sorts_fin_files(tmp_path: Path) -> None:
    obs_dir = tmp_path / "obs"
    obs_dir.mkdir()
    (obs_dir / "obs_cont").write_text("x", encoding="utf-8")
    (obs_dir / "obs_fin10").write_text("x", encoding="utf-8")
    (obs_dir / "obs_fin2").write_text("x", encoding="utf-8")
    (obs_dir / "obs_fin_alpha").write_text("x", encoding="utf-8")

    discovered = fs.discover_final_spectrum_files(tmp_path)
    assert discovered is not None
    fin_names = [path.name for path in discovered["fin_files"]]
    assert fin_names == ["obs_fin2", "obs_fin10", "obs_fin_alpha"]


def test_obs_series_helpers_heading_trim_and_bounds() -> None:
    assert fs._series_heading("Continuum Frequencies (12)") == ("continuum_frequencies", 12)
    assert fs._series_heading("Observed intensity (Janskys)") == ("observed_intensity_janskys", None)
    assert fs._series_heading("other") == (None, None)

    x, y, trimmed = fs._trim_short_wavelength_floor([100, 200, 300, 400], [1, 1, 2, 1])
    assert trimmed == 2
    assert x == [300, 400]
    assert y == [2, 1]

    assert fs._normalize_wavelength_bounds(7000.0, 5000.0) == (5000.0, 7000.0)
    assert fs._normalize_wavelength_bounds(-1.0, 5000.0) == (None, 5000.0)


def test_load_obs_spectrum_parses_vectors_and_range_filters(tmp_path: Path) -> None:
    path = tmp_path / "obs_fin"
    path.write_text(
        """Continuum Frequencies (3)
1.0 0.5 0.0
Observed intensity (Janskys)
10.0 5.0 1.0
""",
        encoding="utf-8",
    )
    parsed = fs.load_obs_spectrum(path, lambda_min=3000.0, lambda_max=10000.0)
    assert parsed["expected_count"] == 3
    assert parsed["raw_points"] == 3
    assert parsed["skipped_points"] == 1
    assert parsed["range_skipped_points"] == 1
    assert len(parsed["wavelength"]) == 1
    assert parsed["wavelength"][0] > 5000.0


def test_numeric_helpers_interpolation_conversion_and_bounds() -> None:
    assert fs._interp_linear([1.0, 2.0, 3.0], [10.0, 20.0, 30.0], 2.5) == 25.0
    assert fs._interp_linear([1.0], [10.0], 1.0) is None

    x, y = fs._jy_to_cgs_per_angstrom([5000.0, -1.0], [1.0, 1.0])
    assert x == [5000.0]
    assert len(y) == 1 and y[0] > 0

    resolved = fs._resolve_fit_bounds(
        "both",
        {
            "redshift": (0.01, -0.01),
            "broadening_km_s": (100.0, 100.0),
            "distance_kpc": (0.5, 5.0),
            "invalid": (1.0, 2.0),
        },
    )
    assert resolved["redshift"] == (-0.01, 0.01)
    assert resolved["distance_kpc"] == (0.5, 5.0)


def test_apply_spectrum_transform_and_misc_helpers() -> None:
    transformed = fs.apply_spectrum_transform(
        [4000.0, 5000.0, 6000.0],
        [1.0, 2.0, 3.0],
        mode="normalized",
        redshift=0.1,
        broadening_km_s=0.0,
        ebv=0.0,
        distance_kpc=1.0,
    )
    assert transformed is not None
    out_x, out_y = transformed
    assert len(out_x) == 3 and len(out_y) == 3
    assert out_x[0] < 4000.0

    absolute_scaled = fs.apply_spectrum_transform(
        [4000.0, 5000.0],
        [1.0, 2.0],
        mode="both",
        redshift=0.0,
        broadening_km_s=0.0,
        ebv=0.0,
        distance_kpc=2.0,
        normalization=8.0,
    )
    assert absolute_scaled is not None
    _, absolute_scaled_y = absolute_scaled
    assert absolute_scaled_y == [2.0, 4.0]

    assert fs.apply_spectrum_transform(
        [5000.0, 6000.0],
        [1.0, 2.0],
        mode="both",
        redshift=-1.0,
        broadening_km_s=0.0,
        ebv=0.0,
        distance_kpc=1.0,
    ) is None

    assert fs.fin_file_label("obs_fin") == "obs_fin"
    assert fs.fin_file_label("obs_fin10") == "obs_fin10 (vturb=10)"
