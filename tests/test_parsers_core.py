from __future__ import annotations

from pathlib import Path

from cmfgen_viewer.parsers.mod_sum import parse_mod_sum
from cmfgen_viewer.parsers.obsflux import parse_obsflux
from cmfgen_viewer.parsers.rvtj import parse_rvtj


def _write_file(tmp_path: Path, name: str, contents: str) -> Path:
    target = tmp_path / name
    target.write_text(contents, encoding="utf-8")
    return target


def _table_by_title(parsed: dict[str, object], title: str) -> dict[str, object]:
    tables = parsed.get("tables")
    assert isinstance(tables, list)
    for table in tables:
        if isinstance(table, dict) and table.get("title") == title:
            return table
    raise AssertionError(f"Table not found: {title}")


def test_parse_rvtj_parses_vectors_and_builds_plots(tmp_path: Path) -> None:
    path = _write_file(
        tmp_path,
        "RVTJ",
        """ND: 3
NC: 1
Radius
1.0 2.0 3.0
Velocity
10 20 30
Electron density
1.0E+10 2.0E+10 3.0E+10
Temperature
4.1 4.2 4.3
Mass Density
1.0E-10 2.0E-10 3.0E-10
Clumping Factor
1 2 3
lower populations
9 9 9
""",
    )

    parsed = parse_rvtj(path)

    assert parsed["parser"] == "RVTJ"
    assert parsed["warnings"] == []

    summary_rows = dict(parsed["summary_table"]["rows"])
    assert summary_rows["ND"] == "3"
    assert summary_rows["NC"] == "1"

    vectors = _table_by_title(parsed, "Parsed vectors")
    vector_rows = vectors["rows"]
    assert ["Radius", "3", "10^10 cm"] in vector_rows
    assert ["Velocity", "3", "km/s"] in vector_rows

    plot_titles = {plot["title"] for plot in parsed["plots"]}
    assert "Velocity profile" in plot_titles
    assert "Temperature profile" in plot_titles


def test_parse_rvtj_warns_when_nd_mismatches_vector_length(tmp_path: Path) -> None:
    path = _write_file(
        tmp_path,
        "RVTJ",
        """ND: 2
Velocity
10 20 30
""",
    )

    parsed = parse_rvtj(path)
    warnings = parsed["warnings"]
    assert any("Velocity has 3 values while ND=2" in warning for warning in warnings)


def test_parse_obsflux_extracts_summary_vectors_and_plots(tmp_path: Path) -> None:
    path = _write_file(
        tmp_path,
        "OBSFLUX",
        """NCF diagnostic: 3
Continuum Frequencies (3)
1.0 0.5 0.25
Observed intensity (Janskys)
9.0 4.0 1.0
Luminosity
10 20 30
Mechanical Luminosity
1 2 3
Normalized luminosity check
0.1 0.2 0.3
Total luminosity: 4.5E+5
""",
    )

    parsed = parse_obsflux(path)

    assert parsed["parser"] == "OBSFLUX"
    assert parsed["warnings"] == []

    summary_rows = dict(parsed["summary_table"]["rows"])
    assert summary_rows["Expected NCF"] == "3"
    assert summary_rows["Parsed continuum points"] == "3"
    assert summary_rows["Parsed observed-intensity points"] == "3"
    assert "Wavelength range (Å)" in summary_rows

    vector_table = _table_by_title(parsed, "Parsed vectors")
    assert ["Continuum Frequencies", "3"] in vector_table["rows"]
    assert ["Observed intensity (Janskys)", "3"] in vector_table["rows"]

    plot_titles = {plot["title"] for plot in parsed["plots"]}
    assert "Observed spectrum" in plot_titles
    assert "Luminosity" in plot_titles
    assert "Mechanical luminosity" in plot_titles
    assert "Normalized luminosity check" in plot_titles


def test_parse_obsflux_warns_for_mismatch_and_invalid_frequency(tmp_path: Path) -> None:
    path = _write_file(
        tmp_path,
        "OBSFLUX",
        """Continuum Frequencies (4)
1.0 0.0 0.5
Observed intensity (Janskys)
2.0 3.0 4.0
""",
    )

    parsed = parse_obsflux(path)
    warnings = parsed["warnings"]

    assert any("Continuum frequencies parsed=3, expected=4" in warning for warning in warnings)
    assert any("Some spectrum points were skipped" in warning for warning in warnings)


def test_parse_mod_sum_extracts_metadata_dimensions_and_tables(tmp_path: Path) -> None:
    path = _write_file(
        tmp_path,
        "MOD_SUM",
        """Model Started on: 2026-02-01
Model Finalized on: 2026-02-02
Main program last changed on: 2025-12-31

ND[3] NC[2] NP[1]
RMAX = 1.0E+12  Mdot = 1.5E-6
Tau=1.0 Teff=35000
Tau=2.0 Teff=34000

SPECIES Rel # Fraction Mass Fraction Z/Z(sun) Z(sun)
H 1.0 0.70 1.0 0.70
HE 0.1 0.28 1.0 0.28

Running clumped model: yes
Filling factor at boundary is: 0.25
Maximum correcion (%) on last iteration: 1.5
""",
    )

    parsed = parse_mod_sum(path)

    assert parsed["parser"] == "MOD_SUM"
    assert parsed["warnings"] == []

    summary_rows = dict(parsed["summary_table"]["rows"])
    assert summary_rows["model_started_on"] == "2026-02-01"
    assert summary_rows["model_finalized_on"] == "2026-02-02"

    dimensions = _table_by_title(parsed, "Dimensions")
    dimension_rows = dict(dimensions["rows"])
    assert dimension_rows["ND"] == "3"
    assert dimension_rows["NC"] == "2"
    assert dimension_rows["NP"] == "1"

    scalar_table = _table_by_title(parsed, "Key scalars")
    scalar_rows = dict(scalar_table["rows"])
    assert scalar_rows["RMAX"] == "1.0000e+12"
    assert scalar_rows["Mdot"] == "1.5000e-06"

    tau_table = _table_by_title(parsed, "Tau diagnostics")
    assert tau_table["columns"] == ["Tau", "Teff"]
    assert tau_table["rows"] == [["1", "3.5000e+04"], ["2", "3.4000e+04"]]

    abundance = _table_by_title(parsed, "Abundance table")
    assert ["H", "1", "0.7", "1", "0.7"] in abundance["rows"]
    assert ["HE", "0.1", "0.28", "1", "0.28"] in abundance["rows"]

    clumping = _table_by_title(parsed, "Clumping")
    clumping_rows = dict(clumping["rows"])
    assert clumping_rows["model"] == "yes"
    assert clumping_rows["filling_factor_boundary"] == "0.25"
    assert clumping_rows["max_correction_percent_last_iteration"] == "1.5"
