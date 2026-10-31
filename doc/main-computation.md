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
| Invalid numerical state — `invalid_numerical_state` | Explicit NaN/Infinity temperature-gradient, luminosity, or opacity diagnostics, or a failed selected binary checkpoint check. An old finite RVTJ and zero correction summaries cannot overrule these findings. | Stop for review before applying remedies or accepting convergence; preserve evidence and restore the accepted automatic snapshot. No search for older records or automatic LTE/POP reseeding. Invalid starting checkpoints are blocked in preflight. | Terminal decision; first failure policy. |
| Nonpositive source opacity floor — `source_opacity` | Explicit native `SRCE_CHK nonpositive opacity floor` report with complete finite measurements, negative absorption and positive emissivities/scattering. No companion errors; current limiter is `SRCE_CHK`. | Select native `NEG_OPAC_OPT=ESEC_CHK`, fresh BA and radiation caches. Keep all safeguards and the checkpoint; generic crashes cannot select it. | One application. |
| Saved-population interpolation — `pop_initialization` | Same confirmed, isolated pre-iteration population failure as the LTE rule, but in a **fresh** startup with explicit legacy `DC_METH=R/TR/ED/SPH_TAU`, `LIN_INT=T`, `POP_SCALE=T`, and `LTE_EST=F` if present. The executable must contain the patched POP success marker. Original explicit-ion inputs must be unchanged, complete, have matching full-level counts, and share a saved radius/T/Ne/clumping grid. | Request 2 iterations with temporary `DC_METH=POP`; require native confirmation of fraction interpolation and charge-conserving Ne, fresh finite outputs, and a usable checkpoint. Restore original controls, then request 2 normal continuation iterations. Native atomic/occupation/conservation validation remains mandatory; a failed step rolls the whole procedure back. | One recovery procedure; never reseeds an established continuation. |
| LTE starting populations — `lte_initialization` | Confirmed population-conversion/scaling failure before any iteration in a **fresh** startup: a native `SCALE_POPS`/`CNVT_FR_DC` crash frame or the `SETPOP_WLD_V*` zero-RGU safeguard. No other diagnosed error; LTE was not already selected. Explicit `LIN_INT=F`, and `LTE_EST=F` if present, must be compatible. | Request 2 iterations with temporary `DC_METH=LTE` and a positive `T_EXC`; restore the original initialization controls on every exit. Require finite refreshed outputs/a usable checkpoint, then request 2 normal continuation iterations before committing the recovered state. | One recovery procedure per automatic invocation. |
| Fresh POP/LTE radiation seed — `opacity_lte_seed` | Isolated zero-exit luminosity stop before any population solve in a confirmed fresh interpolated POP or explicit noninterpolated LTE startup; a complete negative luminosity profile, inner τRoss≥30, fixed structure, `SCALE_OPT=MAJOR`, CMFGEN viewer patches ≥2026-10-31.1. POP requires a preceding diagnosed source-floor repair or local matching LTE/hydro provenance. LTE requires matching local provenance and confirmed native LTE/charge initialization; the matching profile must not already be selected without grey refinement. | Zero-iteration native LTE initialization, preferring the model’s matching promoted LTE/hydro temperatures; then 3 fixed-T Lambda solves at temporary `MAX_LAM=1e12` and full guarded variable-T/fresh-BA verification. Check exact source temperatures, declining uncapped extrema, charge/elements and geometry. No intermediate state is committed. | One provisional procedure; never reseeds a continuation. Failed/interrupted verification restores the pre-seed state. |
| Dormant startup hydro schedule — `startup_hydro` | Isolated zero-exit luminosity guard before the first POP population solve, or at its first continuation (checkpoint 1). Explicit `DO_HYDRO=T`, `STOP_IF_MW=T`, `N_ITS=0`, `ITS_DONE=0`, `STRT_ITS=2`, valid hydro frequency, full variable-T startup, CMFGEN viewer patch revision ≥2026-10-31.1. Fresh complete profiles must show a positive deficit with minimum in `[0.25,0.5)`, maximum ≤2, and inner τRoss≥30. Fresh startup must confirm the POP marker; continuation must pass checkpoint physics checks. | Schedule exactly one revision (`N_ITS=1`) and fresh BA. If fresh, first run one temporary-guard-off POP seed solve and audit checkpoint 1. Run the one-iteration hydro bridge, restore the guard, then require two guarded continuation iterations. The entire seed/bridge/follow-up recipe remains provisional. | One procedure; at most two guard-off solves for fresh startup, one for continuation. Insufficient budget, interruption, or failed validation rolls back the complete coupled state. |
| Hydro startup bridge — `hydro_bootstrap` | An isolated, zero-exit factor-of-two luminosity stop before the first population solve of a confirmed continuation. A hydro revision is explicitly due in `HYDRO_DEFAULTS`; `DO_HYDRO=T` and the major-warning guard is enabled. Fresh complete luminosity/optical-depth profiles corroborate the stop and establish inner τRoss ≥ 30. | Run 1 iteration with temporary `STOP_IF_MW=F` to complete the scheduled hydro/grey revision, restore the guard, then request 2 guarded continuation iterations. Their luminosity profile must be within `[0.5, 2]` and inner τRoss at least 30. | One recovery procedure. |
| Radiation cache — `radiation_cache` | A failed attempt explicitly reports **incorrect reading of EDDFACTOR**. A generic crash does not qualify. | Restore the appropriate checkpoint, retire the radiation cache, and retry. A cache error within a provisional recovery retries that step from its step snapshot. | One application. |
| Nonfinite radiation cache — `nonfinite_radiation_cache` | Before the first attempt, `COMP_F=F` requests reuse of a supported 2017 EDDFACTOR cache whose radiation records contain NaN/Infinity. Unknown layouts and generic crashes do not qualify. | Preserve the cache and metadata as `.bak` files in the action journal, record the invalid location and checksum, and set `COMP_F=T` to regenerate radiation. `USE_FIXED_J=T` requires review. Normal checkpoint and independent convergence verification still apply. | One preparation action; no failed-attempt allowance consumed. |
| Refined formal rays — `ray_refinement` | A continuation fails the native luminosity safeguard, a refreshed complete normalized luminosity profile contains negative values, the hydro structure is fixed, formal rays are coarse (`VFRAC_FG>0.1`), and the moment grid is original (`VFRAC_MOM=20000`) or the executable has CMFGEN viewer patch revision ≥2026-10-31.1. Relativistic, time-dependent or `INC_GRID` transport requires that revision even on an original moment grid. | Try `VFRAC_FG=0.1`, fresh BA and radiation caches. Require two guarded fresh-BA solves (native Lambda steps permitted), positive luminosities within `[0.5,2]` and inner τRoss≥30. Keep moment/depth grids and all safeguards unchanged; roll back the trial on failure. | One provisional procedure. |
| Explicit large-change safeguard — `population_guard` | Exact zero-exit native post-save `MAX_CHNG` stop after one fresh-BA solve of a continuation. Its counter must match the saved checkpoint; independent before/after audits require positive finite populations, charge/element conservation and unchanged geometry. The executable must report CMFGEN viewer patches ≥2026-10-31.1. | Preserve the failed run's status. Retain its checkpoint only provisionally for the fixed-T Lambda/full-continuation procedure below; restore the pre-failure state if any step fails. Never use a generic crash or failed fresh initialization. | One provisional procedure. |
| Verified numerical convergence — `verified_convergence` | In the independent verification phase, the final 2 steps are full, temperature-varying solves with fresh BA on both. Native solver metric and both absolute raw correction extrema are finite and strictly below `EPS_TERM`; relevant `CORRECTION_SUM` counts agree. No intervening hydro revision invalidates those steps. | Restore the starting `N_FIX_BA`/`FIX_BA` policy for future runs, retain `COMP_BA=T`, finish successfully, and report scientific-quality measurements separately. | Evaluated after each successful verification batch. |
| Candidate verification — `verify_candidate` | The final 2 full, temperature-varying solves meet the raw/native correction tolerance and count checks, but independent verification is still required. | Set `COMP_BA=T`, `N_FIX_BA=0`, `FIX_BA=0.0`, retire `BAMAT`/`BAMATPNT`, and request up to 3 verification iterations. A rebound returns to further diagnosis/iteration. | Shared work budgets; never accepts a candidate without verification. |
| Superlevel temperature derivatives — `superlevel_temperature` | A measured localized persistent temperature cycle, without a hydro revision, while `INCL_dSLdT` is disabled. | Enable `INCL_dSLdT=T` and fresh BA before attempting local damping. Retain the correction thresholds and physical model. | One application. |
| Extreme populations — `population_bootstrap` | Fresh-BA solves have finite extreme population increases (two successive increases≥1e7%, or one≥1e12%). A fixed-structure continuation with `SCALE_OPT=MAJOR` must have an independently auditable positive, charge-conserving checkpoint and a CMFGEN viewer executable at patch revision ≥2026-10-31.1. Native automatic Lambda steps also qualify. | Three fixed-T Lambda solves with temporary `MAX_LAM=1e12`, fresh BA and Ng disabled; require declining uncapped extrema, unchanged T/geometry and conserved elements/charge. Restore normal controls, then require two consecutive full variable-T/fresh-BA solves with the same physical checks. Native Lambda/fixed-T fallback defers verification and repeats the full-step batch within the shared budgets. No floors or LTE reseeding. | One provisional procedure. |
| First Ng cadence — `ng_cadence` | Two short (2–5 solve) full batches stay below `BEG_NG`, past `IBEG_NG`, with native Ng enabled and `LAST_NG=-1000`. No hydro revision or successful Ng occurs. | Increase subsequent batches to eight contiguous physical solves, allowing the native first-Ng delay and final-step suppression to operate normally. Keep all native Ng validity checks; never force an acceleration. | One adjustment, only if the next eight-solve batch fits the remaining budget. |
| Small population cycles — `population_relaxation` | Three complete printed raw solution arrays show repeated, nondecaying population sign reversals, with the last request at least `EPS_TERM`. All requests are ≤1%. Requires a CMFGEN viewer patch revision ≥2026-10-31.1, fresh full/free-temperature solves, a fixed structure, conserved charge/elements, fresh luminosity/optical-depth guards, `SCALE_OPT=MAJOR` and no existing damping or narrower correction scope. | Provisionally set native `RELAX=0.5` across the atmosphere in `ADJUST_CORRECTIONS`, retaining every variable in the stopping test. Request 3 iterations and require at least two full/fresh solves, a lower raw maximum, nonincreasing correction counts, conserved geometry/elements/charge and guarded luminosities. Restore the accepted checkpoint and controls on failure; independent convergence verification remains mandatory. | One provisional procedure. |
| Local oscillation damping — `local_relaxation` | Persistent sign reversals in raw temperature requests, or sufficient completed-batch temperature profiles, with nondecaying amplitude. The affected interval spans at most one third of the depth grid. Requires `SCALE_OPT=MAJOR` and supported simple correction controls. | Set depth-local `RELAX=0.25`, then `0.125` if necessary; set local `T_LIM=0.2` so a tighter cap does not suppress the native RELAX branch. Preserve/extend the existing simple depth interval within the supported width. | At most 2 adjustments; a persistent cycle at the minimum RELAX stops for review. |
| Stalled transfer sampling — `stalled_transfer_refinement` | The ordinary small-correction tail (≤1%) stalls across 3 comparable fresh-matrix batches with `VFRAC_FG` or `VFRAC_MOM` above `0.1`. Requires CMFGEN viewer patches ≥2026-10-31.1, including interpolation, collision, X-ray and moment-Jacobian/limiter repairs, fixed structure, conserved elements/charge and fresh positive luminosity/optical-depth guards. | Provisionally reduce coarse formal/moment sampling controls to `0.1`, preserving any finer setting and the atmosphere grid. Retire BA/radiation caches and request 3 iterations. Keep the change only after full fresh solves reduce the raw maximum without increasing correction counts and pass physical guards. Independent convergence verification still follows. | One provisional procedure; unsupported solver families or unproductive trials require review. |
| Stalled corrections — `stalled_corrections` | Last full, variable-temperature steps from 3 comparable batches show no steady decline or improvement exceeding 2% relative to the first. A native metric at or above its `10,000,000%` cap requires uncapped population extrema; improving raw extrema, temperature requests, or relevant correction counts permit continuation. Counts are compared only for matching final-step modes. Missing raw extrema cannot prove a capped plateau. | Request fresh matrices with `COMP_BA=T`, `N_FIX_BA=0`, `FIX_BA=0.0`, retiring the saved BA caches. If already using fresh matrices, first consider the guarded transfer-sampling remedy above; otherwise stop for review. Trends restart after adjustments and native hydro revisions; a hydro-containing batch is excluded from the new baseline. | One matrix-refresh remedy; shared work budgets still apply. |
| No temperature-varying steps — `fixed_temperature` | Three batches since the last intervention contain no full, variable-temperature solve. | Stop for review; Lambda/fixed-temperature changes cannot prove convergence. The loop does not disable Lambda handling or force a temperature-release policy. | Terminal decision. |
| Healthy continuation — `continue` | Fresh outputs and a coherent, finite-core continuation checkpoint, with no higher-priority rule matching. | Continue another normal batch. | Shared work budgets. |
| Unhandled problem — `unhandled` | Unknown failure, or a recognized problem whose tested remedy is ineligible. Invalid/stale numerical evidence is also passed to failure diagnosis. | Stop with the diagnosis/refusal trail and an investigation report. Do not invent an untested adjustment. | Terminal decision. |

Native control names are case-sensitive. The superlevel-temperature remedy
writes `INCL_dSLdT` exactly, including when repairing a previous uppercase
`INCL_DSLDT` row. Older runner versions could insert the uppercase spelling,
which CMFGEN ignores. Preflight warns about that spelling; it does not count as
enabled when choosing this remedy. The correction still requires fresh BA and
the usual convergence verification.

Native X-ray normalization can adjust both `FIL_FAC_1` and `FIL_FAC_2` when
`INC_XRAYS=T`, `SCL_XLUM=T` and `XSLOW=F`. The runner accepts these changes only
when their finite values match the native `XRAY_NORMALIZATION_FACTOR` evidence.
A batch that changes the source cannot certify convergence, including during
verification; another invocation with a stable source is required. Unrelated
input edits still stop the run.

`NUM_ITS` is a requested batch size. CMFGEN may extend its native schedule,
including to perform follow-up solves after X-ray normalization or Ng
acceleration, or to finish output after a structure revision. A longer batch
with fresh outputs and a coherent, healthy checkpoint is informational, not an
automatic failure. Every completed solve is charged once against the shared
iteration budget; the attempt journal records requested and actual counts.
Checkpoint-counter increments from recognized Ng/hydro updates are distinguished
from physical solves. Ordinary output validation, control-edit safeguards,
recovery validators and convergence verification still apply. Extensions that
exceed the shared budget stop the loop and restore the preceding accepted
checkpoint; native schedule extensions cannot be predicted as a hard per-batch
work cap. Use the shared timeout when a wall-clock limit is needed.

The optional native `FINAL_OUTPUT_ONLY` mode writes complete files at a fixed
checkpoint without solving corrections. Main/test runner plans reject this
mode; restore `FINAL_OUTPUT_ONLY=F` before ordinary or automatic iterations.
It never authorizes starting queued spectrum stages as a converged main result.

### POP initialization recovery

The patched `DC_METH=POP` path reconstructs saved populations before interpolating superlevel fractions, avoiding artificial ionization spikes caused by log-departure-coefficient interpolation across steep temperature gradients. It preserves the saved-model estimates better than rebuilding unrelated LTE guesses when compatible source populations are available. The source-fix investigation records same-grid and refined-grid validation; successful initialization still does not establish atmospheric convergence.

Automatic selection is deliberately tied to a **confirmed fresh-start initialization failure**, with interpolation and population scaling already enabled. It does not flip `LIN_INT` or `POP_SCALE`, react to an opaque crash, restart a healthy continuation, or infer an initialization artifact from a generic stalled run. For a refinement run that finishes but has suspicious ion fractions, inspect the source reconstruction and explicitly choose POP in the parameter editor before a fresh run.

Eligibility requires complete original `*_IN` estimates for all explicit atoms in `MODEL_SPEC`, matching full-level counts and one saved radius/T/Ne/clumping grid; the runner supplies `T_IN` from `He2_IN`. Files generated by the failed attempt's AUTO_ADD do not qualify. The native reader then verifies contiguous explicit stages, atomic mappings, occupation reconstruction and conservation. Incompatible atomic setups must be prepared manually; POP does not repair them. The executable itself must contain the patched native POP completion marker; merely pointing at a source checkout with the patch is insufficient.

The temporary POP trial and the normal-continuation check form one provisional procedure. Original initialization controls are restored on every exit, and either step's failure restores the pre-procedure checkpoint/control set. Ordinary finite runs report the same recommendation and unmet prerequisites without applying it.

### LTE fallback details

LTE initialization remains useful for poor **starting population estimates**; it is not a remedy for an unstable continuation. The fallback never changes `LIN_INT` or `LTE_EST` to force compatibility. It does not reseed a continuation checkpoint or act on a merely suspected/opaque initialization crash. A model explicitly launched with `--fresh-start` remains a fresh-start request; automatic mode preserves its pre-run checkpoint/control baseline for rollback if the recovery fails.

An existing finite positive `VADAT [T_EXC]` is retained for the LTE trial. If absent, the trial uses **1.0 in units of 10⁴ K**. This is a floor for the initial excitation estimates, not a fixed final atmospheric temperature. Supply a suitable positive `T_EXC` in VADAT when a different initialization scale is needed. `DC_METH` and `T_EXC` are temporary overrides; their original values, comments, or absence are restored before normal continuation. An already selected LTE initialization is not retried with the same remedy.

The LTE bootstrap and normal-continuation check are one provisional procedure. If either fails or is interrupted, the loop restores the original checkpoint/control set. Passing the procedure establishes usable initialization and continuation, **not convergence**; normal numerical verification still follows. See [LTE initial populations](/documentation/command-line-runner#lte-initial-populations) for explicit initialization outside automatic mode.

The large-population remedies require the actual executable to report the
maintained CMFGEN viewer patch stream at revision `2026-10-31.1` or later.
No JSON build record is required. See `doc/developer/cmfgen-versioning.md`
for version and build instructions. Unidentified or older executables are declined.
Selected binary layout and complete MODEL ion metadata must also
be recognized for the independent charge/element audit; unsupported layouts are
left for review. These stronger checks are specific to the large-step bootstrap.

### Recovery, native updates, and evidence

Every accepted attempt requires refreshed `OUTGEN`, `CORRECTION_SUM`, finite RVTJ core vectors, and a usable checkpoint whose counter agrees with the solver steps plus verified native hydro/grey revisions. An extra hydro counter is not counted as another radiation/population solve. Scheduled native hydro updates to `VADAT`, `RVSIG_COL`, and `HYDRO_DEFAULTS` are adopted only with completion messages, valid grid output, and matching counters. An explicitly enabled `DO_T_AUTO=T` may release native `FIX_T=T`; this is observed and preserved, not forced by the controller.

Native automatic lambda release in `IN_ITS` is also preserved: a completed lambda solve below the native 50% switching threshold must be followed immediately by a completed full solve, with `DO_LAM_AUTO` enabled. The runner journals the `DO_LAM_IT=T` → `F` change and keeps `IN_ITS` with checkpoint recovery state. Unrelated edits still require review, and the switch itself is not a convergence criterion.

Native hydro revisions reset correction-trend history because they can change the radial grid and structure. The mixed hydro batch is excluded; stall and temperature-profile comparisons restart with subsequent complete batches. Local oscillation damping is not selected from temperature vectors spanning a hydro revision. Per-attempt evidence remains in the journal, and the reset does not replenish work budgets or relax convergence acceptance.

The model is reserved between native attempts. A rolling full recovery snapshot keeps checkpoint files and coupled controls together; multi-step remedies also retain a temporary step snapshot. Failure or cancellation rolls back provisional changes. Temporary POP/LTE/Lambda/guard/iteration overrides are restored, while accepted numerical tuning such as local damping remains installed for later continuation. After independent fresh-Jacobian verification succeeds, the controller restores the `N_FIX_BA` and `FIX_BA` values saved at the start of the automatic run, retaining `COMP_BA=T` for a fresh initial matrix on future runs. Restoration is journaled and included in the recovery controls; the verified checkpoint and its evidence are unchanged. Failed, cancelled, budget-limited, or unverified runs keep their fresh-matrix recovery policy. Starting with reuse already disabled leaves it disabled; no faster defaults are guessed. External control or executable changes stop further automatic mutation and are preserved; if they prevent safe rollback, the report identifies that recovery needs review.

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
- agreement between selected `RVSIG_COL` depth declarations, data rows, and `MODEL_SPEC [ND]`, including native three-column files and standard indexed exports;
- finite `RVSIG_COL` numeric data, positive radii and velocities, strictly decreasing radii, and positive density/clumping columns when present;
- nonnegative and ordered CMF_FLUX turbulence and wavelength bounds in `obs/CMF_FLUX_PARAM_INIT`;
- fresh LTE/hydro outputs that are newer than, and differ from, their promoted root copies.

The validator deliberately avoids fixed astrophysical plausibility ranges and does not require `NP = ND + NC` outside LTE grid construction. Each issue links to the full editor when the file is allowlisted and is a regular file, or otherwise to its file view. Symbolic-link layouts remain readable but are not offered to the editor.

`RVSIG_COL` velocity reversals/repeated values and `sigma < -1` are advisory,
matching the native code's warning treatment of nonmonotonic velocity laws.
Repeated values may come from limited text precision. Sigma equal to -1 is
allowed for constant velocity. A separate advisory screens for gross disagreement
between `sigma + 1` and a three-point estimate of `dln(V)/dln(R)` at interior
depths. It skips turning points, strongly curved intervals, and changes not well
resolved by the printed radius/velocity precision. See the
[detailed screening limits](/documentation/command-line-runner#rvsig_col-numerical-consistency-checks).
These checks cannot establish whether a numerically valid profile matches the
intended mass loss, beta law, or hydrostatic equilibrium; the tracked structure
update requirement remains a separate check.

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


The parameter editor displays a “Fresh BA on every full iteration” notice and
highlights the reuse controls when `COMP_BA=T` and `N_FIX_BA=0`. The advanced
controls open automatically in this case. The notice updates with quick edits;
it is also shown in the VADAT text editor. This is a performance explanation,
not a convergence warning. A stable continuation can test `N_FIX_BA=1` with
`FIX_BA=0`; final automatic verification always uses fresh matrices.

The editor also shows contextual review hints for explicit `DO_LAM_AUTO=F`,
`DO_LAM_IT=T`, `FIX_T=T`, `DO_NG=F`, `MAX_LAM>1e4`, and scoped
`ADJUST_CORRECTIONS [RELAX]` values between 0 and 1. The relevant quick fields
have badges and colored borders; hints update as values are edited and also
appear in each file's text editor. The optional correction file has a quick
`RELAX` field that preserves its depth range and other controls.

These are review hints, not evidence that a setting came from recovery or is
wrong for the model. `DO_LAM_AUTO` controls the native handoff from requested
Lambda iterations to full iterations; disabling it is not itself a performance
penalty during healthy full solves. Large Lambda limits may be bootstrap choices,
fixed temperature may be intentional, and Ng suppression or damping may still be
needed for stability. No setting is reset automatically by these hints. Proven
ray refinement and superlevel-temperature Jacobian improvements remain unchanged.

### Guarded performance trials during automatic iteration

Automatic mode can provisionally reduce numerical overhead after comparable full,
variable-temperature batches show healthy progress. **BA reuse needs two consecutive
batches**, with no 1% correction ceiling. **Releasing damping retains the stricter
three-batch window**, with every raw/native correction metric at most 1%. For both
trials, metrics must be finite, final batch metrics must decrease strictly, and the
last must improve by at least 20% relative to the first in the comparison window.
All correction-threshold counts must be non-increasing. Complete temperature-request
vectors must exclude persistent cycling; hydro revisions and Ng steps invalidate this comparison window.
The running executable must authenticate the line/BA repairs. Fresh complete
luminosity/optical-depth profiles and a recognized, positive, charge-conserving
checkpoint are required. Missing evidence skips performance tuning while ordinary
iteration and recovery remain available. If this invocation introduced damping
that can still be released, its fresh-BA release trials take precedence over BA
reuse; rejected or exhausted damping-release trials do not block a reuse trial.

| Trial | Conditions and provisional change | Required demonstration |
|---|---|---|
| `ba_reuse_trial` | `COMP_BA=T`, `STORE_BA=T`, `N_FIX_BA=0`. Try `N_FIX_BA=1`, `FIX_BA=0`. At most once per automatic invocation. This can include a run that started with zero reuse. | Exactly two full solves, the first with fresh BA and the second with reused BA; improving corrections and unchanged-or-better counts/physical checks. |
| `relaxation_release` | Damping was introduced by this automatic invocation and the current matrix policy is fresh. Double `RELAX`, capped at the starting value (or 1 when no correction file existed). Keep the depth range and other controls. At most three trials, with another healthy comparison window before each increase. | Exactly two full solves with fresh BA, improving corrections, no temperature cycling, and unchanged-or-better counts/physical checks. |

Each trial reserves two iterations plus room for a subsequent verification batch
(at least five remaining iterations and two remaining attempts before selection).
The trial's final correction metric must improve, neither trial step may rebound
above the baseline, no threshold count may increase, and normalized luminosities
must remain inside `[0.5,2]` without widening the baseline range by more than 0.01.
Inner Rosseland depth must remain at least 30. Geometry, element densities and
charge conservation are checked using the recognized checkpoint metadata.

Changes and checkpoints remain provisional until all checks pass. A completed
trial with valid evidence that fails these checks restores the conservative
checkpoint and coupled controls, retires incompatible BA/radiation caches, and
continues ordinary iteration. Rejected BA reuse is not retried; rejection of a
damping release disables further damping-release trials for this invocation.
Unknown native failures still stop for review after rollback. Cancellation,
timeout or an incomplete trial also restores the conservative baseline. Trial
outcomes and rollback reasons appear in the journal, CLI and workflow report.

These trials do not promise a universal speedup: the BA trial must demonstrate
an actual skipped rebuild, and damping release must demonstrate continued progress.
They never relax convergence tolerances, safeguards, radiation refinement or
superlevel Jacobian terms. They do not automatically enable Ng, change Lambda
handoff, reset `MAX_LAM`, or remove user-selected damping. Native/temporary recovery
handling of those controls is unchanged. Final acceptance always requires a
separate fresh-Jacobian verification batch, after which the starting BA-reuse
settings are restored as described above.

### Earlier runs in the convergence plots

Enable **Show earlier runs** below the two convergence charts to
include retained corrections and luminosity differences from previous automatic batches and consecutive
main runs. The choice is remembered per model in the browser; the default view
remains the current run. Historical data is fetched only when enabled, and
turning the checkbox off returns to the current-run view. The control is also
available while a new OUTGEN run has no completed solves yet.

The checkbox controls both panels. Luminosity differences retain their sign,
including zero values; missing historical luminosity values are left out.
Panels without current-run points stay hidden while history is off. The checkbox
remains available; enabling it reveals panels with retained history.

Earlier invocations are separate, lighter dotted traces. Hover details identify
the run, status, automatic phase when recorded, and Lambda/temperature mode.
Failed and rolled-back attempts remain visible with labels; curves are not
joined across invocations. The horizontal axis remains the native global
iteration counter, which can repeat or move backward after restarts. Runs may
also have used different physical parameters or numerical controls.

History uses earlier appended OUTGEN segments, retained native main-run logs,
and automatic-run evidence when logs have been compacted. The current invocation
and duplicate copies are excluded. Missing or overwritten unarchived history
cannot be reconstructed. Reads are limited to 250 recent runner archive entries,
64 MiB total (8 MiB per file), and 5,000 historical completed solves; the chart
reports truncation. Archive symlinks are not followed.

This overlay is for visual comparison. Current-run summary cards, quality checks,
convergence acceptance, and automatic policy decisions retain their existing
sources and rules.


### Stopping a UI run cleanly

For main computations launched by the updated UI runner, **Stop after this iteration**
is available in the workflow card and run-details page. The owning worker temporarily
reduces `IN_ITS/NUM_ITS` to 1. CMFGEN rereads this control between iterations and exits
through its normal final-output path. This can require **one additional final-output
iteration**; it is not an immediate interruption. The original iteration setting is
restored afterward, including on failure or cancellation.

The job shows **Finishing iteration** while waiting, then **Stopped cleanly** after
validation. Ordinary automatic batches retain their validated completed checkpoint
and do not start another attempt or queued spectra. A stop during a provisional
multi-step remedy or performance trial restores the conservative checkpoint rather
than accepting an unfinished repair. Native failures and invalid evidence still
follow the existing recovery rules; requesting a stop does not validate bad output.

**Stop now** retains immediate cancellation and its batch rollback behavior. CLI
Ctrl-C is unchanged. Older workers started before this feature was installed must
finish or be cancelled normally; their UI does not offer the new control.


### Runner-owned input links

The automatic runner recognizes links installed by its reviewed native recipe,
including replacement of missing or stale `T_IN` links after copying a model
between machines. Adoption happens immediately after runner link setup. Source
contents remain protected, and subsequent removal or retargeting of an adopted
link stops automatic execution, even if the new target has identical contents.


A hydro structure is considered fixed for population and ray remedies when
`DO_HYDRO=F`, or when an explicit schedule has completed (`N_ITS=0`, integer
`ITS_DONE>=1`). A copied zero schedule with no completed revisions does not
qualify. This permits the existing population bootstrap to take over after a
verified hydro recovery without disabling the user's hydro configuration.
`startup_hydro` addresses the Bstar3512 startup guard; it does not require manually
converging the atmosphere or adding another population-recovery algorithm.


### Native fallback during population verification

The full-step verification after population bootstrap (including the explicit
large-change safeguard recovery) honors native automatic Lambda/fixed-temperature
fallback. A completed batch containing such steps remains **provisional**, and
the controller requests another two-step verification batch. It does not repeat
the preceding three-step Lambda bootstrap or disable `DO_LAM_AUTO`.

Every deferred batch must still complete fresh-BA solves and pass positivity,
charge, geometry, and element-conservation checks. Element conservation remains
anchored to the first full-verification checkpoint across repeated batches.
Two consecutive full, variable-temperature fresh-BA solves are required to finish
the recovery; final convergence still needs its separate tolerance and independent
verification checks. Lambda steps never satisfy either full-step requirement.

Repeats consume the normal attempt, iteration, and timeout budgets. If those
limits are exhausted, or cancellation/failure prevents verification, the entire
provisional population procedure rolls back to its conservative checkpoint.
The CLI, live UI, and run journal explain when verification is waiting on native
fallback rather than reporting it as failed numerical evidence.

Deferred verification keeps a separate history for stall, missing-full-step, and
localized temperature-cycle diagnostics. A diagnosed failure stops for review
and restores the conservative checkpoint; it cannot nest another remedy inside
the provisional recovery. Consistently declining corrections may continue within
the shared budgets. The result panel and issue reports explicitly identify
rolled-back recovery attempts, discarded checkpoints, and the restored checkpoint.

The three-solve Lambda bootstrap may also finish after two solves when native
convergence shortens the batch. Both solves must have native and uncapped raw
correction extrema below `EPS_TERM`, use fixed temperature and fresh BA, and
pass the same physical checks. A single solve, missing evidence, or a shortened
batch above tolerance is rejected. This exception only ends the bootstrap;
full variable-temperature verification and independent convergence verification
remain required.

### Nonpositive source-function opacity floor

A patched native diagnostic, `CMFGEN diagnostic: SRCE_CHK nonpositive opacity
floor`, identifies a failure before the transfer solver takes `LOG(CHI)`. With
`NEG_OPAC_OPT=SRCE_CHK`, negative continuum absorption can cause the limiter
itself to choose a negative value. A generic `SIGILL`, floating-point exception,
or NaN luminosity does not establish this diagnosis.

The `source_opacity` rule requires complete finite frequency/depth and opacity
measurements, negative absorption, and positive emissivity, continuum emissivity,
and electron scattering. It selects the existing `NEG_OPAC_OPT=ESEC_CHK` option
once, requests fresh BA, and retires BA and Eddington caches. The native
scattering limiter uses `0.1*CHI_SCAT`; the runner does not invent a new floor,
change populations, reseed a continuation, or disable luminosity safeguards.

The selected option is retained for ordinary continuation. It is a numerical
limiter adjustment, not convergence acceptance: the next attempt must still
pass native/output validation and can invoke existing hydro/population remedies.
Final convergence still needs independent fresh-Jacobian verification. Additional
nonfinite-state/checkpoint errors, an already selected `ESEC_CHK`, missing or
invalid measurements, or a repeated exhausted remedy stop for review.

Older executables may trap or propagate NaNs without this diagnostic. Install
the source guard from the consolidated CMFGEN patch (or the incremental
`doc/developer/patches/cmfgen-source-opacity-guard.patch`) and rebuild before
expecting automatic recognition. Previously poisoned checkpoints remain invalid.

### Fresh POP radiation initialization

An opacity-limiter adjustment can expose a separate inherited-seed problem:
the first radiation sweep still fails the luminosity safeguard before any
population correction. `opacity_lte_seed` applies only to this narrowly
diagnosed **fresh** startup, never to an established continuation. Positive
moderate deficits remain the responsibility of `startup_hydro`.

Explicit `DC_METH=LTE, LIN_INT=F` starts are also eligible when native LTE and
charge initialization are confirmed and a matching local LTE/hydro profile is
available. `DC_METH=LTE` selects populations; it does not itself select the
rebuilt thermal profile. Without `LTE_EST=T`, main initialization can still read
inherited temperatures from `T_IN`; `IT_ON_T=T` can further refine them with the
grey solver. The recipe explicitly uses the reviewed `FIN_CAL_GRID` and skips
that grey refinement during its zero-iteration seed. A start already using
`LTE_EST=T, IT_ON_T=F` is refused because repeating the same seed is not a tested
remedy. LTE starts never use the inherited-temperature fallback without a
matching LTE/hydro profile. No existing continuation is reseeded.

When present, `lte/FIN_CAL_GRID` must have a byte-identical paired promoted
`lte/RVSIG_COL_NEW`, matching target TEFF/LOGG/LSTAR/MDOT and abundances, matching
radii/velocities/depths, finite positive thermodynamic inputs, and outputs no
older than their LTE/hydro controls. Incompatible or stale local artifacts
stop recovery for review. Without such artifacts, only a preceding typed
source-floor repair permits an LTE seed on the inherited temperature grid.

The runner temporarily selects `LIN_INT=F, IT_ON_T=F, DC_METH=LTE` and, when
using the reviewed LTE/hydro profile, `LTE_EST=T` plus an exact temporary
`FIN_CAL_GRID`. It runs native test mode with zero radiation iterations, checks
positive populations and charge consistency, and verifies the binary
checkpoint’s temperatures against the reviewed source. It restores all
initialization controls and any pre-existing root FIN_CAL_GRID on every exit;
the consumed input and source provenance remain in the journal. The public
`--lte-initialization` flag retains its original compatibility restrictions.

This initialization consumes an attempt but **zero convergence iterations**.
It cannot certify numerical progress or convergence. The recipe then uses the
existing three-step population bootstrap and full-step verification, including
unchanged 1e-6 element/charge checks and rollback. Native Lambda/fixed-T fallback
can defer full verification within the shared work budgets. The luminosity
safeguard stays enabled throughout.

A complete explicit hydro schedule with `N_ITS=ITS_DONE=0` and positive integer
`STRT_ITS/FREQ_ITS` is considered fixed for these guarded population/transfer
remedies. This neither disables DO_HYDRO nor changes the schedule; the separate
startup-hydro rule can still rearm it when its own evidence qualifies.


### Native source revision requirements

Numerical remedies that require patched CMFGEN code query the selected
`cmfgen_dev.exe --version` and require the maintained cumulative patch stream
at revision `2026-10-31.1` or later. Future remedies can require a later revision.
Official/foreign build dates and stamps in older model outputs do not qualify
a different executable. A JSON build record is not required. Unidentified older
executables can still run normally and use remedies independent of these
repairs. See [native versioning](developer/cmfgen-versioning.md) for the release
stamp and clean serial build/final-link procedure.
