# Cancellation in CMFGEN line population Jacobians

The scientific line/BA repairs and separately validated Ng temperature safeguard
are included in the [cumulative source patch](cmfgen-source-fixes.md). Diagnostic
instrumentation and experimental alternative Q integration are excluded. The
chronological comparisons below record isolated reproductions and validation;
they are evidence for the repair, not a required sequence of model adjustments.

Matched saved-checkpoint tests reproduced a tiny-population instability and
demonstrated stable recovery with the repaired runtime, including fresh-process
continuation. In a retained later state, the raw maximum request was 0.2530594%,
the temperature request was 0.000378099%, and 11,818 variables exceeded 0.02%;
these measures were decreasing while positivity, original geometry and
conservation checks passed. The luminosity offset was approximately +0.455%.
This demonstrates progress, not final convergence or exact transport accuracy.
See the [archived investigation](bstar3502-lambda-investigation.md) for the
matched inputs, original artifact locations and supporting provenance.

## Defect and repair

In `new_main/subs/update_ba_for_line.f`, the explicit upper-population
rate derivative for Lambda iterations and weak lines includes

```fortran
ZNET_SIM(K,SIM_INDX)+VC(K)+STIM_FAC*VB(K)
```

The frequency integration in `CMFGEN_SUB` defines, at fixed line populations,

```text
ZNET = sum(w * (1 - J * chi_line / eta_line))
JBAR = sum(w * J)
QW   = sum(w)
VC   = JBAR * chi_line / eta_line
```

Therefore `ZNET + VC = QW` exactly. For very small upper-level populations,
`ZNET` and `VC` can be enormous and nearly opposite. Their rounded sum can lose
its finite spontaneous-emission contribution and leave a much larger error,
including derivatives of the wrong sign. An accurate linear solve cannot
repair a Jacobian assembled this way.

The isolated patch substitutes

```fortran
LINE_QW_SUM(K,SIM_INDX)+STIM_FAC*VB(K)
```

Only this algebraic expression changes. It retains the actual integrated profile
weight, including incomplete profiles; substituting a constant one would be
incorrect. Rates and right-hand sides, populations, opacities, radiation,
abundances, damping, and convergence thresholds are unchanged. The heating
Jacobian in the same routine already uses direct `LINE_QW_SUM` expressions.

The patch covers the shared Lambda/weak-line branch. Full strong-line
linearization is unchanged and is not certified by the branch-specific test.

## Native regression

The [standalone test](cmfgen-review-tests/check_lambda_line_jacobian.py) compiles
and calls the actual source routine with an explicit caller interface. Only
profiling `TUNE` is stubbed. The fixture covers upper populations from `1e-4`
to `1e-128`, an inverted-opacity case, two depths, and a non-unit profile weight
sum of `0.91`. The independent oracle uses 350-digit central differences of
the original source-function net-rate expression.

From the viewer repository, using the built source tree read-only:

```bash
OPENBLAS_NUM_THREADS=1 python \
  doc/developer/cmfgen-review-tests/check_lambda_line_jacobian.py \
  --cmfgen-root /path/to/cur_cmf \
  --compiler /opt/local/bin/gfortran
```

The unpatched source is expected to fail. To test a patched source copy, add
`--source /absolute/path/to/update_ba_for_line.f`. Each invocation writes exact
commands, source/fixture hashes, native output, and `report.json` to its temporary
work directory; `--work-dir` can specify a new directory explicitly.

Observed results:

| Check | Original | Patched |
| --- | ---: | ---: |
| Maximum relative upper derivative error | `1.5022e98` | `0` |
| Native cases passing | Fewer than 10 | 10/10 |
| Lower derivative agreement | Within roundoff | Within roundoff |
| Source-column particle-number balance | Exact | Exact |

The test is independent of a CMFGEN model run and does not modify the source
tree. The test's deliberate failure on the old source is the defect reproducer.

## Matched saved-checkpoint comparison

Two isolated runs start from exactly the same original physical checkpoint68,
without LTE reseeding. They share `VFRAC_FG=.1`, `MAX_LAM=1e12`, all other
controls, and observational instrumentation. The source expression is the only
difference between the pair.

| Observation | Original | Patched |
| --- | ---: | ---: |
| Maximum log10 population-unscaled N V coefficient magnitude | 89.9734 | 11.3556 |
| Positive excited-state N V diagonals | 17 | 0 |
| Negative unlimited population targets | 31 | 0 |
| Of those, N V targets | 17 | 0 |
| Maximum N V componentwise backward error | `1.72e-15` | `1.99e-15` |

Input radiation differs by at most `1.26e-11` relative to each field's peak;
frequency weights and prepared checkpoint/control hashes are identical.
The unpatched equations were accurately solved but contained the anomalous
assembled coefficients. The controlled source change removes those coefficients
without changing the physical input or radiation calculation.

The corrected derivative exposes a genuine large relative request for an O V
population initially at about `1.1e-134` of Ne. The first patched run consequently
hits the unchanged `MAX_CHNG=1e100` guard. **Its native status remains
`invalid_output`.** CMFGEN writes a capped checkpoint before stopping. That
provisional state was separately validated: all values finite and positive,
geometry and temperature unchanged, charge error `1.33e-15`, elemental abundance
error `1.22e-14`. It was used only in an isolated follow-up, not promoted to the
main model or relabelled as a successful run.

The follow-up completes normally at70 with the guard unchanged. Five further
normal Lambda steps reach75 with zero negative unlimited targets and charge
and abundance errors near `1e-15`. The number of variables above 100% falls 63 → 47 → 28 → 14 → 6 over checkpoints 71–75.
The raw maximum drops by twelve orders per
step as the existing `1e12` cap raises the tiny seeds. This demonstrates removal
of the initial numerical obstruction, **not full convergence**. Native DO_LAM_AUTO releases Lambda after 75 because its unchanged
SOLVEBA_V13 DO_LEVEL_CHK measure uses the tenth-largest corrections (1.77%),
while the actual maximum remains 8.08e37%. Independent acceptance retains the
raw extrema and counts. The continuing
batch must still demonstrate full temperature-varying solves and fresh-matrix
convergence at the original `EPS_TERM=.02%`.

The continuation runtime also includes the independently tested
[BA-cache header/EOF repair](patches/bstar3502-ba-restart-flags-experimental.patch)
to prevent cached matrix reads from changing the intended temperature mode.
That repair was not part of the matched source pair above.

## Historical scope and artifacts

The cancellation is present in the mid-2023 source used for the original model,
commit `b5f07ccc930a4096eaae482184d4a7b8bac8da87`. The current expression is blamed
to a 2012 refactoring, but its parent already contains `ZNET+VC`; the defect
predates that refactoring. A rollback to mid-2023 does not remove it. This does
not establish that the original machine followed the same tiny-population path.

- [Minimal experimental patch](patches/bstar3502-stable-lambda-line-experimental.patch).
- [Native fixture](cmfgen-review-tests/fixtures/lambda_line_jacobian.f90).
- [Complete investigation and subsequent validation](bstar3502-lambda-investigation.md).

The [archived investigation](bstar3502-lambda-investigation.md) records the
matched measurements and coefficient-versus-depth plots, including CSV data
and their generators. The plots compare the same N V SL22 coefficient across
90 depth indices. This is evidence for the diagnosed cancellation, not a claim
that every large correction has this cause.


## Experimental strong-line repair

The unchanged full strong-line branch has the analogous cancellation: its
explicit `EINA*U*ZNET` term is combined with an accumulated normalized emissivity
derivative in `dZ_POPS`. In a prescribed-radiation test of the actual routine,
this fails even when all radiation derivatives are zero. A separate candidate
omits that explicit emissivity term from `dZ` and combines it algebraically at
final population/thermal assembly, using `LINE_QW_SUM` when line linearization
is active. Radiation and opacity derivatives remain in `dZ`.

The first candidate preserves the native skipped-linearization approximation
and the original path when lower and upper derivative pointers alias. Its
compatibility fixture covered that pointer layout only; it did not certify all
shared-superlevel storage layouts or physical correctness. The later shared-level
section records the stronger test and the gap it exposed. Installed CMFGEN and the main model remain unchanged; the experiments use
separate isolated executables.

[Expanded native reproducer](cmfgen-review-tests/check_line_jacobian_branches.py)
uses four depths, three bands, five populations, Lambda/weak/strong modes,
prescribed neighboring-depth radiation responses, electron-density coupling,
and optional temperature-dependent superlevel ratios. Its independent 350-digit
source-function rate differences also verify the corresponding line-heating
derivatives. Continuum `BA_UPDATE_V7`, `ADD_PAR_TO_FULL_V2`, and profiling are
stubbed: this isolates the actual line routine, not the full transport solver.

Observed candidate result: 2,750 derivative entries agree within `1.12e-15`
(rate and heat); 250 skipped-linearization and 1,000 strong-line shared-superlevel
entries are bitwise identical to the original source. Particle-number column
balance is exact. Original source fails by up to `2.33e98` in rate and `2.83e98`
in heat. Lambda/weak tests retain those branches' native frozen-ratio response;
only the full strong-line scenarios exercise the temperature-ratio derivative.

```bash
OPENBLAS_NUM_THREADS=1 python \
  doc/developer/cmfgen-review-tests/check_line_jacobian_branches.py \
  --cmfgen-root /path/to/cur_cmf \
  --compiler /opt/local/bin/gfortran \
  --source /absolute/path/to/isolated/update_ba_for_line.f
```

The candidate source must include both the earlier Lambda/weak repair and the
[additional experimental strong-line patch](patches/bstar3502-stable-strong-line-experimental.patch)
to pass all branches. Without `--source`, the old-source failure is reproduced.
Exact commands, native output, source/fixture hashes and report are retained in
the printed temporary work directory. The additional patch passes read-only
`git apply --check` against the current source tree.

**The matched full-model test now attributes the strong-line defect to the
actual checkpoint.** Both fresh-process full 75→76 runs completed normally and
passed their independent saved-state gates. Prepared checkpoint/control hashes
and all captured input population columns are identical. Full-spectrum frequency
weights match; input radiation differs by at most 1.23e-11 relative to each field's
peak, with integrated luminosity differences ≤9.41e-9 Lsun at the five recorded
depths. The selected outer O V RHS agrees within 2.16e-15 relative.

| Matched observation | Lambda/weak repair only | Plus guarded strong repair |
| --- | ---: | ---: |
| Outer O V SL26 log10 population-unscaled diagonal magnitude | 18.66386 | 10.69079 |
| Same diagonal at depth 2 | 10.69078 | 10.69078 |
| Maximum raw temperature request (%) | 34.88373 | 34.88370 |
| Negative unlimited population targets | 5,140 | 5,140 |
| Applied temperature cap (%) | 20 | 20 |

The eight-order coefficient anomaly is removed without changing the physical
input or corresponding RHS. These are assembled coupled-Jacobian coefficients,
not necessarily individual atomic rates. This establishes the numerical repair;
it does not establish full convergence or remove the remaining nonlinear
population/temperature response.

The largest raw request grows from 3.02e22% to 1.01e26% because the corrected
O V derivative exposes a much larger update to a seed initially near 1.1e-50 Ne.
The full-step cap still bounds the applied growth. Saved states remain positive,
geometry is unchanged, charge mismatch is 1.14e-11 and elemental abundance
mismatch 4.03e-8 or smaller. Only four cold outer depths reach the 20% temperature
cap; most depths change much less. The captured full equations are accurately
solved, so negative unlimited targets alone do not prove linear-solver failure.

Three explicit Lambda steps from corrected checkpoint 76 have now completed
normally, with temperature fixed and native automatic Lambda release disabled.
This prevents the native tenth-largest-correction switch from ending the seed
bootstrap prematurely. Convergence EPS and population floors are unchanged.

| Checkpoint | Actual raw maximum (%) | Variables >100% | Variables >10% |
| --- | ---: | ---: | ---: |
| 77 | 9.697e24 | 17,552 | 31,780 |
| 78 | 9.710e12 | 3 | 1,347 |
| 79 | 32.281 | 0 | 363 |

Every saved population is positive; all 90 temperatures and the geometry remain
bitwise unchanged. Charge and elemental abundance mismatch stay below 2.67e-15.
Unlimited population targets are nonnegative at every variable and depth in
each of the three solves. The extreme O V/N V seed deficits have cleared without imposed targets
or population floors. The captured raw maximum at 79 is 32.281%; native reported
MAXCH is a different diagnostic (47.669%), so these measurements are kept distinct.

This is bootstrap progress, not convergence. A bounded three-iteration native
continuation from 79 completed with full80/Lambda81/full82, using `N_FIX_BA=0`,
`FIX_BA=0`, `COMP_BA=T`, `DO_LAM_IT=F` and `DO_LAM_AUTO=F`. It rebuilds the
Jacobian every iteration and retains the original full-step caps and EPS=0.02%.
Full80's maximum temperature request is 7.536%; full82's is 8.087%, both uncapped.
Full82 has seven corrections above100%, none with negative unlimited population
targets, and all saved states pass conservation checks. The cold outer temperatures
reverse direction, so thermal settling is still unproven. Requested full mode
does not prevent the native internal Lambda cycle.
Actual full-T convergence and independent fresh-matrix/radiation verification
remain required. Large paired evidence is retained in
`root-cause-v1/matched-full75-source-comparison.json`.
Bootstrap evidence and the rendered trajectory figure are retained in
`original76-guarded-line-lambda-bootstrap3/reconciled-batch-analysis.json` and
the guarded-bootstrap trajectory plots referenced in the archived investigation.


Additional standalone options are covered by `--variant cooling` and
`--variant mixed-new-line`. Each tests 2,750 derivative entries plus the 250
skipped-linearization and 1,000 strong shared-superlevel compatibility entries.
Cooling variant doubles the heat scaling in low-density depths and resets it
in high-density depths. Mixed variant uses old heating at depths 1/2 and the
new direct-line heating method at 3/4. Since continuum BA_UPDATE is stubbed,
its new-method heat oracle explicitly excludes that missing continuum radiation
response; population-rate radiation coupling is still tested. These are
line-kernel checks, not a certification of the full transfer/heating solver.
All three candidate variants pass with maximum rate/heat errors ≤1.12e-15;
unpatched default still fails as expected. No active model inputs or executable
were changed for these tests.

## Source-path scope

These repairs cover `UPDATE_BA_FOR_LINE`, used for the blanketed-line treatment
in this model. Its `GLOBAL_LINE=BLANK` control bypasses the separate line loop
in `CMFGEN_SUB` that calls `SUB_CMF_LINE` and `SUB_SOB_LINE_V3`. Those routines
retain similar normalized-emissivity derivative expressions. This source scan
does not prove their numerical behavior, and the present patches do not repair
or test them. Extending the repair to those options requires separate native
reproducers. The read-only path audit, physical source line references and file
hashes are retained in `root-cause-v1/line-jacobian-path-scope-audit.json`.

## Additional shared-superlevel heating derivative

The compatibility check above deliberately preserved the old strong-line path
when the lower and upper levels share a superlevel. A stronger physical test
now shows that this path is also wrong. Both full-level populations depend on
one superlevel population, so its derivative must include both absorptive and
stimulated opacity responses. The old `IF lower ELSE IF upper` pointer dispatch
loses the upper contribution when the pointers alias. Its population heating
derivative can consequently be about twice the physical value. This is a
separate defect from the catastrophic cancellation proved on the actual model.

A new candidate combines both opacity responses for a shared pointer, defers
the explicit emissivity derivative for shared temperature terms too, and uses
the integrated profile weight in final assembly for those cases. It retains
the deliberately skipped-linearization approximation. The physical line rate
and heating RHS are unchanged. The [incremental experimental patch](patches/bstar3502-shared-superlevel-line-experimental.patch)
applies after the earlier Lambda/weak and guarded strong-line patches.

There is a second native layout: `NEW_VST_METH=T` (the default) uses separate
lower/upper derivative slots that both map to the same population. The earlier
guarded candidate excluded the upper-slot emissivity term but retained the old
`ZNET` assembly for a shared population, introducing a population-heating error
in that layout. The original source passes its fixed-ratio population derivative
test there; the guarded candidate fails by about a factor of two. The updated
repair checks both layouts and corrects this inconsistency. Its distinct-level
results remain unchanged. The completed full80/Lambda81/full82 run is a control
using the earlier candidate; it must not be treated as validation of this
corrected shared path.

The [native shared-superlevel test](cmfgen-review-tests/check_shared_line_jacobian.py)
varies the upper full-level ratio from `1e-4` to `1e-128`, with an inverted-opacity
case, while both levels use the same superlevel population. It checks the line
heating against independent 350-digit differences of the original `eta*ZNET`,
and verifies that the internal transition cancels from the superlevel population
equation. Prescribed local/neighbor radiation responses and temperature-ratio
stress cases are included; continuum and profiling are stubbed. The extreme
temperature-ratio derivatives are algebraic tests, not physical bounds.

The previous guarded source fails (worst relative heat error `3.847e98` in the
temperature stress cases); the new candidate passes all 2,750 heating entries
in each pointer layout within `9.49e-16`. Its scaled internal population equation
residual is ≤`5.90e-17`. All 250 shared skipped-linearization entries per layout
stay bitwise identical. The existing distinct-superlevel oracle still passes
2,750 entries, and all 3,000 distinct native output rows remain bitwise identical to
the prior guarded kernel. The old test's shared bitwise-compatibility condition
now fails intentionally; its report is retained, and the stronger physical
oracle replaces that compatibility requirement in the combined validation.
`check_line_jacobian_branches.py --shared-check physical` now runs the distinct
oracle and both independent shared-layout oracles, retaining the observed legacy
compatibility difference. That flag currently supports the baseline variant.
The focused shared test accepts `--pointer-layout shared|separate`.
Its `--cooling-reset` option uses the model-like `SCL_LN=T` and
`SCL_LN_FAC=0.5`. Since the two levels share one mean superlevel energy, their
energy difference is zero and the native tolerance resets that heating multiplier
to one. Both layouts pass the physical oracle with these settings; all 3,000
native output rows per layout are bitwise identical to the unscaled fixture.
The model's cooling-rate option therefore does not automatically suppress the
shared-level error. This remains kernel coverage, not whole-model attribution.

```bash
OPENBLAS_NUM_THREADS=1 python \
  doc/developer/cmfgen-review-tests/check_shared_line_jacobian.py \
  --cmfgen-root /path/to/cur_cmf \
  --compiler /opt/local/bin/gfortran \
  --source /absolute/path/to/isolated/update_ba_for_line.f
```

The matched first full79→80 comparison has now completed. Prepared checkpoint/
control hashes and all captured input population columns match exactly. Input
radiation differs by at most `1.10e-11` peak-relative and luminosity by at most
`6.64e-9` Lsun. The shared repair changes deep heating-Jacobian coefficients:
the largest thermal-row L1 change is `4.34e-6` at depth79, while the corresponding
maximum over depths1..5 is only `2.34e-12`. These are assembled, population-column-
scaled coefficients, not individual atomic rates.

The largest raw temperature request remains `7.536017%`; the maximum saved
temperature difference is `5.40e-5` K. Correction counts above100% and negative
unlimited population targets are unchanged. Thus this repair is exercised in
the model's deep Jacobian but does not explain its remaining outer temperature
cycle. The candidate's three-step native job subsequently succeeded, with all
saved states passing the independent gates. Its second full temperature request
is still `8.08718%`; convergence has not been established. Exact evidence is in
`matched-shared79-firstfull-comparison.json` and its summary under the diagnostics
root.

The next controlled test enabled `INCL_dSLdT=T`, adding temperature variation
within superlevels to the Jacobian. Its three native steps also succeeded
(full80, fixed-temperature Lambda81, full82), from the identical original79
checkpoint and with the same repaired executable, iteration budget and controls.
The sole VADAT change is archived as exact before/after bytes and hashes.
The largest full temperature requests fell from `4.61514%` to `0.843411%`,
compared with `7.53602%` then `8.08718%` with the option absent/default false.
All temperatures remain positive, all saved states conserve charge and abundance,
and geometry is unchanged. No temperature clipping occurs on these two full
steps. This is promising evidence for a missing temperature coupling in this
model's default Jacobian, rather than a need for further outer-grid tuning.
The benefit is demonstrated with all three experimental line repairs and the
BA-restart fixes already present. The matched option comparison changes only
`INCL_dSLdT` within that repaired runtime; it does not establish the behavior of
enabling the flag alone in an unmodified executable. The original shared-level
temperature branch has separately failed the physical derivative stress test.

It is not yet convergence: full82 still has four raw variable corrections above
100% and 11,776 above 10%. These counts use the full undamped solution, not the
native tenth-largest convergence statistic. A bounded continuation from the
successful temperature-enabled checkpoint82 started at00:21UTC on2026-10-24
(`original82-sl-temperature-fresh-full6`, six freshBA steps). It retains the
temperature option and all physical controls; convergence is still unproven.

Its first continuation full83 also passes the physical gates. Raw/applied
temperature maximum falls to `0.258750%` at depth3, without limiting; the maximum
electron-density request is `0.386211%`. All saved populations, electron densities
and temperatures equal the unlimited linearized target **bit for bit**.
There are no negative unlimited targets. Charge and abundance errors remain
below `2.00e-15`, with original geometry unchanged. The 22 corrections above100%
are two OIII and twenty NiIV variables whose input populations are all below
`3.94e-21 Ne`; the largest request is `290.420%`. Only four populations initially
above `1e-6 Ne` still exceed10%, versus twenty at full82. All trace variables
remain in the convergence counts; 147,333 variables still exceed0.02%, so this
is further progress rather than a convergence certificate. Exact evidence is in
`continuation-observations/through083/`; the updated trajectory and reproducible
CSV data and plot generators are referenced in the archived investigation.

Full84 continues the improvement: temperature maximum `0.0424533%` at depth4,
electron-density maximum `0.120092%`, and all-variable maximum `33.4069%`.
No variable exceeds100%; 1,180 exceed10%, all starting below `1e-6 Ne`.
All saved population/Ne/T values again equal the unlimited target bitwise;
there are no negative targets, and physical gates pass with errors≤`2.23e-15`.
The outermost T request is only `-0.0143976%`. This is still short of the
all-variable0.02% threshold: 135,346 variables exceed it. Closed evidence is in
`continuation-observations/through084/`; the unchanged bounded run continues.

Full85 remains healthy and unlimited: temperature maximum `0.0244157%` and
electron-density maximum `0.0991372%`, both at depth33 (`9884.66 K` before the
step). Outer-depth3 cools by `0.0243924%`; the outer response has not returned to
the former8% cycle. All-variable maximum decreases to `24.4894%`; none exceed100%,
255 exceed10%, and 127,423 still exceed0.02%. No negative targets, unchanged
geometry and conservation errors below `2.34e-15`. Every saved value again equals
the unlimited linearized target bitwise. This is continuing progress, not full
convergence; the depth33 ionization/temperature response and population tail
still require iteration. Evidence: `continuation-observations/through085/`.

Full86 passes with temperature maximum `0.0187151%` and Ne maximum `0.0691056%`
at depth34. All outer-five temperature requests are below `0.0073%`. The largest
all-variable correction is `18.3491%`, with zero above100%,97 above10%, and
120,957 above0.02%. All97 above10% start below `1e-12 Ne`; no variables are
excluded from the convergence checks. Saved values again equal unlimited targets
bitwise; no negative targets, unchanged geometry, and conservation errors
below `2.45e-15`. Temperature alone meeting0.02% does not establish model
convergence while population/Ne corrections remain larger. Evidence:
`continuation-observations/through086/`.

The original matched full80 matrices localize the change to temperature
columns: all 273 captured input population columns match exactly, while the
largest difference in non-temperature coefficients is only `1.90e-12`
peak-relative. At outer depth1 the local thermal temperature coefficient changes
from `+1.994e-7` to `-7.788e-5`, and at depth3 from `+2.447e-7` to `-6.740e-5`.
These are assembled, scaled Jacobian coefficients. This is evidence for the
intended coupling change, not an independent finite-difference certification
of the complete transport Jacobian. The original-solution comparison plot and
CSV are referenced in the archived investigation; the second plot panel
explicitly compares evolved inputs.

The original temperature-enabled first80 radiation was overwritten before its
external observer was attached; its matrices and saved state are intact. An
isolated one-step replay has now recovered that spectral evidence. Its different
diagnostic budget (one final solve versus the original first nonfinal solve of
three) requires an independent matrix, RHS, full correction-vector and saved-state
equivalence check before using its spectrum as representative. All predefined
bounds passed across 273 matrix blocks: peak matrix difference `5.15e-12`,
peak RHS difference `1.16e-8`, scaled full-vector difference `1.56e-10`,
maximum saved-population relative difference `5.18e-10`, and maximum saved
temperature difference `1.61e-8` K. The replay also computes a final-step grey
diagnostic; equivalence was measured against the original solution with that
mode difference retained. The original
missing capture is not reconstructed or relabelled. Evidence is under
`original79-shared-line-sl-temperature-full3/` and
`original79-sl-temperature-first80-replay/` in the diagnostics root.

Using that explicitly verified replay, the full 152,174-frequency F/T input
spectra agree within `1.18e-11` peak-relative. Thus the first-step temperature
change is attributable to the intended Jacobian option at matched input, with
the replay scope retained, rather than a changed physical radiation field.
`sl-temperature-replay-equivalence.json` and
`matched-sl-temperature79-firstfull-{comparison,summary}.json` retain the
independent gates and exact provenance. The physical continuation starts from
the original accepted82, not the replay's earlier80 state.

The isolated candidate build has a byte-identical relink of the control base
proving unchanged link dependencies. Both first full radiation/matrix snapshots
are now preserved. Native
fixture reports, combined validation and exact patch-series application checks
are retained in `root-cause-v1/shared-superlevel-heat-audit/`.

## Ng scheduling and short continuation blocks

The original model already enables Ng acceleration, with `BEG_NG=10%`,
`IBEG_NG=25`, `BW_NG=10` and `ITS/NG=20`. Full86's maximum18.35% remains above
that trigger. No Ng has occurred (`POINT1 LAST_NG=-1000`).

A source-derived scheduling limitation matters once corrections fall below10%.
Each new process initializes `NEXT_NG=2000`; with no previous Ng, the first
eligible solve schedules it four solves ahead. Native code also suppresses Ng
on `LST_ITERATION`. A normal five-solve block therefore places its first possible
Ng on the final step, skips it, then loses `NEXT_NG` at process restart. Repeated
five-solve chunks can keep postponing the first Ng indefinitely. This is a
continuation-cadence issue, distinct from the proven Jacobian and transfer defects.

`ng-scheduling-source-audit.json` retains exact source excerpts and hashes.
This is source-derived scheduling evidence, not a native Ng acceptance or
convergence experiment. The current controlled run keeps its inputs unchanged.
A later healthy continuation should leave more than five contiguous solves
when starting below the trigger, allowing an interior Ng opportunity; its
proposals still need the independent physical gates and fresh full verification.

## Mid-2023 native reproduction and experimental backport

The exact `UPDATE_BA_FOR_LINE` from original-model commit
`b5f07ccc930a4096eaae482184d4a7b8bac8da87` has now been compiled and run in
the same independent fixtures. It reproduces the Lambda derivative error
`1.5022e98` and the full-branch rate/heat errors up to `2.8321e98`.
This is native evidence from the historical routine, beyond textual similarity.
It uses current built module types/libraries for the isolated fixture; it does
not reconstruct the original operating system or historical full executable.

An [experimental combined mid-2023 backport](patches/bstar3502-line-cancellation-mid2023-experimental.patch)
preserves that routine's `REAL*8`/`D0` dialect and now includes all three line
repairs, including the shared-level correction. Read-only `git apply --check` passes against the compiled mid-2023
source tree, whose original line routine matches the exact Git object.
The updated backport passes 2,750 distinct-level derivative comparisons and
2,750 physical shared-level comparisons in each pointer layout (maximum error
≤`1.12e-15`), retaining the skipped-linearization checks. The superseded two-repair
backport and its cooling/mixed/legacy compatibility reports remain in the local
evidence directory; they do not certify the now-corrected shared-level behavior.
The Lambda-only historical repair separately passes all ten native cases.

No installed source has been changed, and no historical full model has been
run with this backport. It covers the line repairs only, not the separate BA
restart defects. Evidence, original source bytes, commands, hashes and reports
are retained under `root-cause-v1/historical2023-line-audit/`. These results
show that rollback retains the cancellation defect; they do not prove the
original model-producing run encountered the same tiny-population inputs.


## Completed T-enabled continuation through88 — 2026-10-24

The six-step continuation from accepted82 completed normally, with full
variable-temperature, freshly computed BA solves83–88. Raw all-variable
maxima decrease290.420→33.4069→24.4894→18.3491→13.9427→10.7981%;
>10% counts decrease6671→1180→255→97→45→10. From84 onward no correction
exceeds100%. Terminal T correction is .0194566%, Ne correction .0439300%,
and110643 variables still exceed the unchanged .02% threshold. All six states
pass positivity, original geometry and charge/abundance checks (errors≤2.67e-15).
This is sustained recovery, not established convergence.

An eight-step continuation from original accepted88 began at06:31UTC to permit
an interior Ng opportunity if MAXCH falls below10%. All physical controls and
existing Ng settings remain unchanged. It runs only in isolated diagnostics;
main model and installed source remain untouched. The previous final88 input
radiation capture is complete and epoch-verified, but it belongs to input87;
an independent final saved-state probe remains required after convergence.


## Separate Ng temperature-sign safety defect

A native arithmetic test found another defect while the accepted88 recovery
continued unchanged. `DO_NG_BAND_ACCEL_V4` appends R, V and Sigma+1 to the
physical population vector and calls its inner fitting helper with NT+3.
The helper's temperature-direction check still indexes NT, which now selects
Sigma+1. Constant geometry bypasses the intended temperature-sign safeguard.
This is separate from the three line-Jacobian defects; no wrong-sign Ng event on the retained
instability reproducer was established. The original failures preceded Ng.

For a positive synthetic history with current T=1, previous=.98, older=.97/.965,
the extrapolated T=.96 opposes the latest increase. The actual original V4
wrapper incorrectly accepts it at all four tested depths. Its physical-only
inner layout correctly rejects the same history. Both current and exact
mid-2023 source contain the dimension/index mismatch; the native numerical
fixture currently compiles the current source only.

The [experimental Ng guard patch](patches/bstar3502-ng-temperature-guard-experimental.patch)
passes the physical T index separately to a private V4 helper and initializes
the comparison temporary. It leaves the Ng fitting mathematics and legacy
V1 helper/caller signatures unchanged. The complete native V4 wrapper passes
25 candidate cases: wrong-sign warming/cooling rejected, correct-sign
warming/cooling and fixed T preserved, each over five band widths. All
geometry remains bitwise unchanged, with bounds checks and invalid/division
by zero/overflow traps enabled in the candidate. Another25 unpatched controls
reproduce the original defective acceptance while retaining the valid cases.
Read-only patch application checks pass against the current source.

The [reusable native test](cmfgen-review-tests/check_ng_temperature_guard.py)
compiles the actual full V4 source with a deterministic scratch-reader stub.
It opens no model checkpoint and never runs a model:

```bash
python3 doc/developer/cmfgen-review-tests/check_ng_temperature_guard.py \
  --source /path/to/unpatched/do_ng_accel_band_v4.f --expect-original-defect
python3 doc/developer/cmfgen-review-tests/check_ng_temperature_guard.py \
  --source /path/to/patched/do_ng_accel_band_v4.f
```

`--expect-original-defect` certifies reproduction, not a corrected implementation.
Reports and commands are retained under local `ng-temperature-guard-audit/`,
`ng-temperature-guard-candidate/`, `ng-temperature-outer-wrapper-audit/`, and
`ng-temperature-public-{original,corrected}/`. The patch has not been added to
the running model's runtime or installed source; actual Ng benefit and any
need for this safeguard in the recovery branch remain to be measured.


### Actual first Ng93→94 in the recovery branch

The longer continuation has now permitted the first native Ng after full93.
An independent native replay on exact93/92/91/90 states reproduces published94
bit-for-bit, including all populations, Ne, T and geometry. Its applied maxima
are22.5478% in population and .0868822% in T, with positivity and conservation
checks passing (charge1.39e-13, abundance2.54e-13). Full93's raw maximum3.47748%
is a pre-Ng residual and must not be relabelled as a residual of94. The next
full95, in the same unchanged process, is still needed to measure improvement.

On these actual inputs the experimental corrected Ng guard accepts the step
but skips three deep layers85/89/90. Largest population difference from the
actual original Ng is .008174%, T difference≤.047K; all component changes in
those layers are below .02%, and87 other depths plus the dominant update are
bitwise identical. Thus the safety defect is real but does not account for
the bulk correction in this event. It remains an unapplied experimental patch,
not a demonstrated convergence remedy. Evidence: active case
`ng93-reconciliation.json` and sibling `*-ng093-arithmetic/report.json`.


### First full solve after Ng

Full95 is healthy and unlimited. Largest raw correction2.56308%, T .0101243%,
Ne .00182803%; no negative targets, original geometry, charge/abundance
errors≤2.67e-15. Relative to full93 before Ng, Ne falls .0195827%→.0018280%
and the largest HeI-ground correction among populations≥.01Ne falls
.747519%→.122433%. The full >1% count falls10639→2647, with all remaining
>1% populations below1e-12Ne. However >.02% rises89899→91395; smaller
populations still readjust and convergence remains unproven. This is an
observed before/after trajectory, not a controlled no-Ng counterfactual.
The same unchanged process continues with full96/97.


### Completed continuation through97

The eight physical solves89–93/95–97 all finish full/variable-T/fresh-BA and
pass physical state checks, with native success and exact Ng93→94 replay.
Terminal97 raw maximum .5426303%, T .00078236%, Ne .00038314%; no variables
>1%,10% or100%, but55362>.02%. All populations initially≥.01Ne are below
.02% (maximum .0188310%); the gate still includes every smaller population.
A new ten-step fresh-BA continuation from exact97 is running with unchanged
physics and threshold. No final convergence or independent saved-state
radiation certification is claimed.
