# Bstar3518 slow thermal tail — 14 November 2026

Initial read-only inspection of the new production copy at checkpoint 310;
the subsequent explicitly requested remedy experiment is described below.
The original model remains unchanged. The copied incomplete iteration 311 is
excluded from the initial diagnosis. Diagnostics, proposals and trial evidence
are retained under `output/bstar3518-slow-tail/`.

## Finding

The helium repair held. The remaining limitation is a slowly improving deep
thermal imbalance, closely resembling the later Bstar3514 slow mode. The
initial next experiment was the existing conserved positive global Ng method,
whose 5% profile-error boundary excludes this approximately 4.2% case.
The native experiment below rejects that candidate: its population transient
exceeds the existing guard. The global eligibility boundary is retained.
The matched one-step BA-reuse experiment passes all checks and cuts two-solve
elapsed time by 42.96%, with virtually identical saved-state thermal progress.

The production controller also tried matrix reuse and bounded affine Ng.
Matrix reuse was rolled back; bounded affine Ng was accepted at 290 and retained
some benefit, but did not remove the slow tail. Native Ng still rejects its
ordinary proposals. None of these facts justifies forcing native Ng or treating
the model as numerically converged.

## State, recovery history and rate

The selected binary record is 310, with LAST_NG=-1000. Populations are positive
and finite (minimum 4.75055e-61 cm^-3), charge error is 1.66533e-15, and the
isolated-spike scan finds no qualifying spike anywhere on the grid. The latest
CORRECTION_SUM has no coordinates above 10% or 100%, 15 above 1%, and 38,346
above 0.1%.

The active copied controller journal is
`.cmfgen-runs/20261112T213846Z-auto-a625abb6/`. It records the version-3
localized population repair, a rejected BA-reuse trial, an eight-solve Ng
cadence adjustment, and an accepted bounded affine Ng trial from checkpoint
290 through six full follow-up solves ending at 296. No global geometric Ng
trial has been applied.

| Full solve | Native metric (%) | Maximum raw decrease (%) | Luminosity above target (%) |
| --- | ---: | ---: | ---: |
| 264 | 4.83334 | 6.81 | 4.66567 |
| 274 | 1.67274 | 2.09 | 4.55121 |
| 282 | 1.11755 | 1.23 | 4.46136 |
| 290 | 1.12863 | 1.28 | 4.37317 |
| 296 | 1.01200 | 1.15 | 4.23343 |
| 304 | 1.00800 | 1.12 | 4.15279 |
| 310 | 1.02992 | 1.15 | 4.09196 |

The last six complete solves are 305–310, with fresh BA, variable T and unit
major-species scale throughout. Their remaining luminosity error decreases by
about 0.246% per solve, an empirical e-folding time of approximately 406 solves
if that local rate persisted. This is slow progress, rather than a stationary
or nonfinite checkpoint. Ordinary eight-solve production batches take roughly
201 minutes (about 25 minutes per solve).

The worst requested reduction at 310 is the implicit O VI population at depth
55, 9.76271e-54 cm^-3, only 1.90e-62 of the local oxygen density. Its relative
correction is temperature-sensitive; removing this coordinate from convergence
checks would not resolve the separate, substantial thermal error.

## Thermal localization and damping

The last completed forward calculation, associated with solve 310, has an
absolute integrated RE residual of 3,464.1744 Lsun. Depths 71–88 contain
93.0766% of that absolute residual, and depths 77–85 contain 67.5211%.
The normalized luminosity profile spans 1.0–1.0422; inner Rosseland depth is
95.94. Printed emergent luminosity is 87,437.2691 versus 84,000.0193 Lsun.
These forward diagnostics precede the final population update; the subsequent
zero-solve radiation audit of saved 310 is recorded below.

Existing RELAX=0.125 covers depths 16–27. A binary 309-to-310 comparison
against the raw T request verifies:

| Depth | Requested T change (%) | Applied T change (%) |
| --- | ---: | ---: |
| 18 | -0.0080108 | -0.001001345 |
| 24 | -0.0074830 | -0.000935375 |
| 55 | -0.0027021 | -0.002702112 |
| 80 | -0.0019065 | -0.001906495 |

Shallow damping is active, but the deep correction is already fully applied.
Releasing shallow damping could affect the outer population front; it does not
directly release the dominant deep thermal correction. This is consistent with
the limited benefit of that experiment in the earlier Bstar3514 investigation.
The current snapshot alone does not prove the exact same Jacobian mechanism.

## Positive global Ng candidate and automatic gate

`global_ng.propose` produces a read-only numerical candidate from states
310–307. Its metadata reports:

- positive geometric step fraction 0.5;
- population/T ratio range 0.141687–1.172242, within the existing 0.1–10 bounds;
- maximum T change 0.653508%, within the existing 1% cap;
- element-density error 2.10942e-15 and zero measured charge error;
- proposed depth-80 T change -0.365787%, versus an ordinary -0.0019065%;
- native affine rejection at 37 depths, 20 temperature reversals, and an
  affine backoff limited to 1/256.

The last-six-solve correction-metric ratio is 0.9504, the slow-thermal-tail
check passes, and a replay of `global_ng_trial` reaches the physical guard.
That guard declines because the measured profile deviation 0.0422 is below
the hard-coded 0.05 eligibility threshold. The preceding history check itself
allows luminosity errors down to 0.02. This explains why a numerical candidate
exists but the automatic global rule has not fired at this state.

The larger positive step is a candidate, not an accepted saved atmosphere.
The proposed next trial should retain the existing whole-procedure rollback,
fixed physical parameters, six consecutive full/free-T/fresh-BA responses and
final acceptance checks: settled significant corrections, physical conservation,
and at least 10% retained improvement in both absolute RE residual and profile
deviation. A successful trial at this lower error would support extending the
automatic eligibility range below 5%. Merely lowering the production gate
without native response validation is not an established speedup.

## Matrix reuse: a separate wall-clock opportunity

The rejected trial at checkpoint 264 produced exactly the requested fresh/reused
BA schedule. Metrics were 6.04% and 5.36%, against the 6.81% baseline; significant
threshold counts also improved. The only worsened counts were:

| Threshold | Baseline | Trial |
| --- | ---: | ---: |
| 0.001% | 195,604 | 195,702 |
| 0.0001% | 200,013 | 200,051 |

Both are below EPS_TERM=0.02%. `_counts_ok` currently compares every diagnostic
threshold, so these small changes alone reject the trial before its later
physical checks. By contrast, Ng's final significant-count comparison already
uses thresholds at or above EPS_TERM.

The recorded two-solve reuse trial takes 33.10 minutes, versus roughly 50.8
minutes for two ordinary solves at the surrounding batch-average rate. This
suggests a wall-clock opportunity, but is not a controlled benchmark at 310.
The rejected branch's later conservation checks were not completed, and its
checkpoint was rolled back. Any revised reuse acceptance rule therefore needs
another bounded native trial; the eventual fresh-BA convergence verification
must remain unchanged. The subsequent global transient makes reuse the next
controlled experiment.

## Accelerator file-size headroom

SCRTEMP is 507,688,752 bytes (484.17 MiB). At initial inspection the population-state
and Ng helpers capped the entire file at 512 MiB, although diagnosis reads only selected
records. With the present fixed grid and record layout, record 327 fits and
record 328 exceeds that cap: only 17 ordinary saved solves remain before those
helpers decline on file size. Ordinary native iteration has a different limit.

This storage-bound eligibility should be addressed before relying on repeated
accelerator trials over a long continuation, using a reviewed bounded-streaming
limit or guarded checkpoint-history management. Do not delete or truncate old
native records manually. The proposed six-solve trial from 310 fits within the
former 512-MiB cap.

Related evidence: [Bstar3514 deep thermal comparison](bstar3514-deep-thermal-investigation.md)
and [Bstar3518 population recovery](bstar3518-production-followup.md).

## Requested remedy experiment

Two separate copies start at the same checksum-bound saved 310:
`models/test/model_Bstar3518_control_310` and
`models/test/model_Bstar3518_global_310`. Original controls and source inputs
are retained; no physical parameter or stopping tolerance is changed.

The control first performs the existing native FINAL_OUTPUT_ONLY protocol,
with fresh radiation and zero population solves. Restart files and decoded
populations are unchanged. This establishes the actual saved-state baseline:
normalized luminosity 1.0–1.0421, inner Rosseland depth 95.94, and absolute RE
residual 3,455.3383 Lsun. This corrects the small pre-update offset in the
initial ordinary-output diagnostics above.

The control then requests two ordinary full/free-T/fresh-BA solves, with native
Ng disabled. The global branch is queued after that control to avoid memory
overcommit on the 32-GiB workstation. It applies the conserved numerical seed
at unchanged counter 310 and requests three two-solve pairs with the identical
full/free-T/fresh-BA/native-Ng-off protocol. Each pair uses the existing
`auto_ng._validate` checks; final acceptance still needs settled significant
corrections and at least 10% retained thermal improvement. No convergence
credit comes from applying the seed. Failed candidates remain isolated from
the original model. Native trial records are in
`output/bstar3518-slow-tail/native-trial/`.

The file-size blocker is addressed separately by a shared 2-GiB recovery limit,
consistent with accepted-history hashing. Selected-record inspection and
whole-file hashing remain streaming, and atomic writes retain their disk-space
checks. Native geometry, counters and history layout are unchanged. Sparse
native fixtures place selected population records and four-state Ng histories
beyond 512 MiB; both extrapolators still diagnose them correctly without
loading the whole checkpoint. Files above 2 GiB and unsafe input roles still
decline. Affected policy manifests are versioned for this eligibility change.

### Global trial rejected after the first response

The control completes 311–312 in 49.67 minutes. Raw correction maxima are
1.19% and 1.17%, with native metrics 1.039067% and 1.035272%; the last ordinary
forward residual is 3,446.5843 Lsun and profile deviation 4.20%.

The global proposal's first forward sweep improves profile deviation to 2.26%
and absolute RE residual to 2,578.3379 Lsun. Its first full solve nevertheless
requests a 27.9% population decrease and 3.53% increase, with native metric
10.410457%. The existing maximum transient bound is twice the starting raw
metric, 2.30%. This is a failed candidate despite the thermal improvement.
The isolated experiment is cancelled after saved 311, during construction of
the second solve. No state is transferred to the original model; no acceptance
guard or global profile threshold is relaxed.

### Slow-tail matrix-reuse experiment

`models/test/model_Bstar3518_reuse_310` starts independently from original 310,
with the control's native-Ng-off, full/free-T settings and `N_FIX_BA=1`.
It requests exactly two solves, requiring a fresh/reused schedule, and restores
all original controls afterward. The provisional policy extension recognizes
six consecutive fresh/free-T observations of the existing deep thermal tail.
This separate eligibility path allows a 5% envelope around the starting raw
maximum, requires the reused solve to settle relative to the fresh solve,
and requires at least 0.1% reduction in both absolute RE residual and normalized
luminosity deviation. Counts at thresholds at or above EPS_TERM cannot worsen
during the trial. Counts below EPS_TERM cease to reject BA reuse; damping
release retains its existing all-threshold guard. Conservation, geometry,
rollback and independent fresh-BA convergence verification remain mandatory.

The fresh/reused trial passes the revised policy's complete checks. Its raw
maxima are 1.19% and 1.17%, with native metrics 1.0390674% and 1.0390055%.
Counts above 1% remain 15; counts above 0.1% fall from 38,346 to 38,202
(the all-fresh control reaches 38,175). The last pre-update forward residual
and profile match the control to their printed precision: 3,446.5843 Lsun and
4.20%. Element-density and charge errors are 3.44e-15 and 1.44e-15.

| Matched two-solve case | BA schedule | Elapsed (minutes) | Final raw maximum |
| --- | --- | ---: | ---: |
| Ordinary control | fresh, fresh | 49.6834 | 1.17% |
| Reuse trial | fresh, reused | 28.3406 | 1.17% |

This is 42.96% less elapsed time, or 1.753 times the solve throughput, on this
workstation. It improves convergence per elapsed time while retaining the slow
thermal mode's small per-solve progress; it does not establish a faster thermal
rate per solve or universal production timing. The first saved atmosphere
agrees between branches within 9.70e-12 relatively, with identical geometry.

An independent fresh radiation-only audit at saved reuse 312 leaves checkpoint
populations, geometry, and all 56 protected inputs unchanged. It measures
absolute RE residual 3,437.7361 Lsun (0.5094% below saved 310) and profile
deviation 4.19% (0.4751% relative reduction). The matched control's independent
endpoint audit measures 3,437.7765 Lsun and the same 4.19% deviation, also with
zero population solves and unchanged protected inputs. The difference in
retained absolute RE residual between the cases is 0.0404 Lsun, about 0.0012%
of the residual. This validates the measured computational saving without
losing the ordinary thermal progress over this bounded pair.

The original 310 checkpoint and all proposal-input signatures still match the
initial hashes. Production receives code changes only; no experiment checkpoint
or control edit is promoted. `ba_reuse_trial` version 4 can select this regime
once the controller has the required trusted ordinary observations. An old,
nonmatching accepted-history receipt still requires fresh observations rather
than bypassing provenance checks. The global step remains guarded at its
existing 5% profile boundary and original transient limits.

Validation: 205 focused performance/population/Ng tests passed, including the
new slow-tail eligibility/acceptance cases, all-threshold damping behavior,
controller rollback, and real selected records beyond 512 MiB. A separate
193-test controller/Ng/resumption/history run passed. Python compilation and
`git diff --check` pass. No full-convergence claim is made.
