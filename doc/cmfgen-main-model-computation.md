# Main Model Computation

Use **Preview main workflow** or **Preview spectra only** for read-only HTML/JSON stage plans. The workflow now adds executable, dependency, workspace, disk, and activity checks to structural preflight. See [Workflow Safety and Dry-Run Plans](/documentation/cmfgen-workflow-plans) for configuration, mutation guards, and the limits of legacy-script inspection.

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

The run section polls read-only status every five seconds. A process is considered part of the model only when its command/name resembles the CMFGEN executable or `batch.sh` **and** its `/proc` working directory exactly matches the model directory. For each match, the page shows PID, process state, elapsed time, accumulated CPU time and average CPU use, resident memory, and thread count. This is Linux-specific; if `/proc` is unavailable, the external command still works normally but the page reports no detected process.

The same monitor follows the spectral phase when `batch.sh` changes into the model's `obs/` directory. In that phase it recognizes `batch.sh`, `batobs.sh`, `bat_ins.sh`, and `cmf_flux.exe` only with an exact `obs/` working-directory match. The display changes to **CMF_FLUX**, counts completed and running spectrum passes from the newly written `batobs.log`, derives the expected pass count from `batobs.sh` and `bat_ins.sh`, and shows the latest `OUT_FLUX` `LS loop` as an activity counter. LS loop totals are not known reliably in advance, so no within-pass percentage is invented.

When no process is active, the panel retains separate **Last recorded CMFGEN progress** and **Last recorded CMF_FLUX progress** blocks when their logs are available. This keeps the completed spectral stage visible without replacing the iteration history of the main solution.

The same live panel classifies the latest recorded result for each branch as **Running**, **Succeeded**, **Failed**, **Incomplete**, or **Unknown**. Failure detection intentionally uses strong process-level signatures such as a Fortran runtime error, error termination, a fatal signal, segmentation fault, or core dump. It does not match the word `error` on its own, so CMFGEN convergence messages and numerical warnings (including floating-point underflow notes) do not become false failures.

For CMFGEN, success requires current `MOD_SUM` and `RVTJ` files and the `Model Finalized on:` marker in `MOD_SUM`. For CMF_FLUX, the viewer derives both the expected pass count and output spectrum names from `batobs.sh`/`bat_ins.sh`, then requires every pass marker, fresh moved `OBSFRAME` result, and the final `CMF_FLUX has finished` marker in `OUT_FLUX`. A shell `Program finished on:` line is not accepted as proof of success when the preceding program output contains a fatal signature. Diagnostic entries link directly to the relevant log or missing/stale result. Because CMFGEN scripts normally replace their short batch logs on each invocation, failures from older overwritten runs can only be reported as unknown.

Progress is estimated from the growing `OUTGEN`. Because CMFGEN appends repeated invocations to the same file and keeps a global "great iteration" counter, the latest `Model started on:` marker defines the current run. The monitor counts iteration markers after that boundary and compares the count with `IN_ITS [NUM_ITS]`; it also shows the global great-iteration number as a diagnostic. Counting markers, rather than subtracting global numbers, handles CMFGEN's deliberately skipped great-iteration values. The latest luminosity difference and maximum solution change are taken only from the current run when available. The percentage remains an orientation aid rather than a completion guarantee. When no matching process exists, retained output is explicitly labeled **Last recorded progress**, not a running calculation. Old output is suppressed when it predates a newly detected process.

## Convergence overview

The result section parses every iteration record in the latest visible appended `OUTGEN` run. It summarizes the recorded/requested iteration count, global-iteration range, latest and best SOLVEBA maximum change, generated-versus-target luminosity, maximum population increase/decrease and their depths, latest full-spectrum change, and the final cumulative timing values when a current `TIMING` file is available.

Two interactive plots show correction magnitudes on a logarithmic axis and signed luminosity difference on a separate linear axis. Lambda iterations are marked explicitly and excluded from the simple recent-direction comparison, because their deliberately large changes should not be compared directly with normal iterations. BA reuse/computation and fixed-temperature state remain available in the parsed iteration records even though the overview does not turn them into pass/fail criteria.

When current auxiliary files are available, the panel also reduces `CORRECTION_SUM` to the largest counts in the 1%, 0.1%, and 0.01% threshold columns and identifies the corresponding depths. Repeated output messages are grouped into a compact diagnostic list, including outer-boundary `J(mom)`/`J(ray)` discrepancies, oscillator-strength notices, continuum-frequency warnings, potentially omitted ions, weak-transition cuts, and atomic-data format metadata. Each group links to its source file.

No universal **converged** badge is assigned. The displayed recent direction is descriptive, based on up to five non-lambda solver-change records, and may be decreasing, increasing, mixed, or non-monotonic. Scientific acceptance thresholds remain model- and workflow-dependent. Auxiliary files older than the latest run start are shown as stale or excluded instead of being mixed into the current summary.

Opening `OUTGEN` itself in **Parsed** mode exposes the same latest-run cards as tables, the full per-iteration diagnostic table, both plots, current correction thresholds, and grouped diagnostics. This view shares the workflow parser rather than independently interpreting the output; its cache also follows changes to `IN_ITS`, `TIMING`, `CORRECTION_SUM`, and `WARNINGS`.

After an external run, the workflow links to available `MOD_SUM`, `OUTGEN`, `batch.log`, `MODEL`, and `RVTJ` files. `MOD_SUM` is current only when it is newer than the relevant model inputs and no newer modified-input marker exists.
