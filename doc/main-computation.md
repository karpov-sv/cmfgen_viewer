# Main computation

Use **Preview main workflow** or **Preview spectra only** for read-only HTML/JSON stage plans. The workflow now adds executable, dependency, workspace, disk, and activity checks to structural preflight. See [Templates and configuration](/documentation/templates-and-configuration) for configuration, mutation guards, and the limits of legacy-script inspection.

Main CMFGEN computation is intentionally separate from LTE/hydro structure preparation. Open **Main Computation** from a model's workflow actions, or continue there from the final LTE/hydro handoff guard.

Use **Run main** or **Run spectra** in the run card to start a stage without leaving the workflow. Confirm the model, stage, and settings in the popup; the server validates current inputs before launching. Previewing a plan is available on the full **Model runner** page. The card restores saved job status after reload, offers **View output** and **Stop run** while active, and refreshes workflow results on completion. **Run main + spectra** runs main computation followed by spectral synthesis, using the same iteration and thread settings. Spectra are preflighted after the main outputs are available; a failed main stage stops the sequence. For other stage sequences and resource settings, use **Model runner**. Both interfaces execute in an independent process that keeps running across viewer restarts. Expand **Run in terminal** for external execution:

```bash
cd /absolute/path/to/model && ./batch.sh
```

## Continuation and iteration counts

Main computation can continue an existing model from its saved checkpoints. Native CMFGEN tries `POINT1`, then `POINT2`, with `SCRTEMP` supplying the saved state. The command displayed by the viewer follows that native behavior. The standalone runner checks checkpoint availability and compatibility before execution and continues automatically when a usable checkpoint exists; no resume flag is needed.

```bash
python cmfgen_run.py /path/to/model --stage main
```

To deliberately start from the latest text population outputs instead, use `python cmfgen_model.py out2in /path/to/model --plan`, then omit `--plan` to apply it. This copies `*OUT → *_IN` and `GAMMAS → GAMMAS_IN`, preserves the outputs, and retires `POINT1`/`POINT2`/`SCRTEMP`. The next ordinary main run then starts from the refreshed inputs. By comparison, runner `--fresh-start` only retires checkpoints; it does not refresh existing `*_IN` files. See [Templates and configuration](/documentation/templates-and-configuration) for recovery storage and compatibility considerations.

Without `--iterations`, the runner uses `IN_ITS [NUM_ITS]`. This is the number of iterations requested **for this invocation**, including when continuing a model. For example, `NUM_ITS=20` requests **20 additional iterations** from the saved checkpoint, regardless of how many iterations the model has already completed. CMFGEN may stop earlier if its native stopping conditions are met.

To request five additional iterations while preserving the saved IN_ITS settings, use a temporary runner override:

```bash
python cmfgen_run.py /path/to/model --stage main --iterations 5
```

An ordinary finite run continues from live checkpoints without archiving their binary state. Its recovery retains saved inputs for a fresh run; automatic mode below additionally retains full rollback checkpoints. Add `--plan` to inspect the detected startup mode and readiness without launching a calculation. Use `--fresh-start` explicitly to remove checkpoints and start from the initial inputs. Promoting new LTE/hydro results also retires incompatible old checkpoints, so the next main run starts fresh. See [Command-line runner](/documentation/command-line-runner#continuation-and-fresh-starts) for checkpoint checks, recovery, and native fallback reporting.

## End-of-run recommendations

Every ordinary Python-runner **main** run (CLI, the viewer's **Run main** button, or the main stage of a sequence) now performs a read-only check on completion or native failure. The terminal summary, no-stage model inspection (`cmfgen_run.py MODEL`), job result, and main workflow page show recognized conditions, suggested controls/cache retirement/recovery steps, and whether the registered automatic remedy's prerequisites were established. Recommendations are saved as `main_diagnostics` in the run's `result.json`; execution status and exit codes retain their original meaning. No controls are changed and no retry is launched by this check.

The check uses the same versioned rules listed below as automatic mode. It can list several findings; the automatic controller selects the first applicable rule and reassesses after its remedy. It validates fresh outputs and checkpoint/iteration agreement before judging numerical progress. Stalled corrections and missing variable-temperature steps require **three consecutive compatible successful batches**; the temperature-profile fallback for oscillation requires four. History is reset by failures, fresh starts, changed solver controls/executable, missing evidence, or discontinuous checkpoints. A single short run cannot establish those multi-batch diagnoses. Incomplete evidence is reported explicitly, and a numerical candidate is recommended for independent verification rather than declared converged.

Remedy availability describes the diagnosed invocation, not a guarantee that starting `--auto` after a failed run will work: first review its restart state and any required recovery. Unknown failures or unmet prerequisites need manual investigation. Interrupted runs do not propose recovery. Existing boundary, hydrostatic, and energy-budget quality diagnostics still need separate review.

The workflow shows saved recommendations only while their controls and output evidence remain current, and hides them during an active run. For older or shell-script models without a current saved report, both the workflow and CLI recompute an explicitly marked historical assessment from existing outputs. `cmfgen_run.py MODEL --diagnose` forces this recheck even when saved recommendations exist; add `--json` for structured results. No model run or file write occurs. Native failure and quality screening remain useful, but automatic recovery eligibility, original startup context, multi-batch history, and alignment of old STEQ_VALS vectors are unverified. A numerical candidate requires trustworthy timestamps, current finite outputs, and checkpoint/counter agreement, and still needs a new independent verification run.

## Automatic convergence and recovery rules

Use the standalone runner's optional automatic mode for an unattended main-stage loop:

```bash
python cmfgen_run.py /path/to/model --stage main --auto
```

Add `--plan` for a read-only preview. **All registered remedies are enabled automatically**; no per-problem flags are needed. The loop runs a batch, validates its output/checkpoint, diagnoses the result, applies an eligible tested remedy, and continues. Numerical success requires a separate fresh-Jacobian verification. The **Automatic mode** checkbox on Main Computation applies the same bounded loop to the main stage of **Run main** or **Run main + spectra**. Leave it unchecked for finite main runs; **Auto settings and limits** opens the configurable preview.

Defaults are **5 additional iterations per normal batch**, **100 native attempts**, and **500 total iterations**, including recovery and verification. Set these with `--iterations`, `--auto-max-attempts`, and `--auto-max-iterations`; `--timeout` supplies a shared wall-clock limit. Failed attempts conservatively consume their full requested allowance. A recovery procedure is started only when its complete sequence fits the remaining budgets. Cancellation, exhausted limits, or an unhandled problem ends the loop without claiming convergence.

### Automatic runs in the UI

On **Main Computation**, check **Automatic mode**, then use **Run main** or **Run main + spectra**. The entered iteration count becomes the batch size (default 5), with the standard 100-attempt/500-iteration limits. The confirmation identifies the automatic behavior and limits. Unchecking the box restores finite-run behavior for both buttons.

For custom limits, open **Model runner** (or **Auto settings and limits**), select **Main computation** or **Main computation → spectra**, enable **Automatic main convergence**, and enter the batch size, maximum attempts, maximum total iterations, and optional shared timeout. Preview and launch the reviewed plan. With spectra selected, the main stage must pass independent convergence verification before spectra start. A review-needed stop, exhausted automatic budget, timeout, or cancellation skips spectra. Scientific-quality warnings remain advisory; review the resulting atmosphere and spectra.

Automatic jobs run in the detached worker and retain the model reservation between attempts. Closing the page or restarting the viewer does not stop the loop. The workflow and job page show the current attempt, recovery/verification phase, and native progress; when spectra start, their own progress replaces the automatic-main attempt prefix; **Stop run** cancels the loop with the same control restoration and provisional checkpoint rollback as CLI cancellation. The completed report lists attempts, adjustments, convergence or stop reason, charged work, scientific-quality warnings, and the investigation report location when review is needed. **Needs review** and **Work limit reached** are distinct from successful convergence.

Previews include the policy manifest and work budgets in their launch fingerprint. Inline automatic confirmation tokens are bound to automatic mode, so a finite-run confirmation cannot silently launch an automatic loop. Existing read-write gating and native preflight checks still apply.

The following table lists every registered rule and the two fallback decisions. Policy identifiers also appear in previews, journals, and issue reports. More specific failure remedies are considered before the general unhandled-problem decision; verified convergence and verification candidates take priority over further numerical tuning.

| Rule / policy identifier | Recognition and eligibility | Remedy or result | Limit |
| --- | --- | --- | --- |
| Saved-population interpolation — `pop_initialization` | Same confirmed, isolated pre-iteration population failure as the LTE rule, but in a **fresh** startup with explicit legacy `DC_METH=R/TR/ED/SPH_TAU`, `LIN_INT=T`, `POP_SCALE=T`, and `LTE_EST=F` if present. The executable must contain the patched POP success marker. Original explicit-ion inputs must be unchanged, complete, have matching full-level counts, and share a saved radius/T/Ne/clumping grid. | Request 2 iterations with temporary `DC_METH=POP`; require native confirmation of fraction interpolation and charge-conserving Ne, fresh finite outputs, and a usable checkpoint. Restore original controls, then request 2 normal continuation iterations. Native atomic/occupation/conservation validation remains mandatory; a failed step rolls the whole procedure back. | One recovery procedure; never reseeds an established continuation. |
| LTE starting populations — `lte_initialization` | Confirmed population-conversion/scaling failure before any iteration in a **fresh** startup: a native `SCALE_POPS`/`CNVT_FR_DC` crash frame or the `SETPOP_WLD_V*` zero-RGU safeguard. No other diagnosed error; LTE was not already selected. Explicit `LIN_INT=F`, and `LTE_EST=F` if present, must be compatible. | Request 2 iterations with temporary `DC_METH=LTE` and a positive `T_EXC`; restore the original initialization controls on every exit. Require finite refreshed outputs/a usable checkpoint, then request 2 normal continuation iterations before committing the recovered state. | One recovery procedure per automatic invocation. |
| Hydro startup bridge — `hydro_bootstrap` | An isolated, zero-exit factor-of-two luminosity stop before the first population solve of a confirmed continuation. A hydro revision is explicitly due in `HYDRO_DEFAULTS`; `DO_HYDRO=T` and the major-warning guard is enabled. Fresh complete luminosity/optical-depth profiles corroborate the stop and establish inner τRoss ≥ 30. | Run 1 iteration with temporary `STOP_IF_MW=F` to complete the scheduled hydro/grey revision, restore the guard, then request 2 guarded continuation iterations. Their luminosity profile must be within `[0.5, 2]` and inner τRoss at least 30. | One recovery procedure. |
| Radiation cache — `radiation_cache` | A failed attempt explicitly reports **incorrect reading of EDDFACTOR**. A generic crash does not qualify. | Restore the appropriate checkpoint, retire the radiation cache, and retry. A cache error within a provisional recovery retries that step from its step snapshot. | One application. |
| Verified numerical convergence — `verified_convergence` | In the independent verification phase, the final 2 steps are full, temperature-varying solves with fresh BA on both. Native solver metric and both absolute raw correction extrema are finite and strictly below `EPS_TERM`; relevant `CORRECTION_SUM` counts agree. No intervening hydro revision invalidates those steps. | Finish successfully and report scientific-quality measurements separately. | Evaluated after each successful verification batch. |
| Candidate verification — `verify_candidate` | The final 2 full, temperature-varying solves meet the raw/native correction tolerance and count checks, but independent verification is still required. | Set `COMP_BA=T`, `N_FIX_BA=0`, `FIX_BA=0.0`, retire `BAMAT`/`BAMATPNT`, and request up to 3 verification iterations. A rebound returns to further diagnosis/iteration. | Shared work budgets; never accepts a candidate without verification. |
| Local oscillation damping — `local_relaxation` | Persistent sign reversals in raw temperature requests, or sufficient completed-batch temperature profiles, with nondecaying amplitude. The affected interval spans at most one third of the depth grid. Requires `SCALE_OPT=MAJOR` and supported simple correction controls. | Set depth-local `RELAX=0.25`, then `0.125` if necessary; set local `T_LIM=0.2` so a tighter cap does not suppress the native RELAX branch. Preserve/extend the existing simple depth interval within the supported width. | At most 2 adjustments; a persistent cycle at the minimum RELAX stops for review. |
| Stalled corrections — `stalled_corrections` | Last full-step metrics from 3 batches show a plateau/nonimproving sequence, with no ≥2% improvement relative to the first. Consistently decreasing corrections are allowed to continue even when decay is slow. | Request fresh matrices with `COMP_BA=T`, `N_FIX_BA=0`, `FIX_BA=0.0`, retiring the saved BA caches. Stop for review if already using fresh matrices. Correction trends restart after an adjustment. | One matrix-refresh remedy. |
| No temperature-varying steps — `fixed_temperature` | Three batches since the last intervention contain no full, variable-temperature solve. | Stop for review; Lambda/fixed-temperature changes cannot prove convergence. The loop does not disable Lambda handling or force a temperature-release policy. | Terminal decision. |
| Healthy continuation — `continue` | Fresh outputs and a coherent, finite-core continuation checkpoint, with no higher-priority rule matching. | Continue another normal batch. | Shared work budgets. |
| Unhandled problem — `unhandled` | Unknown failure, or a recognized problem whose tested remedy is ineligible. Invalid/stale numerical evidence is also passed to failure diagnosis. | Stop with the diagnosis/refusal trail and an investigation report. Do not invent an untested adjustment. | Terminal decision. |

### POP initialization recovery

The patched `DC_METH=POP` path reconstructs saved populations before interpolating superlevel fractions, avoiding artificial ionization spikes caused by log-departure-coefficient interpolation across steep temperature gradients. It preserves the saved-model estimates better than rebuilding unrelated LTE guesses when compatible source populations are available. The source-fix investigation records same-grid and refined-grid validation; successful initialization still does not establish atmospheric convergence.

Automatic selection is deliberately tied to a **confirmed fresh-start initialization failure**, with interpolation and population scaling already enabled. It does not flip `LIN_INT` or `POP_SCALE`, react to an opaque crash, restart a healthy continuation, or infer an initialization artifact from a generic stalled run. For a refinement run that finishes but has suspicious ion fractions, inspect the source reconstruction and explicitly choose POP in the parameter editor before a fresh run.

Eligibility requires complete original `*_IN` estimates for all explicit atoms in `MODEL_SPEC`, matching full-level counts and one saved radius/T/Ne/clumping grid; the runner supplies `T_IN` from `He2_IN`. Files generated by the failed attempt's AUTO_ADD do not qualify. The native reader then verifies contiguous explicit stages, atomic mappings, occupation reconstruction and conservation. Incompatible atomic setups must be prepared manually; POP does not repair them. The executable itself must contain the patched native POP completion marker; merely pointing at a source checkout with the patch is insufficient.

The temporary POP trial and the normal-continuation check form one provisional procedure. Original initialization controls are restored on every exit, and either step's failure restores the pre-procedure checkpoint/control set. Ordinary finite runs report the same recommendation and unmet prerequisites without applying it.

### LTE fallback details

LTE initialization remains useful for poor **starting population estimates**; it is not a remedy for an unstable continuation. The fallback never changes `LIN_INT` or `LTE_EST` to force compatibility. It does not reseed a continuation checkpoint or act on a merely suspected/opaque initialization crash. A model explicitly launched with `--fresh-start` remains a fresh-start request; automatic mode preserves its pre-run checkpoint/control baseline for rollback if the recovery fails.

An existing finite positive `VADAT [T_EXC]` is retained for the LTE trial. If absent, the trial uses **1.0 in units of 10⁴ K**. This is a floor for the initial excitation estimates, not a fixed final atmospheric temperature. Supply a suitable positive `T_EXC` in VADAT when a different initialization scale is needed. `DC_METH` and `T_EXC` are temporary overrides; their original values, comments, or absence are restored before normal continuation. An already selected LTE initialization is not retried with the same remedy.

The LTE bootstrap and normal-continuation check are one provisional procedure. If either fails or is interrupted, the loop restores the original checkpoint/control set. Passing the procedure establishes usable initialization and continuation, **not convergence**; normal numerical verification still follows. See [LTE initial populations](/documentation/command-line-runner#lte-initial-populations) for explicit initialization outside automatic mode.

### Recovery, native updates, and evidence

Every accepted attempt requires refreshed `OUTGEN`, `CORRECTION_SUM`, finite RVTJ core vectors, and a usable checkpoint whose counter agrees with the solver steps plus verified native hydro/grey revisions. An extra hydro counter is not counted as another radiation/population solve. Scheduled native hydro updates to `VADAT`, `RVSIG_COL`, and `HYDRO_DEFAULTS` are adopted only with completion messages, valid grid output, and matching counters. An explicitly enabled `DO_T_AUTO=T` may release native `FIX_T=T`; this is observed and preserved, not forced by the controller.

Native automatic lambda release in `IN_ITS` is also preserved: a completed lambda solve below the native 50% switching threshold must be followed immediately by a completed full solve, with `DO_LAM_AUTO` enabled. The runner journals the `DO_LAM_IT=T` → `F` change and keeps `IN_ITS` with checkpoint recovery state. Unrelated edits still require review, and the switch itself is not a convergence criterion.

The model is reserved between native attempts. A rolling full recovery snapshot keeps checkpoint files and coupled controls together; multi-step remedies also retain a temporary step snapshot. Failure or cancellation rolls back provisional changes. Temporary POP/LTE/guard/iteration overrides are restored, while accepted numerical tuning such as local damping and fresh-matrix controls remains installed for later continuation. External control or executable changes stop further automatic mutation and are preserved; if they prevent safe rollback, the report identifies that recovery needs review.

The parent `.cmfgen-runs/<timestamp>-auto-<id>/` journal contains the versioned rule manifest, decisions, action backups, and links to native-run logs. Unhandled/review/budget stops also write `issue.json` and `issue.md`, collecting the failure and policy evidence for investigating and adding the next tested rule. New rules are registered in `auto_policies.py`; updates invalidate older previews. Source/executable edits, arbitrary grid/atomic-data changes, and speculative retries are outside the current remedy set.

Scientific-quality warnings remain a separate assessment. Numerical convergence does not certify boundary transfer, hydrostatic balance, spectral accuracy, or full energy closure. See the [automatic runner guide](/documentation/command-line-runner#automatic-main-stage-convergence) for execution/recovery details.

## Input checks and monitoring

The initial guard checks for `batch.sh`, `VADAT`, `MODEL_SPEC`, `IN_ITS`, and either `GAMMAS_IN` or `GAMMAS`. When both gamma files exist, `GAMMAS_IN` is the input freshness dependency and the generated `GAMMAS` is an output; `GAMMAS` is treated as an input only as a fallback when `GAMMAS_IN` is absent. LTE/hydro-derived models are handed off only after `RVSIG_COL` and `ROSSELAND_LTE_TAB` have been promoted to the model root.

Before displaying the external command, the page also performs a read-only preflight validation. **Errors** block the command, **warnings** remain advisory, and **information** records intentional-but-notable configuration such as additional impact rays. The initial conservative checks cover:

- readable, nonempty control files and an executable `batch.sh`;
- unique and valid `MODEL_SPEC` values for `ND`, `NC`, and `NP`, requiring `NP >= ND + NC` (main models may intentionally include extra rays);
- positive `IN_ITS [NUM_ITS]` and valid supported `T`/`F` controls;
- finite positive values for commonly used stellar controls when they are present;
- complete clumping parameters when `VADAT [DO_CL]` is enabled;
- a complete, finite, nonnegative `ROSSELAND_LTE_TAB` in the model root when `VADAT [DO_HYDRO]=T`, unless `HYDRO_DEFAULTS [N_ITS]=0` explicitly disables further revisions; this also applies to continuation runs without an `lte/` workspace;
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

Progress is estimated from the growing `OUTGEN`. Because CMFGEN appends repeated invocations to the same file and keeps a global "great iteration" counter, the latest `Model started on:` marker defines the current run. The monitor counts iteration markers after that boundary. The progress bar compares completed solver steps with `IN_ITS [NUM_ITS]`: a start marker alone does not advance it, so iteration 1 of 5 starts at 0%. The next iteration start or a solver-return message confirms completion of the preceding/current step; it also shows the global great-iteration number as a diagnostic. Counting markers, rather than subtracting global numbers, handles CMFGEN's deliberately skipped great-iteration values. The latest luminosity difference and maximum solution change are taken only from the current run when available. The percentage remains an orientation aid rather than a completion guarantee. When no matching process exists, retained output is explicitly labeled **Last recorded progress**, not a running calculation. Old output is suppressed when it predates a newly detected process.

## Convergence overview

The result section parses every iteration record in the latest visible appended `OUTGEN` run. It summarizes the recorded/requested iteration count, global-iteration range, latest and best SOLVEBA maximum change, generated-versus-target luminosity, maximum population increase/decrease and their depths, latest full-spectrum change, and the final cumulative timing values when a current `TIMING` file is available.

Two interactive plots show correction magnitudes on a logarithmic axis and signed luminosity difference on a separate linear axis. Lambda iterations are marked explicitly and excluded from the simple recent-direction comparison, because their deliberately large changes should not be compared directly with normal iterations. BA reuse/computation and fixed-temperature state remain available in the parsed iteration records even though the overview does not turn them into pass/fail criteria.

When current auxiliary files are available, the panel also reduces `CORRECTION_SUM` to the largest counts in the 100%, 10%, 1%, 0.1%, and 0.01% threshold columns and identifies the corresponding depths. Repeated output messages are grouped into a compact diagnostic list, including outer-boundary `J(mom)`/`J(ray)` discrepancies, oscillator-strength notices, continuum-frequency warnings, potentially omitted ions, weak-transition cuts, and atomic-data format metadata. Each group links to its source file.

No universal **converged** badge is assigned. The displayed recent direction is descriptive, based on up to five non-lambda solver-change records, and may be decreasing, increasing, mixed, or non-monotonic. Scientific acceptance thresholds remain model- and workflow-dependent. Auxiliary files older than the latest run start are shown as stale or excluded instead of being mixed into the current summary.

The results section displays **Convergence and numerical quality checks**, expanded automatically when review is needed. Execution success remains separate from scientific acceptance. Advisory screening thresholds are 1% for solver/population corrections and spectrum changes, and 2% for generated-versus-target luminosity and depth-dependent normalized luminosity consistency. These are viewer screening values, not native stopping criteria or a guarantee of convergence. Each measurement identifies its iteration or depth; the latest available spectrum measurement may precede the final iteration.

Additional checks flag a rising recent correction trend, fewer than three iterations after a lambda step, temperatures held fixed throughout recent iterations, limited major-species corrections, and variables still changing by more than 1% in `CORRECTION_SUM`. Reaching the requested iteration count is informational; the current `IN_ITS` may differ from the controls used for that run. Review several stable full iterations and the populations relevant to the intended spectral diagnostics before accepting results.

Current `J_COMP` data provide maximum absolute outer-boundary `J(mom)`/`J(ray)` differences over all frequencies and within UV (0.09–0.3 μm), optical (0.3–1 μm), and infrared (1–1000 μm) bands, including the wavelength of each maximum. A 10% advisory screen flags discrepancies for review. These differences measure consistency between radiation methods, **not emergent-flux errors**. Compare a finer outer radial grid when the warning persists. The summary streams files up to 64 MiB and caches only the band maxima, invalidating them when the file changes.

Native photospheric hydrostatic warnings expose their mean, RMS, and maximum residuals from the latest warning block in the latest run. Native limits include RMS above 5%, maximum above 20%, or disagreement in photospheric gravity; review `HYDRO` and structure preparation if the warning persists after further convergence. `OBSFLUX` supplies the normalized luminosity profile through the depth grid, and `MEANOPAC` supplies the innermost Rosseland optical depth (native guidance: at least 50, preferably 100). Missing, stale, unsupported, or unreadable auxiliary measurements remain **Unassessed**. All checks are read-only and provide source links and suggested review actions.

Opening `OUTGEN` itself in **Parsed** mode exposes the same latest-run cards as tables, the full per-iteration diagnostic table, both plots, current correction thresholds, quality checks, and grouped diagnostics. This view shares the workflow parser rather than independently interpreting the output; its cache also follows changes to `IN_ITS`, `MODEL_SPEC`, `TIMING`, `CORRECTION_SUM`, `CORRECTION_LINK`, `WARNINGS`, `J_COMP`, `HYDRO`, `OBSFLUX`, and `MEANOPAC`.

After an external run, the workflow links to available `MOD_SUM`, `OUTGEN`, `batch.log`, `MODEL`, and `RVTJ` files. `MOD_SUM` is current only when it is newer than the relevant model inputs and no newer modified-input marker exists.


When a current `CORRECTION_LINK` is present, quality checks identify the three largest
listed solver corrections with species/variable, superlevel, equation index and depth.
The dedicated parsed file also provides ranked entries and a species overview. These
are selected solver corrections before damping or scaling, not an exhaustive depth
survey. The 1% warning threshold is advisory; stale or malformed snapshots remain
unassessed. Editing `CORRECTION_LINK` refreshes the parsed `OUTGEN` diagnostics.

Model diagnostics show a separate **numerical convergence** status in the workflow
and command-line model summary. The native criterion requires the final two full,
variable-temperature steps to meet `EPS_TERM` in the ranked solver metric, with
the latest raw increase/decrease and correction counts also passing screening.
The status identifies fresh Jacobians when both steps computed them. Older models
are checked from timestamp-screened saved outputs; this does not establish the
original invocation or an independent verification phase. When a candidate's two
final solves already computed fresh Jacobians, read-only recommendations omit
the redundant request to recompute them. Automatic execution still requires its
separate verification phase. Missing, stale, edited,
or inconsistent evidence cannot establish convergence. Physical-quality warnings
remain visible even when the native iteration has converged. The automatic
controller retains its stricter two-step raw-correction acceptance rule.
