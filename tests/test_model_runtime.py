from __future__ import annotations

import os
from pathlib import Path

import pytest

from cmfgen_viewer.model_runtime import find_workflow_processes, inspect_workflow_runtime


def _empty_proc(root: Path) -> Path:
    proc_root = root / "proc"
    proc_root.mkdir()
    (proc_root / "uptime").write_text("1000.0 0.0\n", encoding="ascii")
    return proc_root


def _write_fake_process(
    proc_root: Path,
    pid: int,
    *,
    cwd: Path,
    command: str,
    comm: str,
) -> None:
    process = proc_root / str(pid)
    process.mkdir()
    os.symlink(cwd, process / "cwd")
    (process / "cmdline").write_bytes(command.encode("utf-8") + b"\0")
    (process / "comm").write_text(f"{comm}\n", encoding="utf-8")
    ticks = int(os.sysconf("SC_CLK_TCK"))
    fields = ["R"] + ["0"] * 50
    fields[1] = "42"
    fields[11] = str(2 * ticks)
    fields[12] = str(ticks)
    fields[19] = str(500 * ticks)
    (process / "stat").write_text(
        f"{pid} ({comm}) " + " ".join(fields) + "\n",
        encoding="ascii",
    )
    (process / "status").write_text(
        "Name:\ttest\nState:\tR (running)\nVmRSS:\t2048 kB\nThreads:\t4\n",
        encoding="utf-8",
    )


def test_process_detection_requires_expected_name_and_exact_working_directory(
    tmp_path: Path,
) -> None:
    target = tmp_path / "model" / "lte"
    target.mkdir(parents=True)
    other = tmp_path / "other"
    other.mkdir()
    proc_root = _empty_proc(tmp_path)
    _write_fake_process(
        proc_root,
        123,
        cwd=target,
        command="/opt/cmfgen/exe/main_lte.exe",
        comm="main_lte.exe",
    )
    _write_fake_process(proc_root, 124, cwd=target, command="zsh", comm="zsh")
    _write_fake_process(
        proc_root,
        125,
        cwd=other,
        command="/opt/cmfgen/exe/main_lte.exe",
        comm="main_lte.exe",
    )

    processes = find_workflow_processes(target, "lte", proc_root=proc_root, now_epoch=2000)

    assert len(processes) == 1
    process = processes[0]
    assert process["pid"] == 123
    assert process["state"] == "running"
    assert process["elapsed"] == "00:08:20"
    assert process["cpu_time"] == "00:00:03"
    assert process["rss"] == "2.0 MB"
    assert process["threads"] == 4


def test_main_progress_reads_iterations_and_convergence_metrics(tmp_path: Path) -> None:
    proc_root = _empty_proc(tmp_path)
    model = tmp_path / "model"
    model.mkdir()
    (model / "IN_ITS").write_text("20 [NUM_ITS]\n", encoding="utf-8")
    (model / "OUTGEN").write_text(
        "Luminosity of star (d=1,ND)(iteration 11) is: 2.0100E+05 2.0000E+05\n"
        "Maximm changes as returned by SOLVEBA_V9 is 4.25E-01\n"
        "Current great iteration count is 12\n",
        encoding="utf-8",
    )

    runtime = inspect_workflow_runtime(model, "main", proc_root=proc_root)

    assert runtime["active"] is False
    progress = runtime["progress"]
    assert progress is not None
    assert progress["current"] == 12
    assert progress["maximum"] == 20
    assert progress["percent"] == 60.0
    metrics = {item["label"]: item["value"] for item in progress["metrics"]}
    assert metrics["Luminosity difference"] == "+0.5%"
    assert metrics["Latest maximum change"] == "0.425"


def test_main_progress_counts_only_iterations_in_latest_appended_run(tmp_path: Path) -> None:
    proc_root = _empty_proc(tmp_path)
    model = tmp_path / "model"
    model.mkdir()
    (model / "IN_ITS").write_text("30 [NUM_ITS]\n", encoding="utf-8")
    (model / "OUTGEN").write_text(
        "Model started on: 01-Jan-2026 10:00:00\n"
        "Current great iteration count is 34\n"
        "Luminosity of star (iteration 34) is: 2.1E+05 2.0E+05\n"
        "Maximm changes as returned by SOLVEBA_V13 is 4.0E-01\n"
        "Current great iteration count is 35\n"
        "Model started on: 02-Jan-2026 10:00:00\n"
        "Current great iteration count is 36\n",
        encoding="utf-8",
    )

    progress = inspect_workflow_runtime(model, "main", proc_root=proc_root)["progress"]

    assert progress is not None
    assert progress["current"] == 1
    assert progress["maximum"] == 30
    assert progress["percent"] == pytest.approx(3.3)
    assert progress["detail"] == "Run iteration 1 of 30 requested"
    metrics = {item["label"]: item["value"] for item in progress["metrics"]}
    assert metrics["Current run iteration"] == "1"
    assert metrics["Global great iteration"] == "36"
    assert "Luminosity difference" not in metrics
    assert "Latest maximum change" not in metrics


def test_main_run_progress_counts_markers_instead_of_skipped_global_numbers(
    tmp_path: Path,
) -> None:
    proc_root = _empty_proc(tmp_path)
    model = tmp_path / "model"
    model.mkdir()
    (model / "IN_ITS").write_text("3 [NUM_ITS]\n", encoding="utf-8")
    (model / "OUTGEN").write_text(
        "Model started on: 01-Jan-2026 10:00:00\n"
        "Current great iteration count is 1\n"
        "Current great iteration count is 2\n"
        "Current great iteration count is 4\n",
        encoding="utf-8",
    )

    progress = inspect_workflow_runtime(model, "main", proc_root=proc_root)["progress"]

    assert progress is not None
    assert progress["current"] == 3
    assert progress["percent"] == 100.0
    metrics = {item["label"]: item["value"] for item in progress["metrics"]}
    assert metrics["Global great iteration"] == "4"


def test_main_runtime_detects_cmf_flux_processes_in_obs_subdirectory(tmp_path: Path) -> None:
    model = tmp_path / "model"
    obs = model / "obs"
    obs.mkdir(parents=True)
    proc_root = _empty_proc(tmp_path)
    _write_fake_process(
        proc_root,
        123,
        cwd=obs,
        command="/opt/cmfgen/exe/cmf_flux.exe",
        comm="cmf_flux.exe",
    )
    _write_fake_process(
        proc_root,
        124,
        cwd=obs,
        command="tcsh ./batobs.sh",
        comm="tcsh",
    )

    runtime = inspect_workflow_runtime(
        model,
        "main",
        proc_root=proc_root,
        now_epoch=2000,
    )

    assert runtime["active"] is True
    assert runtime["phase"] == "flux"
    assert runtime["phase_label"] == "CMF_FLUX"
    assert {process["pid"] for process in runtime["processes"]} == {123, 124}


def test_cmf_flux_progress_tracks_script_passes_and_latest_loop(tmp_path: Path) -> None:
    model = tmp_path / "model"
    obs = model / "obs"
    obs.mkdir(parents=True)
    proc_root = _empty_proc(tmp_path)
    (obs / "bat_ins.sh").write_text(
        "$PROG_CMF_OBS < IN_FILE >>& batobs.log\n" * 3,
        encoding="utf-8",
    )
    (obs / "batobs.sh").write_text(
        "source bat_ins.sh\n$PROG_CMF_OBS < IN_FILE >>& batobs.log\n",
        encoding="utf-8",
    )
    (obs / "batobs.log").write_text(
        "PID of /opt/cmfgen/exe/cmf_flux.exe is: 456\n",
        encoding="utf-8",
    )
    (obs / "OUT_FLUX").write_text(
        "LS loop 11 is finished. Number of points along ray=100\n"
        "LS loop 12 is finished. Number of points along ray=90\n",
        encoding="utf-8",
    )
    (obs / "CMF_FLUX_PARAM").write_text("15.0D0 [VTURB_FIX]\n", encoding="utf-8")
    _write_fake_process(
        proc_root,
        123,
        cwd=obs,
        command="/opt/cmfgen/exe/cmf_flux.exe",
        comm="cmf_flux.exe",
    )

    runtime = inspect_workflow_runtime(
        model,
        "main",
        proc_root=proc_root,
        now_epoch=2000,
    )

    progress = runtime["progress"]
    assert progress is not None
    assert progress["detail"] == "CMF_FLUX pass 1 of 4 running"
    assert progress["current"] == 0
    assert progress["maximum"] == 4
    assert progress["percent"] == 0.0
    metrics = {item["label"]: item["value"] for item in progress["metrics"]}
    assert metrics == {
        "Completed passes": "0 of 4",
        "Latest LS loop": "12",
        "VTURB_FIX": "15.0D0",
    }


def test_inactive_main_runtime_retains_main_and_flux_progress(tmp_path: Path) -> None:
    model = tmp_path / "model"
    obs = model / "obs"
    obs.mkdir(parents=True)
    proc_root = _empty_proc(tmp_path)
    (model / "IN_ITS").write_text("2 [NUM_ITS]\n", encoding="utf-8")
    (model / "OUTGEN").write_text(
        "Model started on: 01-Jan-2026 10:00:00\n"
        "Current great iteration count is 10\n"
        "Current great iteration count is 11\n",
        encoding="utf-8",
    )
    (obs / "bat_ins.sh").write_text(
        "$PROG_CMF_OBS < IN_FILE >>& batobs.log\n" * 3,
        encoding="utf-8",
    )
    (obs / "batobs.sh").write_text(
        "$PROG_CMF_OBS < IN_FILE >>& batobs.log\n",
        encoding="utf-8",
    )
    (obs / "batobs.log").write_text(
        "".join(
            f"PID of /opt/cmfgen/exe/cmf_flux.exe is: {pid}\nProgram finished on: now\n"
            for pid in range(1, 5)
        ),
        encoding="utf-8",
    )
    (obs / "CMF_FLUX_PARAM").write_text("15.0D0 [VTURB_FIX]\n", encoding="utf-8")
    (obs / "OUT_FLUX").write_text(
        "LS loop 84 is finished. Number of points along ray=19\nCMF_FLUX has finished\n",
        encoding="utf-8",
    )

    runtime = inspect_workflow_runtime(model, "main", proc_root=proc_root)

    assert runtime["active"] is False
    assert [record["phase"] for record in runtime["recorded_progress"]] == ["main", "flux"]
    main, flux = runtime["recorded_progress"]
    assert main["progress"]["detail"] == "Run iteration 2 of 2 requested"
    assert flux["progress"]["detail"] == "Completed 4 of 4 CMF_FLUX passes"
    flux_metrics = {
        item["label"]: item["value"] for item in flux["progress"]["metrics"]
    }
    assert flux_metrics["Latest LS loop"] == "84"


def test_lte_progress_reads_frequency_counter(tmp_path: Path) -> None:
    proc_root = _empty_proc(tmp_path)
    model = tmp_path / "lte"
    model.mkdir()
    (model / "OUTLTE").write_text("Number of frequencies is 112508\n", encoding="utf-8")
    (model / "ML_COUNTER").write_text("54000 55000 56000\n", encoding="utf-8")

    progress = inspect_workflow_runtime(model, "lte", proc_root=proc_root)["progress"]

    assert progress is not None
    assert progress["current"] == 56000
    assert progress["maximum"] == 112508
    assert progress["percent"] == 49.8


def test_hydro_progress_reads_partial_output_grid(tmp_path: Path) -> None:
    proc_root = _empty_proc(tmp_path)
    model = tmp_path / "lte"
    model.mkdir()
    (model / "RVSIG_COL_NEW").write_text(
        "3 !Number of depth points\n"
        "1.0 2.0 3.0 4.0 1\n"
        "1.1 2.1 3.1 4.1 2\n",
        encoding="utf-8",
    )

    progress = inspect_workflow_runtime(model, "hydro", proc_root=proc_root)["progress"]

    assert progress is not None
    assert progress["detail"] == "Depth point 2 of 3"
    assert progress["percent"] == pytest.approx(66.7)


def test_old_file_progress_is_hidden_for_a_new_process(tmp_path: Path) -> None:
    target = tmp_path / "model"
    target.mkdir()
    (target / "IN_ITS").write_text("20 [NUM_ITS]\n", encoding="utf-8")
    output = target / "OUTGEN"
    output.write_text("Current great iteration count is 12\n", encoding="utf-8")
    os.utime(output, (1000, 1000))
    proc_root = _empty_proc(tmp_path)
    _write_fake_process(
        proc_root,
        123,
        cwd=target,
        command="/opt/cmfgen/exe/cmfgen_dev.exe",
        comm="cmfgen_dev.exe",
    )

    runtime = inspect_workflow_runtime(
        target,
        "main",
        proc_root=proc_root,
        now_epoch=2000,
    )

    assert runtime["active"] is True
    assert runtime["progress"] is None


def test_main_diagnostic_reports_fortran_failure_despite_shell_completion(
    tmp_path: Path,
) -> None:
    proc_root = _empty_proc(tmp_path)
    model = tmp_path / "model"
    model.mkdir()
    (model / "batch.log").write_text(
        "Model started at: Sat Aug 8 08:44:59 PM CEST 2026\n"
        "At line 2233 of file cmfgen_sub.f\n"
        "Fortran runtime error: Expected INTEGER for item 14, got REAL\n"
        "Error termination. Backtrace:\n"
        "Program finished on: Sat Aug 8 08:45:01 PM CEST 2026\n",
        encoding="utf-8",
    )
    # Existing result files must not mask a failed rerun.
    (model / "MOD_SUM").write_text(
        "Model Finalized on: 01-Jan-2026 00:00:00\n",
        encoding="utf-8",
    )
    (model / "RVTJ").write_text("old restart\n", encoding="utf-8")

    runtime = inspect_workflow_runtime(model, "main", proc_root=proc_root)

    diagnostic = runtime["diagnostics"][0]
    assert diagnostic["status"] == "failed"
    assert diagnostic["phase"] == "main"
    assert diagnostic["details"][0]["path"] == "batch.log"
    assert "Fortran runtime error" in diagnostic["details"][0]["message"]


def test_flux_diagnostic_reports_failure_when_script_still_writes_finished_marker(
    tmp_path: Path,
) -> None:
    proc_root = _empty_proc(tmp_path)
    model = tmp_path / "model"
    obs = model / "obs"
    obs.mkdir(parents=True)
    (obs / "batobs.sh").write_text(
        "$PROG_CMF_OBS < IN_FILE >>& batobs.log\n"
        "mv -f OBSFRAME obs_cont\n",
        encoding="utf-8",
    )
    (obs / "batobs.log").write_text(
        "PID of /opt/cmfgen/exe/cmf_flux.exe is: 4321\n"
        "Fortran runtime error: Expected INTEGER for item 14, got REAL\n"
        "Error termination. Backtrace:\n"
        "Program finished on: now\n",
        encoding="utf-8",
    )

    diagnostic = inspect_workflow_runtime(model, "main", proc_root=proc_root)[
        "diagnostics"
    ][1]

    assert diagnostic["status"] == "failed"
    assert diagnostic["phase"] == "flux"
    assert diagnostic["details"][0]["path"] == "batobs.log"
    assert diagnostic["details"][0]["message"].startswith("CMF_FLUX pass 1:")


def test_run_diagnostics_accept_success_and_ignore_benign_numerical_notes(
    tmp_path: Path,
) -> None:
    proc_root = _empty_proc(tmp_path)
    model = tmp_path / "model"
    obs = model / "obs"
    obs.mkdir(parents=True)
    for name in ("batch.sh", "VADAT", "MODEL_SPEC", "IN_ITS", "GAMMAS_IN"):
        (model / name).write_text("input\n", encoding="utf-8")
    (model / "batch.log").write_text(
        "Note: The following floating-point exceptions are signalling: "
        "IEEE_UNDERFLOW_FLAG IEEE_DENORMAL\n"
        "Error --- J(mom) convergence was not obtained at one frequency\n"
        "Program finished on: now\n",
        encoding="utf-8",
    )
    (model / "MOD_SUM").write_text(
        "Model Finalized on: 09-Aug-2026 01:00:00\n",
        encoding="utf-8",
    )
    (model / "RVTJ").write_text("restart\n", encoding="utf-8")

    (obs / "bat_ins.sh").write_text(
        "$PROG_CMF_OBS < IN_FILE >>& batobs.log\n"
        "mv -f OBSFRAME obs_fin_15\n",
        encoding="utf-8",
    )
    (obs / "batobs.sh").write_text(
        "$PROG_CMF_OBS < IN_FILE >>& batobs.log\n"
        "mv -f OBSFRAME obs_cont\n",
        encoding="utf-8",
    )
    (obs / "batobs.log").write_text(
        "PID of /opt/cmfgen/exe/cmf_flux.exe is: 1\n"
        "Note: The following floating-point exceptions are signalling: "
        "IEEE_UNDERFLOW_FLAG IEEE_DENORMAL\n"
        "Program finished on: now\n"
        "PID of /opt/cmfgen/exe/cmf_flux.exe is: 2\n"
        "Program finished on: now\n",
        encoding="utf-8",
    )
    (obs / "obs_fin_15").write_text("spectrum\n", encoding="utf-8")
    (obs / "obs_cont").write_text("continuum\n", encoding="utf-8")
    (obs / "OUT_FLUX").write_text("CMF_FLUX has finished\n", encoding="utf-8")

    diagnostics = inspect_workflow_runtime(model, "main", proc_root=proc_root)[
        "diagnostics"
    ]

    assert [item["status"] for item in diagnostics] == ["succeeded", "succeeded"]
    assert "All 2 CMF_FLUX passes" in diagnostics[1]["summary"]


def test_flux_diagnostic_reports_incomplete_missing_or_unfinished_results(
    tmp_path: Path,
) -> None:
    proc_root = _empty_proc(tmp_path)
    model = tmp_path / "model"
    obs = model / "obs"
    obs.mkdir(parents=True)
    (obs / "batobs.sh").write_text(
        "$PROG_CMF_OBS < IN_FILE >>& batobs.log\n"
        "mv -f OBSFRAME obs_cont\n",
        encoding="utf-8",
    )
    (obs / "batobs.log").write_text(
        "PID of /opt/cmfgen/exe/cmf_flux.exe is: 1\nProgram finished on: now\n",
        encoding="utf-8",
    )
    (obs / "OUT_FLUX").write_text("partial output\n", encoding="utf-8")

    diagnostic = inspect_workflow_runtime(model, "main", proc_root=proc_root)[
        "diagnostics"
    ][1]

    assert diagnostic["status"] == "incomplete"
    messages = [detail["message"] for detail in diagnostic["details"]]
    assert "Expected spectrum obs_cont is missing." in messages
    assert "OUT_FLUX has no successful completion marker." in messages


def test_main_diagnostic_rejects_results_from_before_latest_batch_start(
    tmp_path: Path,
) -> None:
    proc_root = _empty_proc(tmp_path)
    model = tmp_path / "model"
    model.mkdir()
    (model / "batch.log").write_text(
        "Model started at: Sat Aug 8 08:44:59 PM CEST 2030\n"
        "Program finished on: Sat Aug 8 08:45:01 PM CEST 2030\n",
        encoding="utf-8",
    )
    (model / "MOD_SUM").write_text(
        "Model Finalized on: 01-Jan-2026 00:00:00\n",
        encoding="utf-8",
    )
    (model / "RVTJ").write_text("old restart\n", encoding="utf-8")

    diagnostic = inspect_workflow_runtime(model, "main", proc_root=proc_root)[
        "diagnostics"
    ][0]

    assert diagnostic["status"] == "incomplete"
    assert {detail["path"] for detail in diagnostic["details"]} == {"MOD_SUM", "RVTJ"}
