from __future__ import annotations

from pathlib import Path

from cmfgen_viewer.parsers.extended_text import (
    parse_auto_check,
    parse_cmf_spectrum,
    parse_ewdata,
    parse_keyword_control,
    parse_species_masses,
    parse_steq_vals,
    parse_vector_diagnostic,
)


def _write(tmp_path: Path, name: str, contents: str) -> Path:
    path = tmp_path / name
    path.write_text(contents, encoding="utf-8")
    return path


def test_parse_cmf_spectrum_builds_wavelength_plot(tmp_path: Path) -> None:
    path = _write(tmp_path, "cmf.sed", "# metadata\n100 1e-12\n200 2e-12\n300 3e-12\n")
    parsed = parse_cmf_spectrum(path)
    assert parsed["parser"] == "CMF_SPECTRUM"
    assert parsed["plots"]
    assert parsed["tables"][0]["columns"] == ["Wavelength (Angstrom)", "Flux"]


def test_parse_ewdata_preserves_transition_text(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "ewdata_fin",
        """Lam(Ang) C. Flux EW(Ang) Sob Trans. Name
95.08 2.9461E-10 0.175 T OSIX(8p-2s)
96.84 1.4656E-09 0.041 T OSIX(7p-2s)
""",
    )
    parsed = parse_ewdata(path)
    assert parsed["parser"] == "EWDATA"
    assert dict(parsed["summary_table"]["rows"])["transitions"] == "2"
    assert parsed["tables"][0]["rows"][0][-1] == "T OSIX(8p-2s)"
    assert parsed["plots"]


def test_parse_keyword_control_extracts_comments(tmp_path: Path) -> None:
    path = _write(tmp_path, "GAMRAY_PARAMS", "30000 [NU_GRID_MAX] ! maximum points\n")
    parsed = parse_keyword_control(path)
    assert parsed["tables"][0]["rows"] == [["NU_GRID_MAX", "3.0000e+04", "maximum points"]]

    simple = _write(tmp_path, "GAMMA_MODEL", "30000 NU_GRID_MAX\nT NORM_GAM\n")
    simple_parsed = parse_keyword_control(simple)
    assert simple_parsed["tables"][0]["rows"] == [
        ["NU_GRID_MAX", "3.0000e+04", ""],
        ["NORM_GAM", "T", ""],
    ]


def test_parse_species_masses_builds_composition_table(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "SPECIES_MASSES",
        "Species M(Msun) MF(OB) MF(IB)\nCARB 2.286E-03 4.906E-01 1.117E-10\nOXY 9.855E-02 4.906E-01 5.058E-10\n",
    )
    parsed = parse_species_masses(path)
    assert dict(parsed["summary_table"]["rows"])["species"] == "2"
    assert parsed["tables"][0]["rows"][0][0] == "CARB"


def test_parse_vector_diagnostic_detects_labeled_blocks(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "GENCOOL",
        """Radius [1.0E+10cm]
1 2 3
Temperature [1.0E+4K]
4 5 6
""",
    )
    parsed = parse_vector_diagnostic(path, parser_name="GENCOOL")
    assert dict(parsed["summary_table"]["rows"])["vectors"] == "2"
    assert len(parsed["plots"]) == 2


def test_parse_auto_check_preserves_level_labels(tmp_path: Path) -> None:
    path = _write(tmp_path, "AUTO_CHK_C2", "1 level_a 0.0\n2 level_b 1.5E-4\n")
    parsed = parse_auto_check(path)
    assert parsed["parser"] == "AUTO_CHK_*"
    assert dict(parsed["summary_table"]["rows"])["nonzero_rates"] == "1"
    assert parsed["tables"][0]["rows"][1] == ["2", "level_b", "1.5000e-04"]


def test_parse_steq_vals_collects_indexed_chunks(tmp_path: Path) -> None:
    path = _write(tmp_path, "STEQ_VALS", "1( 1)& 1 2 3\n1( 4)& 4 5 6\n2 * 7 8 9\n")
    parsed = parse_steq_vals(path)
    assert dict(parsed["summary_table"]["rows"])["series"] == "2"
    assert parsed["plots"]
