from __future__ import annotations

import os
from pathlib import Path

import pytest

from cmfgen_viewer.model_preflight import inspect_model_preflight


def _write_valid_model(root: Path) -> Path:
    model = root / "model_a"
    model.mkdir()
    (model / "batch.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (model / "batch.sh").chmod(0o755)
    (model / "VADAT").write_text(
        "1.0 [RSTAR]\n"
        "2.0 [RMAX]\n"
        "3.0 [VINF]\n"
        "1.0E+05 [LSTAR]\n"
        "20.0 [MASS]\n"
        "3.0 [TEFF]\n"
        "RVSIG_COL [VEL_OPT]\n"
        "T [DO_CL]\n"
        "2 [N_CL_PAR]\n"
        "0.1 [CL_PAR_1]\n"
        "100.0 [CL_PAR_2]\n",
        encoding="utf-8",
    )
    (model / "MODEL_SPEC").write_text(
        "2 [ND]\n1 [NC]\n3 [NP]\n",
        encoding="utf-8",
    )
    (model / "IN_ITS").write_text(
        "10 [NUM_ITS]\nT [DO_LAM_AUTO]\n",
        encoding="utf-8",
    )
    (model / "GAMMAS_IN").write_text("gamma input\n", encoding="utf-8")
    (model / "RVSIG_COL").write_text(
        "2 ! Number of depth points\n"
        "2.0 3.0 4.0 5.0 1\n"
        "1.0 2.0 3.0 4.0 2\n",
        encoding="utf-8",
    )
    return model


def _codes(report: dict[str, object]) -> set[str]:
    return {str(issue["code"]) for issue in report["issues"]}


def test_valid_model_passes_preflight(tmp_path: Path) -> None:
    model = _write_valid_model(tmp_path)

    report = inspect_model_preflight(model)

    assert report["passed"] is True
    assert report["blocking"] is False
    assert report["counts"] == {"error": 0, "warning": 0, "info": 0}


@pytest.mark.parametrize('key,warn', [('INCL_DSLDT', True), ('incl_dsldt', True), ('INCL_dSLdT', False),
                                    ('MAX_DT', True), ('MAX_dT', False)])
def test_superlevel_temperature_key_requires_native_case(tmp_path, key, warn):
    model = _write_valid_model(tmp_path)
    with (model/'VADAT').open('a') as stream:
        stream.write(f'T [{key}]\n')
    report = inspect_model_preflight(model)
    assert report['blocking'] is False
    issues = [i for i in report['issues'] if i['code'] == 'native-control-key-case']
    assert bool(issues) is warn
    if warn:
        assert issues[0]['file'] == 'VADAT'
        assert ('[MAX_dT]' if key == 'MAX_DT' else '[INCL_dSLdT]') in issues[0]['message']


@pytest.mark.parametrize("table,valid", [
    pytest.param(None, False, id="missing"),
    pytest.param("", False, id="empty"),
    pytest.param("invalid", False, id="malformed"),
    pytest.param("2 !Number of temperatures\n1 !Number of densities\n1 2 3 4 5 6 7 8\n", False, id="incomplete"),
    pytest.param("1 !Number of temperatures\n1 !Number of densities\nNaN 2 3 4 5 6 7 8\n", False, id="nonfinite"),
    pytest.param("1 !Number of temperatures\n1 !Number of densities\n1 2 3 4 -5 6 7 8\n", False, id="negative"),
    pytest.param("1 !Number of temperatures\n1 !Number of densities\n1 2 3 4 5 6 7 8\n", True, id="valid"),
])
def test_enabled_hydro_requires_valid_opacity_in_model_root(tmp_path: Path, table, valid) -> None:
    model = _write_valid_model(tmp_path)
    with (model / "VADAT").open("a") as stream:
        stream.write("T [DO_HYDRO]\n")
    (model / "HYDRO_DEFAULTS").write_text("5 [N_ITS]\n")
    # A table in an LTE workspace alone cannot satisfy the native root read.
    (model / "lte").mkdir()
    (model / "lte/ROSSELAND_LTE_TAB").write_text(
        "1 !Number of temperatures\n1 !Number of densities\n1 2 3 4 5 6 7 8\n")
    if table is not None:
        (model / "ROSSELAND_LTE_TAB").write_text(table)

    report = inspect_model_preflight(model)

    assert report["blocking"] is not valid
    if not valid:
        issue = next(item for item in report["issues"] if item["code"].endswith("hydro-opacity"))
        assert issue["code"] == ("missing-hydro-opacity" if table is None else "invalid-hydro-opacity")
        assert issue["file"] == "ROSSELAND_LTE_TAB"


@pytest.mark.parametrize("hydro,remaining", [("F", "5"), ("T", "0")])
def test_inactive_hydro_does_not_require_opacity(tmp_path: Path, hydro, remaining) -> None:
    model = _write_valid_model(tmp_path)
    with (model / "VADAT").open("a") as stream:
        stream.write(f"{hydro} [DO_HYDRO]\n")
    (model / "HYDRO_DEFAULTS").write_text(f"{remaining} [N_ITS]\n")

    assert inspect_model_preflight(model)["passed"]


def test_grid_controls_and_booleans_are_validated_without_requiring_np_equality(
    tmp_path: Path,
) -> None:
    model = _write_valid_model(tmp_path)
    (model / "MODEL_SPEC").write_text("2 [ND]\n1 [NC]\n4 [NP]\n", encoding="utf-8")

    extra_ray_report = inspect_model_preflight(model)

    assert extra_ray_report["blocking"] is False
    assert _codes(extra_ray_report) == {"additional-impact-rays"}

    (model / "MODEL_SPEC").write_text("2 [ND]\n1 [NC]\n2 [NP]\n", encoding="utf-8")
    (model / "IN_ITS").write_text(
        "0 [NUM_ITS]\nMAYBE [DO_LAM_AUTO]\n",
        encoding="utf-8",
    )

    invalid_report = inspect_model_preflight(model)

    assert invalid_report["blocking"] is True
    assert {
        "impact-grid-too-small",
        "integer-out-of-range",
        "invalid-boolean",
    }.issubset(_codes(invalid_report))


def test_selected_rvsig_grid_must_match_model_spec_and_rows(tmp_path: Path) -> None:
    model = _write_valid_model(tmp_path)
    (model / "RVSIG_COL").write_text(
        "3 ! Number of depth points\n"
        "2.0 3.0 4.0 5.0 1\n"
        "1.0 2.0 3.0 4.0 3\n",
        encoding="utf-8",
    )

    report = inspect_model_preflight(model)

    assert report["blocking"] is True
    assert {"structure-grid-mismatch", "structure-row-count"}.issubset(_codes(report))


def test_selected_rvsig_radius_ratio_must_match_vadat(tmp_path: Path) -> None:
    model = _write_valid_model(tmp_path)
    contents = (model / "VADAT").read_text(encoding="utf-8")
    (model / "VADAT").write_text(contents.replace("2.0 [RMAX]", "10.0 [RMAX]"), encoding="utf-8")

    report = inspect_model_preflight(model)

    assert report["blocking"] is True
    assert "structure-radius-ratio-mismatch" in _codes(report)


def test_selected_rvsig_outer_velocity_must_match_vinf(tmp_path: Path) -> None:
    model = _write_valid_model(tmp_path)
    contents = (model / "VADAT").read_text(encoding="utf-8")
    (model / "VADAT").write_text(contents.replace("3.0 [VINF]", "1000.0 [VINF]"), encoding="utf-8")

    report = inspect_model_preflight(model)

    assert report["blocking"] is True
    assert "structure-terminal-velocity-mismatch" in _codes(report)


def test_spectrum_control_ranges_are_checked_and_file_is_editable(tmp_path: Path) -> None:
    model = _write_valid_model(tmp_path)
    obs = model / "obs"
    obs.mkdir()
    (obs / "CMF_FLUX_PARAM_INIT").write_text(
        "30.0 [VTURB_FIX]\n"
        "50.0 [VTURB_MIN]\n"
        "20.0 [VTURB_MAX]\n"
        "5000.0 [F_LAM_BEG]\n"
        "1000.0 [F_LAM_END]\n"
        "0.8 [OBS_EXT_RAT]\n",
        encoding="utf-8",
    )

    report = inspect_model_preflight(model)

    assert report["blocking"] is True
    assert {"turbulence-order", "wavelength-order", "small-observer-extent"}.issubset(
        _codes(report)
    )
    spectrum_issues = [
        issue
        for issue in report["issues"]
        if issue["file"] == "obs/CMF_FLUX_PARAM_INIT"
    ]
    assert spectrum_issues
    assert all(issue["editable"] is True for issue in spectrum_issues)


def test_only_newer_fresh_unpromoted_lte_results_block_preflight(tmp_path: Path) -> None:
    model = _write_valid_model(tmp_path)
    lte = model / "lte"
    lte.mkdir()
    for name in ("VADAT", "MODEL_SPEC", "GRID_PARAMS"):
        (lte / name).write_text("input\n", encoding="utf-8")
    generated = lte / "ROSSELAND_LTE_TAB"
    generated.write_text("new opacity\n", encoding="utf-8")
    promoted = model / "ROSSELAND_LTE_TAB"
    promoted.write_text("old opacity\n", encoding="utf-8")
    input_time = max((lte / name).stat().st_mtime_ns for name in ("VADAT", "MODEL_SPEC", "GRID_PARAMS"))
    os.utime(generated, ns=(input_time + 2_000_000, input_time + 2_000_000))
    os.utime(promoted, ns=(input_time + 1_000_000, input_time + 1_000_000))

    unpromoted = inspect_model_preflight(model)

    assert "unpromoted-lte-result" in _codes(unpromoted)
    assert unpromoted["blocking"] is True

    promoted.write_text("locally newer opacity\n", encoding="utf-8")
    os.utime(promoted, ns=(input_time + 3_000_000, input_time + 3_000_000))

    newer_root = inspect_model_preflight(model)

    assert "unpromoted-lte-result" not in _codes(newer_root)


def test_terminal_batch_permission_is_advisory(tmp_path: Path) -> None:
    model = _write_valid_model(tmp_path)
    (model / "batch.sh").chmod(0o644)

    report = inspect_model_preflight(model)

    assert report["blocking"] is False
    assert "script-not-executable" in _codes(report)


def test_advisory_warning_does_not_block_external_run(tmp_path: Path) -> None:
    model = _write_valid_model(tmp_path)
    (model / "batch.sh").write_text("#!/bin/sh\ncd obs\n", encoding="utf-8")

    report = inspect_model_preflight(model)

    assert report["blocking"] is False
    assert report["counts"]["warning"] == 1
    assert _codes(report) == {"missing-spectrum-controls"}


def _profile_model(tmp_path, *, radii=(4.,2.,1.), velocities=(16.,4.,1.),
                   sigmas=(1.,1.,1.), indexed=True, extras=()):
    model=_write_valid_model(tmp_path)
    vadat=(model/'VADAT').read_text().replace('2.0 [RMAX]',f'{radii[0]/radii[-1]} [RMAX]').replace(
        '3.0 [VINF]',f'{velocities[0]} [VINF]')
    (model/'VADAT').write_text(vadat)
    (model/'MODEL_SPEC').write_text(f'{len(radii)} [ND]\n1 [NC]\n{len(radii)+1} [NP]\n')
    rows=[]
    for i,(r,v,s) in enumerate(zip(radii,velocities,sigmas),1):
        row=' '.join(f'{n:.9e}' for n in (r,v,s,*extras))
        rows.append(row+(f' {i}' if indexed else ''))
    (model/'RVSIG_COL').write_text(f'{len(rows)} !Number of depth points\n'+'\n'.join(rows)+'\n')
    return model


@pytest.mark.parametrize('column', [0,1,2,3,4])
@pytest.mark.parametrize('token', ['NaN','Inf','-Infinity','1e999'])
def test_rvsig_nonfinite_values_block_without_derived_arithmetic(tmp_path,column,token):
    model=_profile_model(tmp_path,extras=(1e-10,1.0))
    path=model/'RVSIG_COL'
    lines=path.read_text().splitlines()
    fields=lines[2].split();fields[column]=token;lines[2]=' '.join(fields)
    path.write_text('\n'.join(lines)+'\n')
    report=inspect_model_preflight(model)
    assert report['blocking']
    assert 'structure-nonfinite-data' in _codes(report)
    assert 'structure-sigma-gradient-mismatch' not in _codes(report)
    issue=next(x for x in report['issues'] if x['code']=='structure-nonfinite-data')
    assert issue['file']=='RVSIG_COL' and issue['line']==3


@pytest.mark.parametrize('column,bad,code', [
    (0,'0','structure-nonpositive-radius'), (0,'-1','structure-nonpositive-radius'),
    (1,'0','structure-nonpositive-velocity'), (1,'-1','structure-nonpositive-velocity'),
])
def test_rvsig_nonpositive_profile_values_block(tmp_path,column,bad,code):
    model=_profile_model(tmp_path)
    path=model/'RVSIG_COL';lines=path.read_text().splitlines()
    fields=lines[2].split();fields[column]=bad;lines[2]=' '.join(fields)
    path.write_text('\n'.join(lines)+'\n')
    report=inspect_model_preflight(model)
    assert report['blocking'] and code in _codes(report)


@pytest.mark.parametrize('middle', [4.,5.])
def test_rvsig_repeated_or_reversed_radii_block(tmp_path,middle):
    model=_profile_model(tmp_path,radii=(4.,middle,1.))
    report=inspect_model_preflight(model)
    assert report['blocking'] and 'structure-radius-order' in _codes(report)
    assert 'structure-sigma-gradient-mismatch' not in _codes(report)


def test_rvsig_malformed_body_reports_the_actual_line(tmp_path):
    model=_profile_model(tmp_path)
    path=model/'RVSIG_COL';path.write_text(path.read_text().replace('4.000000000e+00 1.000000000e+00 2','broken 1.0 2'))
    report=inspect_model_preflight(model)
    assert report['blocking']
    assert 'structure-invalid-row' in _codes(report)


@pytest.mark.parametrize('extras', [(0.,1.),(1.,-1.)])
def test_rvsig_density_and_clumping_must_be_positive(tmp_path,extras):
    report=inspect_model_preflight(_profile_model(tmp_path,extras=extras))
    assert report['blocking'] and 'structure-invalid-density' in _codes(report)


def test_rvsig_decelerating_flow_is_advisory_not_blocking(tmp_path):
    report=inspect_model_preflight(_profile_model(tmp_path,velocities=(1.,2.,4.),sigmas=(-2.,-2.,-2.)))
    assert not report['blocking']
    assert {'structure-negative-gradient','structure-velocity-order'} <= _codes(report)
    assert all(x['severity']=='warning' for x in report['issues'])


def test_rvsig_sigma_minus_one_is_allowed_for_constant_velocity(tmp_path):
    report=inspect_model_preflight(_profile_model(tmp_path,velocities=(3.,3.,3.),sigmas=(-1.,-1.,-1.)))
    assert not report['blocking']
    assert 'structure-negative-gradient' not in _codes(report)
    assert 'structure-velocity-order' in _codes(report)


def test_rvsig_gross_sigma_mismatch_is_advisory(tmp_path):
    report=inspect_model_preflight(_profile_model(tmp_path,sigmas=(1.,100.,1.)))
    assert not report['blocking']
    issue=next(x for x in report['issues'] if x['code']=='structure-sigma-gradient-mismatch')
    assert issue['severity']=='warning' and issue['line']==3
    assert 'depth 2' in issue['message'] and 'Recalculate sigma' in issue['message']


@pytest.mark.parametrize('indexed',[True,False])
def test_rvsig_consistent_power_law_and_native_three_column_format(tmp_path,indexed):
    model=_profile_model(tmp_path,indexed=indexed)
    report=inspect_model_preflight(model)
    assert report['passed'] and report['counts']=={'error':0,'warning':0,'info':0}


def test_rvsig_radius_normalization_is_not_a_mismatch(tmp_path):
    model=_profile_model(tmp_path,radii=(4000.,2000.,1000.))
    assert inspect_model_preflight(model)['counts']=={'error':0,'warning':0,'info':0}


def test_rvsig_missing_e_notation_remains_valid_for_gradient_checks(tmp_path):
    model=_profile_model(tmp_path)
    path=model/'RVSIG_COL';path.write_text(path.read_text().replace('e+','+'))
    assert inspect_model_preflight(model)['counts']=={'error':0,'warning':0,'info':0}


def test_rvsig_gradient_screen_skips_unresolved_print_precision(tmp_path):
    model=_profile_model(tmp_path,velocities=(1.0001,1.0,0.9999),sigmas=(1.,100.,1.))
    path=model/'RVSIG_COL';lines=path.read_text().splitlines()
    for i in range(1,len(lines)):
        fields=lines[i].split();fields[1]=f'{float(fields[1]):.4f}';lines[i]=' '.join(fields)
    path.write_text('\n'.join(lines)+'\n')
    report=inspect_model_preflight(model)
    assert 'structure-sigma-gradient-mismatch' not in _codes(report)


def test_rvsig_gradient_screen_skips_sharply_curved_profiles(tmp_path):
    report=inspect_model_preflight(_profile_model(tmp_path,velocities=(256.,4.,1.),sigmas=(5.,100.,1.)))
    assert not report['blocking'] and 'structure-sigma-gradient-mismatch' not in _codes(report)


def test_rvsig_accepts_native_revision_header_with_trailing_backtick(tmp_path):
    model=_profile_model(tmp_path)
    path=model/'RVSIG_COL'
    path.write_text(path.read_text().replace('!Number of depth points','!Number of depth points`'))
    report=inspect_model_preflight(model)
    assert report['counts']=={'error':0,'warning':0,'info':0}
