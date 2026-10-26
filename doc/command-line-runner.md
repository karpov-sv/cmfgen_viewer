# Command-line runner

`cmfgen_run.py` runs a reviewed subset of the ostar workflows directly in Python. It never executes `batch.sh`, `batobs.sh`, sourced setup scripts, or arbitrary shell commands. The same runner can be launched from the viewer as an independent process.

Text completion messages include elapsed wall-clock time, for example
`[OK] main: completed in 125.34s`. The automatic-run summary reports total
time across all attempts and verification. In a sequence, each accepted-stage
message also reports that stage's total time before advancing.

## Launching from the viewer

In read-write mode, choose **Model runner** in the shared model toolbar, beside the workflow links. Select a stage preset or enter a custom ordered sequence, optionally set additional main iterations, threads, timeout, memory limit, or fresh startup, then **Preview run**. Review the findings and choose **Launch reviewed run**. Changed inputs or configuration require a new preview. For sequences, only the first stage is fully checked initially; later stages are preflighted against the outputs just produced.

The launch opens a persistent job page with current stage/progress, logs, final results, and a **Stop run** action. Running jobs also appear in the Tasks menu. Closing the browser or restarting the viewer leaves the detached runner and its native child active. The viewer recovers saved jobs after restart without relying on its former in-memory task store or process handles.

Launch records are retained in `.cmfgen-runner-jobs/` under the configured model-tree root. Normal `.cmfgen-runs/` journals remain in each model. A separate model reservation lock protects the complete sequence, including gaps between stages; conflicting edits and launches are blocked. Stopping targets the verified runner process, which stops its native process group and restores temporary controls. PID reuse cannot redirect a stop request to an unrelated process.

If the runner disappears without a final result, the job is shown as interrupted, with surviving native processes identified when visible. It is never automatically relaunched. Machine reboot or logout survival is not guaranteed; inspect checkpoints and journals before explicitly continuing. Restarting with a different model-tree root shows that root's own launch history.

## Quick start

With roots configured, show model information, recorded run/checkpoint state, saved and logged iteration counts, and main-stage preflight without changing the workspace:

```bash
python3 cmfgen_run.py /path/to/model
python3 cmfgen_run.py /path/to/model --json
```

No stage means read-only inspection, including when `--plan` is supplied. Model information remains available if installation configuration or preflight is incomplete. Exit status reflects main-stage preflight readiness (`0` ready, `2` blocked), independently of whether a previous run failed. A saved checkpoint iteration count and the latest logged iteration are shown separately: an attempted iteration can fail before saving a checkpoint. Recorded execution success does not establish convergence.

The summary also shows the latest ordinary main run's end-of-run diagnostics and suggestions when its saved evidence is still current, including proposed control changes, cache retirement, and POP/LTE/hydro recovery steps. This uses the same read-only report as the workflow page. Stale advice is hidden after model/output/executable or policy changes, and while activity is running or cannot be established as idle. With `--json`, the report is available as `state.main_diagnostics` (`null` when unavailable). Inspection applies no remedy.

For older models without a current saved report, the summary automatically recomputes read-only checks from the latest visible native run and existing outputs. To force a new assessment even when a saved report exists:

```bash
python cmfgen_run.py /path/to/model --diagnose
python cmfgen_run.py /path/to/model --diagnose --json
```

`--diagnose` cannot be combined with `--stage`. It creates no journal or recommendation file. Historical reports are marked `mode: retrospective`: they include recognizable native failures, correction/quality warnings, and timestamp-screened numerical candidates where possible. Missing dates, stale outputs, edited inputs, or inconsistent checkpoints are reported explicitly. Original startup mode and recovery baselines cannot be recovered from those files, so automatic eligibility remains unverified. Multi-batch stall rules and invocation-aligned temperature oscillations are not inferred from an undated aggregate log. Candidates still need a new independent verification run. The workflow page uses the same fallback; active or uncertain process state suppresses it.

Preview a startup check without changing the model:

```bash
python3 cmfgen_run.py /path/to/model --plan \
  --stage test --fresh-start \
  --cmfgen-root /path/to/cur_cmf \
  --atomic-root /path/to/atomic \
  --threads 1 --timeout 60 --memory-mib 2048
```

Execution requires an explicit `--stage`: omit `--plan` from the command above to execute the selected stage with the same options. Use `--stage main` for model iterations and `--stage test` for a zero-iteration startup check. Planning through `--plan` never changes the workspace. Main/test runs continue from usable checkpoints by default, following CMFGEN's native behavior. `--fresh-start` explicitly removes existing `POINT1`, `POINT2`, and `SCRTEMP` before starting from `*_IN`. Recovery retains input files and run evidence rather than binary checkpoints. Use a disposable or staged workspace when trying a new configuration.

### LTE initial populations

For unreliable starting populations, explicitly select **LTE initial populations** on the Model runner page, or preview:

```bash
python3 cmfgen_run.py /path/to/model --stage main --plan \
  --lte-initialization --t-exc 1.0
```

This temporarily sets `VADAT [DC_METH]=LTE` and `[T_EXC]=1.0` (the default when selected), then restores those controls after success, failure, cancellation, or timeout. When the file has no external edits, its original bytes, permissions, and modification time are restored. Unrelated edits made during execution are preserved; edits to the temporary controls themselves are retained and reported as conflicts. The effective `VADAT` is archived in the run journal's `effective/` directory; the original remains in `inputs/`. `--t-exc` uses units of 10⁴ K: `1.0` means 10,000 K for initial excitation estimates, not a constraint on the final atmospheric temperature. Review the value for cooler atmospheres. The option is off by default and applies only to main/test; it does not automatically change `IT_ON_T` or promise convergence.

This method requires `LIN_INT=F` and, if present, `LTE_EST=F`. These controls select compatible initialization paths; adjust them explicitly when needed. A usable checkpoint requires an explicit `--fresh-start` before choosing LTE initialization. That explicitly retires the checkpoint. Recovery retains fresh-run inputs. In sequences the option is forwarded to main/test stages and other stages retain their own controls.

For a persistent choice, **Edit parameters → Quick parameters → Initialization**, below the abundance groups, provides a `DC_METH` selector and a `T_EXC` field. The section is collapsed initially. Missing controls remain unset until explicitly filled, so ordinary stellar/abundance edits do not add initialization settings. Selecting `LTE` requires a positive `T_EXC`; `1.0` means 10,000 K for initial estimates. Review and save the diff through the usual backup workflow.

The selector also supports `POP` (population fractions interpolated in radius) for
the locally patched CMFGEN. The **Initialization** section exposes `LIN_INT`
(interpolate the saved model onto the grid) and `POP_SCALE` (scale initial
populations). Selecting POP sets both switches to `T` in the form; their changes
appear in the review diff and are written only after saving. Switching away
from POP leaves the switches at their current values for you to review. Loading
the editor does not toggle them. The server rejects review or save of POP if
either switch is missing, duplicated, or disabled; with JavaScript unavailable,
set both to `T` manually. Missing switches offer **Unset (leave unchanged)**
until set. Existing values are preserved during unrelated edits.
Changing `LIN_INT` while using LTE also checks
the LTE compatibility requirements above. The consolidated source-fix summary
in `doc/developer/cmfgen-source-fixes.md` records the native implementation and validation.

Population-initialization failures receive suggested LTE recovery steps. Named `SCALE_POPS`/`CNVT_FR_DC` crash frames or the native zero-RGU safeguard provide specific evidence. An opaque fatal crash during fresh initialization is labeled **Possible initial population failure**; `SIGILL` alone is insufficient. On macOS, available `.ips` crash reports are correlated by process name, PID, and report freshness, and only their symbol names are used. Crash reports can arrive after the runner finishes, so a later web/status refresh may provide more specific evidence. A failure after iteration has begun is not assigned this initialization diagnosis. The analyzer is read-only; with `--auto`, its confirmed diagnosis can select the bounded LTE recovery rule below. Ordinary finite runs do not restart themselves.

The automatic registry also supports a bounded **POP initialization** trial for confirmed fresh-start population failures when `LIN_INT=T` and `POP_SCALE=T` are already selected. It requires the patched executable and compatible original saved-model inputs, then verifies ordinary continuation with the original controls restored. It never automatically converts a continuation into a fresh POP start. See [POP initialization recovery](/documentation/main-computation#pop-initialization-recovery) for conditions and limitations. Ordinary runs show the recommendation without applying it.

## Continuation and fresh starts

No `--resume` flag is needed:

```bash
python3 cmfgen_run.py /path/to/model --stage main
```

Preflight reports a `restart` object with the requested policy, detected mode, present files, selected pointer, saved iteration count, and checks. Text progress announces, for example, `Continuation from POINT1 (saved iteration 7, record 2)`. `NUM_ITS`, including `--iterations N`, retains native semantics: iterations to perform in this invocation, not an absolute lifetime iteration target.

The runner checks `POINT1`, falling back to `POINT2` if the first pointer is missing or invalid. A usable pointer and nonempty readable `SCRTEMP` select continuation. No checkpoint files selects a fresh start. An orphan `SCRTEMP` without either pointer also leaves CMFGEN to start fresh, with a warning. Malformed pointers without a usable fallback, missing/empty or obviously truncated scratch data, and unsafe symlinked/hard-linked writable checkpoint files block execution. Repair the checkpoint or use `--fresh-start` to bypass content checks (not filesystem-safety checks).

When `RVTJ` is available for a continuation, preflight also uses its core atmosphere vectors as a checkpoint-health proxy. Its depth count must match `MODEL_SPEC`; radius, velocity, temperature, and electron-density vectors must be complete and finite, with radius, temperature, and electron density positive. A failure blocks continuation as a likely poisoned checkpoint and recommends a known-good checkpoint or `--fresh-start`. Missing `RVTJ` produces a warning rather than rejecting an otherwise usable native checkpoint. Auxiliary radiation fields are deliberately not required because a valid zero-iteration initialization can leave them uncomputed. The checked `RVTJ` is included in the immutable input snapshots.

The runner also checks the **selected binary `SCRTEMP` checkpoint** when it recognizes the native `SCR_READ_V2` layout: `28-Feb-2004` pointers, IEEE binary64 values in 16,376-byte direct-access records, consistent `MODEL`/`MODEL_SPEC` dimensions, and recognizable geometry headers. Both byte orders and `WR_RVS` modes are supported. Truncation, nonfinite populations or geometry, and nonpositive temperature/electron density reject continuation. A stale finite `RVTJ` cannot override this failure. Structured plans report the selected record, layout, counts, and first invalid depth/variable in `restart.binary_health`. Unknown layouts remain explicitly unverified with a warning and retain the text checks above; their binary populations are not certified.

When a recognizable `MODEL` is available, preflight cross-checks its depth count and ion/full-level/superlevel layout against `MODEL_SPEC`. Missing metadata produces a warning rather than a blanket rejection. `DO_HYDRO` or `REV_RGRID` requires a checkpoint with per-iteration radius/velocity/gradient storage (`WR_RVS=T`). These are conservative consistency checks: `MODEL` is not guaranteed checkpoint provenance, and complete atomic-data compatibility remains unverified. A finite checkpoint does not establish convergence.

After every main/test native attempt, the runner repeats the selected binary check and treats explicit NaN/Infinity temperature-gradient, luminosity, or opacity diagnostics as errors, even with zero exit status or tiny correction summaries. Automatic mode's first failure policy, `invalid_numerical_state`, stops for review before any remedy or convergence decision. Existing rollback restores the last accepted automatic snapshot. The runner does not search older binary records, select an earlier iteration, or reseed the continuation automatically.

Continuation does not require the fresh-start `He2_IN`/`GAMMAS_IN` files and does not recreate `T_IN`. Fresh-start structure/gamma and pending LTE-promotion findings are reported as warnings for continuation: the checkpoint, not a newly prepared input structure, supplies the starting state. If native checkpoint loading falls back to startup, missing fresh-start inputs can still make that native run fail.

Existing checkpoint files remain in place for CMFGEN to update during continuation. Ordinary runs do not copy them into recovery storage; automatic mode retains a rolling full checkpoint as described below. Explicit `--fresh-start` removes them instead. Snapshots include missing checkpoint paths so newly appeared files invalidate a previously prepared plan. Ordinary recovery stores pre-run input files and bounded diagnostic evidence; it does not provide an exact rollback to an earlier solver iteration.

After execution, `startup_observed` distinguishes native evidence from preflight expectations. A matching first iteration counter confirms continuation; the native fresh-start message identifies startup/fallback. A fallback emits a prominent progress warning and is recorded even if the computation otherwise succeeds. When neither marker is available (notably a zero-iteration continuation), the observed mode is `unconfirmed`, not an invented confirmation. Normal native-output validation still applies.

The installation roots must be supplied by CLI options, environment, or configuration; shell setup is not sourced. Planning checks executable availability, required inputs, dimensions, active-ion atomic dependencies, workspace safety, process activity, and free disk space. Shell launchers are optional: their absence, executable permissions, interpreter, setup paths, and other shell commands do not block native execution. Atomic declarations come from an explicit `atomic_links.json`, existing literal atomic links, or packaged ostar defaults. Real missing atomic targets and unsafe destinations still block execution; no shell fallback is used.

Ordinary finite main runs also perform a read-only end-of-run diagnostic. Recognized problems, suggested remedies, and automatic-remedy eligibility appear in the terminal and saved `main_diagnostics` report, without changing controls or restarting. See [End-of-run recommendations](/documentation/main-computation#end-of-run-recommendations) for evidence requirements and multi-batch rules.

## Automatic main-stage convergence

The viewer also exposes this same controller through the **Automatic mode** checkbox on Main Computation and **Automatic main convergence** on the Model runner page. See [Automatic runs in the UI](/documentation/main-computation#automatic-runs-in-the-ui) for detached monitoring, cancellation, and configurable limits.

Opt in from the command line with an explicit `--stage main`:

```bash
# Read-only preview of the policy, starting state, and budgets:
python3 cmfgen_run.py /path/to/model --stage main --auto --plan

# Execute batches and corrective actions, including final verification:
python3 cmfgen_run.py /path/to/model --stage main --auto

# Set batch size, total work limits, threads, and a shared wall-clock limit:
python3 cmfgen_run.py /path/to/model --stage main --auto --iterations 5 \
  --auto-max-attempts 20 --auto-max-iterations 100 --threads 5 --timeout 86400
```

Automatic mode is currently a CLI option; the viewer's ordinary launch form continues to launch the selected finite stage/sequence. Existing native progress remains live, and automatic attempt summaries, decisions, and correction counts are printed between runs. `--json --progress json` exposes both native progress and structured automatic events for other clients.

The default batch size is **5 additional iterations**, independently of the saved `IN_ITS`. With `--auto`, `--iterations` sets the batch size and must be at least 2. Defaults are **100 native attempts** and **500 total iterations**, including verification. Failed attempts conservatively consume their entire requested batch allowance. Attempts stop at either budget; a configured `--timeout` applies to the complete automatic operation. A remaining budget too small to finish a remedy and its verification stops without installing that remedy. `Ctrl-C` or `SIGTERM` stops the child and ends the controller. There is no unlimited retry mode or automatic relaunch after controller/machine failure.

To compute spectra only after verified automatic main convergence, use:

```bash
python cmfgen_run.py MODEL --stage main --stage flux --auto
```

The main-stage batch/work limits apply to automatic main attempts; the wall-clock timeout is shared with spectra. A review-needed stop, exhausted main budget, timeout, or cancellation skips spectra. The model remains reserved across the stage transition. Other automatic stage orders are rejected.

`--auto` is the single switch for unattended operation. **Every registered, tested remedy is enabled automatically**, including hydro-startup recovery; the controller diagnoses the current evidence and chooses the applicable one. No problem-specific recovery flags are needed. The prototype `--auto-hydro-recovery` argument remains accepted as a hidden compatibility alias and adds no behavior. A run proceeds without interactive questions until independently verified numerical convergence, an explicit work limit, cancellation, or a problem with no applicable tested remedy.

The initial policy is deliberately limited to measured numerical conditions:

| Evidence | Automatic response |
| --- | --- |
| Healthy continuation with corrections still decreasing | Continue from the saved checkpoint. |
| Persistent, localized, sign-alternating temperature requests | With `SCALE_OPT=MAJOR`, install depth-local fractional relaxation: `RELAX=0.25`, then `0.125` if necessary. Set local `T_LIM=0.2` so a tighter temperature cap does not suppress the conditional native RELAX branch. |
| Corrections stall across three batches | Request fresh matrices with `COMP_BA=T`, `N_FIX_BA=0`, `FIX_BA=0.0`, and retire `BAMAT`/`BAMATPNT`. Stop for review if already using fresh matrices. |
| Native error explicitly says “incorrect reading of EDDFACTOR” | Restore the latest accepted checkpoint, invalidate generated caches, and retry once. Repeated errors stop. |
| Before execution, a supported EDDFACTOR requested with `COMP_F=F` contains NaN/Infinity | Preserve the cache and metadata as `.bak` files in the action journal and set `COMP_F=T` to regenerate radiation. A generic crash or unrecognized cache layout does not trigger this remedy; `USE_FIXED_J=T` requires review. |
| Confirmed fresh-start population failure before iteration | With compatible initialization controls, try temporary LTE estimates, restore normal controls, and verify continuation; at most one LTE recovery procedure. |
| Luminosity safeguard prevents an explicitly scheduled hydro revision | If the documented eligibility checks below pass, run one temporary guard-off iteration and a mandatory guarded follow-up. |
| Convergence candidate | Run a separate verification batch of up to 3 iterations with fresh Jacobians. |
| Unknown crash, invalid/stale evidence, incompatible continuation, unsupported adjustment, external input edit, or exhausted budget | Stop and record the reason. |

Oscillation detection uses complete temperature-request vectors appended to `STEQ_VALS`; with insufficient vectors it can use several completed-batch RVTJ profiles. It requires repeated sign reversals and a persistent amplitude above the numerical tolerance. A decaying alternating mode does not trigger damping. The affected depth interval must span at most one third of the grid. Existing simple correction ranges are preserved/extended within that limit; other scoped `ADJUST_CORRECTIONS` controls require review to avoid changing their meaning. Models without usable temperature-vector evidence can still continue and undergo convergence verification, but cannot receive an inferred local damping adjustment.

This is a bounded numerical policy, not a general cure for every CMFGEN failure. It does not choose new physical parameters, change atomic data, heating/energy choices, source code, or the executable. Native hydrostatic revisions already requested with `DO_HYDRO=T` may update the structure and its coupled controls as described below. The only temporary safeguard bypass is the narrowly diagnosed hydro procedure below. LTE fallback is limited to confirmed fresh initialization failures and never reseeds a continuation checkpoint. Explicit `--fresh-start`/`--lte-initialization` still apply to initial startup; subsequent accepted checkpoints use continuation. Unrecognized physics or source problems require investigation and a new, specifically tested policy. The complete [automatic rule reference](/documentation/main-computation#automatic-convergence-and-recovery-rules) lists every policy, its conditions, remedy, and limits.

### Automatic LTE initialization recovery

The `lte_initialization` rule requires a confirmed `initial_population_scaling` diagnosis before any solver iteration, a fresh startup plan, and no other diagnosed error. It declines suspected/opaque crashes, failures on continuation checkpoints, and initialization already using LTE. It requires explicit `LIN_INT=F`, `LTE_EST=F` if present, and unambiguous compatible initialization controls; it does not rewrite the interpolation mode.

Once per automatic invocation, it requests 2 iterations using the existing temporary LTE mechanism. A positive finite `VADAT [T_EXC]` is used when present; otherwise the trial uses 1.0 (10,000 K for initial excitation estimates). Original `DC_METH`/`T_EXC` values or absence are restored on every exit. A successful bootstrap must produce refreshed, finite model outputs and a usable checkpoint. Then 2 ordinary continuation iterations must complete with the original initialization controls. Only after both stages pass is the new state committed; failure/cancellation rolls the provisional checkpoint and coupled controls back together. Independent fresh-Jacobian numerical convergence verification remains required afterwards. The full procedure must fit the remaining budgets before it starts.

### Automatic recovery before a scheduled hydrostatic revision

The Bstar3500 investigation of 21 October 2026 identified a luminosity stop **before** a scheduled hydrostatic/grey-temperature revision could execute. One iteration with `STOP_IF_MW=F` allowed that revision; subsequent radiation iterations improved the luminosity consistency. This is a tested startup workaround, not a source patch or a demonstration of convergence. The report did not run the subsequent restored-guard test. The controller therefore requires an actual guarded follow-up before retaining the revised state.

```bash
python3 cmfgen_run.py /path/to/model --stage main --auto --plan
```

Remove `--plan` to run. Automatic mode selects this remedy itself. It permits at most one temporary guard-off iteration per automatic invocation, only after all of these checks:

- Native execution returned zero but stopped with the specific factor-of-two luminosity safeguard; no other diagnosed safeguard/crash is present.
- The invocation continued a previously reviewed checkpoint and stopped before its first population solve. Fresh-start failures are not automatically bridged.
- `DO_HYDRO=T`, `STOP_IF_MW` is enabled, and explicit `HYDRO_DEFAULTS` counters/scheduling (`N_ITS`, `ITS_DONE`, `STRT_ITS`, `FREQ_ITS`) show a revision due at that iteration.
- Fresh, complete, finite stellar `OBSFLUX` and `MEANOPAC` profiles corroborate the deficit and establish inner Rosseland optical depth **at least 30**. Unknown/shallow optical depth is refused because the same flag also disables that safeguard.
- The remaining iteration/attempt budgets cover both the one-iteration bridge and a guarded follow-up.

`STOP_IF_MW=F` is a temporary, journaled native-run override. The runner restores the original enabled setting (including its enabled native default if originally absent) on success, failure, timeout, or cancellation, preserving unrelated native control updates. The bridge must complete exactly one hydro revision, produce finite final output and a matching checkpoint, and show consistent hydro counters and a valid new `RVSIG_COL`. It cannot establish convergence.

The next invocation requests two additional radiation/population iterations with the safeguard **enabled**. It must complete normally with fresh luminosity ratios all within `[0.5, 2]` and inner optical depth at least 30. The lesser 25% luminosity warning and other scientific-quality checks remain advisory. A failed/interrupted follow-up, or a budget stop before it completes, rolls back the provisional checkpoint **and its coupled controls** together. External edits that prevent safe rollback are reported for manual recovery. The controller never leaves the flag disabled merely to keep iterating.

The automatic runner also supports ordinary scheduled native hydro revisions. It journals the native-owned `RSTAR`, `RMAX`, `MASS`, and applicable `LSTAR`/`TEFF` changes alongside `RVSIG_COL` and `HYDRO_DEFAULTS`. Only documented control changes backed by completion messages, valid grid output, and matching `ITS_DONE`/`N_ITS` deltas are adopted. Other edits stop for review. The extra saved counter for each hydro/grey revision is distinguished from a radiation/population iteration and does not consume another iteration allowance; unexplained counter gaps still stop the controller. Checkpoints immediately following a revision do not qualify as numerical convergence candidates.

An initially fixed `VADAT [FIX_T]=T` is accepted only when `[DO_T_AUTO]=T` explicitly requests native automatic release. The controller can adopt that native T→F transition after a qualifying full solve; it does not change the release policy itself. Fixed-temperature and Lambda steps still cannot establish convergence.

The controller also preserves CMFGEN's native `IN_ITS [DO_LAM_IT]=T` → `F` transition when `DO_LAM_AUTO` is enabled (including its native enabled default). Adoption requires a completed lambda solve with native maximum change below 50%, immediately followed by a completed full solve. Only the native flag rewrite and its trailing-whitespace normalization are accepted; other input edits still stop for review. The transition remains valid if later corrections rebound and native scheduling returns to lambda steps. `IN_ITS` is journaled and included with checkpoint recovery snapshots; this handoff does not establish convergence or bypass independent verification.

### Acceptance and scientific quality

The model's convergence tolerance is editable under **Edit parameters → Quick
parameters → VADAT → Convergence and solver controls → Convergence tolerance** (`EPS_TERM`).
Enter a positive number in percent: `0.02` means a fractional correction of
`0.0002`. The existing model value is retained until explicitly edited; 0.02%
is an inherited setting in the Bstar/ostar inputs, not a universal accuracy
requirement. Smaller values request tighter solver convergence. This tolerance
does not specify spectral accuracy or energy-balance accuracy. Changes use the
usual reviewed diff and recoverable backup workflow.

The same section exposes `MAX_LIN`, the full-iteration population correction
limit (a factor greater than 1), and `MAX_dT`, the temperature correction limit
(a fraction in `(0, 0.2]`, so `0.05` means 5%). A missing `MAX_dT` stays unset
unless explicitly filled, retaining the native 20% default. `SCALE_OPT=NONE`
always uses a fixed 20% temperature limit.

The **Advanced solver controls** group exposes `COMP_BA`, `N_FIX_BA`,
`FIX_BA`, `SCALE_OPT`, and `MAX_LAM`. With `COMP_BA=T` and `N_FIX_BA=0`, the solver computes a fresh Jacobian on
every full iteration, even with a positive `FIX_BA`. The reuse count and freeze threshold
both affect matrix computation. `FIX_BA` is in percent; `MAX_LAM` is a factor
greater than 1 for Lambda population updates. `SCALE_OPT` selects MAJOR, LOCAL,
GLOBAL, or NONE correction scaling. These settings control damping and matrix
reuse separately from the convergence tolerance. Automatic recovery and
verification can adjust solver controls as documented above.

Automatic success requires two final, full, variable-temperature iterations in the independent verification batch, with BA computed on both. The native solver metric **and both absolute raw correction extrema** must be finite and strictly below the model's explicit positive `VADAT [EPS_TERM]` in percent. Relevant `CORRECTION_SUM` counts must agree. Lambda/fixed-temperature steps, small limiter-scaled applied updates, and a small ranked solver metric alone cannot establish convergence.

Each accepted attempt must produce refreshed `OUTGEN`, `CORRECTION_SUM`, and finite RVTJ core vectors, a usable continuation checkpoint matching the logged solver iterations plus explicitly verified hydro/grey or successful Ng acceleration counter increments, and confirmed native continuation when continuation was requested. Ng acceleration advances the saved counter without adding a radiation/population solve; an explicit native success message is required to explain that increment. A convergence candidate needs two final full solves without an intervening or subsequent acceleration. Unexplained gaps and ambiguous evidence still stop for review. Scientific-quality checks are reported separately: numerical success does not certify boundary transfer, hydrostatic structure, spectral stability, or energy closure.

Stall detection compares three complete batches on a consistent structure, using their last full, variable-temperature solves. A native hydro revision clears trend history and excludes the mixed batch from the new baseline; the terminal and journal report this reset. Local temperature oscillation damping also skips hydro-containing batches. Work budgets continue accumulating normally.

CMFGEN's native maximum-change metric saturates at `10,000,000%` for excessive requested population decreases. If any compared metric reaches that level, equality alone cannot establish a stall. The rule instead requires finite uncapped population increase/decrease extrema and also examines available raw temperature-request maxima and correction counts at thresholds at or above `EPS_TERM`. Counts are comparable only when the final solves share the same lambda/fixed-temperature mode. A steady decrease, even if slow, or an improvement exceeding 2% in any comparable diagnostic permits further bounded iteration. Missing raw extrema defer the stall decision. A plateau in all comparable diagnostics still requests the one supported matrix refresh, or stops for review if matrices are already fresh. Decisions record the compared trends and improving diagnostics in their evidence; these checks never establish convergence.

### Journals, recovery, and persistent controls

An automatic run creates a parent `.cmfgen-runs/<timestamp>-auto-<id>/` journal. It contains the versioned policy manifest/plan, `events.jsonl`, `result.json`, per-attempt plans and links to native-run journals, `original-controls/`, and a numbered action directory with its policy identifier, reason, original controls, and exact changes. Each decision includes the ordered policy matches/refusals. The result distinguishes `succeeded`, `needs_review`, `limit_reached`, timeout, and cancellation. Only verified success returns exit code 0; budget/review stops return 1, preflight failures 2, timeout 124, and cancellation 130.

Unhandled problems and budget/review stops also produce **`issue.json` and `issue.md`** containing the stopping reason, policy versions/decisions, executable identity, native diagnostic evidence, and journal/recovery locations. These provide a bounded handoff for reproducing a new problem and adding its validated remedy. The controller does not improvise an untested fix or silently accept an unconverged atmosphere.

Automatic mode additionally keeps **one rolling full recovery snapshot**, including `POINT1`, `POINT2`, `SCRTEMP`, coupled `VADAT`/`RVSIG_COL`/`HYDRO_DEFAULTS`, `ADJUST_CORRECTIONS`, and associated diagnostic/model files. Multi-step remedies also use a temporary step snapshot, allowing a simple registered remedy such as EDDFACTOR recovery to retry a failed step without repeating an already completed guard-off iteration. The original baseline remains available until the complete procedure passes verification. Nested multi-step procedures are unsupported and stop for review. Temporary step snapshots are removed at run end. This is an exception to ordinary compact recovery. Each snapshot replacement requires enough free disk space for the new full copy plus a 64 MiB margin. `recovery.json` identifies the committed baseline. A failed/invalid native attempt restores the appropriate snapshot and invalidates generated BA/radiation caches. Snapshot acceptance includes the restart/finite-core checks and selected-record numerical checks for recognized binary layouts; unsupported binary layouts remain unverified. Never run an external shell job concurrently.

`IN_ITS` batch overrides are temporary and restored by the native runner. Installed `VADAT` matrix controls and `ADJUST_CORRECTIONS` damping **remain installed**, including at a budget/review stop, so a later ordinary continuation retains the working numerical settings. Original controls are retained for manual comparison/reversal while the model is idle; use `plan.json` input snapshots to identify controls that were originally absent. Inspect `result.json` and the recorded recovery directory before manually restoring a checkpoint. External control/executable edits stop further automatic changes and are preserved. The controller reserves the model between attempts, blocking other cooperating launches and edits.

The implementation separates evidence collection (`auto_diagnostics.py`, `auto_hydro.py`), diagnosis/remedy selection (`auto_policies.py`), and guarded execution (`runner_auto.py`). New diagnosed problems and tested remedies are added to the versioned `POLICIES` registry. A policy returns a declarative decision, optionally with a sequence of `RecoveryStep` validators; it never launches a process or writes model files itself. The controller supplies the shared lifecycle, application limits, work budgets, journaling, temporary-control restoration, and provisional rollback. Changes to policy versions invalidate saved previews.

Correction trends restart after an adjustment so a remedy is assessed using new evidence. Slow but consistently decreasing corrections continue; a small rate of improvement alone is not treated as a stall. See `tests/test_auto_policies.py` for registry-only extension, multi-step rollback, and combined-remedy examples, and the developer guide `doc/developer/automatic-convergence-policies.md` for the extension contract.

## Configuration

See [Templates and configuration](/documentation/templates-and-configuration) for installation roots, thread defaults, configuration precedence, and template lookup. The runner reads settings without sourcing shell scripts. Human-readable plans show effective settings; `--verbose` shows their sources, and JSON plans include `configuration_sources`.

## Preparing the LTE workspace

Use the explicit filesystem stage before the first LTE calculation:

```bash
python3 cmfgen_run.py /path/to/model --plan --stage prepare-lte \
  --template-root /path/to/templates
python3 cmfgen_run.py /path/to/model --stage prepare-lte \
  --template-root /path/to/templates
```

`--template-root` names a directory with `lte/GRID_PARAMS`,
`lte/ltebat.sh`, and `lte/HYDRO_PARAMS`; an optional cleanup script
lives at `clean.sh`. Each file is selected independently from the source
model, the explicit directory, model-tree `templates/` directories (nearest
first), then `cmfgen_viewer/data/templates/`. See
[workflow templates](/documentation/templates-and-configuration) for the shared layout and
packaged defaults. There is no `examples/` or `lte2/` compatibility lookup.
Preparation alone requires no native executable or atomic-data configuration. It uses the
same guarded, atomic preparation as the viewer and records a runner journal.
An existing or incomplete `lte/` path is rejected without overwriting it.

The plan lists copies and proposed HYDRO_PARAMS values. Preparation copies the
model's VADAT and MODEL_SPEC, resolves the LTE templates and clean.sh, and preserves
RVSIG_COL as RVSIG_COL_OLD when needed. HYDRO_PARAMS is initialized from VADAT,
including derived REF_R and CON_R. Unsupported inputs retain the template values
with a warning; review them before hydro. CON_R retains the template's radius
ratio and always needs review. Source contents are rechecked under the model
write guard before preparation; changed inputs require a new plan. No scripts
are executed and no native calculation starts during this stage.

## Multi-stage runs

Repeat `--stage` to execute an ordered sequence:

```bash
python3 cmfgen_run.py /path/to/model --plan \
  --stage prepare-lte --stage lte --stage hydro --stage promote-hydro --stage test --stage main --stage flux

python3 cmfgen_run.py /path/to/model \
  --stage prepare-lte --stage lte --stage hydro --stage promote-hydro --stage test --stage main --stage flux
```

The `--plan` mode fully preflights the first stage and records the remaining order. Later stages are deliberately not accepted in advance: each is rebuilt and preflighted immediately before it runs, after the preceding stage has produced and validated its outputs. A stage starts only when its predecessor returned `succeeded` or, for `test`, `tested`. Execution failure, invalid output, timeout, cancellation, or a just-in-time preflight error stops the sequence and leaves all remaining stages unstarted. Duplicate stages are rejected; issue a separate runner command when a stage genuinely needs to be repeated.

Executable settings apply to every native stage in the sequence. `--iterations` applies only to its `main` stage. `--fresh-start` applies only to the first `test` or `main` stage, allowing a following `main` stage to continue from a successful initialization. `--cleanup-file` applies to the sequence's `cleanup` stage. A configured `--timeout` is a shared native-execution budget: elapsed execution is deducted before each subsequent native stage, while filesystem-only preparation/promotion/cleanup does not consume it. With no `--timeout`, the complete sequence remains unlimited.

## Stages

- `prepare-lte`: prepares a new `lte/` workspace as described above. May be the first stage of a sequence; subsequent LTE preflight runs after preparation finishes. Existing workspaces are never overwritten. `--template-root` applies only to this stage.
- `lte`: runs `main_lte.exe` in an already prepared `lte/` directory. Checks its own controls and validates the generated Rosseland table's dimensions, complete rows, and finite nonnegative values. It does not prepare, promote, or automatically run hydro.
- `hydro`: runs `wind_hyd.exe` directly in the prepared `lte/` directory after a successful LTE stage. It requires a complete, finite `ROSSELAND_LTE_TAB`, `HYDRO_PARAMS`, and `MODEL_SPEC`; stale Rosseland tables are rejected. The runner selects PGPLOT's `/null` device, exits the diagnostic plot, requests the `MODEL_SPEC` depth count, and accepts the executable's calculated maximum optical depth. When `OLD_MOD=T`, `lte/RVTJ` is also required and selected. Stdout/stderr is captured as both the journal `process.log` and `lte/WIND_HYD`. Success requires a fresh `RVSIG_COL_NEW` with matching depth count, complete ordered rows, and finite physical grid values. Before running the new-model hydro branch (`OLD_MOD=F`), the plan reads the mean atomic weight from the fresh validated LTE table. Execution automatically aligns `HYDRO_PARAMS [MU_ATOM]` under the model write guard, preserving a recovery checkpoint. The journal retains original and effective controls and records the applied value. Missing or invalid mean-weight metadata blocks this branch. With `OLD_MOD=T`, native hydro obtains mean atomic mass from RVTJ instead. The generated structure is not promoted automatically.
- `promote-hydro`: performs the same guarded LTE/hydro handoff as the web UI without launching an executable or requiring CMFDIST/ATOMIC. Run `python3 cmfgen_run.py /path/to/model --plan --stage promote-hydro` first to review it, then omit `--plan` to execute. It requires fresh LTE and hydro results, extracts the generated radius ratio, synchronizes `lte/VADAT [RMAX]`, copies `ROSSELAND_LTE_TAB`, `RVSIG_COL_NEW`, and `RVSIG_COL` to the model root, patches only generated `RSTAR`/`RMAX` in the current root `VADAT` while preserving other controls and comments, and archives then invalidates incompatible main/restart/radiation state. It also archives known LTE scratch and population files, retaining regular controls, final results, and diagnostics; top-level LTE symbolic links are archived without following their targets; the plan and result report cleanup counts and sizes. See [LTE/hydro workflow](/documentation/lte-hydro) for the candidate policy and independent UI cleanup action. Promotion checks file integrity and freshness, not scientific suitability; review the reported luminosity and radius ratio before running it. An already-promoted identical result is rejected to protect any newer main solution. Executable resource controls such as `--threads`, `--timeout`, `--memory-mib`, and `--no-core-dumps` do not apply. Backups remain under `.cmfgen-viewer-backups/lte-hydro/`, and the runner records the handoff under `.cmfgen-runs/`.
- `main`: runs `cmfgen_dev.exe` using `IN_ITS`, optionally with a temporary positive `--iterations N` override. Main/test preflight requires a complete, finite, nonnegative `ROSSELAND_LTE_TAB` in the model root when `VADAT [DO_HYDRO]=T`, unless `HYDRO_DEFAULTS [N_ITS]=0` explicitly disables further revisions. This applies to continuation too; an `lte/` copy alone is insufficient. The checked table is included in the input snapshot, so changing or removing it invalidates the prepared plan. Requires fresh `MODEL`, `RVTJ`, and `MOD_SUM`, a native finalization record, valid core vectors, and no nonfinite/overflow tokens in `RVTJ`. It does not automatically launch observer synthesis.
- `flux`: runs `cmf_flux.exe` in an already prepared `obs/` directory with `IN_FILE` as stdin. Preflight checks the conventional parent `RVTJ` core vectors and depth count, rejecting NaN temperatures/densities before they can cause misleading native line-profile errors. This is not a complete check of populations or scientific suitability. Runs the reviewed 15, 10, and 20 km/s passes plus continuum by patching the current `CMF_FLUX_PARAM`. If that file is absent, the first pass starts from `CMF_FLUX_PARAM_INIT`. Previous pass overrides are reset to template values; unrelated active-file settings and edits are preserved. Editing `CMF_FLUX_PARAM_INIT` during execution stops subsequent passes. Each pass requires a native completion marker and a fresh, complete, finite spectrum before publishing `obs_fin_15`, `obs_fin_10`, `obs_fin_20`, or `obs_cont`. The frequency heading must provide a point count; the intensity heading may omit it, as in native `OBSFRAME`, but its actual vector length must match exactly. Failure stops subsequent passes. Scientific suitability of the parent model and requested wavelength coverage still require review.
- `cleanup`: performs the viewer's conservative cleanup across the main, LTE, and observer workspaces without launching an executable or requiring CMFDIST/ATOMIC. Preview with `python3 cmfgen_run.py /path/to/model --plan --stage cleanup`; omit `--plan` to archive every listed candidate, or repeat `--cleanup-file NAME` to select model-relative paths such as `BAMAT`, `lte/POPHYD`, and `obs/fort.63`. Each workspace uses its established cleanup policy, including LTE population/scratch files and all top-level symlinks. Other subdirectories, recovery archives, run history, metadata, locks, checkpoints, main products, and the commented-out `EDDFACTOR*` legacy cleanup commands are excluded. Candidates are atomically moved under the run journal's `removed/` directory using model-relative workspace paths, then the input-based recovery policy is applied. Candidate identity and metadata are rechecked under the shared activity/write guard before anything moves.
- `test` (zero-iteration startup check): temporarily sets `NUM_ITS=0` and runs `cmfgen_dev.exe`. It checks native startup and writes initial atmosphere/checkpoint outputs; it does not create or configure a model directory. Requires fresh `MODEL` and text `RVTJ`, matching depth count, and complete finite radius, velocity, temperature, and electron-density vectors. Radius, temperature, and electron density must also be positive. Returns **tested**, not a completed solution. Uncomputed auxiliary diagnostics can be nonfinite; no `MOD_SUM` finalization is required. Passing the startup test alone does not establish scientifically valid spectral-synthesis input.

Successful ordinary execution is distinct from convergence or scientific acceptance. Automatic mode adds the numerical verification described above; scientific acceptance still requires separate review. A zero exit code alone is insufficient: Fortran `STOP` can return zero after an error. Text `RVTJ` is supported; binary variants are not validated by this version.

Observer templates may omit `SOB_EW_LAM_BEG` and `SOB_EW_LAM_END`. The continuum pass overrides these only when present, matching the legacy script's replacement-only edits. Absent bounds retain CMF_FLUX's native defaults (900–50,000 Å in the inspected installation), with Sobolev EW calculations disabled for this pass. Missing required controls and duplicate active controls still fail preflight. Atomic-link extraction reads only literal declarations and ignores unrelated shell commands, including continued `sed` commands. Shell launchers and their hashes are not execution prerequisites.

## Resources and progress

Execution resource controls are opt-in. By default, the runner adds no memory or time limit, inherits the host's core-dump policy, and preserves native/library thread settings. Existing OS, shell, container, or scheduler limits still apply. On Linux, the runner raises the child stack limit to its permitted hard limit because CMFGEN requires a larger stack. On macOS, a fixed internal shell/exec bootstrap raises the inherited soft stack limit to the permitted hard limit before native execution, since attempting that change inside the running Python process can fail. This avoids inheriting a viewer's small stack allowance (commonly about 8 MiB). The bootstrap preserves the process identity, resource limits, and model lock descriptor; it does not source shell setup or execute model scripts. If the permitted stack is still insufficient, review the OS limits and executable's main-thread stack setting, such as `-Wl,-stack_size,0x4000000` (64 MiB) in `F90` and `F90nomp` in `Makefile_definitions`, then relink as needed.

- `--memory-mib MIB` applies a per-child POSIX `RLIMIT_AS` virtual-address-space cap, not an RSS cap (minimum 128 MiB). This option is unsupported on macOS and is rejected during planning, before the model is modified or a child is launched; omit it to inherit host limits. Without it, both inherited address-space limits are preserved. Large models can require substantially more than 4 GiB.
- `--threads N` (or `--nthreads N`), `OMP_NUM_THREADS`, or a `.cmfgenrc` thread setting explicitly selects a positive thread count. When configured, the runner sets OpenMP/OpenBLAS/MKL thread environment variables to that count; otherwise those variables remain as inherited.
- `--no-core-dumps` explicitly disables child core dumps with `RLIMIT_CORE=0`. Without it, both inherited core-dump limits are preserved.
- `--timeout SECONDS` opts into a time limit for smoke tests or supervised jobs. That timeout is shared across all passes and native stages; initial preflight/setup and final archival/validation are outside its budget. Termination can take a few additional seconds.

These settings apply to each native child in single-stage and multi-stage runs and are recorded in the JSON plans. Unset memory, timeout, and thread overrides are represented by `null`; `no_core_dumps` defaults to `false`.

Each child has an owned process group. Timeout, Ctrl-C, and SIGTERM stop that group; the inherited workspace lock remains held while the native executable is alive. This requires a POSIX environment and usable native process visibility through `psutil` (Linux or macOS). Run on the same host/PID namespace as other model jobs: hidden external jobs cannot be reliably excluded.

The no-stage summary separates model information, run status/checkpoint, diagnostics/recommendations, and main-stage preflight with visible headings and blank lines. Findings are numbered with a title, measured evidence, and a `Next:` suggestion; assessment limits follow the findings. This formatting also works without terminal colors and does not change JSON output.

Default output is human-readable: a preflight summary, stage updates, and a final result with elapsed time, pass counts, diagnostics, saved spectrum paths, and the run-report location. `[OK]`, `[WARN]`, and `[ERROR]` distinguish success, warnings, and failures. Colors are enabled automatically on terminals; redirected output stays plain. `--color never` disables colors, `--color always` forces them, and automatic mode respects `NO_COLOR` and `TERM=dumb`.

Repeated warnings across passes are grouped. Unavailable inactive-ion links are summarized rather than listed individually. Failed passes show key problems and the last 12 lines of their captured diagnostic tail. `--verbose` shows all reported warnings, captured diagnostic tails, and additional preflight detail; full native logs remain in the journal.

After each accepted automatic batch, the checkpoint message includes the first and last recorded native solver maximum change, plus its minimum and maximum across that batch, all in percent. Correction-distribution counts and convergence-candidate status follow. Structured `auto_assessment` events retain the per-iteration values in `solver_maximum_changes`.

`--progress text` (the default) reports stage starts, finishes, and warnings on stderr. In an interactive terminal, progress with a reliable current and total value is rendered through `tqdm` for main iterations, LTE frequencies, hydro depth points, CMF_FLUX passes, and multi-stage completion. Main iteration bars count completed solver steps within the latest logged run, matching the workflow monitor: iteration 1 of 5 starts at 0%, and a solver-return message or the next iteration start advances the count. Phases without an estimate run silently between stage messages. The bars use terminal autodetection (`disable=None`); redirected/noninteractive output omits periodic progress updates. `--progress none` suppresses live updates, not preflight diagnostics or the final summary. Human plan output and final run summaries go to stdout; run preflight and live updates normally go to stderr.

JSON output is opt-in for debugging and future workers:

```bash
# Full structured preflight, without launching:
python3 cmfgen_run.py /path/to/model --plan --stage main --json

# One final JSON result on stdout; JSON-lines progress events on stderr:
python3 cmfgen_run.py /path/to/model --stage main --json --progress json
```

The same modes apply to multi-stage runs. The final JSON object contains ordered `stage_results`, `completed_stages`, `remaining_stages`, and `failed_stage` when applicable.

`--json` by itself disables live progress by default. Without a stage, it returns one status object containing model information, `state`, `preflight`, and `ready`, and creates no journal. `--progress json` explicitly selects structured stderr events for an executed stage; with human final output, the preflight summary moves to stdout to keep that event stream clean. Executed actions retain JSON journals (`plan.json`, `result.json`, and `events.jsonl`) independently of terminal output options. Exit codes are unchanged.

No percentage is invented when native output lacks a reliable total. The structured Python event callback remains available for a future UI/progress adapter independently of the terminal renderer.

Exit codes: `0` tested/succeeded (or ready read-only preflight), `1` execution/output-validation failure or automatic budget/review stop, `2` preflight/argument failure, `124` timeout, `130` cancellation.

## Evidence and recovery

Known CMFGEN safeguard failures are explained in the normal terminal summary and read-only status output without requiring `--verbose`. The runner recognizes the insufficient-inner-optical-depth and factor-of-two inner luminosity messages, including Fortran `STOP` with exit code zero. It prints the native evidence and suggested recovery steps before generic missing-output problems. Optical-depth guidance points to `MEANOPAC` and LTE/hydro alignment; flux-accuracy guidance points to `OBSFLUX`, initial temperature refinement (`IT_ON_T`, `GREY_TAU`), starting estimates, and grid resolution. Suggestions do not change inputs or guarantee convergence.

Each pass stores structured `diagnostic_findings` in `result.json` and its `stage_finished` event, with a stable code, severity, explanation, evidence, current controls, suggestions, and diagnostic file links. A major message is a failure when completion is absent and `STOP_IF_MW` is enabled (the native default); completed runs or disabled/ambiguous safeguards retain it as a warning. The 25% luminosity message remains a warning. Appended logs are limited to the latest invocation, and current control values are labeled because they may differ from those used in an older failed run. The web UI uses the same analyzer for its page and live diagnostics API.

Recovery has one input-based storage policy: new journals and cleanup/promotion checkpoints retain complete input files and run history (`plan.json`, `result.json`, `events.jsonl`), plus diagnostic logs bounded to 2 MiB using beginning/end excerpts. Binary checkpoints, calculated products, and scratch files are omitted regardless of size. Required fresh-run inputs, including population files larger than 2 MiB, are kept in full. Working model outputs are preserved. Main/test journals include a hashed fresh-input manifest: History offers **Restore inputs for a fresh run** only for a complete, intact input set with available unchanged external dependencies. Promotion and cleanup retain complete rollback copies until their transaction succeeds. Existing journals and backups are unchanged automatically. Use the model toolbar’s **History** page to inspect or download archived files, compare controls, preview eligible fresh-input recovery, and explicitly compact or delete selected old archives. See [History and recovery](/documentation/getting-started#history-and-recovery).

The same fixed policy applies to UI-launched and command-line operations. There is no full-state retention option. Existing full-size archives remain browsable and may be explicitly compacted or deleted from History.

Every executed runner action creates `.cmfgen-runs/<UTC-time>-<id>/` containing:

- `plan.json`, updated `result.json`, and timestamped `events.jsonl`;
- retained input files, a `fresh-inputs.json` bundle manifest for main/test, and previous atomic-link targets in `links-before.json`;
- for executable stages, each pass's bounded stdout/stderr `process.log`, native diagnostics, and effective overridden control file;
- `before/` copies of retained input files and old diagnostic logs;

A promotion journal records its plan, events, final result, synchronized `RMAX` and (when reported) core radius `RSTAR`, promoted and invalidated filenames, and the path to the separate recovery backup. Synchronizing `RSTAR` preserves the generated hydro structure's radius scale. A cleanup journal retains eligible removed files and symlinks under `removed/`, records discarded calculated state and scratch files, and reports that recovery path.

A multi-stage invocation adds a parent sequence journal containing the requested order, orchestration events, the initial plan, each just-in-time `stage-NN-NAME-plan.json`, and the aggregate result. Every stage that actually starts also retains its normal detailed child journal; the aggregate `stage_results` link those reports. A stage rejected during just-in-time preflight has no child execution journal because nothing was launched.

Temporary `IN_ITS` or `CMF_FLUX_PARAM` overrides are restored after normal completion, failure, timeout, or handled cancellation. Restoration patches only runner-owned values, preserving unrelated edits and comments. Original bytes and timestamps are restored only when there were no external edits. Changes, duplicate rows, or deletions affecting runner-owned controls stop subsequent passes and appear as conflicts in the terminal, journal, and web result; safe controls are still restored. An externally removed file stays removed. A runner-created control file is deleted only when it has no external edits. A main run without overrides does not rewrite `IN_ITS`. SIGKILL, host failure, or disk failure can prevent restoration: consult the archived input/effective-control copies. Named spectra are published with atomic replacement only after validation. Old named spectra are backed up.

Before **every** flux pass, including the first pass of a rerun, the runner retires `EDDFACTOR`, `EDDFACTOR_INFO`, `ES_J_CONV`, `ES_J_CONV_INFO`, `J_COMP`, `MEANOPAC`, and `TRANS_INFO` into that pass's `before/` archive when present. These are grid/profile-dependent observer caches: retaining them in place can cause incompatible-depth failures or reuse radiation data from a different pass. Retired caches are discarded regardless of size. This implements the terminal workflow's cold-cache behavior. Explicit warm-cache/resume workflows are not supported.

Executable stages retain installed atomic links and other native scratch/diagnostic files; cleanup occurs only through the explicit `cleanup` stage and its reviewed candidate list. Native executables still write directly into the selected workspace. Selected backups are **not** a full directory snapshot or transactional rollback, and the child is **not** sandboxed against arbitrary filesystem writes. Use trusted executables and input workspaces. Unknown symlinks and unsafe known output targets are refused, but these checks are not a general security sandbox.

Inputs and the executable are rechecked under the viewer's shared advisory lock before mutation. Files up to 2 MiB use SHA-256 plus metadata; larger files use metadata only. Atomic data content is not comprehensively hashed or scientifically validated. External scripts do not honor this lock and must not be launched concurrently. Journals are retained for inspection, not cryptographically immutable provenance.

## Updating a tabulated hydrostatic structure

For models using `VEL_OPT=RVSIG_COL`, saving changes to mass loss (`MDOT`), core
radius (`RSTAR`), the velocity law (including `BETA` or `VINF`), or
`MODEL_SPEC [ND]` does not rebuild the structure file. The CMFGEN manual
(`web/full_descr.tex`, new-model instructions) explicitly requires reviewing or
updating `RVSIG_COL` for these changes. Abundance, `LOGG`, model-atom, and species
changes alone do not require this particular update; other preparation and
reconvergence requirements still apply.

Both quick and text editor reviews, and CLI `set --plan`, warn about relevant
changes. Before the first such save, the viewer retains the original VADAT,
MODEL_SPEC, and RVSIG_COL contents in `.cmfgen-structure-update.json`. Subsequent
pending edits retain that original baseline. Resolved baselines are inactive:
ordinary native hydro revisions after an update do not create a new editor
warning, and the next relevant editor save captures a fresh baseline.
The editor shows a persistent **Structure
update required** notice and main/test preflight blocks execution until the
structure is reviewed/applied, including continuation that would otherwise
restore the old grid from a binary checkpoint. Numerically equivalent notation
changes and fully reverted parameter changes do not require an update.
Tracking applies to edits through these tools; external edits made before any
baseline was captured cannot be diagnosed from this metadata.

Use **Edit Parameters → Update structure** after saving the desired controls.
The guided action runs the configured `exe/rev_rvsig.exe` in a temporary
directory, using the saved old structure and parameters and the current target
parameters. It supports native `MDOT`, `SCLR`, and `NEW_ND` operations, composing
a physical/velocity update with a depth-count update when necessary. The reader's
simple radius normalization is applied to the baseline before native revision.
The supported wind prescriptions are types 1, 2, and 6; choose a suitable
connection velocity explicitly (the form suggests 10 km/s). Type 6 retains the
outer velocity law and cannot implement BETA/VINF changes. Connection velocities
that would produce an unsafe native search are rejected. Native plots use the
null device. A timeout, unsuccessful exit, or invalid output leaves the model
unchanged.

For other wind prescriptions, changed outer-radius controls, density/clumping
input structures, or a missing/externally changed baseline, prepare a candidate
manually with `rev_rvsig.exe`, `wind_hyd.exe`, or another appropriate method and
upload it on the same page. This checks the candidate's grid and endpoints; it
does not establish that the chosen physical structure is appropriate.

The review displays the resulting grid dimensions and endpoints, a complete
structure diff, native operation logs, any accompanying `VADAT [RMAX]` update,
and any increase of `MODEL_SPEC [NP]` needed to keep `NP >= ND + NC`,
and the checkpoint/cache files to retire. Applying verifies that all inputs and
checkpoints still match the review, requires an idle model, backs up replaced
files, and archives `POINT1`, `POINT2`, `SCRTEMP`, `BAMAT`, `BAMATPNT`,
`EDDFACTOR`, and `J_COMP` when present. Installation failures roll back the
structure, coupled controls, metadata, and archived checkpoints together.
Recovery copies and the operation record are kept under
`.cmfgen-viewer-backups/structure-<timestamp>-<id>/`. The update-required notice
clears only after successful installation or full reversion of the tracked
parameter changes. Preserve the metadata file while an update is pending.
Model creation/copy carries this baseline into the destination; ordinary and
full cleanup preserve it so they cannot silently discard a pending structure
dependency. An externally running `rev_rvsig.exe` in the model directory also
counts as model activity and prevents concurrent editor writes.

The equivalent CLI workflow is:

```sh
# Save desired parameters; the warning and original baseline are retained.
python3 cmfgen_model.py set /path/to/model MDOT=2e-8

# Generate a candidate for review without changing the model.
python3 cmfgen_model.py structure /path/to/model --plan \
  --velocity-type 2 --connection-velocity 10 \
  --review-file /tmp/structure-review.json

# Or review a manually prepared candidate.
python3 cmfgen_model.py structure /path/to/model \
  --candidate /path/to/RVSIG_COL_NEW --review-file /tmp/manual-review.json

# Apply the exact reviewed candidate; stale reviews are rejected.
python3 cmfgen_model.py structure /path/to/model --apply /tmp/structure-review.json
```

To generate, validate, and apply the revision in one command, use `--execute`:

```sh
python3 cmfgen_model.py structure /path/to/model --execute \
  --velocity-type 2 --connection-velocity 10
```

This resolves pending parameter edits using the saved pre-edit baseline. It
uses the same native generation, candidate validation, idle-model and unchanged-
input checks, coupled-control updates, backups, and checkpoint/cache retirement
as the separate review/apply workflow. Unsupported or ambiguous changes still
stop. It does not launch an atmosphere calculation or prepare population inputs.
Without `--execute`, generation remains read-only by default.

`--execute` also works with `--candidate` and the grid-operation options below.
An optional `--review-file` saves the generated plan before installation; the
applied plan is always recorded in the structure backup's `operation.json`.
`--execute`, `--plan`, and `--apply` are mutually exclusive.

Native generation uses the shared `cmfgen_root` configuration or
`--cmfgen-root`. `--review-file` creates a new file and refuses to overwrite an
existing review. Generating a candidate never changes the model. Review files
contain model-control contents and native logs; keep them with the model's
working records.

After application, the next atmosphere run initializes from the **existing text
inputs**. The update action does not export current populations, change
`DC_METH`/`LIN_INT`/`POP_SCALE`, regenerate LTE opacity tables, or certify
hydrostatic equilibrium or numerical convergence. Prepare compatible estimates
before running. In particular, applying after changing ND retires the old binary
checkpoint but does not itself create a new-grid population checkpoint.

### Grid operations on an existing structure

**Update Model Structure → Native revision → Operation** also offers the
following operations without first editing the model controls:

| Operation | Native option | Inputs and effect |
|---|---|---|
| Resample to a new depth count | `NEW_ND` | Choose 3–5000 points. Retains similar overall grid spacing; old interior nodes are generally replaced. |
| Insert points over a depth interval | `NINS` | Choose start/end depth indices and a point count per interval. Index 1 is outermost. Existing radius nodes are retained; new points are equally spaced in radius within each selected interval. |
| Refine the outermost interval | `FGOB` | Choose a total number of new points. Inserts them in the first interval, progressively closer to the outer boundary; the outer endpoint remains unchanged. |
| Insert explicit radii | `ADDR` | Supply unique radii in decreasing order, strictly inside the current grid. Units are 10¹⁰ cm after normalization to `VADAT [RSTAR]`. Existing nodes and endpoints cannot be duplicated. |
| Recalculate sigma | `SIGU` | Recompute `sigma = (r/v) dv/dr - 1` from the existing radius and velocity values using the native monotonic interpolation. No extra parameters are required. |

These actions use the **current** `RVSIG_COL`; parameter-driven revisions use
the saved pre-edit baseline instead. Resolve any pending parameter-driven update
before choosing a separate grid operation. Native interpolation supplies revised
velocities and sigma where needed. Every operation retains the 5000-point limit,
finite/monotonic radius checks, candidate review, stale-input checks, backups,
and checkpoint/cache retirement. Density/clumping input structures and SN or
variable-mass-loss modes still require a prepared candidate.

The review includes the proposed `MODEL_SPEC [ND]` change. `NP` is increased
when necessary to satisfy `NP >= ND + NC`; reducing ND retains existing extra
impact rays. `NC` is preserved. The new controls and structure are applied
together. The selected operation is recorded in the saved review and recovery
record. It does not select a new population-initialization method or prepare
compatible population exports for you.

```sh
# Resample the full grid, then inspect the structure and MODEL_SPEC diffs.
python3 cmfgen_model.py structure /path/to/model --operation new_nd \
  --new-depths 135 --review-file /tmp/resample-review.json

# Insert one point in each of the first ten intervals.
python3 cmfgen_model.py structure /path/to/model --operation insert \
  --start-depth 1 --end-depth 11 --points 1 --review-file /tmp/refine-review.json

# Concentrate two new points close to the outer boundary.
python3 cmfgen_model.py structure /path/to/model --operation outer \
  --points 2 --review-file /tmp/outer-review.json

# Explicit radii must be appropriate to your model's normalized radius range.
python3 cmfgen_model.py structure /path/to/model --operation radii \
  --radii '44300, 44000' --review-file /tmp/radii-review.json

python3 cmfgen_model.py structure /path/to/model --operation sigma \
  --review-file /tmp/sigma-review.json

# Apply only the chosen reviewed operation.
python3 cmfgen_model.py structure /path/to/model --apply /tmp/refine-review.json
```

The interactive cursor editor, optical-depth redistribution, outer-radius
extension, and additional wind-law/geometry conversions remain available through
the native utility and the prepared-candidate workflow. They are not exposed as
guided actions here.

### RVSIG_COL numerical consistency checks

Preflight checks native three-column R/V/sigma files and standard indexed
exports with an optional Tau column or density/clumping columns. It reports
malformed rows and nonfinite values (including NaN, infinity, and numeric
overflow), nonpositive radius/velocity, and repeated or reversed radii as
errors. Density and clumping columns, when present in the six-column format,
must also be positive. Existing ND/row-count, index-sequence, RMAX-ratio, and
outer-velocity checks remain in effect. Pure radius normalization to RSTAR is
allowed; a different absolute inner radius alone is not an inconsistency.

Nonmonotonic or repeated velocities and sigma below -1 generate **warnings**,
not errors: the native reader warns about nonmonotonic velocity laws. Sigma
of -1 is valid for constant velocity. Findings include the first affected file
line. No check changes the file. Continuation runs retain the existing policy
that fresh-start RVSIG_COL input errors are advisory when the grid instead
comes from a binary checkpoint; a tracked pending structure update still blocks
execution until resolved.

A further advisory compares `sigma + 1` with the numerical logarithmic velocity
gradient at interior depths. It uses a three-point derivative on the possibly
uneven log-radius grid. To avoid interpreting rounding noise or unresolved
curvature as a stale sigma column, the screen:

- Requires both neighboring radius and velocity differences to exceed 20 times
  the estimated text-rounding uncertainty, using half of each token's last
  printed digit. Fortran D and missing-E notation are supported.
- Skips intervals whose two secant slopes have different signs or differ by
  more than 50% of the larger magnitude.
- Reports a discrepancy only when its absolute magnitude exceeds both **0.5**
  and **50% of the larger gradient magnitude**. Endpoints are not tested.

These deliberately loose screening thresholds flag gross mismatches; they are
heuristics, not native CMFGEN acceptance tolerances or a physical error estimate.
A warning suggests reviewing the velocity profile or using **Update structure →
Recalculate sigma**. Absence of a warning does not establish derivative accuracy
in coarse or low-precision regions. The checks cannot infer the intended MDOT
or BETA from R/V/sigma alone, and historical header comments are not treated as
proof of physical consistency.


After independent fresh-Jacobian verification succeeds, automatic mode restores
`N_FIX_BA` and `FIX_BA` from the start of that automatic run, and retains
`COMP_BA=T` so a later invocation computes its initial matrix afresh. Other
accepted recovery settings are retained. The restoration is recorded in the
action journal and rolling recovery controls; it does not change the verified
checkpoint. Runs stopped before successful verification keep the fresh-matrix
policy. Starting with zero reuse still leaves zero reuse; automatic mode does
not choose faster defaults. The parameter editor explains and highlights this
configuration, opening the advanced controls when reuse is disabled.

Automatic main runs also include bounded performance trials after three healthy,
improving full-solve batches. They can test one reused BA iteration or gradually
release damping introduced by the current automatic run. Trial state stays
provisional; adverse corrections, counts, temperature behavior or physical checks
restore the conservative checkpoint and controls. Missing scientific evidence
skips these optimizations, and unknown native failures still stop for review.
Final acceptance continues to require independent fresh-Jacobian verification.
See [conditions, budgets and rollback](/documentation/main-computation#guarded-performance-trials-during-automatic-iteration).
