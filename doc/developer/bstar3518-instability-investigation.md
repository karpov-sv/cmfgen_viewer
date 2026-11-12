# Bstar3518 copied production run — 12 November 2026

Initial read-only investigation of `models/tests/model_Bstar3518`, followed by
the explicitly requested bounded repair trial described below. The initial
inspection did not modify the model or run the native solver.

## Finding

The localized neutral-helium instability has been repaired in the local model.
The verified state at **checkpoint 193** is installed in
`models/tests/model_Bstar3518`, with the original state preserved in a recovery
backup. Full variable-T/fresh-BA solves **190 and 192** have positive He I/Ne
targets at the repaired depth, and the spike remains absent. Automatic main
preflight is ready. No further native computation is running.

This is the same failure family as the earlier Bstar3514 neutral-helium spike,
with a lower contrast and an additional settling transient. Policy version 2
handles that signature through bounded, uncredited settling followed by the
unchanged strict two-full-response checks. It does not identify a new solver
defect or address the later small-correction deep thermal slow mode. The model
is **not fully converged**: further normal/automatic iteration is still needed.

## Copied state and numerical evidence

POINT1 selects record 185, with LAST_NG=-1000. Current OUTGEN contains only an
incomplete iteration-186 startup; it must not be counted as a completed solve.
Imported running flags describe the production run at copying time.
MOD_SUM is from the restart-history output probe, not a new population solve.
The reported executable revision is 2026-11-02.1.

The selected binary checkpoint passes the repository's physical audit:
all populations are positive and finite, minimum population is
1.1393299245e-60 cm^-3, and maximum relative charge error is 5.1070e-15.
This does not mean that its populations solve statistical equilibrium.

At saved 185, helium stage fractions (sums of explicit levels divided by the
complete local helium total) are:

| Depth | Temperature (K) | He I fraction | He II fraction |
| --- | ---: | ---: | ---: |
| 23 | 11049.51 | 0.00340412 | 0.99360475 |
| 24 | 11271.45 | 0.96103783 | 0.03894595 |
| 25 | 11473.41 | 0.01179130 | 0.98635927 |
| 26 | 10752.35 | 0.00007805 | 0.99860917 |

The isolated depth-24 He I fraction is 81.50399 times the larger immediate
neighbor. The temperature has no comparably sharp excursion there.

The last completed five-solve batch, retained in
`.cmfgen-runs/20261111T214523Z-auto-2e6fc441/result.json`, reports:

| Solve | Mode | Maximum decrease (%) | Minimum major-species scale |
| --- | --- | ---: | ---: |
| 181 | Full, fresh BA, variable T | 1.33e8 | 0.00078083 |
| 182 | Fixed-T Lambda | 83.7 | 1 |
| 183 | Full, fresh BA, variable T | 2.57e7 | 0.0048595 |
| 184 | Fixed-T Lambda | 34.8 | 1 |
| 185 | Full, fresh BA, variable T | 4.29e7 | 0.0029963 |

The full-solve maximum reductions are all at depth 24. An independent read of
the final complete STEQ solution arrays binds the 183 and 185 reductions to
variable 36, He I level 5: raw requests are 2.5741e7% and 4.2942e7%.
In both arrays, all 68 excited He I levels and Ne have nonpositive unlimited
targets at this depth; the ground-state target remains positive. This is the
same specific pattern as the earlier Bstar3514 depth-31 failure. The intervening
Lambda arrays have zero such He I/Ne targets but do not remove the next full
solve's failure.

CORRECTION_SUM has 4,247 coordinates above 100%, 12,709 above 10%, and 28,636
above 1%. The solver metric is saturated at 1e7; that number must not be read
as a meaningful constant rate of progress. Pre-update luminosity at solve 185
is 88,538.5459 versus 84,000.0193 Lsun, a 5.4030% excess. The luminosity has
slowly improved, while the localized population failure continues.

## Original production remedies and why version 1 did not resolve it automatically

- **Temperature coupling:** exact native INCL_dSLdT is already T, and BA is
  freshly computed. Enabling it again adds no remedy.
- **Local damping:** the first automatic invocation applied RELAX=0.25 at
  depths 26–27, then RELAX=0.125 at 16–27. At checkpoint 135 it stopped with
  “Persistent cycle at the minimum automatic RELAX; review physics/grid/linearization”.
  Depth 24 is already inside that interval. As in the Bstar3514 investigation,
  native population scaling can prevent this RELAX setting from controlling
  the problematic updates; further blind damping is not established here.
- **Localized population projection:** the repeated full decreases and last
  two full-solve scales pass the corresponding numerical gates. However,
  `population_projection._candidate` in version 1 required stage-fraction contrast >=100;
  the copied 81.504 contrast failed it. A read-only scan finds no eligible
  projection anywhere on this checkpoint. This is a recognition near-match,
  not an already-authorized automatic action.
- **Large fixed-T Lambda bootstrap:** its gate requires persistent enormous
  *increases* (two final records >=1e7%, or the final record >=1e12%). The present
  obstruction is enormous *decreases*, and native Lambda already alternates
  with full solves without curing it. The analogous Bstar3514 Lambda trial
  failed its improvement gate.
- **Bounded/global Ng and small-stall refinements:** these require a healthy
  small-correction regime. Current requests are many orders of magnitude
  outside that regime, with repeated Lambda fallback. They are not applicable
  to this instability.

The restarted controller's progress message is also explainable from existing
code. `auto_policies._progress` treats any tracked diagnostic dipping by more
than 2% below the first of three batch endpoints as improvement, even when the
next endpoint rebounds. Oscillating large requests can therefore repeatedly
produce “Correction diagnostics show continuing progress”. The latest startup
diagnosis compares checkpoints 175, 180 and 185 and does exactly this. It is
not evidence that the helium failure is resolving. The restart-history probe
preserves that evidence; it does not apply the missing population repair.

## Original experiment plan

Use an isolated copy of accepted checkpoint 185 to test the established
Bstar3514 conservative helium/Ne projection at depth 24, explicitly treating
the lower contrast as an investigated extension of eligibility. Preserve the
helium total, all other element populations, T, geometry, physical parameters
and stopping tolerances; recompute charge-balanced Ne and fresh radiation/BA.
Require at least two actual full, variable-T, fresh-BA native responses, with
the existing positivity, abundance/charge, luminosity and local raw-target
checks. Native Lambda steps alone cannot establish success. Roll back the
trial if the spike returns or the response checks fail.

The threshold change alone is insufficient: the native trial below also
requires a bounded settling phase. Its successful verification and regression
coverage establish the version-2 extension; no new solver defect is claimed.

Related evidence: [Bstar3514 localized instability](bstar3514-instability-investigation.md)
and [automatic convergence policy contract](automatic-convergence-policies.md).

## Bounded repair trial

With explicit authorization to repair and run the model, a separate copy was
created at `models/test/model_Bstar3518_projection_test`. Initial inputs and
checkpoint are copied from accepted 185; regenerable matrix/radiation caches
and imported running journals are excluded. Trial evidence is retained under
`output/bstar3518-repair/`.

Policy version 2 lowers the minimum isolated-peak contrast from 100 to 50.
The two fresh full-solve gates, raw-coordinate binding, majority of impossible
ion targets, positive/conserved checkpoint, consistent neighbors and complete
provisional native verification remain unchanged. A read-only replay on the
original model, using the exact final five complete raw arrays, now selects
`localized_population_projection` (`recognition-original.json`).

Applying the projection to the copy preserves T/geometry/counters exactly,
changes element totals by at most 5.5511e-16 relative, and leaves charge error
4.8850e-15. Only helium and Ne at depth 24 change; Ne rises from
2.383610574e9 to 2.583429304e9 cm^-3. Log-radius interpolation weight is
0.508674107. This is a repaired starting guess, not a solved iteration.

The initial two-solve trial completed 186 (full) and 187 (Lambda). At 186, all
68 excited He I targets and Ne become positive, but the He I ground state
still requests a 210.04% decrease. The original strict validator correctly
rejects that first response; this trial is not relabeled a verification pass.
The saved stage contrast is 1.80154 at 186 and 1.34169 after Lambda 187.
The first full global increase is 1.02e8%, while its decrease is 1940% at
depth 27; the original depth-24 excited-level failure is gone. After 187,
element error is 7.6608e-10 and charge error 1.7764e-15, geometry is unchanged,
and the normalized luminosity profile spans 1.0–1.0548.

This motivates a separate, uncredited settling stage for peaks below contrast
100: up to two two-solve ordinary batches with at least one actual full/free-T/fresh-BA
response, no returned spike, and the same physical/luminosity guards. Its
first full response may have a ground-only decrease up to 1000% for an ion
with at least ten explicit levels; all excited-level and Ne targets must be
positive. A repeated bad full response within a batch, an excited/Ne failure, a larger
request or a returned spike rejects the entire procedure. A second settling
batch may retain a ground-only overshoot only if its request is at least 10%
smaller than the first; no third settling batch is permitted. Higher-contrast repairs retain
their original strict recipe.

After settling, **two additional full responses with strictly positive ion/Ne
targets are still required**, across at most two further two-solve batches.
Settling receives no verification credit. Everything remains provisional
against the original checkpoint until those checks pass; cancellation, budget
exhaustion or failed checks roll back the whole repair. No attempt to fully
converge is made. The continuation trial starts from 187 and records this
separate settling audit in `settling-check.json`.

Targeted regression validation passes: 113 tests across
`test_population_projection.py`, `test_auto_population_projection.py`,
`test_auto_policies.py` and `test_auto_history.py`. Added cases cover the
50-fold boundary, the 81.5-fold near-match, binding to actual bad raw targets,
and refusal when the full response retains either the spike or negative
targets. The controller lifecycle test also exercises the lower-contrast case
through provisional application and verified handback without claiming
convergence. Existing failure/ineffectiveness/cancellation rollback and stale
history tests pass. The lower-contrast staged procedure also restores the original
spike checkpoint on failure or cancellation after successful settling. Required Python compilation and `git diff --check` pass.

The first attempted strict follow-up, full 188, still has one negative ground
state target (102.43% decrease), while all excited He I/Ne targets remain
positive. It correctly fails strict verification. This is measured settling,
not a credited positive response: the request is less than half the first
210.04% request. Full 188 and Lambda 189 form the second and final allowed
settling batch. At 189, contrast is 0.38456, element error is 7.6608e-10,
charge error is 1.1102e-15 and the normalized luminosity range is 1.0–1.0551.
The subsequent strict verification starts at 190, with a fresh empty list of
credited full responses (`settling-check-2.json`, `verify_trial.py`).

## Completed strict verification and handoff

The separate verification batches completed 190–191 and 192–193. Solves 190
and 192 are actual variable-temperature full solves with fresh BA; 191 and
193 are native fixed-T Lambda solves and receive no full-response credit.
`verified.json` passes the production response validator with:

| Full solve | Largest local decrease (%) | Largest local increase (%) | Nonpositive He I/Ne targets | Other helium-ion nonpositive targets |
| --- | ---: | ---: | ---: | ---: |
| 190 | 10.914 | 76.061 | 0 | 0 |
| 192 | 16.339 | 44.324 | 0 | 0 |

At saved 193, the local stage contrast is 0.778844. Every population is
positive and finite, with minimum 1.09323e-60 cm^-3. Maximum element-density
change from the original baseline is 7.66079e-10, charge error is 1.11022e-15,
and geometry is exact. There is no eligible isolated spike elsewhere on the
grid. All 56 protected source/control inputs remain byte-identical, including
VADAT, MODEL_SPEC, IN_ITS, ADJUST_CORRECTIONS and the structure/atomic inputs.
No physical parameter, tolerance or installed executable was changed.

| Correction count | Copied 185 | Repaired 193 |
| --- | ---: | ---: |
| Above 100% | 4,247 | 9 |
| Above 10% | 12,709 | 836 |
| Above 1% | 28,636 | 16,749 |
| Above 0.1% | 96,699 | 56,221 |

The final Lambda maximum is 504.727%; pre-update emergent luminosity is
88,477.7363 versus 84,000.0193 Lsun (5.33061% excess). The normalized luminosity
profile spans 1.0–1.0546, with inner Rosseland depth 95.71. These remaining
corrections and the flux discrepancy are explicitly not convergence credit.
The existing outer-boundary moment/ray warning also remains.

The verified checkpoint, matching native outputs and finite radiation cache
were transferred under the model read/write and run-reservation guards. The
handoff rechecked original checkpoint/source hashes, staged and verified all
replacement hashes, and retained a complete rollback backup. Replaced original
files, obsolete matrix caches and stale automatic history are preserved at:

```
models/tests/model_Bstar3518/.cmfgen-recovery/
  bstar3518-localized-population-handoff-20261112T140018Z/
```

`handoff.json` records the transfer hashes and status `completed`;
`evidence/` retains the trial/physical audits. `next-auto-check.json` confirms
ready automatic continuation from 193, healthy selected binary populations,
and a supported finite radiation cache. This preflight starts no native run.
The four ordinary native journals remain in the isolated test copy; no
interrupted trial is relabeled a successful automatic invocation. The local
model is handed back at this point without pursuing full convergence.
