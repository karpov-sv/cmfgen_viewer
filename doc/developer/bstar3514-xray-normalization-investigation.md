# Bstar3514 X-ray normalization scheduling (2 November 2026)

Scope: investigate the post-repair disturbance and remove its specific cause,
without trying to converge the atmosphere. The original model is
`models/tests/model_Bstar3514`; the isolated native trial is
`models/test/model_Bstar3514_xray_gate_test`.

## State at the stop

The completed batch ends at checkpoint 119. Automatic attempt 10 was cancelled
before completing another solve and restored that checkpoint. Process inspection
confirmed the model idle. Populations are positive and finite, minimum
6.88933e-65 cm^-3; charge error is 1.11022e-15. The repaired depth-31 He I stage
contrast is 0.906243, so the original isolated helium spike has not returned.

After the legitimate 0.1 filling-factor multiplier following full solve 95,
large full-step corrections declined. At full 115, however, the maximum decrease
was still 221%: its unlimited target was negative. The subsequent fixed-T Lambda
116 returned `MAXCH=97.50728`, satisfying the native `MAXCH<100` source gate.
It therefore applied a filling-factor multiplier of 1.4762399868465603.
The source emissivity scales with the square of those factors, so this changed
it by a factor 2.17928 while the full solve was still unsettled.

| Iteration | Type | Maximum increase | Maximum decrease | Source event |
| --- | --- | ---: | ---: | --- |
| 115 | Full | 72% | 221% | None |
| 116 | Lambda/fixed T | 22.7% | 49.4% | Filling factors multiplied by 1.47624 |
| 117 | Full | 2150% | 140% | Response to changed source |
| 118 | Lambda/fixed T | 868% | 52.5% | None |
| 119 | Full | 563% | 105% | None |

At 119, the largest increase is N III superlevel 11 at depth 25; the largest
reduction is Ne II superlevel 12 at depth 29. Luminosity remains 15.0783% above
target. This is a broad ionization readjustment, distinct from the isolated
He I checkpoint defect repaired on 1 November. A new projection or a relaxed
convergence tolerance is not justified by this evidence.

## Cause and targeted correction

`new_main/cmfgen_sub.f` originally used only `MAXCH<100` and the existing X-ray
controls to authorize normalization. A small fixed-T Lambda update does not
establish that the coupled variable-T equations have settled. The full and
Lambda metrics cannot be interchanged for that decision.

Group 34 captures the solve's eligibility **before** `SOLVE_FOR_POPS`. This
ordering matters: that subroutine changes `LAMBDA_ITERATION`, `FIXED_T` and
`COMPUTE_BA` to schedule the next solve. Looking only at their values afterward
can misclassify the just-completed Lambda step as full, or a fresh full step
as a reused or Lambda step.

Ordinary normalization now requires a freshly computed matrix, a full solve
with T free, no actual partial T fixing, no concurrent Ng acceleration, and
the existing `MAXCH<100` condition. Ineligible small steps print
`XRAY_NORMALIZATION_DEFERRED`. Explicitly requested `RD_LAMBDA` bootstrap keeps
its existing source normalization behavior. Source target `XRAY_LUM`, tolerance
`XRAY_ERR`, intrinsic-emission checks, square-root multiplier and `[0.1,10]`
bounds are unchanged. The existing fresh-radiation/matrix continuation after
an accepted source change is unchanged.

The cumulative patch revision is `2026-11-02.1`. The incremental review diff is
[cmfgen-xray-normalization-gate.patch](patches/cmfgen-xray-normalization-gate.patch).
This is a native scheduling fix, active during ordinary and automatic runs;
no model-specific recovery switch is required.

## Native regression evidence

The existing `check_convergence_repairs.py` compiles the actual normalization
block and both production eligibility assignments. Its expanded driver checks
20 successful branches plus invalid-input exits. Coverage includes:

- The recorded iteration-116 metric and multiplier: the old production block
  changes the source by 1.47624 and fails the no-mutation assertion; the repaired
  block preserves both filling factors and does not request source continuation.
- Automatic Lambda switching to a full next step and a full solve switching
  to a Lambda next step, proving the mode snapshot has the correct timing.
- Fixed and partially fixed T, reused BA, and simultaneous Ng rejection.
- Explicit Lambda bootstrap, ordinary upward/downward normalization, tolerance,
  zero emission, multiplier bounds, intrinsic emission and invalid luminosities.
- Fresh solved continuation after legitimate source changes.

The production branches pass at `-O0` and `-O2`, with invalid/zero/overflow
traps. Existing interpolation positivity and collision finite-difference checks
also pass in the same runs. Reports are retained in
`/private/tmp/bstar3514-xray-native-final-O0/report.json` and
`/private/tmp/bstar3514-xray-native-final-O2/report.json`.

## Isolated model response

The trial starts from a checksum-bound copy of original checkpoint 119 using
the staged binary. It requests only three native solves with fresh radiation
and BA (`COMP_F=T`, `COMP_BA=T`, `N_FIX_BA=0`, `FIX_BA=0`), retaining all source
controls, physical inputs and tolerances. The original model stays stopped.

Run `20261102T120219Z-f5866f95` completed exactly three native solves, 120–122:
full/free-T/fresh BA, Lambda, then another full/free-T/fresh BA. At Lambda 121,
`MAXCH=60.7349` would satisfy the old scalar gate; the new code reports
`XRAY_NORMALIZATION_DEFERRED` and retains the source. Full 122 also writes the
ordinary TGREY diagnostic, which does not replace its full variable-T solve.

| Iteration | Type | Maximum increase | Maximum decrease | Nonpositive unlimited population/Ne targets |
| --- | --- | ---: | ---: | ---: |
| 120 | Full | 167.890% | 101.360% | 1 (Ne II level 12, depth 29) |
| 121 | Lambda | 60.735% | 21.248% | 0 |
| 122 | Full | 127.520% | 95.118% | 0 |

`raw-response-audit.json` checks all 200,970 finite coordinates in each complete
invocation-bound raw solution array. The final full solve has no nonpositive
unlimited population or electron-density target anywhere. Its transformed
solver metric is 1948.438%, versus the earlier 1e7% sentinel for an impossible
negative target; it remains well above numerical convergence.

Relative to 119, element totals change by at most 3.10862e-15 and charge error
is 1.33227e-15; geometry is identical. Depth-31 He I contrast is 0.901414.
Variables requesting more than 10% correction fall from 30,116 at 119 to 4,456;
those above 1% fall from 69,167 to 47,117. Major-species scale is unity in both
full verification solves. Normalized luminosity spans 0.9987–1.1507, with inner
Rosseland depth 103.1. Generated luminosity is still 14.9222% above target.

The X-ray luminosity at 119 was already within 1.8% of target. At 122 it is
5.1426e-9 Lstar, within 2.9% of the unchanged 5e-9 target and existing 10%
tolerance. No source adjustment occurred in this trial. The decline demonstrates
continued recovery at the corrected source strength; it is not a measured
speedup caused by a different Jacobian. The old/new production-branch replay
provides the causal demonstration that the fix prevents the premature
iteration-116 adjustment.

## Installation and handoff

The local main executable was serially rebuilt and replaced atomically with
revision `2026-11-02.1`. Main objects match the staged objects byte for byte.
Recursive make refreshed two archive members; repeating the identical link
command and working directory reproduced the entire trial binary byte for
byte, confirming no additional linked numerical change. Old sources, objects
and executable are preserved under:

```
/Users/karpov/CMFGEN2023/cur_cmf/.cmfgen-backups/bstar3514-xray-normalization-20261102T125511Z/
```

The source updater separately backed up its two changed files and update state
in `.cmfgen-backups/20261102T125511Z-source-patch-4a66742b/`. Local compiler settings
and aliases were preserved. The cumulative patch was applied and reversed
against all 50 controlled source/build files; two local settings files were
excluded and preserved.

Verified checkpoint 122 and 136 matching output files were transferred into
`models/tests/model_Bstar3514`. Verification-only fresh-BA/radiation controls
were restored to the original values. Every protected original input, including
source factors/target, tolerances, structure and atomic inputs, is byte-identical.
The 182 replaced original matrix caches were moved intact into the recovery
backup, and all replaced original outputs were copied there:

```
.cmfgen-recovery/bstar3514-xray-normalization-handoff-20261102T132053Z/
```

`handoff.json` records transfer hashes and physical checks. Its `evidence/`
contains the native result, complete raw audit, installed-binary provenance,
patch, branch regression and roundtrip reports. `next-auto-check.json` confirms
ordinary automatic continuation from 122 with the new executable and a finite
matching radiation cache. Automatic iteration remains stopped. No additional
native batch was started to pursue convergence.

Validation also passed 127 affected updater/version/build/automatic-transition
Python tests plus two new deferral-evidence tests, compilation, and viewer
listing/RVTJ/OBSFLUX/MOD_SUM/documentation smoke checks. The remaining luminosity
error, large positive corrections, outer-boundary moment/ray warning and
hydrostatic residual are outside this scheduling repair; global convergence
and scientific acceptance remain separate checks.
