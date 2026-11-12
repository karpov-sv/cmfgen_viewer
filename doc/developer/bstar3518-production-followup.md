# Bstar3518 production follow-up — 12 November 2026

Read-only inspection of the newly copied production snapshot at checkpoint
204. Iteration 205 is incomplete and receives no solve credit. No native run,
control edit or checkpoint modification was performed for this inspection.

## Finding

Production has the version-2 policy, but **never applied the population repair**.
The same depth-24 helium instability persists on the unrepaired trajectory.
This snapshot does not demonstrate a recurrence after the verified local
repair. The automatic recognition remains too restrictive despite the earlier
contrast-threshold fix.

The automatic journal is
`.cmfgen-runs/20261112T140524Z-auto-db54f665/`. Its registry lists
`localized_population_projection` version 2, its `actions` array is empty,
and every recorded evaluation of that policy is `not_matched`.
It resumes production checkpoint 190, refreshes radiation without population
solves, and then continues ordinary batches 191–195, 196–200 and 201 onward.
It did not start from our verified local checkpoint 193.

The production binary's historical record 193 has He I fraction 0.209104 at
depth 24, unlike the retained repaired test trajectory. The matching counter
therefore does not identify the repaired population state. The original local
verification evidence and test copy remain available.

## Current state

Selected record 204 is positive and finite, with maximum charge error
1.33227e-15 and minimum population 1.06013e-60 cm^-3. Depth-24 He I fraction
is 0.750676 versus 0.00315446 and 0.00274706 at depths 23 and 25: contrast
237.973. It independently qualifies as an isolated spike. CORRECTION_SUM
has 1,762 coordinates above 100%, 10,344 above 10%, and 34,941 above 1%.
The final Lambda luminosity is 5.23651% above the imposed target.

Full 203 again requests impossible targets for all 68 excited He I levels;
its largest local He I decrease is 1.5116e6%. Full 201 instead has a large
increase and only one nonpositive He I target. Alternating full and Lambda
steps keep revisiting the same instability.

## Exact missed recognition at checkpoint 200

The completed 196–200 invocation provides complete raw arrays bound by its
recorded `solution_start_offset`. Diagnostic-only slices and summaries are
retained in `output/bstar3518-production-followup/`; the source is untouched.

| Full solve | Printed maximum decrease (%) | Variable of raw maximum at depth 24 | Minimum major-species scale | He I maximum decrease (%) | Nonpositive excited He I targets |
| --- | ---: | ---: | ---: | ---: | ---: |
| 196 | 1.59e7 | 102 (He II) | 0.0033962 | 131,730 | 68 |
| 198 | 6.45e6 | 102 (He II) | 0.021046 | 984,690 | 68 |
| 200 | 6.64e7 | 36 (He I level 5) | 0.0011526 | 66,400,000 | 68 |

Historical binary record 200 independently has a He I fraction of 0.889451
and contrast 58.0902, satisfying the version-2 spike requirement.

The current evaluator nevertheless rejects the batch:

1. It selects only the last two full solves, 198 and 200. Solve 198 exceeds
   its scale cutoff 0.01. It never considers qualifying full solve 196 instead.
2. Selecting 196 and 200 alone is insufficient: the later raw-coordinate gate
   requires the He I maximum itself to exceed 1e6% in both solves. At 196,
   that maximum is 131,730%; the much larger printed maximum belongs to He II.
   The He I failure is still independently severe, with all 68 excited targets
   nonpositive. At 198 the He I maximum also narrowly misses 1e6%.

Thus the journal's `not_matched` is explained by actual code gates, not an
absent installation, stale policy version or a failed execution of the remedy.

The generic progress evaluator also continues to accept a temporary dip in
any diagnostic across three batch endpoints, even when the next endpoint
rebounds. Its progress messages do not demonstrate removal of this spike.

## Recognition correction

The next change should address the recognition logic, with a regression based
on the complete 196–200 batch. It must bind repeated impossible targets to the
outlier ion even when the global maximum belongs to another ion, and consider
independent qualifying full solves within the same validated invocation.
The independent positive/conserved spike, exact raw-coordinate binding,
bounded provisional procedure and strict native response checks must remain.
Simply restarting automatic mode or repeating an unrecorded manual projection
does not fix this automation gap.

The earlier local checkpoint-193 recovery and its native verification remain
valid within their tested scope. Automatic readiness established successful
preflight; it did not establish that this production trajectory would trigger
the recovery policy. That distinction was missing from the previous handoff.

## Implemented policy version 3

Version 3 now locates the unique eligible binary spike independently of the
printed global maximum's ion or depth. Complete invocation-scoped raw arrays
bind the failure to that ion. It selects two independent failing full solves
from the complete invocation, requiring that the latest full response still
fails. A temporary weaker intermediate solve no longer hides the evidence.

A severe ion-specific response requires a decrease >=1e5% and nonpositive
targets in at least half the explicit levels. Two such responses qualify.
Alternatively, one severe response can pair with a ground-only nonpositive
target at 100–1000% in an ion with at least ten levels. Two moderate ground
overshoots alone, an unrelated ion's huge maximum, a minority-level failure,
a healthy latest full response and historical-only observations do not qualify.
Printed global extrema must still be finite and cover the ion-specific raw
request within rounding tolerance; valid global scaling is retained as metadata,
not a 0.01 cutoff for diagnosing a different ion.

Ground/excited cycles receive the existing uncredited, bounded settling stage
at either low or high contrast. Its maximum two batches, improving ground-only
overshoot requirement, physical guards and strict subsequent two-positive-full
verification remain. No convergence acceptance or native safeguard is relaxed.
The policy version bump invalidates previews built with earlier semantics.

A read-only replay against the actual copied checkpoint 204, excluding the
incomplete 205 header and using the four complete 201–204 solution arrays,
now selects the repair with full observations **201 and 203**, at depth 24
and contrast 237.973. It requests settling followed by strict full-response
verification. `output/bstar3518-production-followup/version3-recognition-204.json`
retains the decision and unchanged checkpoint/control hashes. This is diagnostic
replay, not an authorization to execute an incomplete copied invocation.
Production automatic execution still waits for validated fresh evidence after
restart; it uses the existing checkpoint and does not need the old local 193
state. No model computation or checkpoint/control edit was performed here.

Regression coverage reproduces the 196–200 and 201–204 signatures, independent
global maxima, intermediate weaker solves, the healthy-latest refusal,
minority/unrelated failures, severe-request boundary and strict high-contrast
settling checks. An isolated subprocess test also verifies actual controller
selection and recovery despite the production scale factor 0.034148. Existing
physical, stale-data, budget and whole-procedure rollback checks remain active.

The ordered policy registry was also replayed against that actual snapshot:
`choose` selects `localized_population_projection` as an action, ahead of
generic continuation, using full solves 201 and 203. The decision trail is in
`version3-registry-selection-204.json`. Final validation passes **126 targeted
tests**, required Python compilation and `git diff --check`. Deploy version 3
and restart automatic mode from the current production state; recovery is
still dispatched only after valid fresh invocation evidence is available.
