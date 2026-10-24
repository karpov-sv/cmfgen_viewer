# CMFGEN local source fixes — consolidated record

Updated **24 October 2026**. Source checkout: `~/CMFGEN2023/cur_cmf/`, based on
CMFGEN website release **version 18jun25**. This is the current implementation
record for the original ten fixes and nine additions from the Bstar3502
investigation. Earlier investigation documents retain their historical status.

**Status:** all nineteen fixes below are installed. The atmosphere executable
`exe/cmfgen_dev.exe` and the spectrum executables `exe/cmf_flux.exe` and
`exe/obs_frame.exe` were rebuilt serially on 24 October. Existing compiler,
platform, aliases and FORMAT adaptations are preserved. No user model controls
or checkpoints were changed by this installation.

The exact build hashes, source hashes and rollback directory are in
`~/CMFGEN2023/cur_cmf/cmfgen-local-build.json` and the tracked
[patch manifest](patches/cmfgen-current.json). The new atmosphere executable SHA-256
is `ff678bc4bc57908e31096d7eeb26d101e645249eb540b3b4624091a3d024c467`.
The installed source contains the tested scientific repairs, without matrix/ray
recorders, transport-only STOP branches, or experimental Q-integration changes.

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
| 11 | `DET_LTE_ED` attempts to impose a starting-temperature floor but assigns the original temperature again. | Use `TMIN` for the temporary Saha estimate below the floor; do not change the model temperature. | `new_main/subs/det_lte_ed.f` |
| 12 | LTE text reconstruction can retain an electron estimate inconsistent with the actual normalized ionic populations. | For `DC_METH=LTE`, iterate reconstructed populations and Ne to charge consistency with positive finite checks; leave other methods unchanged. | `new_main/mod_subs/init_population_estimates.f90`, `Makefile` |
| 13 | Nonpositive/nonfinite grey mean intensity reaches a fractional power and can trap. | Emit `GREY_RJ_INVALID`, return `COMPUTED=F`, and let the existing caller skip unsuccessful grey diagnostics; never manufacture a temperature. | `new_main/mod_subs/comp_grey_v4.f` |
| 14 | Lambda/weak-line upper population derivatives subtract huge nearly opposite terms and lose the finite spontaneous term. | Use the actual integrated profile weight `LINE_QW_SUM` in the algebraically equivalent derivative. | `new_main/subs/update_ba_for_line.f` |
| 15 | Full strong-line derivatives have a separate source-function cancellation. | Combine the explicit emissivity term with the integrated profile weight at assembly; retain distinct-level population and heating responses. | `new_main/subs/update_ba_for_line.f` |
| 16 | A line whose two levels share a superlevel loses or double counts population/heating derivatives, depending on pointer layout; its temperature expression also cancels. | Explicit physical shared-superlevel treatment for both pointer layouts and stable heating/temperature expressions, including the model's cooling reset. Supersedes the intermediate strong-line candidate. | `new_main/subs/update_ba_for_line.f` |
| 17 | BA reader swaps the producer's FIXED_T/COMPUTE_BA flags, can alter FIXED_T on failure, accepts truncated tails, and the initial caller ignores a fresh-compute request. | Read the writer's flag order, commit FIXED_T only after a complete read, handle EOF, and forward `COMPUTE_BARDIN` at initial read. | `new_main/subs/read_ba_data_v3.f`, `new_main/cmfgen_sub.f` |
| 18 | Ng temperature-direction guard checks appended `Sigma+1` instead of physical T. | Pass the physical temperature index to a private V4 helper; initialize the guard ratio. Preserve the separate V1 ABI, geometry and existing Ng validity checks. | `new_main/subs/do_ng_accel_band_v4.f` |
| 19 | Inserted moment points leave angular factors on a different grid from the old Jacobian; coarse remapping alone is not a derivative of the refined solve. | Carry rectangular responses and frequency history on the actual moment grid, differentiate native interpolation/quadrature/boundaries, then project to model locations. Include coherent-scattering interpolation, clumping, line-slot reuse and build dependencies. Preserve the unrefined path. | `plane/mom_j_cmf_v11.f`, `var_mom_j_cmf_v12.f`, `get_moms_non_rel.f`, `mod_var_mom_j_cmf.f`; `subs/edd_j_var_v6.f`, `up_tx_tvx_v2.f`; `new_main/mod_subs/do_var_cont.f`, `var_rad_mod.f`, `init_line_opac_var_v2.f`; Makefiles |

The complete current checkout diff is
[cmfgen-current.patch](patches/cmfgen-current.patch), with the release baseline,
capture time, patch SHA-256, installed executable hashes and before/after file
SHA-256 values in [cmfgen-current.json](patches/cmfgen-current.json). It captures
**35 files**, including the new population-initialization module which ordinary
`git diff` would omit while untracked in the external checkout.

The full diff also preserves local macOS and Ubuntu compiler/linker settings
in `Makefile_definitions`, local directory aliases in `com/aliases_for_cmfgen.sh`,
and FORMAT separator corrections in `new_main/cmfgen_sub.f`,
`obs/cmf_flux_sub_v5.f`, and `opac/par_opac_sub.f`. These adaptations are captured
as they stand; the Ubuntu configuration was not covered by the validation below.
Generated modules, binaries, logs, save files, and scratch patches are excluded.

Patch application was checked against the baseline contents in a fresh temporary
directory. All 35 resulting files matched the captured checkout byte for
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

## Earlier validation of fixes 1–10

A separate serial build of `cmfgen_dev.exe` completed with MacPorts gfortran
15.2 and OpenBLAS, including all ten original fixes. Installed executables were preserved.
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

## Bstar3502 validation and automatic remedies

The final line routine passes **8250 physical derivative comparisons** across
Lambda, weak/strong branches and both shared-level pointer layouts, with maximum
relative error about `1.12e-15`. Native BA tests pass all flag combinations,
failed/missing/truncated reads and fresh-compute bypass. The corrected Ng wrapper
passes **25 cases** covering both temperature directions and fixed T across five
band widths, with bounds and floating-point traps enabled. The existing O2/five-
thread source review passes again, including the actual N I reader/rates and a
new LTE charge/element reconstruction case with inconsistent starting Ne (level dissolution disabled for that charge-loop test).

Matched model tests and subsequent isolated recovery establish the importance
of fixes 14–17. Enabling **`INCL_dSLdT=T`**, an existing native option, removes the
remaining outer thermal cycle. Refining **`VFRAC_FG=0.1`** removes the reproduced
negative-luminosity ray-transport collapse on the original moment grid. The
successful recovery includes fresh-process continuation and full variable-T,
fresh-BA steps with positive populations and conservation near machine precision.
The Ng guard fix was tested separately: its effect on actual Ng93 is small and
it is not claimed as the cause of the recovery. The installed binary has been
rebuilt; a new full atmosphere run with that installed binary was not required
or performed during installation.

The automatic workflow now registers these additional remedies, also exposed
as read-only recommendations outside auto mode:

- `ray_refinement`: fresh negative normalized luminosities after the native
  luminosity safeguard, coarse formal rays and fixed structure/original moment
  grid. Try finer rays without bypassing guards; require two guarded fresh-BA
  solves. Native Lambda steps may settle populations before full verification.
- `superlevel_temperature`: measured persistent T oscillation with superlevel
  T derivatives disabled. Enable the derivatives and fresh BA before damping.
- `population_bootstrap`: extreme finite population increases with fresh BA,
  an authenticated repaired runtime, `SCALE_OPT=MAJOR` and a physically auditable
  checkpoint. Three fixed-T Lambda steps use temporary `MAX_LAM=1e12`; all normal
  controls are restored before two full/fresh-BA checks. Charge, element sums,
  geometry and fixed bootstrap T are independently checked.
- `population_guard`: the exact zero-exit, post-save `MAX_CHNG` stop can enter
  that same provisional procedure only after an independent before/after
  physical audit and a matching single solved/saved counter. Its original
  failure status is retained; failed follow-up restores the pre-failure state.
- `ng_cadence`: repeated short full batches below native `BEG_NG`, past
  `IBEG_NG`, with `LAST_NG=-1000` and Ng enabled. Use eight contiguous physical
  solves so process restarts do not keep postponing the first Ng. Native
  scheduling/validity tests and all automatic work limits remain active.

Bootstrap recognition needs `cmfgen-local-build.json` whose atmosphere-executable
hash matches the running binary and advertises the line/BA repairs. Rebuilding
changes that hash: refresh the build record after source regression checks,
using `cmfgen-review-tests/record_local_build.py`. Unknown binaries are declined.

These are numerical controls, not changes to stellar parameters, atomic data,
Rmax or population floors. They never raise `EPS_TERM` or bypass the luminosity
or `MAX_CHNG` safeguards. The original instability is resolved in the tested
recovery branch; formal final model convergence is a separate task. See
[rule conditions and limits](../main-computation.md#automatic-convergence-and-recovery-rules)
and the [source investigation](cmfgen-line-jacobian-cancellation.md).

**Inserted moment grids are repaired** in the nonrelativistic spherical
variation path. The refined Jacobian uses the actual moment grid and retains
fine-grid frequency history before projecting back to atmosphere locations.
Bounds-checked single-threaded and optimized five-thread tests preserve forward
transport and the no-insertion path bit for bit, and verify kernel and production
wrapper derivatives by finite differences. See the
[implementation, validation and remaining scope limits](cmfgen-inserted-moment-grid.md).
Auto ray refinement accepts an already inserted grid only with an authenticated
`moment-grid-jacobian-v1` executable; it does not change `VFRAC_MOM`. Experimental
log-radius `QFROMF` integration and diagnostic-only instrumentation remain excluded.

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
python doc/developer/cmfgen-review-tests/check_line_jacobian_branches.py --shared-check physical
python doc/developer/cmfgen-review-tests/check_ba_restart_flags.py
python doc/developer/cmfgen-review-tests/check_ng_temperature_guard.py
python doc/developer/cmfgen-review-tests/check_moment_grid_jacobian.py
python doc/developer/cmfgen-review-tests/check_moment_grid_jacobian.py --optimization O2 --threads 5
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
make -C plane INSTALL_DIR="$PWD/"
make -C new_main INSTALL_DIR="$PWD/"
make -C obs INSTALL_DIR="$PWD/"
python ~/sciwork/cmfgen_viewer/doc/developer/cmfgen-review-tests/record_local_build.py --relink "$PWD"
```

The helper performs the three final links after both recursive builds have
finished updating shared archives; it then checks source hashes and executable
ordering before recording capabilities. Rebuild other affected executables if used. The latest installation preserved source, library, module and executable backups in the build record's `build_evidence` directory under `installed-before/`. Keep pre-fix executables and binary checkpoints separate
for comparisons. Do not run a parallel make: the archives and module directories
are shared by recursive targets. No source fixes from this work were committed
to the external Git repository.

The work directories `/private/tmp/cmfgen-fixes-20261020/` and
`/private/tmp/cmfgen-initialization-fixes-20261020/` contain pre-fix source copies,
file hashes, build/test logs, the isolated build, and additional native test
artifacts. Each regression invocation also prints its own temporary output
location. The older investigation documents are historical background, not
additional instructions required to use these fixes.
