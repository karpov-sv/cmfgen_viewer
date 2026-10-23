# Extending automatic convergence

The public contract is one command: `cmfgen_run.py MODEL --stage main --auto`.
Every shipped, tested rule is active. Users do not diagnose the problem or
choose recovery switches. Unknown problems produce an investigation report;
after investigation, the validated remedy becomes another registered policy.

## Components

- `auto_diagnostics.py`: invocation-specific correction evidence, raw temperature
  vectors, finite-core/restart validation, and convergence candidates.
- `pop_initialization.py`: executable capability and original saved-source grid/level checks for the bounded POP trial.
- `auto_hydro.py`: native hydro handoff evidence and profile/scheduling checks.
- `auto_policies.py`: ordered, versioned `POLICIES` and read-only decision functions.
- `runner_auto.py`: shared execution engine, locks, budgets, recovery snapshots,
  guarded mutations, provisional procedures, policy events, and issue reports.
- `runner.py`: native process execution and temporary-control restoration.
- `checkpoint_health.py`: bounded read-only inspection of the selected `SCRTEMP` record for recognized native binary layouts; unsupported layouts are explicitly unverified.

## Adding a diagnosed problem and debugged remedy

Reproduce the problem from `issue.json`, the model inputs and linked native-run
journals. Establish an exact recognition signature, the conditions where the
remedy applies, which files it changes, and an independent check of its effect.
Do not turn a generic crash into a speculative adjustment.

Implement a read-only evaluator accepting `Context`. Return `None` when the
problem does not match. Raise `Declined(reason)` when it matches but the remedy's
prerequisites cannot be established; the refusal is retained in the policy
trail. Return a `Decision` when a supported action, continuation, or stop is
appropriate. Expected file/validation errors stop for review rather than
allowing an uncontrolled retry.

Register a `Policy` in the ordered `POLICIES` tuple with a unique, stable `id`,
a positive `version`, a `when` value (`failure` or `success`), a description,
the evaluator, and a per-invocation `max_applications` for a bounded remedy.
Raise the version whenever eligibility or remedy semantics change. Plans retain
the registry manifest and reject changes between preview and execution.

`Context` includes the model path, native plan/result, pre-attempt snapshots,
validated numerical evidence, correction history since the last intervention,
current phase, previous actions, and the latest invocation's log. Failed
numerical/output evidence reaches failure policies with `status=invalid_evidence`
and its validation error. Cancellation and timeout always stop immediately.

## Decisions and execution primitives

| Field | Meaning |
| --- | --- |
| `kind` | `action`, `continue`, `stop`, or `converged` |
| `reason` | Specific diagnosis and why this response applies |
| `action` | Stable action name for the journal |
| `changes` | Value-only patches to supported model controls |
| `caches` | Explicitly supported regenerable caches to retire |
| `steps` | Optional tuple of provisional `RecoveryStep` objects |
| `next_phase` | `iterate` or `verify` after a simple action |
| `evidence` | Bounded, JSON-serializable measurements supporting the decision |

The registry assigns `policy_id`; actions and decision events retain it.
All actions use the engine's locks, input/executable checks, action backups,
and application/work limits. Existing mutation primitives support value-only
VADAT and ADJUST_CORRECTIONS patches and a short whitelist of regenerable
BA/radiation caches. A remedy requiring a new mutation class must first add a
reviewed, guarded execution primitive and its recovery support; arbitrary
scripts and source/executable edits are not policy actions.

The engine independently requires fresh-Jacobian verification before accepting
`converged`, even if a buggy rule requests it earlier. Scientific quality
remains a separate assessment. Rules cannot redefine this acceptance invariant.

## Multi-step remedies

A `RecoveryStep` declares a name, positive requested iteration count, a read-only
validator receiving `Context`, and supported `native_options`. Its validator
returns optional JSON metadata or raises an error. The normal native-output,
checkpoint and finite-core checks always run before the custom validator.
The hydro temporary guard override and the existing temporary LTE initialization
(`lte_initialization`/`t_exc` and `pop_initialization` builder options) are reviewed native options;
POP requires the exact native completion marker and a normal-continuation check;
additional native options require corresponding runner validation/restoration support.

The entire recipe is budgeted before applying it. Initial control changes and
all intermediate native states remain provisional against one complete baseline.
Only the last successfully validated step commits the new rolling state.
A failure, cancellation, or budget stop rolls back the whole provisional recipe,
including its ADJUST_CORRECTIONS changes and native-updated structure controls.
External edits that prevent safe rollback are preserved and explicitly reported.

A simple known remedy may run within a provisional recipe. The step snapshot
restores the pre-step state, the fix is applied, and that same step is retried.
For example, an EDDFACTOR mismatch during the guarded hydro follow-up retires the
cache and retries the guarded step; it does not repeat the guard-off iteration.
The remedy's application limit and the shared work budget still apply. Nested
multi-step procedures are deliberately unsupported.

Correction history is reset after adjustments or completed recovery procedures,
so stalled/oscillating evidence from the old regime cannot immediately reject a
new remedy. Slow but consistently decreasing corrections are permitted to run
until convergence or a configured limit.

## Validation and evidence

Preflight and main/test attempt completion inspect the selected binary checkpoint.
The supported `SCR_READ_V2` layout uses 16,376-byte records of IEEE binary64
values, a `28-Feb-2004` pointer, recognizable geometry and `MODEL` dimensions.
Only the selected population record is streamed; record padding and unselected
history are ignored. Nonfinite populations/geometry and nonpositive T/Ne fail
validation, regardless of an older finite `RVTJ`. Unsupported layouts retain
an explicit unverified warning and the existing text checks.
`native_diagnostics.py` also recognizes specific NaN/Infinity numerical-state
messages. These errors remain fatal even with native completion markers.
The first failure policy, `invalid_numerical_state`, stops before recovery
policies; the controller retains its normal rollback behavior. It never chooses
an older native record or reseeds the failed continuation. Regression coverage
is in `tests/test_checkpoint_health.py`, `tests/test_native_diagnostics.py`,
and the real subprocess tests in `tests/test_runner_auto.py`.

The checkpoint sequence includes native Ng acceleration increments only when
an explicit success marker follows a completed population solve. These
increments do not add radiation solves to the work budget. Missing/duplicate
completion evidence, unexplained gaps, and mismatched final pointers remain
errors. An acceleration after either of the last two full solves prevents
convergence acceptance from those solves. `tests/test_auto_ng.py` covers this
handoff and the near-matches that must still roll back.

Add a regression reproducing the failure and the complete successful recovery.
Also cover a near-match that must decline, an ineffective remedy, its retry
limit, stale/invalid evidence, and failure/cancellation rollback where applicable.
Use isolated subprocess fixtures and native output/checkpoint markers. Do not
run the user's scientific model as a test.

`tests/test_auto_policies.py` demonstrates registering a remedy and a multi-step
recipe without modifying the controller, rejecting false convergence, restoring
failed provisional edits, composing cache and hydro recovery, and invalidating
a preview when policy versions change. `tests/test_auto_hydro.py` tests the
Bstar3500 eligibility and guard-restoration checks. `tests/test_runner_auto.py`
checks the shared controller lifecycle and numerical acceptance.
`tests/test_auto_lte.py` covers confirmed initialization failures, compatibility
refusals, temporary LTE restoration, normal-continuation verification, and
preservation of pre-existing checkpoints. Keep the user-facing rule table in
`doc/main-computation.md` synchronized with the registry.

On unhandled/review/budget stops the journal contains `issue.json` and `issue.md`.
The structured report includes native diagnostics, decision/refusal trails,
policy versions, executable identity, and recovery/journal locations. It is
bounded evidence for investigation, not a complete copy of all scientific
outputs or authentication of binary populations.


Ordinary main runs reuse each registered evaluator through `main_recommendations.py` in advisory mode. Evaluators must remain read-only: recommendations are persisted and displayed but never executed. Success rules run only on validated fresh evidence; trend rules receive consecutive compatible batch summaries, not synthetic subdivisions of one invocation. Native children of an automatic run suppress this extra advisory assessment because the controller already owns diagnosis and recovery. Add coverage for both automatic selection and ordinary-run advice when introducing a rule.

`tests/test_auto_pop.py` covers temporary POP recovery, native compatibility refusals, missing capability/source inputs, coefficient formats, original-control restoration, full rollback, and ordinary-run recommendations. A compiled POP success marker establishes capability; native completion evidence is still required at runtime. Source files are checked against the pre-failure plan so AUTO_ADD-created or changed estimates cannot silently qualify as original inputs.

Automatic main followed by flux is represented by an ordinary sequence whose initial plan is automatic and whose `stage_options.automatic_main` retains the reviewed policy manifest and work budgets. Main is rebuilt and its manifest rechecked before execution. The sequence holds the model reservation across the transition and starts flux only if main returns independently verified success. UI and CLI share this configuration path.
