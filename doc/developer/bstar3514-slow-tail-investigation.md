# Bstar3514 slow continuation at checkpoint 206 (4 November 2026)

Scope: inspect the production copy and test a bounded remedy for its slow tail.
The original local model is `models/tests/model_Bstar3514`; the two-solve
control trial is `models/test/model_Bstar3514_damping_release_test`.

**6 November update:** the matched six-solve 1/64 trial passed, and the guarded
automatic fallback is implemented. See the completed comparison and implementation
verification at the end of this report. The original local checkpoint remains 206.

## Copied state and progress

The selected checkpoint is record/iteration 206. OUTGEN contains complete
solves 201–206 followed by an incomplete 207 header. Imported journals remain
marked running, but local process inspection confirms this copy is idle.
Production was still running when this copy was made. The copied CORRECTION_SUM/CORRECTION_LINK are
slightly older than record 206: the former reports 6,566 coordinates above 1%,
whereas the complete raw solution for 206 has 6,473. The baseline comparison
therefore uses the complete raw array, whose T request matches the saved
205-to-206 temperature change. Historical running flags do not establish a
live local computation. The
production outputs identify native patch revision `2026-11-02.1`.

The model is progressing slowly rather than repeating the earlier instability:

| Iteration | Native correction metric | Maximum decrease | Maximum increase | Generated luminosity above target |
| --- | ---: | ---: | ---: | ---: |
| 168 | 3.72693% | 3.93% | 1.24% | 13.1232% |
| 184 | 3.41410% | 3.60% | 1.05% | 12.4364% |
| 200 | 3.12990% | 3.29% | 0.988% | 11.8063% |
| 206 | 3.03138% | 3.19% | 0.961% | 11.5834% |

The recent spectral change is about 0.102% per full solve. At 206, no correction
exceeds 10%; 6,473 variables exceed 1% and 84,154 exceed 0.1%. All populations
are positive and finite, with minimum 6.08973e-66 cm^-3 and charge error
1.22125e-15. The isolated-spike detector finds no qualifying ionization peak.
X-ray luminosity is 5.2185e-9 Lstar, inside the unchanged 10% tolerance around
5e-9. Neither the original He I spike nor an X-ray normalization jump explains
this current tail.

The largest reduction is the implicit O VI ground state at depth 54. Its
population is only 2.91714e-58 cm^-3, or 6.25185e-67 of local oxygen. Such tiny
high-ionization populations are very temperature-sensitive. This explains why
a small temperature drift can still produce a percent-level population metric;
it does not justify dropping those coordinates from convergence checks. The
11.6% luminosity discrepancy remains a physically significant unresolved error.

## Inherited local damping

`ADJUST_CORRECTIONS` still contains `L_ST=26`, `L_END=30`, `RELAX=0.125`,
`T_LIM=0.2`. Fresh full solves have major-species scale one, so this damping
is actively applied. Raw temperature corrections across this region have had
the same sign for dozens of solves, without a return of the old oscillation.

At 206, the raw depth-30 T request is -0.037477%, while the saved T changes by
only -0.00468463% from 205 to 206, matching the factor 0.125. At adjacent depth
31, the undamped raw/saved change is approximately -0.004944%. Thus the solver
requests a much larger update inside the restricted region but applies a slow
update comparable to that just outside it.

Automatic `relaxation_release` intentionally preserves inherited user damping:
it releases only damping introduced by an action of the current automatic
invocation, up to that invocation's original ceiling. Its measured acceptance
window is also restricted to the small correction tail. Consequently, auto
mode cannot silently turn this original 0.125 setting into 0.25 or 1.

The first conservative trial doubles RELAX to 0.25 at the same depths, retaining
the T limit, physical model, source controls, all native safeguards and fresh
BA schedule. This is a single-control experiment; it does not change the
convergence tolerance or force acceleration.

## Why changing the Ng band is not supported

The production controller already applied `ng_cadence`, extending batches to
eight ordinary solves. Ng is therefore reached, but its proposals are rejected.
At iteration 205 it rejects 50 depths and preserves the ordinary saved state.
`LAST_NG=-1000` correctly records that no Ng acceleration was accepted.

A read-only replay uses the actual `DO_TRANS_AND_NG_V1`/`NGACCEL` routines on
saved records 205, 204, 203 and 202, including the same appended geometry
coordinates. For band width 10 it reproduces the native 50 rejected depths,
22,227 negative proposed coordinates, and minimum proposal/current ratio
-5.88146 at the implicit O VI variable 829, depth 54.

| Band width | Rejected depths | Negative proposed coordinates |
| --- | ---: | ---: |
| 1 | 49 | 15,229 |
| 5 | 55 | 24,336 |
| 10 | 50 | 22,227 |
| 15 | 49 | 22,752 |
| 18 | 51 | 20,284 |
| 30 | 46 | 18,506 |
| 45 | 51 | 23,595 |
| 90 (global) | 46 | 18,762 |

A second read-only screen tests history spacings 2, 4, 8 and 16 with the
same eight band widths. All 32 additional candidates also fail native guards.
The least-rejected case (spacing 16, global band) still rejects 12 depths;
the spacing-16/band-30 case stays positive but proposes ratios outside the
allowed range (minimum 0.0146, maximum 17.89). Neither is an admissible native
acceleration. These results are retained in
`/private/tmp/bstar3514-ng-spacing-screen-20261104/report.json`.

Every band violates the existing checks. Increasing batch length again,
forcing Ng, or merely changing its band is not supported by this replay.
The kernel screening leaves the checkpoint untouched. Its driver, arrays,
production-kernel excerpt and report are retained under
`/private/tmp/bstar3514-ng-screen-20261104/`.

## Radiation-cache check

A second isolated copy, `models/test/model_Bstar3514_fresh_radiation_check`,
uses the documented native `FINAL_OUTPUT_ONLY` mode with `FLUX_CAL_ONLY=T`,
`COMP_F=T`, coherent scattering and a positive one-pass output budget. It
recomputes the ordinary radiation and standard atmosphere outputs at the saved
206 state, with zero population solves and no convergence credit.

The native pass succeeds. POINT1, POINT2 and SCRTEMP remain byte-identical,
and decoded populations, T and geometry are exactly unchanged. Fresh radiation
gives 93699.3893 Lsun versus the target 84000.0193, an excess of 11.5469%.
The complete normalized profile spans 1.0–1.1169, with inner Rosseland depth
103.4. This is consistent with the copied ordinary trajectory, allowing for
the final population update from the iteration-206 pre-update flux diagnostic.
The ordinary cached-factor trial computes 93699.4176 Lsun at the identical
pre-update 206 state, only 0.0283 Lsun different (3.02e-7 relative). This direct
comparison rules out stale factors as the dominant cause of the slow tail.
The outer-boundary moment/ray warning persists. Cache refresh alone does not
remove the thermal/flux discrepancy and is not established as the primary remedy.

## Bounded control trial

The two-solve RELAX=0.25 trial starts from a checksum-bound copy of checkpoint
206, using the installed native executable. Source inputs remain unchanged.
Run `20261104T103508Z-d0f3a8d6` completed two full/free-T/fresh-BA solves:

| Iteration | Solver metric | Maximum increase | Maximum decrease | Luminosity above target |
| --- | ---: | ---: | ---: | ---: |
| 207 | 3.01320% | 0.957% | 3.17% | 11.5469% |
| 208 | 3.00953% | 0.863% | 3.17% | 11.5096% |

There is no Lambda fallback, source change or accepted Ng step. Geometry is
unchanged, element error is 3.77476e-15 and charge error 9.99201e-16. The local
raw T request at depth 30 falls from -0.037322% to -0.033714%. Local behavior is
stable, but the deep mode barely accelerates: the luminosity decrement rises
from 30.6360 to 31.2946 Lsun per step, about 2.15%. The maximum metric improves
less than the preceding ordinary trend. Coordinates above 1% fall to 5,925,
but those above 0.1% rise to 87,636 versus the raw-206 baseline of 84,154.

This is not sufficient evidence to adopt damping release as the main remedy.
It improves the outer front, whereas most excess luminosity is generated at
depths 77–85: the normalized profile rises from 1.0 at 90 to 1.0578 at 80 and
1.1102 at 70, remaining almost constant outward through 26–30. Original local
inputs and checkpoint remain unchanged. The completed trial's regenerable
matrices were removed after preserving its outputs and physical reports.

## Jacobian-accuracy trial

A separate copy, `models/test/model_Bstar3514_jacobian_accuracy_test`, starts
again at original checkpoint 206. It retains the original RELAX=0.125 and
changes only `BA_CHK_FAC` from 1e-3 to 1e-4. Two full solves are requested.

The source describes 1e-4 as the usual setting (`control_variable_mod.f`,
`ba_update_v7.f`). The cutoff omits selected line-radiation response terms
whose population-normalized effect is small compared with J. It changes the
approximate Jacobian, not forward rates or the convergence tolerance. The
thermal row is accumulated separately, so an improvement of deep thermal
coupling cannot be assumed from the parameter alone; the native response is
being measured.

The trial failed before its first population solution: the larger matrices
exhausted local disk space (`WRITE_BCD_MAT`, `BCSCRATCH0085`, `IOSTAT=28`).
No completed population solve is available, so this parameter remains
inconclusive. The failed trial's own regenerable matrix files (10.396 GB)
were removed after verifying it was idle; outputs and checkpoint were kept.
This failure is a local resource limit, not evidence of model instability.

## Bounded Ng proposal: promising, not yet a production remedy

An isolated experiment uses the actual native band-10 Ng proposal from saved
records 206, 205, 204 and 203, then halves one common step length until all
population/Ne/T ratios lie in [0.5, 2] and every temperature change is at most
0.5%. The accepted trial length is 1/16:

`trial = current + (native_proposal - current) / 16`

This is a single affine step across all physical unknowns. Geometry is held
exactly fixed. No population is clipped, floored or excluded; temperature
changes retain the preceding direction. The minimum ratio is 0.579663 and
the maximum 1.037782. Maximum T change is 0.153716%. Element-density change
and charge error remain below 1.7e-13.

Only the selected population block in the owned experimental copy
`models/test/model_Bstar3514_bounded_ng_check` was changed. No solved
iteration or accepted native Ng was credited. Its checkpoint counter still
reads 206, but it is an experimental restart guess, not the original 206
solution. A fresh, zero-solve `FINAL_OUTPUT_ONLY` radiation calculation then
compares this guess with fresh radiation at the original state:

| Quantity | Original 206 | Shortened Ng guess |
| --- | ---: | ---: |
| Generated luminosity, Lsun | 93699.3893 | 93252.7326 |
| Excess over target | 11.5469% | 11.0151% |
| Maximum normalized luminosity | 1.1169 | 1.1115 |
| Sum of absolute radiative-equilibrium energy residuals, Lsun | 9582.0140 | 9300.1600 |

The luminosity decreases by 446.6567 Lsun and the absolute energy-residual
sum by 2.94%. These initial radiation diagnostics justified testing a
bounded Ng fallback. They did not establish how populations would respond
to a nonlinear solve. The subsequent paired experiment below measures that
response. No native acceleration code has been modified or installed.

Any eventual implementation must retain the current native acceptance
checks and leave already accepted Ng proposals unchanged.

## Subsequent nonlinear verification

After disk cleanup, the seed was reconstructed exactly from the unchanged
206 checkpoint. A paired experiment uses
`models/tests/model_Bstar3514_bounded_ng_verification` and
`models/tests/model_Bstar3514_ordinary_verification`. Both have identical
controls: the original RELAX=0.125 and BA_CHK_FAC=1e-3, two requested solves,
and COMP_F=T for a fresh radiation-factor calculation on the first pass.
The native solver resets that flag afterward and reuses those factors on
the second pass. Both passes recompute BA and keep temperature free.
The only difference between the two branches is the shortened Ng seed.

The first bounded-Ng full solve (207) completes with major-species scale one,
without Lambda fallback. Its pre-update luminosity, 93252.7326 Lsun, exactly
reproduces the static radiation test. The population corrections widen:
maximum increase 11.215%, maximum decrease 5.2953%, solver metric 8.98291%,
15,923 coordinates above 1%, and 96,342 above 0.1%. One coordinate exceeds
10%. The largest increase is at the trace O VI coordinate at depth 54,
which the seed had reduced to 0.579663 of its original value.

The saved 207 state remains positive and finite. Geometry is unchanged;
element-density error is 4.32987e-15 and charge error is 2.66454e-15.
Maximum applied T change from the seed is 0.039670%. Thus this first solve
is physically admissible, but the enlarged population corrections prevent
declaring the remedy successful on its static luminosity improvement alone.
The second bounded-Ng full solve (208) completes without Lambda fallback or
an accepted native Ng event. Maximum increase falls to 0.936%, maximum
decrease is 5.1994%, and the solver metric falls to 5.09346%. Counts above
1% and 0.1% fall to 10,816 and 66,418 respectively; no coordinate exceeds
10%. Pre-update luminosity falls further to 93218.1513 Lsun (10.9740%
excess). Element-density error remains 4.66294e-15 and charge error
1.77636e-15. Both saved updates remain positive and finite.

The log's grey-solution message on the last pass is a diagnostic:
`cmfgen_sub.f` computes TGREY for `GREY_SCL_FACOUT` without assigning it to
the atmosphere T. DO_GT_AUTO remains F. It is not an applied grey update.
The ordinary branch also completes two full solves. Its solver metric falls
from 3.014345% to 3.001684%. The last maximum increase/decrease are
0.952%/3.16%. Both branches keep major-species scale one, positive finite
populations, unchanged geometry, and element/charge errors below 5e-15.
Neither branch changes source controls, applies hydro revisions, or credits
an accepted native Ng step. Their controls remain byte-identical.

| Last full solve (208), requests before its population update | Ordinary | Shortened Ng |
| --- | ---: | ---: |
| Solver correction metric | 3.00168% | 5.09346% |
| Maximum requested population increase | 0.952% | 0.936% |
| Maximum requested population decrease | 3.16% | 5.20% |
| Coordinates above 1% correction | 6175 | 10816 |
| Coordinates above 0.1% correction | 83720 | 66418 |
| Largest applied T change across the two solves | 0.011277% | 0.039670% |

Thus the initial population rebound contracts, and the broad 0.1% tail
improves, but the worst correction and the 1% tail remain worse than the
matched ordinary continuation. No coordinates are excluded from these
counts, including extremely small trace-ion populations. The table uses the
complete printed raw STEQ arrays; rounding at a threshold makes the ordinary
0.1% count one larger than its native CORRECTION_SUM count (83719).

Separate `FINAL_OUTPUT_ONLY` runs recompute fresh radiation at each saved
208 state. They perform zero population solves and preserve POINT1, POINT2
and SCRTEMP byte-for-byte. Both native runs succeed. Their results are:

| Fresh radiation at saved checkpoint 208 | Ordinary | Shortened Ng |
| --- | ---: | ---: |
| Generated luminosity, Lsun | 93638.5957 | 93192.3314 |
| Target luminosity, Lsun | 84000.0193 | 84000.0193 |
| Luminosity excess | 11.47449% | 10.94323% |
| Maximum normalized luminosity | 1.1161 | 1.1108 |
| Signed radiative-equilibrium energy-residual sum, Lsun | -9378.4077 | -8930.6621 |
| Absolute radiative-equilibrium energy-residual sum, Lsun | 9522.8937 | 9096.3291 |

The Ng branch retains a 446.2643 Lsun luminosity improvement over the matched
ordinary branch, and its absolute energy residual is 4.48% smaller. This
is a real thermal improvement after nonlinear updates, not solely a static
guess or a stale-radiation diagnostic. It does not establish improved overall
population-convergence speed in this two-solve window.

The trial passes its bounded stability and conservation checks. It remains
an experimental thermal nudge: positivity and a small temperature step alone
are insufficient evidence for an unconditional automatic Ng fallback. A
production acceptance rule would also need to evaluate population recovery
and thermal merit. A smaller step is a possible follow-up, but was not tested
here. No further population solves were performed.

The reconstruction and verification drivers, original preservation hashes,
and native-kernel sources are retained in
`models/tests/model_Bstar3514_bounded_ng_seed`. Native revision is
`2026-11-02.1`; the two main run IDs are `20261104T124427Z-7ed04ada` and
`20261104T133809Z-97cc4660`. Per-branch evidence and raw-array comparisons
are in `verification-check.json` and `paired-comparison.json`; final radiation
copies end in `_final_radiation` and contain `radiation-merit.json` and
checkpoint-preservation hashes. The completed trials' own regenerable
matrices (22.420 GB total) were removed with idle-model guards. All physical
checkpoints, correction arrays and diagnostic outputs were retained.

## Handoff

The copied model is slowly converging; it does not exhibit the former He I
spike or X-ray normalization instability. Failed extrapolation leaves a slow
deep thermal mode without useful acceleration. Increasing the Ng interval
or changing its band has no demonstrated benefit. Damping release provides
only a small improvement to luminosity progress, and cache refresh does not
resolve the discrepancy.

Bounded Ng survives two full solves and improves thermal balance compared
with two matched ordinary solves. Population corrections show a settling
transient but remain mixed, so automatic deployment is not justified yet.
This investigation stops at that bounded comparison and does not attempt
to converge the model.
Production was still running when the copy was made. Neither the original
local controls/checkpoint nor production have been changed. Do not deploy this older copied
checkpoint over the live production state. Apply any eventual remedy to a
consistent, stopped snapshot of the latest production state.

## Adaptive-step follow-up protocol (6 November 2026)

The authorized follow-up first tests alpha=1/32 from the same checksum-bound
206 state, preserving the matched ordinary controls and native executable.
Alpha=1/64 is the next candidate if 1/32 does not resolve the population
rebound. These are common affine steps of the same native Ng proposal;
geometry, source parameters, local damping and convergence tolerances remain
unchanged. The initial screen consists of two fresh-BA/free-T full solves.

A candidate can advance to an extended comparison only if it preserves
positive finite populations, element totals, charge and geometry, has no
unaccounted source/hydro/grid/Ng transition, and demonstrates recovery of
the population corrections after any initial transient. A lower luminosity
alone is insufficient. The promising candidate and the ordinary branch will
then receive equal additional full-solve budgets, up to four--six full solves
in total. Acceptance requires a retained thermal benefit without a persistent
penalty in the correction maximum or significant correction counts.

If this numerical gate passes, test a second application from newly generated
history and refusal on normally converging/ineligible histories. Implementation
must use provisional execution, checkpoint-bound proposal validation and
rollback on failed verification. Cancellation, exhausted budgets, disk/copy
failures and repeated rejected proposals must not silently accept an
unverified state or create an unlimited retry loop. Existing recovery tests
are a baseline; they are not a substitute for tests of the new policy.

The 84 existing controller tests in `test_auto_performance.py`,
`test_auto_population_projection.py` and `test_runner_auto.py` passed before
any automatic-policy changes. A real-checkpoint audit also restored every
recovery file byte-for-byte after applying the 1/32 guess, removed all four
incompatible EDD/BA cache files, and preserved the previous committed recovery
snapshot under an injected ENOSPC backup-copy failure. These results are
retained in `models/tests/model_Bstar3514_ng_rollback_audit`.

A standalone Python replay reproduced the archived native proposal exactly
at all eight band widths. Forty further native-versus-Python fixture tests
(five histories times eight bands) also matched exactly, including constant,
geometric/singular, near-singular, irregular and large-dynamic-range histories.
The replay retains the native 1e-13 singularity tolerance derived from its
hard-coded X02AJF value. This validates a potential operator implementation;
it does not install a new automatic policy or establish model convergence.
The 1/32 two-solve trial completes with positive finite populations, unchanged
geometry and controls, no native transition, and element/charge errors below
4e-15. Its initial largest increase is reduced to 1.0693%, but its correction
metric changes from 3.78340% to 4.00025%; the second maximum decrease is
4.1550%. The final native counts are 8686 above 1%, 74879 above 0.1%, 172058
above 0.01%, 197238 above 0.001%, and 200274 above 0.0001%. This is still a
population penalty relative to ordinary continuation, although its broad
0.1% tail improves. The 1/64 screen is therefore required before selecting
a candidate for longer verification.

This trial's 806 archived atomic-dependency snapshots and all archived
pre-run input-file hashes exactly match the earlier ordinary baseline.
Native binary snapshots and patch revisions also match. Its initial
temperature change is at most 0.076858%; the largest temperature change in
the first subsequent solve is 0.024217%. First/second pre-update luminosities
are 93475.8626 and 93443.3223 Lsun. Evidence is retained under
`models/tests/model_Bstar3514_ng_32_trial`. Fresh radiation at its saved 208
state gives 93415.2437 Lsun (11.20860% excess), with absolute energy residual
9311.424681 Lsun. This retains a 223.3520 Lsun luminosity gain and a 2.22064%
energy-residual reduction over ordinary 208, with zero population solves
and no checkpoint change. Its regenerable matrices were subsequently removed.

Six additional operator-only native-versus-Python fixtures cover different
NT/ND dimensions, overlapping partial bands, zero/global bands and widths
larger than ND. All match exactly. These test algebra, not six more stellar
models.

The first 1/64 full solve has metric 3.378884%, maximum increase 0.97777%
and maximum decrease 3.2706%. Its saved state remains positive and finite,
geometry is unchanged, element/charge errors are below 4e-15, and maximum
applied T change is 0.017402%. This is gentler than 1/32, but its first
correction metric still exceeds the matched ordinary result. The second
response and extended comparison remain necessary before implementation.

## Completed extended comparison and automatic remedy (6 November 2026)

The numerical gate passed after **six full solves per branch**, ending at saved
checkpoint 212. The 1/64 branch is selected. The 1/32 branch was stopped after its
two-solve screen; its thermal benefit alone did not establish population recovery.
Both 1/64 and ordinary continuation use identical physical inputs, damping and
fresh-BA/free-T schedules. All 806 atomic dependency snapshots and native binary
identities match the earlier ordinary baseline. No hydro, source, grid or native
Ng transitions occurred in the matched six-solve comparison.

| Final measurement | Bounded 1/64 branch | Ordinary branch |
| --- | ---: | ---: |
| SOLVEBA maximum correction | 2.845325% | 2.938037% |
| Last pair: maximum of solver/increase/decrease | 3.10%, 3.00% | 3.11%, 3.09% |
| Coordinates above 1% correction | 4,920 | 5,818 |
| Coordinates above 0.1% correction | 80,344 | 82,750 |
| Coordinates above 0.01% correction | 169,082 | 170,604 |
| Absolute radiative-equilibrium energy residual, last full-solve diagnostics | 9,333.0491 Lsun | 9,435.2622 Lsun |
| Maximum normalized luminosity, same diagnostics | 1.1138 | 1.1151 |

The final full-solve diagnostics precede their last population updates in both
branches. Separate **zero-solve fresh-radiation probes at saved 212** confirm
that the benefit remains in the saved states:

| Fresh saved-state measurement | Bounded branch | Ordinary branch |
| --- | ---: | ---: |
| Generated luminosity | 93,415.3889 Lsun | 93,518.8797 Lsun |
| Luminosity excess above target | 11.208771% | 11.331974% |
| Absolute radiative-equilibrium energy residual | 9,305.9928 Lsun | 9,406.3481 Lsun |
| Maximum normalized luminosity | 1.1135 | 1.1147 |

This is a 1.0669% reduction in the saved-state energy residual. Both probes
completed with zero population solves, unchanged checkpoint hashes and unchanged
physical state. Final element/charge errors in the solved branches remain below
4e-15. The comparison stops here; neither branch is numerically converged.

The population response is transient: the first two 1/64 solves have solver
metrics 3.378884% and 3.489161%, and four solves still fail the matched acceptance
gate. A two-solve automatic acceptance test would therefore be premature. Six
solves establish both population settling and the retained thermal benefit.

A repeat-eligibility check from the candidate's newly generated 212 history
returns **no fallback proposal**: its native-equivalent Ng proposal is now
admissible. The ordinary 212 history still produces a rejected native proposal,
with a bounded fraction of 1/64. The remedy leaves native-admissible proposals
alone; a second artificial step was neither necessary nor applied.

### Installed policy and limits

`bounded_ng.py` implements the checkpoint-bound operator. It uses the native
weighted four-state algebra, band traversal and singularity tolerance. All
populations, including the trace ion that limits the native proposal, retain
one common affine fraction. The current test chooses 1/64 automatically under
the 12.5% coordinate-change and 0.1% temperature-change bounds. There is no
population floor, trace exclusion, clipping, band change or counter increment.

`auto_ng.py` registers `bounded_ng` after first-Ng cadence handling. It waits for
six observed consecutive fresh-BA/free-T solves with slowly declining 1–10%
corrections in a fixed physical regime. It requires the authenticated
2026-11-02.1 runtime or later, complete temperature/thermal evidence, fixed
structure, inner Rosseland optical depth at least 50, and a current proposal
that fails the native core guards. Missing evidence, fast healthy convergence,
candidates, transitions and temperature-direction reversals refuse the trial.

The trial is provisional across three two-solve pairs. Early population
transients may remain below twice the starting maximum, capped at 10%; every
pair retains positivity, conservation, geometry, complete temperature vectors
and the luminosity guard. The last pair must settle below the starting maximum,
without increasing any correction count at thresholds at or above EPS_TERM,
with at least a 0.5% energy-residual reduction and an improved normalized
luminosity profile. The installed final validator also passes when replayed on
the actual saved 212 result against the starting 206 measurements. The online
policy compares with its starting state; it does not run a shadow ordinary model.

At least nine remaining iterations and four attempts reserve six trial solves
and an independent convergence verification batch. An unhelpful trial rolls
back and continues ordinary iteration. Cancellation, partial completion and
unknown failures restore the conservative checkpoint; unknown failures stop for
review. A durable checkpoint fingerprint receipt survives rollback and prevents
repeating that same checkpoint across invocations. At most one trial can occur
per invocation. Native convergence acceptance remains separate and unchanged.

The six-solve experiment and safety tests support this restricted automatic
trial, not a guarantee of eventual convergence for arbitrary stellar models.
Passing the trial hands the state back to normal automatic policies.

### Implementation verification

The installed operator matches the native Fortran output exactly in all 54
comparisons: eight archived real-history bands, forty additional history/band
cases and six dimension/band-edge fixtures. The regression suite also retains
a small independent native-output fixture, so its algebra can be checked without
a local Fortran installation.

The 322 MB real-checkpoint fault audit verifies byte preservation outside the
selected population block, descriptor tamper refusal, stale-input refusal,
low-space refusal, injected staging ENOSPC, cancellation before publication,
cleanup of temporary files and byte-exact recovery after a post-publication
audit failure. Old histories with changed geometry, zero populations, wrong
charge or large temperature changes are refused. Unsupported modes, mismatched
pointers, unsafe files and recent native Ng are refused. These audits modify
only the owned rollback experiment copy.

Subprocess controller tests cover acceptance after six solves, rollback after
an unhelpful six-solve response, native failure, cancellation in the second
pair, clean stops immediately after seeding and after four solves, receipt-write
failure and action-directory creation failure. All recovery files are compared
byte-for-byte. Fault injection exposed a controller gap in abort bookkeeping
before an action was fully applied; provisional ownership is now journaled before
mutation, and rollback handles failure even before action-directory creation.

The broader suite exposed a pre-existing missing-history KeyError in provisional
verification. It reproduces on unchanged HEAD. Missing record lists now decline
the progress comparison and produce the intended safe stop instead of crashing.
A transient subprocess fixture failure did not reproduce in isolation.

Read-only checks on poems1025, poems504_orig, MCA_483_9_new, Bstar3513 and
Bstar3513.2 all refuse the policy or lack qualifying fresh evidence; their
checkpoint/input hashes remain unchanged. These are refusal checks, not new
numerical continuation experiments on those models.

Evidence is retained in `model_Bstar3514_ng_64_trial`,
`model_Bstar3514_ng_control_long`, the two `*_radiation_212` folders and
`model_Bstar3514_ng_rollback_audit`, all under `models/tests`. The latter includes
`installed-scientific-audit.json`, `installed-transaction-fault-audit.json`,
`installed-history-refusal-audit.json` and `installed-negative-policy-audit.json`.
The original POINT1/POINT2/SCRTEMP/VADAT/IN_ITS/ADJUST_CORRECTIONS hashes still
match `original-preservation-hashes.json`, and its checkpoint remains 206.
No production process or production checkpoint was changed by this work.

Final validation: the full automatic-policy, population and checkpoint regression
selection passed **506 tests**. After adding the independent native-output fixture
and final finite-energy/tolerance boundaries, the focused new suite passed
**74 tests** (overlapping the broad selection). `compileall` and `git diff --check`
pass. Flask smoke checks return HTTP 200 for the model listing, directory,
RVTJ/OBSFLUX/MOD_SUM details and both updated documentation pages, following the
normal Documentation landing-page redirect. Changes are implemented locally; production deployment is separate.
