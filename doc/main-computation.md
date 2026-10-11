# Main computation

Use **Preview main workflow** or **Preview spectra only** for read-only HTML/JSON stage plans. The workflow now adds executable, dependency, workspace, disk, and activity checks to structural preflight. See [Templates and configuration](/documentation/templates-and-configuration) for configuration, mutation guards, and the limits of legacy-script inspection.

Main CMFGEN computation is intentionally separate from LTE/hydro structure preparation. Open **Main Computation** from a model's workflow actions, or continue there from the final LTE/hydro handoff guard.

The viewer never starts, stops, or supervises CMFGEN. It checks the model inputs and displays the exact terminal command:

```bash
cd /absolute/path/to/model && ./batch.sh
```

The initial guard checks for `batch.sh`, `VADAT`, `MODEL_SPEC`, `IN_ITS`, and either `GAMMAS_IN` or `GAMMAS`. When both gamma files exist, `GAMMAS_IN` is the input freshness dependency and the generated `GAMMAS` is an output; `GAMMAS` is treated as an input only as a fallback when `GAMMAS_IN` is absent. LTE/hydro-derived models are handed off only after `RVSIG_COL` and `ROSSELAND_LTE_TAB` have been promoted to the model root.

Before displaying the external command, the page also performs a read-only preflight validation. **Errors** block the command, **warnings** remain advisory, and **information** records intentional-but-notable configuration such as additional impact rays. The initial conservative checks cover:

- readable, nonempty control files and an executable `batch.sh`;
- unique and valid `MODEL_SPEC` values for `ND`, `NC`, and `NP`, requiring `NP >= ND + NC` (main models may intentionally include extra rays);
- positive `IN_ITS [NUM_ITS]` and valid supported `T`/`F` controls;
- finite positive values for commonly used stellar controls when they are present;
- complete clumping parameters when `VADAT [DO_CL]` is enabled;
- agreement between selected `RVSIG_COL` depth declarations, indexed rows, and `MODEL_SPEC [ND]`;
- nonnegative and ordered CMF_FLUX turbulence and wavelength bounds in `obs/CMF_FLUX_PARAM_INIT`;
- fresh LTE/hydro outputs that are newer than, and differ from, their promoted root copies.

The validator deliberately avoids fixed astrophysical plausibility ranges and does not require `NP = ND + NC` outside LTE grid construction. Each issue links to the full editor when the file is allowlisted and is a regular file, or otherwise to its file view. Symbolic-link layouts remain readable but are not offered to the editor.

The run section receives server-sent status updates; the server checks process and file status every five seconds while subscribed. When a monitored run stops, the page refreshes automatically to update result checks and plots. Unsaved control edits defer the reload and show a **Refresh results** button. A process is considered part of the model only when its executable/script name matches the CMFGEN executable or `batch.sh` **and** its native working directory exactly matches the model directory. For each match, the page shows PID, process state, elapsed time, accumulated CPU time and average CPU use, resident memory, and thread count. Detection uses `psutil` on Linux and macOS. If process visibility is unavailable or denied, the panel reports monitoring unavailable and workspace changes remain blocked until activity can be checked.

The same monitor follows the spectral phase when `batch.sh` changes into the model's `obs/` directory. In that phase it recognizes `batch.sh`, `batobs.sh`, `bat_ins.sh`, and `cmf_flux.exe` only with an exact `obs/` working-directory match. The display changes to **CMF_FLUX**, counts completed and running spectrum passes from the newly written `batobs.log`, derives the expected pass count from `batobs.sh` and `bat_ins.sh`, and shows the latest `OUT_FLUX` `LS loop` as an activity counter. LS loop totals are not known reliably in advance, so no within-pass percentage is invented.

When no process is active, the panel retains separate **Last recorded CMFGEN progress** and **Last recorded CMF_FLUX progress** blocks when their logs are available. This keeps the completed spectral stage visible without replacing the iteration history of the main solution.

The same live panel classifies the latest recorded result for each branch as **Running**, **Succeeded**, **Failed**, **Incomplete**, or **Unknown**. Failure detection uses strong process-level signatures such as a Fortran runtime error, error termination, a fatal signal, segmentation fault, or core dump, plus specific native messages for insufficient inner optical depth and major inner luminosity discrepancies. These scientific safeguards can execute Fortran `STOP` with exit code zero, so a zero exit alone does not prove success. The panel shows the native evidence, relevant current settings, suggested next steps, and links to the diagnostic files. A failed run opens the run panel automatically, including when a live status update first reports the failure.

For insufficient optical depth, review `MEANOPAC`, the LTE/hydro parameters, and the promoted radius scale; the native code checks for depth below 30 and recommends at least 50, preferably 100. For a luminosity consistency discrepancy, inspect the normalized check in `OBSFLUX`, initial temperature refinement (`IT_ON_T`, `GREY_TAU`), starting estimates, and grid resolution. The suggestions do not edit inputs or assess convergence. Values are read from current inputs and may have changed since the recorded failure.

Major safeguard messages become failure findings when completion is absent and `STOP_IF_MW` is enabled (the native default). Completed runs or a disabled/ambiguous safeguard retain them as warnings. The separate 25% luminosity warning does not itself stop the run. The analyzer does not match the word `error` on its own, so benign convergence messages and floating-point underflow notes do not become false failures. Appended logs are restricted to their latest invocation.

For CMFGEN, success requires current `MOD_SUM` and `RVTJ` files and the `Model Finalized on:` marker in `MOD_SUM`. For CMF_FLUX, the viewer derives both the expected pass count and output spectrum names from `batobs.sh`/`bat_ins.sh`, then requires every pass marker, fresh moved `OBSFRAME` result, and the final `CMF_FLUX has finished` marker in `OUT_FLUX`. A shell `Program finished on:` line is not accepted as proof of success when the preceding program output contains a fatal signature. Diagnostic entries link directly to the relevant log or missing/stale result. Because CMFGEN scripts normally replace their short batch logs on each invocation, failures from older overwritten runs can only be reported as unknown.

Progress is estimated from the growing `OUTGEN`. Because CMFGEN appends repeated invocations to the same file and keeps a global "great iteration" counter, the latest `Model started on:` marker defines the current run. The monitor counts iteration markers after that boundary and compares the count with `IN_ITS [NUM_ITS]`; it also shows the global great-iteration number as a diagnostic. Counting markers, rather than subtracting global numbers, handles CMFGEN's deliberately skipped great-iteration values. The latest luminosity difference and maximum solution change are taken only from the current run when available. The percentage remains an orientation aid rather than a completion guarantee. When no matching process exists, retained output is explicitly labeled **Last recorded progress**, not a running calculation. Old output is suppressed when it predates a newly detected process.

## Convergence overview

The result section parses every iteration record in the latest visible appended `OUTGEN` run. It summarizes the recorded/requested iteration count, global-iteration range, latest and best SOLVEBA maximum change, generated-versus-target luminosity, maximum population increase/decrease and their depths, latest full-spectrum change, and the final cumulative timing values when a current `TIMING` file is available.

Two interactive plots show correction magnitudes on a logarithmic axis and signed luminosity difference on a separate linear axis. Lambda iterations are marked explicitly and excluded from the simple recent-direction comparison, because their deliberately large changes should not be compared directly with normal iterations. BA reuse/computation and fixed-temperature state remain available in the parsed iteration records even though the overview does not turn them into pass/fail criteria.

When current auxiliary files are available, the panel also reduces `CORRECTION_SUM` to the largest counts in the 1%, 0.1%, and 0.01% threshold columns and identifies the corresponding depths. Repeated output messages are grouped into a compact diagnostic list, including outer-boundary `J(mom)`/`J(ray)` discrepancies, oscillator-strength notices, continuum-frequency warnings, potentially omitted ions, weak-transition cuts, and atomic-data format metadata. Each group links to its source file.

No universal **converged** badge is assigned. The displayed recent direction is descriptive, based on up to five non-lambda solver-change records, and may be decreasing, increasing, mixed, or non-monotonic. Scientific acceptance thresholds remain model- and workflow-dependent. Auxiliary files older than the latest run start are shown as stale or excluded instead of being mixed into the current summary.

The results section displays **Convergence and numerical quality checks**, expanded automatically when review is needed. Execution success remains separate from scientific acceptance. Advisory screening thresholds are 1% for solver/population corrections and spectrum changes, and 2% for generated-versus-target luminosity and depth-dependent normalized luminosity consistency. These are viewer screening values, not native stopping criteria or a guarantee of convergence. Each measurement identifies its iteration or depth; the latest available spectrum measurement may precede the final iteration.

Additional checks flag a rising recent correction trend, fewer than three iterations after a lambda step, temperatures held fixed throughout recent iterations, limited major-species corrections, and variables still changing by more than 1% in `CORRECTION_SUM`. Reaching the requested iteration count is informational; the current `IN_ITS` may differ from the controls used for that run. Review several stable full iterations and the populations relevant to the intended spectral diagnostics before accepting results.

Current `J_COMP` data provide maximum absolute outer-boundary `J(mom)`/`J(ray)` differences over all frequencies and within UV (0.09–0.3 μm), optical (0.3–1 μm), and infrared (1–1000 μm) bands, including the wavelength of each maximum. A 10% advisory screen flags discrepancies for review. These differences measure consistency between radiation methods, **not emergent-flux errors**. Compare a finer outer radial grid when the warning persists. The summary streams files up to 64 MiB and caches only the band maxima, invalidating them when the file changes.

Native photospheric hydrostatic warnings expose their mean, RMS, and maximum residuals from the latest warning block in the latest run. Native limits include RMS above 5%, maximum above 20%, or disagreement in photospheric gravity; review `HYDRO` and structure preparation if the warning persists after further convergence. `OBSFLUX` supplies the normalized luminosity profile through the depth grid, and `MEANOPAC` supplies the innermost Rosseland optical depth (native guidance: at least 50, preferably 100). Missing, stale, unsupported, or unreadable auxiliary measurements remain **Unassessed**. All checks are read-only and provide source links and suggested review actions.

Opening `OUTGEN` itself in **Parsed** mode exposes the same latest-run cards as tables, the full per-iteration diagnostic table, both plots, current correction thresholds, quality checks, and grouped diagnostics. This view shares the workflow parser rather than independently interpreting the output; its cache also follows changes to `IN_ITS`, `MODEL_SPEC`, `TIMING`, `CORRECTION_SUM`, `WARNINGS`, `J_COMP`, `HYDRO`, `OBSFLUX`, and `MEANOPAC`.

After an external run, the workflow links to available `MOD_SUM`, `OUTGEN`, `batch.log`, `MODEL`, and `RVTJ` files. `MOD_SUM` is current only when it is newer than the relevant model inputs and no newer modified-input marker exists.
