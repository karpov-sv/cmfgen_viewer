from cmfgen_viewer.model_metadata import read_model
from cmfgen_viewer.parsers.mod_sum import parse_mod_sum, read_mod_sum


def test_model_metadata_and_preview_share_structured_mod_sum(tmp_path):
    (tmp_path / "VADAT").write_text("T [DO_CL]\n1.15D+4 [LSTAR]\n", encoding="utf-8")
    path = tmp_path / "MOD_SUM"
    path.write_text(
        "Model Started on: example\nND[2] NC[1]\nHI[30/20]\n\n"
        "L*=1.15D+4 Mdot=2.0-8\n"
        "Tau=20.0 T*(K)=26000 Log g=3.72\n"
        "Tau=6.667E-1 R /Rsun=5.7 Teff(K)=25000 Log g=3.70\n\n"
        "SPECIES Rel # Fraction Mass Fraction Z/Z(sun) Z(sun)\n"
        "HYD 1.0 0.7 1.0 0.7\nPHOS ********* ********* ********* 6.12E-6\n"
        "IRON 3.54-5 1.385-3 1.02 1.36-3\n\n"
        "Running clumped model: EXPO\nCL_P_1=0.1 CL_P_2=20\n"
        "Maximum correcion (%) on last iteration: 8.979E+0\n",
        encoding="utf-8",
    )
    structured = read_mod_sum(path)
    model = read_model(tmp_path)
    assert model["params"] == structured.parameters
    assert model["species"] == structured.species
    assert model["params"]["R_/Rsun"] == 5.7
    assert model["params"]["Log_g"] == 3.7
    assert model["params"]["CL_P_1"] == 0.1
    assert model["maxcorr"] == 8.979
    assert model["ions"] == ["HI"]
    preview = parse_mod_sum(path)
    abundances = next(table["rows"] for table in preview["tables"] if table["title"] == "Abundance table")
    assert [row[0] for row in abundances] == ["HYD", "PHOS", "IRON"]
    assert abundances[1][1] == "*********"
    assert preview["warnings"]
