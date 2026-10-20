# Command-line runner

`cmfgen_run.py` runs a reviewed subset of the ostar workflows directly in Python. It never executes `batch.sh`, `batobs.sh`, sourced setup scripts, or arbitrary shell commands. The same runner can be launched from the viewer as an independent process.

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

Preview a startup check without changing the model:

```bash
python3 cmfgen_run.py /path/to/model --plan \
  --stage test --fresh-start \
  --cmfgen-root /path/to/cur_cmf \
  --atomic-root /path/to/atomic \
  --threads 1 --timeout 60 --memory-mib 2048
```

Execution requires an explicit `--stage`: omit `--plan` from the command above to execute the selected stage with the same options. Use `--stage main` for model iterations and `--stage test` for a zero-iteration startup check. Planning through `--plan` never changes the workspace. Main/test runs continue from usable checkpoints by default, following CMFGEN's native behavior. `--fresh-start` explicitly moves existing `POINT1`, `POINT2`, and `SCRTEMP` into that run's `restart-before/` archive before starting from `*_IN`. Recovery retention follows the size policy below; enable `--keep-large-files` to retain full-size checkpoints. Retained checkpoints are not automatically restored over newly generated restart state. Use a disposable or staged workspace when trying a new configuration.

### LTE initial populations

For unreliable starting populations, explicitly select **LTE initial populations** on the Model runner page, or preview:

```bash
python3 cmfgen_run.py /path/to/model --stage main --plan \
  --lte-initialization --t-exc 1.0
```

This temporarily sets `VADAT [DC_METH]=LTE` and `[T_EXC]=1.0` (the default when selected), then restores those controls after success, failure, cancellation, or timeout. When the file has no external edits, its original bytes, permissions, and modification time are restored. Unrelated edits made during execution are preserved; edits to the temporary controls themselves are retained and reported as conflicts. The effective `VADAT` is archived in the run journal's `effective/` directory; the original remains in `inputs/`. `--t-exc` uses units of 10⁴ K: `1.0` means 10,000 K for initial excitation estimates, not a constraint on the final atmospheric temperature. Review the value for cooler atmospheres. The option is off by default and applies only to main/test; it does not automatically change `IT_ON_T` or promise convergence.

This method requires `LIN_INT=F` and, if present, `LTE_EST=F`. These controls select compatible initialization paths; adjust them explicitly when needed. A usable checkpoint requires an explicit `--fresh-start` before choosing LTE initialization. That explicitly retires the checkpoint, with recovery retention controlled by `--keep-large-files`. In sequences the option is forwarded to main/test stages and other stages retain their own controls.

For a persistent choice, **Edit parameters → Quick parameters → Initialization**, below the abundance groups, provides a `DC_METH` selector and a `T_EXC` field. The section is collapsed initially. Missing controls remain unset until explicitly filled, so ordinary stellar/abundance edits do not add initialization settings. Selecting `LTE` requires a positive `T_EXC`; `1.0` means 10,000 K for initial estimates. Review and save the diff through the usual backup workflow.

Population-initialization failures now receive suggested LTE recovery steps. Named `SCALE_POPS`/`CNVT_FR_DC` crash frames or the native zero-RGU safeguard provide specific evidence. An opaque fatal crash during fresh initialization is labeled **Possible initial population failure**; `SIGILL` alone is insufficient. On macOS, available `.ips` crash reports are correlated by process name, PID, and report freshness, and only their symbol names are used. Crash reports can arrive after the runner finishes, so a later web/status refresh may provide more specific evidence. A failure after iteration has begun is not assigned this initialization diagnosis. The analyzer does not change model inputs or restart a failed run automatically.

## Continuation and fresh starts

No `--resume` flag is needed:

```bash
python3 cmfgen_run.py /path/to/model --stage main
```

Preflight reports a `restart` object with the requested policy, detected mode, present files, selected pointer, saved iteration count, and checks. Text progress announces, for example, `Continuation from POINT1 (saved iteration 7, record 2)`. `NUM_ITS`, including `--iterations N`, retains native semantics: iterations to perform in this invocation, not an absolute lifetime iteration target.

The runner checks `POINT1`, falling back to `POINT2` if the first pointer is missing or invalid. A usable pointer and nonempty readable `SCRTEMP` select continuation. No checkpoint files selects a fresh start. An orphan `SCRTEMP` without either pointer also leaves CMFGEN to start fresh, with a warning. Malformed pointers without a usable fallback, missing/empty or obviously truncated scratch data, and unsafe symlinked/hard-linked writable checkpoint files block execution. Repair the checkpoint or use `--fresh-start` to bypass content checks (not filesystem-safety checks).

When `RVTJ` is available for a continuation, preflight also uses its core atmosphere vectors as a checkpoint-health proxy. Its depth count must match `MODEL_SPEC`; radius, velocity, temperature, and electron-density vectors must be complete and finite, with radius, temperature, and electron density positive. A failure blocks continuation as a likely poisoned checkpoint and recommends a known-good checkpoint or `--fresh-start`. Missing `RVTJ` produces a warning rather than rejecting an otherwise usable native checkpoint. Auxiliary radiation fields are deliberately not required because a valid zero-iteration initialization can leave them uncomputed. The checked `RVTJ` is included in the immutable input snapshots.

When a recognizable `MODEL` is available, preflight cross-checks its depth count and ion/full-level/superlevel layout against `MODEL_SPEC`. Missing metadata produces a warning rather than a blanket rejection. `DO_HYDRO` or `REV_RGRID` requires a checkpoint with per-iteration radius/velocity/gradient storage (`WR_RVS=T`). These are conservative consistency checks: `MODEL` is not guaranteed checkpoint provenance, and binary record layout, population values, and complete atomic-data compatibility remain unverified.

Continuation does not require the fresh-start `He2_IN`/`GAMMAS_IN` files and does not recreate `T_IN`. Fresh-start structure/gamma and pending LTE-promotion findings are reported as warnings for continuation: the checkpoint, not a newly prepared input structure, supplies the starting state. If native checkpoint loading falls back to startup, missing fresh-start inputs can still make that native run fail.

Existing checkpoint files within the recovery size limit are copied to `restart-before/` before an automatic-mode run (`--keep-large-files` retains all sizes); they remain in place for CMFGEN to update. Preflight checks space for this backup plus the usual 1 GiB working headroom. Explicit `--fresh-start` moves them instead. Snapshots include missing checkpoint paths so newly appeared files invalidate a previously prepared plan. Backups are not automatically rolled back after failure: the new files may contain useful progress, and retained old versions remain available in the journal.

After execution, `startup_observed` distinguishes native evidence from preflight expectations. A matching first iteration counter confirms continuation; the native fresh-start message identifies startup/fallback. A fallback emits a prominent progress warning and is recorded even if the computation otherwise succeeds. When neither marker is available (notably a zero-iteration continuation), the observed mode is `unconfirmed`, not an invented confirmation. Normal native-output validation still applies.

The installation roots must be supplied by CLI options, environment, or configuration; shell setup is not sourced. Planning checks executable availability, required inputs, dimensions, active-ion atomic dependencies, workspace safety, process activity, and free disk space. Shell launchers are optional: their absence, executable permissions, interpreter, setup paths, and other shell commands do not block native execution. Atomic declarations come from an explicit `atomic_links.json`, existing literal atomic links, or packaged ostar defaults. Real missing atomic targets and unsafe destinations still block execution; no shell fallback is used.

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
- `main`: runs `cmfgen_dev.exe` using `IN_ITS`, optionally with a temporary positive `--iterations N` override. Requires fresh `MODEL`, `RVTJ`, and `MOD_SUM`, a native finalization record, valid core vectors, and no nonfinite/overflow tokens in `RVTJ`. It does not automatically launch observer synthesis.
- `flux`: runs `cmf_flux.exe` in an already prepared `obs/` directory with `IN_FILE` as stdin. Preflight checks the conventional parent `RVTJ` core vectors and depth count, rejecting NaN temperatures/densities before they can cause misleading native line-profile errors. This is not a complete check of populations or scientific suitability. Runs the reviewed 15, 10, and 20 km/s passes plus continuum by patching the current `CMF_FLUX_PARAM`. If that file is absent, the first pass starts from `CMF_FLUX_PARAM_INIT`. Previous pass overrides are reset to template values; unrelated active-file settings and edits are preserved. Editing `CMF_FLUX_PARAM_INIT` during execution stops subsequent passes. Each pass requires a native completion marker and a fresh, complete, finite spectrum before publishing `obs_fin_15`, `obs_fin_10`, `obs_fin_20`, or `obs_cont`. The frequency heading must provide a point count; the intensity heading may omit it, as in native `OBSFRAME`, but its actual vector length must match exactly. Failure stops subsequent passes. Scientific suitability of the parent model and requested wavelength coverage still require review.
- `cleanup`: performs the viewer's conservative cleanup across the main, LTE, and observer workspaces without launching an executable or requiring CMFDIST/ATOMIC. Preview with `python3 cmfgen_run.py /path/to/model --plan --stage cleanup`; omit `--plan` to archive every listed candidate, or repeat `--cleanup-file NAME` to select model-relative paths such as `BAMAT`, `lte/POPHYD`, and `obs/fort.63`. Each workspace uses its established cleanup policy, including LTE population/scratch files and all top-level symlinks. Other subdirectories, recovery archives, run history, metadata, locks, checkpoints, main products, and the commented-out `EDDFACTOR*` legacy cleanup commands are excluded. Candidates are atomically moved under the run journal's `removed/` directory using model-relative workspace paths, then the selected recovery size policy is applied. Candidate identity and metadata are rechecked under the shared activity/write guard before anything moves.
- `test` (zero-iteration startup check): temporarily sets `NUM_ITS=0` and runs `cmfgen_dev.exe`. It checks native startup and writes initial atmosphere/checkpoint outputs; it does not create or configure a model directory. Requires fresh `MODEL` and text `RVTJ`, matching depth count, and complete finite radius, velocity, temperature, and electron-density vectors. Radius, temperature, and electron density must also be positive. Returns **tested**, not a completed solution. Uncomputed auxiliary diagnostics can be nonfinite; no `MOD_SUM` finalization is required. Passing the startup test alone does not establish scientifically valid spectral-synthesis input.

Successful execution is distinct from convergence or scientific acceptance. Every report explicitly leaves scientific acceptance unassessed. A zero exit code alone is insufficient: Fortran `STOP` can return zero after an error. Text `RVTJ` is supported; binary variants are not validated by this version.

Observer templates may omit `SOB_EW_LAM_BEG` and `SOB_EW_LAM_END`. The continuum pass overrides these only when present, matching the legacy script's replacement-only edits. Absent bounds retain CMF_FLUX's native defaults (900–50,000 Å in the inspected installation), with Sobolev EW calculations disabled for this pass. Missing required controls and duplicate active controls still fail preflight. Atomic-link extraction reads only literal declarations and ignores unrelated shell commands, including continued `sed` commands. Shell launchers and their hashes are not execution prerequisites.

## Resources and progress

Execution resource controls are opt-in. By default, the runner adds no memory or time limit, inherits the host's core-dump policy, and preserves native/library thread settings. Existing OS, shell, container, or scheduler limits still apply. On Linux, the runner raises the child stack limit to its permitted hard limit because CMFGEN requires a larger stack. On macOS, a fixed internal shell/exec bootstrap raises the inherited soft stack limit to the permitted hard limit before native execution, since attempting that change inside the running Python process can fail. This avoids inheriting a viewer's small stack allowance (commonly about 8 MiB). The bootstrap preserves the process identity, resource limits, and model lock descriptor; it does not source shell setup or execute model scripts. If the permitted stack is still insufficient, review the OS limits and executable's main-thread stack setting, such as `-Wl,-stack_size,0x4000000` (64 MiB) in `F90` and `F90nomp` in `Makefile_definitions`, then relink as needed.

- `--memory-mib MIB` applies a per-child POSIX `RLIMIT_AS` virtual-address-space cap, not an RSS cap (minimum 128 MiB). This option is unsupported on macOS and is rejected during planning, before the model is modified or a child is launched; omit it to inherit host limits. Without it, both inherited address-space limits are preserved. Large models can require substantially more than 4 GiB.
- `--threads N` (or `--nthreads N`), `OMP_NUM_THREADS`, or a `.cmfgenrc` thread setting explicitly selects a positive thread count. When configured, the runner sets OpenMP/OpenBLAS/MKL thread environment variables to that count; otherwise those variables remain as inherited.
- `--no-core-dumps` explicitly disables child core dumps with `RLIMIT_CORE=0`. Without it, both inherited core-dump limits are preserved.
- `--timeout SECONDS` opts into a time limit for smoke tests or supervised jobs. That timeout is shared across all passes and native stages; initial preflight/setup and final archival/validation are outside its budget. Termination can take a few additional seconds.

These settings apply to each native child in single-stage and multi-stage runs and are recorded in the JSON plans. Unset memory, timeout, and thread overrides are represented by `null`; `no_core_dumps` defaults to `false`.

Each child has an owned process group. Timeout, Ctrl-C, and SIGTERM stop that group; the inherited workspace lock remains held while the native executable is alive. This requires a POSIX environment and usable native process visibility through `psutil` (Linux or macOS). Run on the same host/PID namespace as other model jobs: hidden external jobs cannot be reliably excluded.

Default output is human-readable: a preflight summary, stage updates, and a final result with elapsed time, pass counts, diagnostics, saved spectrum paths, and the run-report location. `[OK]`, `[WARN]`, and `[ERROR]` distinguish success, warnings, and failures. Colors are enabled automatically on terminals; redirected output stays plain. `--color never` disables colors, `--color always` forces them, and automatic mode respects `NO_COLOR` and `TERM=dumb`.

Repeated warnings across passes are grouped. Unavailable inactive-ion links are summarized rather than listed individually. Failed passes show key problems and the last 12 lines of their captured diagnostic tail. `--verbose` shows all reported warnings, captured diagnostic tails, and additional preflight detail; full native logs remain in the journal.

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

Exit codes: `0` tested/succeeded (or ready read-only preflight), `1` execution or output-validation failure, `2` preflight/argument failure, `124` timeout, `130` cancellation.

## Evidence and recovery

Known CMFGEN safeguard failures are explained in the normal terminal summary and read-only status output without requiring `--verbose`. The runner recognizes the insufficient-inner-optical-depth and factor-of-two inner luminosity messages, including Fortran `STOP` with exit code zero. It prints the native evidence and suggested recovery steps before generic missing-output problems. Optical-depth guidance points to `MEANOPAC` and LTE/hydro alignment; flux-accuracy guidance points to `OBSFLUX`, initial temperature refinement (`IT_ON_T`, `GREY_TAU`), starting estimates, and grid resolution. Suggestions do not change inputs or guarantee convergence.

Each pass stores structured `diagnostic_findings` in `result.json` and its `stage_finished` event, with a stable code, severity, explanation, evidence, current controls, suggestions, and diagnostic file links. A major message is a failure when completion is absent and `STOP_IF_MW` is enabled (the native default); completed runs or disabled/ambiguous safeguards retain it as a warning. The 25% luminosity message remains a warning. Appended logs are limited to the latest invocation, and current control values are labeled because they may differ from those used in an older failed run. The web UI uses the same analyzer for its page and live diagnostics API.

Large recovery storage is **opt-in**. By default, new journals and cleanup/promotion checkpoints omit scientific artifacts above **2 MiB per file** and retain the beginning and end of large diagnostic logs, bounded to 2 MiB. Run history (`plan.json`, `result.json`, `events.jsonl`), small input snapshots, and the full working model outputs are preserved. Promotion and cleanup retain complete rollback copies until their transaction succeeds. Existing journals and backups are unchanged automatically. Use the model toolbar’s **History** page to inspect or download archived files, compare controls, preview eligible native restart recovery, and explicitly compact or delete selected old archives. See [History and recovery](/documentation/getting-started#history-and-recovery).

Use `--keep-large-files` to keep complete artifacts and diagnostic logs for a run or sequence. The Model runner and LTE cleanup/promotion forms provide the same checkbox. Set `keep_large_files = true` in `.cmfgenrc` (or viewer JSON/TOML configuration) to opt in by default; explicit `--no-keep-large-files` overrides that setting. The plan/review shows the selected policy.

Every executed runner action creates `.cmfgen-runs/<UTC-time>-<id>/` containing:

- `plan.json`, updated `result.json`, and timestamped `events.jsonl`;
- copies of small startup inputs and the previous atomic-link targets in `links-before.json`;
- for executable stages, each pass's stdout/stderr `process.log`, native diagnostics, selected products, and effective overridden control file;
- `before/` copies of selected pre-existing products and moved old logs;
- `restart-before/` retained checkpoint copies for automatic-mode runs, or retired checkpoints for explicit `--fresh-start`, subject to the recovery size policy.

A promotion journal records its plan, events, final result, synchronized `RMAX` and (when reported) core radius `RSTAR`, promoted and invalidated filenames, and the path to the separate recovery backup. Synchronizing `RSTAR` preserves the generated hydro structure's radius scale. A cleanup journal retains eligible removed files and symlinks under `removed/`, records discarded large files, and reports that recovery path.

A multi-stage invocation adds a parent sequence journal containing the requested order, orchestration events, the initial plan, each just-in-time `stage-NN-NAME-plan.json`, and the aggregate result. Every stage that actually starts also retains its normal detailed child journal; the aggregate `stage_results` link those reports. A stage rejected during just-in-time preflight has no child execution journal because nothing was launched.

Temporary `IN_ITS` or `CMF_FLUX_PARAM` overrides are restored after normal completion, failure, timeout, or handled cancellation. Restoration patches only runner-owned values, preserving unrelated edits and comments. Original bytes and timestamps are restored only when there were no external edits. Changes, duplicate rows, or deletions affecting runner-owned controls stop subsequent passes and appear as conflicts in the terminal, journal, and web result; safe controls are still restored. An externally removed file stays removed. A runner-created control file is deleted only when it has no external edits. A main run without overrides does not rewrite `IN_ITS`. SIGKILL, host failure, or disk failure can prevent restoration: consult the archived input/effective-control copies. Named spectra are published with atomic replacement only after validation. Old named spectra are backed up.

Before **every** flux pass, including the first pass of a rerun, the runner retires `EDDFACTOR`, `EDDFACTOR_INFO`, `ES_J_CONV`, `ES_J_CONV_INFO`, `J_COMP`, `MEANOPAC`, and `TRANS_INFO` into that pass's `before/` archive when present. These are grid/profile-dependent observer caches: retaining them in place can cause incompatible-depth failures or reuse radiation data from a different pass. Small caches are archived; caches above 2 MiB are discarded unless `--keep-large-files` is enabled. This implements the terminal workflow's cold-cache behavior. Explicit warm-cache/resume workflows are not supported.

Executable stages retain installed atomic links and other native scratch/diagnostic files; cleanup occurs only through the explicit `cleanup` stage and its reviewed candidate list. Native executables still write directly into the selected workspace. Selected backups are **not** a full directory snapshot or transactional rollback, and the child is **not** sandboxed against arbitrary filesystem writes. Use trusted executables and input workspaces. Unknown symlinks and unsafe known output targets are refused, but these checks are not a general security sandbox.

Inputs and the executable are rechecked under the viewer's shared advisory lock before mutation. Files up to 2 MiB use SHA-256 plus metadata; larger files use metadata only. Atomic data content is not comprehensively hashed or scientifically validated. External scripts do not honor this lock and must not be launched concurrently. Journals are retained for inspection, not cryptographically immutable provenance.

