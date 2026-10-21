# CMFGEN local source fixes — consolidated record

Fixes validated 20 October 2026; source snapshot captured 21 October 2026.
Source checkout: `~/CMFGEN2023/cur_cmf/`, based on the CMFGEN website release
**version 18jun25** (released version as of 18 Jun 2025).

This is the single current summary of the ten fixes from the source review
and Bstar3000 reconstruction investigation. Earlier documents retain the
historical evidence; use this document for implementation status, controls,
validation, and rebuild instructions.

**Status:** all ten fixes are applied to the source checkout. Existing build
settings, aliases, and local FORMAT fixes are preserved. A complete atmosphere
executable containing all ten fixes was built and tested separately, preserving
the installed binaries during that work. The snapshot below records source
contents; it does not establish which source built the currently installed binaries.

## Fix inventory

| # | Problem and trigger | Implemented correction | Main source files |
|---|---|---|---|
| 1 | Photoionization routes return full-level target IDs to callers that index superlevel populations. | Return the mapped superlevel IDs; retain full-level IDs inside the photoionization data module. | `newsubs/rdphot_gen_v2.f` |
| 2 | Automatic ion addition passes a reference atom's level count; an entirely absent first element can access `ATM(0)`. | Use the atom being generated, `ATM(NID)`, at both incorrect calls. | `new_main/subs/auto_add_ion.f` |
| 3 | Excited-target departure ratios overflow or underflow before their finite product with the source LTE population is formed. | Combine separate population logarithms, LTE logarithms, and the source population before exponentiating. Use the same calculation in the rate and Jacobian; remove the hard-coded exponent cutoff of 780. | `new_main/subs/evalse_qwvj_v8.f`, `vsebyj_multi_v8.f` |
| 4 | The X-ray recombination temperature Jacobian puts the Saha power-law factor inside an energy term. | Use `dlnHNST_A/dlnT - 1.5 - HDKT*EDGE_B/T`. | `new_main/subs/vsebyj_x_v7.f` |
| 5 | The neutral collision approximation at `X > 14` returns a temperature derivative with the wrong sign. | Differentiate the implemented rate: `dlnGBAR/dlnT = 0.5 + 1.5/(X+1.5)`. | `newsubs/omega_gen_v3.f` |
| 6 | Both profile-storage scans can stop before the final line begins. | Stop only after all lines finish; also initialize the V2 average-frequency counter. | `stark/get_prof_storage_limits.f`, `get_prof_storage_limits_v2.f` |
| 7 | GLOBAL correction scaling enforces its temperature limit using only the innermost depth. | Take the maximum correction over all depths and honor `MAX_dT_COR`. | `new_main/subs/solveba_v13.f` |
| 8 | Radius rounding makes temperature/Ne interpolation discard the outer saved depth while departure-coefficient interpolation keeps it. | Snap near-identical endpoints within `1e-10` relative, matching the existing departure-file tolerance. Guard overlap searches, fill genuine inner/outer extensions, and handle a single overlapping target point without calling LINPOP with one point. | `subs/regrid_t_ed_v3.f` |
| 9 | Interpolating log departure coefficients across steep temperature gradients produces artificial ionization spikes. | Add opt-in `DC_METH=POP`: reconstruct populations on the saved grid, interpolate superlevel fractions, normalize each element at the target density, and derive Ne from charge conservation. | `new_main/mod_subs/init_population_estimates.f90`, `set_new_model_estimates.f`, `rd_control_variables.f`, `Makefile` |
| 10 | Text initialization evaluates occupation probabilities using total atom density before knowing the actual charged-ion density. High levels consequently do not round-trip consistently. | Retain original log(b) and continuum seeds while iterating reconstruction and elemental normalization to a self-consistent charged-ion density. Resize occupation-probability work arrays when switching between source and target grids. | `new_main/mod_subs/init_population_estimates.f90`, `set_new_model_estimates.f`, `mod_lev_dis_blk.f` |

The ten fixes affect fifteen source/build files. The complete current checkout
diff is tracked as [cmfgen-current.patch](patches/cmfgen-current.patch), with its
baseline release, capture time, patch SHA-256, and before/after file SHA-256 values
in [cmfgen-current.json](patches/cmfgen-current.json). This snapshot includes
nineteen modified tracked files and the new
`new_main/mod_subs/init_population_estimates.f90` module, which an ordinary
`git diff` would omit while it remains untracked in the external checkout.

The full diff also preserves local macOS and Ubuntu compiler/linker settings
in `Makefile_definitions`, local directory aliases in `com/aliases_for_cmfgen.sh`,
and FORMAT separator corrections in `new_main/cmfgen_sub.f`,
`obs/cmf_flux_sub_v5.f`, and `opac/par_opac_sub.f`. These adaptations are captured
as they stand; the Ubuntu configuration was not covered by the validation below.
Generated modules, binaries, logs, save files, and scratch patches are excluded.

Patch application was checked against the baseline contents in a fresh temporary
directory. All twenty resulting files matched the captured checkout byte for
byte by SHA-256. Do not apply the patch again to the already patched checkout.

## Using population-based initialization

For refinement or reconstruction of a saved model with the same atomic setup:

```text
T     [LIN_INT]
T     [POP_SCALE]
POP   [DC_METH]
```

Retain the other physical and solver controls appropriate to the model. This
option requires complete `*_IN` files for the explicit atoms, with matching
full-level counts and a common saved radius/T/Ne/clumping grid. `T_IN` must
describe that same saved model. Explicit ion stages must be contiguous within
each element. Missing files are rejected rather than generated by AUTO_ADD.
The reader accepts ordinary departure coefficients, natural-log coefficients
(`18-Nov-2010`), and base-10 log coefficients (`10-Dec-2010`).

The algorithm:

1. Reconstruct saved full-level populations at the **saved** T and Ne, with
   occupation probabilities consistent with the saved populations. Conversion
   uses logarithms so that large Saha factors need not be represented alone.
2. Sum full levels into the current superlevels. Interpolate positive
   superlevel and terminal-continuum fractions geometrically in log radius.
   Preserve zeros at exact nodes; when an interval has a zero endpoint, use
   linear interpolation of that fraction instead of an arbitrary population floor.
3. Normalize the fractions of each element to `POP_SPECIES` on the target grid.
   These target densities already include the selected density law and clumping.
4. Compute Ne from the ionic charge sum, including terminal continuum ions.
   Distribute superlevels over full levels using target T and occupation
   probabilities, then honor the existing interpolating-sequence treatment.

Source radii follow the same core-radius scaling convention as the existing
R option. Fractions outside the source radius range use the nearest endpoint;
the temperature reader retains its boundary-T extrapolation. Source and target
grids need not have the same depth count.

`POP` is an initialization method, not a prediction of the converged atmosphere.
It does not silently replace `DC_METH=R`, `TR`, `ED`, `LTE`, or `SPH_TAU`.
It is deliberately restricted to `LIN_INT=T` and `POP_SCALE=T`; do not use it
to mix unrelated atomic models or source atmospheres. Changing an atomic model
requires preparing compatible estimates first.

## Existing initialization options

The endpoint and occupation-probability corrections also apply to the existing
initialization paths. The precise-RMAX workaround is no longer needed for the
demonstrated rounding mismatch. Real changes of outer radius still take the
extrapolation path.

The occupation correction starts from the original DCs and continuum estimates
on every pass, rather than repeatedly converting an already converted population.
It uses damped fixed-point iteration, with a charged-ion-density tolerance of
`1e-10` and a maximum of 100 passes. Failure to converge produces an explicit
initialization error. When level dissolution is disabled, reconstruction needs
one pass. Legacy departure-coefficient interpolation remains available for
cases where maintaining departure coefficients between different atmospheres
is the intended approximation.

The corrections improve consistency with the input estimates. Finite text
precision, old exports made with different constants or physics, and changes
in atomic setup can still prevent exact binary/text equality.

## Validation

A separate serial build of `cmfgen_dev.exe` completed with MacPorts gfortran
15.2 and OpenBLAS, including all ten fixes. Installed executables were preserved.
No user model folders were modified: native tests ran with zero solver
iterations in fresh temporary model copies.

| Check | Result |
|---|---|
| Actual N I photo reader | Returned targets `[1,2,3,4]`; internal full-level targets remain `[1,4,5,6]`. |
| Actual N I integrated recombination | `6.5797154280524034e-13`, matching the corrected reference within `1e-6` relative. |
| X-ray temperature derivative | Analytic and finite-difference derivatives agree within `1e-7` relative; the old isolated discrepancy was 20.6%. |
| Neutral collision derivative | At X=20, both calculations give `+0.56976744186`; the old returned value was negative. |
| Excited-target rates/Jacobians | Seven cases pass, including overflowing/underflowing intermediate ratios, zero source LTE populations, and ground-state targets. |
| Automatic ion addition | Correct 10/20/30-level counts; the absent-element case completes without accessing `ATM(0)`. |
| Profile storage | Single, final, overlapping, Voigt and Sobolev cases pass. |
| GLOBAL scaling | Both outer and inner dominant corrections honor 20% and 10% configured limits. |
| Endpoint interpolation | Rounded outer/inner endpoints, genuine extensions and a single overlapping point pass; disjoint grids are rejected explicitly. |
| Synthetic occupation/population initialization | Same-grid occupation round trip, all three coefficient formats, zero populations, dissolution disabled, element conservation, charge conservation and grid-size changes pass. Mismatched source files are rejected. |
| Native Bstar same-grid R and POP startup, with rounded RMAX | Outer T is `1843.602800 K`, compared with saved `1843.602811 K`; the broken startup had selected `1952.959100 K`. |
| Native Bstar same-grid population round trip, current text export | Maximum relative discrepancy is `4.35e-5` (0.00435%), versus the earlier 8.74% high-level discrepancy. Median discrepancy is about `1.37e-7`. |
| Native 125-depth POP startup using the same current text export | At depth 6, N III/N IV/N VI fractions are about 62.144%/35.005%/0.02848%; the earlier log-b startup had 99.99818% N VI. All population variables agree with the independently constructed 125-depth estimate within `4.35e-5` relative; at depth 6 the maximum is `1.69e-5`. |
| Conservation in the native refined POP startup | Ne matches the charge sum within `1.34e-15` relative. Element densities match the independently specified target densities within `4.0e-9` relative. |

The asserting isolated drivers run with bounds checks at `-O0`/one OpenMP thread
and `-O2`/five threads. The optional one-depth N I frequency integration uses
one thread. Native atmosphere tests verify initialization and text reconstruction,
not radiation iterations or final convergence. Non-GRID grey iteration, SN/dust
models and arbitrary changes in atomic data have not been certified by these tests.

## Reproduce and rebuild

To restore the captured changes, start with a separate clean copy of the CMFGEN
website release **version 18jun25**. Use the extracted release contents as the
baseline; the Git tree included in the archive omits some documentation changes
present in the release files. From that source directory, run
(adjust the viewer repository path if needed):

```sh
git apply --check ~/sciwork/cmfgen_viewer/doc/developer/patches/cmfgen-current.patch
git apply ~/sciwork/cmfgen_viewer/doc/developer/patches/cmfgen-current.patch
```

The patch includes the new initialization module. The build settings and
directory aliases reflect the captured local environment; review them before
building on another machine. When refreshing this snapshot, include newly added
source files as well as tracked changes, and refresh the manifest hashes together
with the patch.

Run the source-level regressions:

```sh
python doc/developer/cmfgen-review-tests/run_review.py ~/CMFGEN2023/cur_cmf/
python doc/developer/cmfgen-review-tests/run_review.py ~/CMFGEN2023/cur_cmf/ \
  --optimization O2 --threads 5 --atomic-data ~/CMFGEN2023/atomic/
```

The optional photo test needs compatible existing `mod/` and `lib/` products;
it compiles the edited reader explicitly ahead of the library copy. Core tests
compile the affected source directly. The Bstar model driver is
`doc/developer/cmfgen-review-tests/run_bstar_initialization_checks.py`; its
`--help` lists the required prepared templates and reference arrays from the
reconstruction investigation. It needs NumPy and invokes the native program
only in fresh temporary model directories.

For production use, rebuild serially in the external checkout:

```sh
cd ~/CMFGEN2023/cur_cmf/
make -C new_main INSTALL_DIR="$PWD/"
```

Rebuild other executables that use the modified libraries as well, including
CMF_FLUX if it is used. Keep pre-fix executables and binary checkpoints separate
for comparisons. Do not run a parallel make: the archives and module directories
are shared by recursive targets. No source fixes from this work were committed
to the external Git repository.

The work directories `/private/tmp/cmfgen-fixes-20261020/` and
`/private/tmp/cmfgen-initialization-fixes-20261020/` contain pre-fix source copies,
file hashes, build/test logs, the isolated build, and additional native test
artifacts. Each regression invocation also prints its own temporary output
location. The older investigation documents are historical background, not
additional instructions required to use these fixes.
