# Related moment solver repairs

25 October 2026. Follow-up to the [related-path audit](cmfgen-related-moment-paths-audit.md)
and [inserted nonrelativistic grid repair](cmfgen-inserted-moment-grid.md).
The fixes are included in the cumulative source patch. Validation included
serial rebuilds and atomic final links of the atmosphere and spectrum
executables. Installation does not change model controls or checkpoints;
existing mapped processes retain their original executable.

## Corrected paths

The active `DO_VAR_CONT` dispatcher now retains variations and frequency history
on the **actual final transport grid** for relativistic (`USE_J_REL`), homologous
time-dependent (`USE_DJDT_RTE`), and explicitly extended (`INC_GRID`) transport.
It composes opacity, emissivity and scattering interpolation derivatives before
solving; clumping, continuum-frequency scaling, line-level and superlevel
responses are applied before projecting to model locations. Merely interpolating
angular factors back to a coarse grid would represent a different operator.

For `INC_GRID`, the mapping includes both `EXTEND3OPAC`'s logarithmic four-point
interpolation and any subsequent moment-grid insertion. When an original model
midpoint is absent, the returned flux and its derivatives use the same fixed
geometric interpolation of final-grid midpoint fluxes. The extended radiation
variation arrays remain available to their existing consumers. The line-slot
initializer clears `(NDEXT, ND_model)` storage; its old square clear could overwrite
neighboring slots.

Relativistic history retains Γr²H. Only the returned model-grid flux and its
responses are converted to physical r²H. The solver/helper allocators support a
changed grid at the start of an initialized sweep. `GET_MOMS_REL` now handles
stored/requested sizes independently, computes stored midpoint moments before
reading them, uses the stored endpoint index, and normalizes interpolated H and
N to J. Tests check values as well as bounds. A separate REL variation scratch
bug overwrote a tridiagonal coefficient during an H-bound check when advection
was disabled; the bound check now uses its own array.

The ordinary, unrefined nonrelativistic variation uses the same exact optical-depth
derivative as the refined entry, including endpoint slopes and the active
Steffen limiter branch. Zero-flux stabilization and alternate outer-boundary
terms/history now match the forward equations. The forward nonrelativistic
transport is unchanged. Both original OpenMP response updaters initialize their
private history inside the parallel loop. Log-interpolation derivatives use an
exact single-column response at an original model node, avoiding artificial
roundoff-size endpoint couplings.

## Time-dependent and hollow-boundary corrections

Native finite differences exposed additional inconsistencies while validating
the new time-dependent and relativistic paths:

- REL's hollow boundary now solves for total physical J, matching the forward
  solve's conversion from partial inward intensity. Current-opacity partials
  use the solved field, and previous-frequency coefficients use the saved
  inward angular ratio. Artificial adjacent-row source shifts are removed.
- DDT's hollow and `HALF_MOM` boundaries likewise use total J, with matching
  current-time and frequency-history terms. Zero-flux stabilization and the
  `HONJM` outer stabilizer have matching opacity derivatives.
- The DDT **forward** solver retains the temporal outer-boundary coefficient at
  the first frequency. `INIT` begins a frequency sweep; it does not disable
  physical time dependence. It also retains the temporal hollow-boundary term.
- DDT's `HONJM` forward source includes the missing r² factor, consistent with
  its r²J unknown. Default `HONJ` is unaffected by that change.
- DDT refinement preserves exactly homologous supplied V/R on inserted points.
  Previously a generic cubic in log R introduced small nonhomology, making the
  forward and variation old-time normalization differ. This applies only to
  genuinely homologous input (within 32 machine epsilons) with inserted points.
- The actual old-time radiation reader resizes its cached interpolation arrays
  on initialized grid changes and invalidates the frequency cache even if the
  first frequency repeats. A grid change during an uninitialized sweep is
  refused rather than silently reusing incompatible history.

These forward changes are intentionally limited to the stated DDT options.
The production workflow no longer calls the legacy `VAR_MOM_JEXT_CMF_V3` entry;
its direct-call history typo is corrected, and a mismatched angular grid is
refused. The old square REL entry also refuses a fine-grid angular prefix.
The legacy extended routine retains its older boundary interface and should
not be used as a substitute for the composed production path.

## Validation and limits

`cmfgen-review-tests/check_moment_families.py` compiles the actual native kernels
and the actual `DO_VAR_CONT` prefix through its projection. Atomic-rate assembly
after that prefix is excluded; the complete production routine is compiled as
well. Kernel checks cover all six optical-depth methods, current opacity,
emissivity and scattering, prior-frequency opacity, diffusion vectors, coherent
and noncoherent scattering, nodal/midpoint stored rays, refinement on/off,
relativistic advection on/off and higher velocity, and DDT time terms on/off,
both DR4JDT modes, hollow/zero-flux/diffusion and HONJ/HONJM/HALF_MOM boundaries.
Workflow checks include continuum, electron scattering, both line populations,
superlevel temperature derivatives and nonuniform clumping across three
frequencies; both odd and even extended-grid insertions are tested.

Separate native tests exercise angular interpolation values and bounds,
full production line-slot clearing with unchanged neighboring slots, first-frequency
OpenMP history, and actual binary old-time reads after a 7→13 point restart at
the same frequency. Only file metadata discovery is stubbed in the reader test.
The DDT kernel/workflow tests prescribe old radiation independently of current
parameters; all native temporal equations are retained.

| Check | O0, one thread | O2, five threads |
|---|---:|---:|
| Related-family native invocations | 5,564 | 5,564 |
| Related-family derivative groups | 430 | 430 |
| Maximum forward/variation J/H relative disagreement | 3.00e-14 | 2.35e-14 |
| Maximum REL/DDT kernel derivative-column relative error | 2.986e-5 | 2.987e-5 |
| Maximum production-wrapper derivative-column relative error | 5.06e-7 | 6.66e-7 |
| Ordinary forward refined/coarse comparisons against fix 19 | 64 + 64 bitwise | 64 + 64 bitwise |

Both ordinary core/wrapper suites also pass: 903 candidate kernel invocations
(including baseline configurations) and 680 workflow invocations per configuration.
The largest ordinary kernel errors are 6.64e-6 (O0) and 1.50e-5 (O2); the wrapper
maximum is 1.62e-7. These ordinary tests now intentionally compare only J/H in
the no-insertion baseline: its Jacobian is corrected by this follow-up.
The recovery/documentation suite passes 27 tests, and two separate atomic-link
tests verify preservation of an open old executable and of installed binaries
when a final link fails. Python compilation checks also pass.

Finite differences freeze formal-ray factors, as required by this approximate
Newton operator. Comparisons require positive, unclipped radiation; they do not
differentiate native negative-J repair or flux clipping. Weak history responses
use Richardson differences with profile-specific steps checked for subtraction
noise and limiter-branch crossings. The relative derivative-column threshold
remains 3e-5. These tests do not establish convergence for a new atmosphere,
validate `N_TYPE=MIXED`, or validate a combined REL/DDT plus `INC_GRID` mode
that the forward dispatcher does not select. Noncoherent `MIX_COH` variations
remain explicitly refused on these grid paths.

```sh
python doc/developer/cmfgen-review-tests/check_moment_families.py --cmfgen-root /path/to/cur_cmf
python doc/developer/cmfgen-review-tests/check_moment_families.py --cmfgen-root /path/to/cur_cmf --optimization O2 --threads 5
python doc/developer/cmfgen-review-tests/check_moment_grid_jacobian.py --cmfgen-root /path/to/cur_cmf
```

The scripts require NumPy and compatible installed native libraries/modules;
`--source-root` selects an isolated candidate tree and `--work-dir` selects
fresh evidence storage. Source/fixture hashes, commands, logs and results are
recorded. Historical evidence and rollback locations are retained in the
[patch manifest](patches/cmfgen-current.json).

## Automatic recovery

Ray recovery with `USE_J_REL`, `USE_DJDT_RTE` or `INC_GRID` requires a supported
cumulative patch revision, even when `VFRAC_MOM=20000`. The selected executable
reports its revision directly; historical capability labels and build records
are not runtime eligibility checks. See [versioning](cmfgen-versioning.md).
Recovery still requires the established luminosity/continuation
checks and never changes `VFRAC_MOM` or enables an optional solver automatically.

The consolidated [patch](patches/cmfgen-current.patch) and
[manifest](patches/cmfgen-current.json) cover 45 files and were verified by
applying to the extracted release baseline outside the viewer Git worktree and
comparing every resulting file byte for byte. Historical build records retain
the source, library, module and executable hashes and their rollback locations.
Final builds use a separate executable
output directory and atomic final links so an existing model run is not modified.

The subsequent [ordinary limiting-branch repair](cmfgen-moment-limits.md)
extends the ordinary and rectangular moment Jacobians to active negative-J
replacement and H caps. Its separate regression suites cover these branches;
this document retains the earlier validation scope.
