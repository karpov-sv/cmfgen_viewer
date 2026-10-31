# CMFGEN interpolation, collision and X-ray convergence repairs

The 29 October 2026 integration adds three numerical repairs, two performance
optimizations and an opt-in fixed-state output feature to the consolidated
[CMFGEN patch](patches/cmfgen-current.patch). It also carries the general recovery
rules into the viewer after upstream commit `f921985`. No particular model seed,
atomic setup, abundance, convergence tolerance or fitted population history is
installed as a general default.

## Numerical repairs

**26 — Positive monotone interpolation.** `MON_INTERP` can cancel a representable
positive value to zero near a node when neighboring radiation values span many
orders of magnitude. A subsequent N/J evaluation can then fail although every
stored J is positive. Return exact stored nodes, reevaluate cancellation-prone
intervals as the same cubic in stable Bezier form, and enforce interval bounds
for finite results. Ordinary interior arithmetic remains unchanged; nonfinite
arithmetic remains visible to caller diagnostics. A retained native reproducer
failed at frequency 1177 before repair. Repaired
full radiation sweeps completed 152,174 frequencies in that fixture; these
values describe validation coverage, not applicability conditions or limits.

**27 — Bidirectional X-ray normalization.** Eligible `SCL_XLUM` iterations now
reduce excessive emission as well as increase deficient emission. Apply the
existing square-root emissivity scaling with factors bounded to `[0.1,10]`,
validate luminosities/tolerance before arithmetic, and retain the native
intrinsic-emission and `MAXCH<100` eligibility checks. A changed source forces
fresh radiation/BA and at least one actual solved update after cycle/IN_ITS
rereads. A terminal formal pass alone cannot satisfy that requirement.

The multiplier is recorded as `XRAY_NORMALIZATION_FACTOR` in `OUTGEN`. The runner
accepts resulting filling-factor edits only when both values match the logged
multiplier and the enabling controls/solver evidence agree. It clears trend and
candidate evidence for that batch. Even a change during fresh verification
requires another stable-source invocation before automatic success is possible.
Other native control edits retain their existing checks.

**28 — Collision temperature Jacobian.** Dissolution contributions to a diagonal
collision derivative must accumulate over transitions. Replacing assignment
with accumulation preserves the forward rate. In the regression fixture the
old derivative differed from finite differences by about 90.2%; the repaired
relative error is `1.50e-12`.

## Performance changes

**29 — Sparse projection.** Skip a projection row when its three interpolation
weights are exactly zero, preserving the order of every nonzero sum. This is
an optimization for finite transport data, rather than a new radiation formula.

**30 — Independent slice copies.** Parallelize complete disjoint remapping
slices in `DO_VAR_CONT`, keeping the inner index thread-private. The investigation
validated these changes together with the numerical repairs in actual native
continuation. It did not establish a universal total-model speedup. Installed
compiler and BLAS settings are preserved. The separate EHB loop-order experiment
is excluded from the standard patch and installed solver.

## General automatic remedies

The existing superlevel-temperature action now writes the case-sensitive native
key `INCL_dSLdT`; the editor likewise writes `MAX_dT`. Uppercase `INCL_DSLDT` and
`MAX_DT` are ignored by the native reader. Preflight identifies them, and targeted
edits repair their spelling without adding a duplicate row.

`population_relaxation` recognizes a nondecaying sign-alternating population
mode using three complete printed raw solution arrays. Every coordinate must
be finite; missing/truncated arrays cannot authorize it. It applies only to the
small-correction tail (all raw requests at most 1%), with fresh full/free-T solves,
a fixed structure, native `SCALE_OPT=MAJOR`, physical guards and a supported
dated patched executable. Existing caller damping and narrower correction scopes are
preserved. The trial writes all-depth `RELAX=0.5` in `ADJUST_CORRECTIONS` and
requires improved full fresh solves plus conserved geometry/elements/charge,
positive guarded luminosity and nonincreasing correction counts. Diagnostic
thresholds do not remove weak populations from the stopping criterion.

`stalled_transfer_refinement` recognizes an otherwise unhandled small stall
across three comparable fresh-matrix batches. With the complete moment,
interpolation, collision and X-ray repairs present in the supported dated
revision, it may refine coarse
`VFRAC_FG` and `VFRAC_MOM` to `0.1` on the existing atmosphere grid. Finer settings
are retained. This recipe is restricted to ordinary steady-state transport and
uses the same physical/improvement follow-up guards. It retires stale BA and
radiation caches before testing the change.

Each procedure is attempted at most once within the shared budgets. Failure,
interruption or insufficient follow-up budget restores the accepted checkpoint
and controls. Passing a remedy only permits continued iteration; independent
fresh convergence verification remains the sole successful automatic main result.
See the [registered policies](../main-computation.md#automatic-convergence-and-recovery-rules).

Additional isolated continuation experiments used compatible neighboring
estimates, temporary initialization stages and bounded history acceleration in
relative coordinates. Their native state/RHS interface and general acceptance
policy are not established sufficiently to install arbitrary fitted vectors
automatically. The two registered remedies, including `RELAX=0.5`, are therefore
not a universal recipe for reproducing every successful experimental recovery.
`EPS_TERM` remains the caller's tolerance and is expressed in percent: a value of
`0.02` means **0.02 percent**.

## 31 — Complete output at a fixed checkpoint

The new optional `FINAL_OUTPUT_ONLY` control belongs in **IN_ITS** and defaults
to `F`. It supports a saved stationary coherent continuation, with a positive
iteration budget and these mode settings:

```text
! IN_ITS
1 [NUM_ITS]
F [DO_LAM_IT]
T [FINAL_OUTPUT_ONLY]
```

```text
! VADAT: other scientific controls must still describe the intended checkpoint
T [FLUX_CAL_ONLY]
T [COH_ES]
T [COMP_F]
F [COMP_BA]
F [STORE_BA]
0 [N_FIX_BA]
0.0 [FIX_BA]
```

Run the native executable from an isolated prepared model copy, with its atomic
links and ordinary resource settings. Impurity mode, fixed J, Lambda mode,
relativistic/time-dependent transfer, extended `INC_GRID` output, gradual X-ray
turn-on, zero iterations, input-solution replacement and a fresh
model are rejected. The normal coherent radiation pass then uses the existing
ordinary luminosity-imposed inner temperature gradient and goes directly to
standard `MOD_SUM`, `RVTJ` and atmosphere writers, bypassing all population,
hydro and source updates. Summaries explicitly say no convergence solve occurred.
Checkpoint pointers and scratch populations are preserved.

Legacy `FLUX_CAL_ONLY` behavior and its boundary remain unchanged when the new
flag is absent/false. Merely doing a legacy flux pass followed by `NUM_ITS=0`
still does not generate a valid complete final atmosphere: the first omits native
atmosphere summaries and the second has zero mean opacities. The new mode also
avoids the flux-only gradient mismatch that produced a spurious 107% integrated
RE discrepancy in the earlier private output experiment.

Output-only execution receives no solved-iteration, fresh-matrix or convergence
credit. Viewer/CLI main and test plans reject `FINAL_OUTPUT_ONLY=T`. Restore it
to `F`, and `FLUX_CAL_ONLY=F`, before ordinary solver restarts.

## Installation and validation

Integration validation included the LTE charge-consistency fix, source hashes
matching the consolidated snapshot, preserved compiler settings and directory
aliases, and serial builds of atmosphere, CMF_FLUX and observer executables.
Use the [source updater and build procedure](cmfgen-versioning.md) for an
installation; captured historical build evidence is linked from the
[consolidated summary](cmfgen-source-fixes.md).

The following checks passed against the integrated sources:

- Interpolation nodes, signed/constant values, extreme ranges and near-node
  relative accuracy at `O0` and `O2`; 800 ordinary interior values are byte-identical
  to the prior interpolation routine.
- Actual collision finite differences; bidirectional/invalid X-ray cases and ten
  extracted native normalization branches, including fresh-solve scheduling.
- Existing native core regression suite, including the LTE Ne charge iteration,
  occupation reconstruction, population interpolation and endpoint handling.
- Ordinary moment-limit suite: 3,480 native calls, maximum field relative error
  `2.42e-14`, maximum column relative error `9.37e-6`; assembly check `1.52e-6`.
- Real subprocess controller tests for both recovery recipes, rollback,
  authentication, scoped controls, stable-source verification and output-only
  main-stage refusal.
- Consolidated 47-file release-patch application/reversal and composed incremental
  patch round trips, with all file hashes checked and the Makefile excluded.

The native regression driver is repeatable without modifying its source checkout:

```sh
python3 doc/developer/cmfgen-review-tests/check_convergence_repairs.py \
  /path/to/cur_cmf/ --optimization O2
```

It needs compatible built precision modules/libraries. Use
`--baseline-interpolation /path/to/old/mon_interp.f` for the ordinary-arithmetic
byte comparison. Build provenance and capability authentication do not certify
scientific convergence of other models.

A complete fixed-state output regression finished in **29.02 minutes** from
a saved checkpoint. All checkpoint/control hashes remained unchanged. All 119,342
printed spectral intensities match the verified reference exactly; the ordinary
inner gradient, energy/luminosity profiles and mean opacities also match. Complete
rate/atmosphere outputs were generated. This is output consistency, not another
convergence solve. The run tested executable `d358911cccd907dcd708bc422f3cddfa0f456aaca87f5ff99d7bf4b674069c00`,
before the later X-ray logging, existing LTE initializer alignment and stricter
output-scope guards. Those changes do not affect this admitted saved-checkpoint
output path; the final executable passed separate default/guard tests and its
sources and native kernels were checked. The initial audit driver had a parser
argument error after native completion; its record is retained alongside a
corrected read-only audit of the already generated output. No radiation rerun
was needed.

The full viewer suite reported **1,785 passed, 2 skipped, 6 failed and 11 setup
errors**. All 17 failures/errors reproduced on an untouched checkout of upstream
`f921985`: stale assertions in LTE action/runtime/quality/restart tests and a
missing `tests.test_model_editor` fixture import. The changed-policy/documentation
checks passed separately (81 tests), followed by 59 source-handoff, recovery and
hydro checks after excluding source-changing batches from trend history.
Listing, RVTJ/OBSFLUX/MOD_SUM pages and both workflow documentation pages returned
HTTP 200. Python compilation passed.
