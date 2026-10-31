# Ordinary moment transport: derivatives of J repair and H limits

Fix 25 corrects `VAR_MOM_J_CMF_V12` and its rectangular inserted-grid
counterpart. The forward radiation solver and model controls are unchanged.
Kernel and workflow validation do not establish full-atmosphere convergence.

The [consolidated source patch](patches/cmfgen-current.patch) now includes this
repair together with fixes 1–24. Use the [source updater](cmfgen-versioning.md#apply-or-update-the-source-patch-set)
to apply or update it while preserving local build settings and aliases. The
[incremental source patch](patches/cmfgen-moment-limits.patch) is retained only
for upgrading a checkout already containing fixes 1–24. Do not apply it after
the current consolidated patch.

The [consolidated manifest](patches/cmfgen-current.json) records the complete
snapshot, and the [incremental manifest](patches/cmfgen-moment-limits.json)
retains the before/after source hashes, validation, installed executable hashes
and rollback paths for this repair. It changes three files:
`plane/var_mom_j_cmf_v12.f`, `new_main/mod_subs/do_var_cont.f`, and the latter
directory's Makefile. Both patch forms have been applied and reversed in scratch
trees, with every resulting byte checked against the captured source hashes.

## Defects and repair

The ordinary forward solver replaces negative solved r²J with `abs(r²J)/10`,
then constructs H from that repaired field. Depending on `CHK_H`, it also
caps r²H at signed 0.99999 times the nodal maximum or average r²J. Previously,
the variation solver used raw J for its reconstruction and history, and did
not differentiate either limit.

The repaired operator keeps **raw J** for the matrix-equation derivative
`d(rhs)/dp - dA/dp * J_raw`. It separately reconstructs the same repaired J and
capped H as the forward solver, and applies their piecewise derivatives:

- Negative-J rows multiply the solved response by -0.1.
- H reconstruction uses those repaired J responses. Its direct opacity partial
  is corrected for the difference between raw and repaired J, using the exact
  optical-depth Jacobian already computed by the kernel.
- An active H cap replaces the flux derivative with the signed derivative of
  the chosen nodal maximum or average. Both inward and outward limiting branches
  are covered; `CHK_H=NONE` leaves that operation disabled.
- Repaired J/H values and derivatives feed subsequent frequency steps, including
  line-variable response slots and diffusion temperature/gradient vectors.
- Inserted-grid opacity/emissivity maps remain on their native rows until final
  model-grid projection. Independent coherent-scattering responses receive the
  same J/H limiting chain.

Coherent scattering changes the raw solve's diagonal. Its equivalent source
forcing therefore uses **raw J**, even though the forwarded radiation is repaired.
The ordinary production wrapper now makes that distinction explicitly. A flag
set only when it calls the ordinary variation entry prevents other solver
families from reading stale ordinary work storage. Shared update-routine ABIs
are unchanged. Relativistic, time-dependent and separately extended paths were
regression-tested; this patch does not add new clipping rules to those families.
The extended ordinary path inherits this repair through the rectangular entry.

The derivatives are local to the selected piecewise branch. At exact zero-J,
H-cap or nodal-maximum switches, the forward map is nonsmooth; the tests use
states and perturbations away from those switches. They freeze formal-ray angular
factors, as required by this approximate Newton operator.

## Actual-model counterexamples

Retained native coefficients provide two independent reproductions:

| Case / response to current ETA(33) | Before | Repaired | Forward finite difference |
| --- | ---: | ---: | ---: |
| Negative J: dJ(33)/dETA(33) | +29.80706790 | -2.98070679 | -2.98070679 |
| All J positive, capped H: d(r²H(33))/dETA(33) | -5,814,002.2543 | +12,514,581.0355 | +12,514,581.0355 |

The [negative-J record](data/bstar3010-negative-j-20261025/README.md) and
[independent H-cap record](data/bstar3010-negative-j-20261025/h-clamp/README.md)
retain the original failing evidence. Historical replay logs there intentionally
show the old operator. New regressions rerun the actual native transport, rather
than applying the diagnostic chain rule to its old results.

## Validation

GNU Fortran 15.2.0 on Linux; bounds checking and invalid/zero/overflow traps.
The two active-limit suites pass at O0/one thread and O2/five threads.

| Suite | FD column comparisons | Largest relative column error |
| --- | ---: | ---: |
| Actual-record ordinary kernel, including inward-history stress | 1056 | 9.37e-6 |
| Actual production ordinary continuum/scattering assembly block | 168 | 1.52e-6 |
| Active limits on inserted moment grids | 780 | 1.11e-5 |
| Production inserted-grid wrapper through projection | 252 | 1.33e-7 |

All acceptance thresholds are 3e-5. Ordinary field reconstruction agrees with
native forward J/H to 2.43e-14 relative; inserted active-limit fields agree to
7.98e-14. The ordinary suite makes 3480 native invocations plus 360 for assembly;
the inserted suite makes 1680 kernel plus 510 wrapper invocations per build.
Its sharp-source fixture exercises positive-J H limiting at the first frequency,
negative-J repair at the second, and propagated responses at the third.

Coverage includes current and earlier-frequency opacity, emissivity and
scattering, coherent/noncoherent scattering, `N_ON_J`/`G_ONLY`, `CHK_H=NONE`,
`MAX_VAL` and `AV_VAL`, both signs of flux caps, diffusion boundary derivatives,
nonuniform clumping, line-level and superlevel-temperature responses. Actual-record
replays prescribe the retained angular factors; inserted-grid tests execute the
native angular interpolation. Both execute the real forward/variation kernels.
Wrapper tests explicitly exclude later atomic-rate assembly.

The original grid suite also passes: 64 bitwise forward comparisons on inserted
grids and 64 without insertion, maximum FD error 6.64e-6, and production-wrapper
maximum 1.62e-7. The alternate-family suite passes 5564 native invocations at
O2/five threads, maximum column error 2.986e-5. The new ordinary regression fails
on the pre-repair source, as expected. A final regression links the installed
archives directly, without private kernel objects.

Commands (use a fresh `--work-dir` for each run):

```sh
python3 doc/developer/cmfgen-review-tests/check_moment_limits.py \
  --cmfgen-root /path/to/cur_cmf
python3 doc/developer/cmfgen-review-tests/check_moment_limit_grids.py \
  --cmfgen-root /path/to/cur_cmf
```

Add `--optimization O2 --threads 5` for the optimized configuration. Both accept
`--source-root` for isolated candidates. See the patch manifest for the exact
commands, reports and source hashes used for this installation. Earlier-frequency
responses can be small relative to the total field; the ordinary scattering
history test uses larger Richardson steps to resolve them above subtraction
noise, without relaxing the acceptance threshold.

## Build and rollback

All native builds were serial. Executables were first built in a separate output
directory, then all three linked against the final archives and installed by
atomic file replacement. Existing mapped processes retain their old executable.
The new atmosphere executable SHA-256 is
`eae34c599335a719ec4dbc7a71ced761c2f3f34676444adfa19b22a5baf6db42`.

Local build evidence, commands, old sources/libraries/executables and validation
reports are under `tmp/cmfgen-moment-limits-fix/`. The rollback snapshot is
`installed-before/`; it is also retained in the native checkout at
`.cmfgen-backups/20261025-moment-limits/`. Installation metadata is
`installation.json`, and the native checkout records this build in
`cmfgen-moment-limits-build.json`. Restoring
sources alone is insufficient: restore/rebuild matching archives and executable
files as well. Main-model controls, checkpoints and radiation caches were not
modified. A subsequent model trial should compute a fresh BA matrix using the
new executable; reusing a matrix formed with the old derivatives does not test
this repair.
