# CMFGEN source fixes — consolidated record

The consolidated patch contains numerical fix groups **1–28**, performance changes
**29–30**, the optional fixed-state output feature **31**, and the opacity diagnostic
safeguard **32**, and dated version/build support **33**, based on CMFGEN
website release **version 18jun25**. Groups 26–31 cover positive interpolation,
bidirectional X-ray normalization, collision derivatives, two optimizations
and a fixed-state output feature. See [validation and scope](cmfgen-convergence-repairs.md).

**Status:** [cmfgen-current.patch](patches/cmfgen-current.patch) includes all the
changes below. The recommended installer/updater is
`python3 cmfgen_patch.py /path/to/cur_cmf` from the viewer checkout; add `--check`
for a read-only preview. It preserves local compiler settings and aliases,
backs up changed files, and safely replaces recognized older patch sets.
See [source updates](cmfgen-versioning.md#apply-or-update-the-source-patch-set).

A clean release needs only this patch. The separate limiter patch
upgrades fixes 1–24 to 1–25; the convergence-repair patch upgrades the previous
1–25 snapshot, followed optionally by the fixed-state-output patch. Do not apply
incremental patches on top of the current consolidated patch.

The 30 October build correction adds the missing forwarding rule for
`libsubs.a(mod_var_mom_j_cmf.o)` in `new_main/mod_subs/Makefile`. The top-level
serial build reaches `DO_VAR_CONT` before `plane/`; a clean build needs this
rule to create the imported variation module. Existing archives could hide the
omission during incremental builds. This correction changes no scientific code.
The cumulative patch includes this forwarding rule in
`new_main/mod_subs/Makefile`:

```make
# Forward the variation-module dependency to its owning directory.
$(LIB)(mod_var_mom_j_cmf.o) : ../../plane/mod_var_mom_j_cmf.f
	$(MAKE) -C ../../plane '$(LIB)(mod_var_mom_j_cmf.o)'
```

Fresh releases need only the current consolidated patch, which includes it.

Build validation covered clean serial builds of all 80 executables on Linux
and a focused macOS dependency test for `mod_var_mom_j_cmf.o`. The tests also
verify that missing or outdated captured build recipes are rejected, local
compiler settings and aliases are preserved, and installed scientific source
hashes match the consolidated manifest. Historical installation paths, binary
hashes, rollback locations and individual build records remain in the
[manifest](patches/cmfgen-current.json); they are provenance, not prerequisites
for applying the fixes elsewhere.

The complete opt-in fixed-state output check preserved its saved checkpoint and
matched all 119,342 printed spectral points and the ordinary boundary/energy
profiles; see the [execution version and validation limits](cmfgen-convergence-repairs.md#installation-and-validation).
This output pass receives no solved-iteration or convergence credit.

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
| 19 | Inserted moment points leave angular factors on a different grid from the old Jacobian; coarse remapping alone is not a derivative of the refined solve. | Carry rectangular responses and frequency history on the actual moment grid, differentiate native interpolation/quadrature/boundaries, then project to model locations. Include coherent-scattering interpolation, clumping, line-slot reuse and build dependencies. Initially preserve the unrefined path (superseded by fix 20). | `plane/mom_j_cmf_v11.f`, `var_mom_j_cmf_v12.f`, `get_moms_non_rel.f`, `mod_var_mom_j_cmf.f`; `subs/edd_j_var_v6.f`, `up_tx_tvx_v2.f`; `new_main/mod_subs/do_var_cont.f`, `var_rad_mod.f`, `init_line_opac_var_v2.f`; Makefiles |
| 20 | Ordinary optical-depth/boundary derivatives and OpenMP-private first-frequency history remain inconsistent with forward transport. | Use the exact native quadrature/limiter derivative, zero-flux and alternate-boundary terms; initialize history per thread. Preserve nonrelativistic forward transport. | `plane/var_mom_j_cmf_v12.f`, `mom_j_cmf_v11.f`; `subs/up_tx_tvx.f`, `up_tx_tvx_v2.f` |
| 21 | REL angular interpolation mixes stored/requested dimensions, reads uninitialized midpoint moments and omits normalization. | Resize shared arrays independently, use stored indices, compute weighted moments before interpolation and normalize to J. | `plane/get_moms_rel.f` |
| 22 | REL variation consumes a coarse grid after inserted transport and overwrites a solve coefficient during H checks; hollow-boundary terms use inconsistent partial intensity. | Retain rectangular final-grid responses/history, correct interpolation and Γr²H projection, separate scratch and solve total-J boundary equations. Support initialized grid resizing. | `plane/mom_jrel_v9.f`, `mod_var_jrel_v2.f`, `var_jrel_v5.f`; `new_main/mod_subs/do_var_cont.f`; Makefiles |
| 23 | `INC_GRID` variation omits the second refinement, uses wrong history and clears rectangular line storage as square. | Compose both interpolation maps, retain final-grid history, project flux consistently even at missing model midpoints, clear exact slot extents. Guard the legacy direct entry and correct its previous-factor typo. | `plane/mom_j_cmf_v11.f`, `var_mom_jext_cmf_v3.f`; `new_main/mod_subs/do_var_cont.f`, `init_line_opac_var_v2.f` |
| 24 | Homologous/time-dependent variation rebuilds coarse transport and exposes temporal/boundary/cache inconsistencies. | Use final-grid rectangular responses and exact quadrature; match total-J hollow/HALF_MOM and zero-flux/HONJM derivatives. Retain first-frequency/hollow temporal terms, correct HONJM r², preserve homology on inserted points and resize/invalidate old-time caches on initialized grid changes. | `plane/mom_j_ddt_v6.f`, `var_mom_j_ddt_v6.f`, `edd_j_hub_var_v3.f`, `get_jh_at_prev_time_step.f`; `new_main/mod_subs/do_var_cont.f`; Makefiles |
| 25 | Ordinary negative-J replacement and H caps are omitted from correction derivatives and frequency history. | Differentiate both limits on native moment rows, retain raw J for matrix/scattering forcing, correct direct H opacity partials, and propagate repaired J/H histories and diffusion responses. | `plane/var_mom_j_cmf_v12.f`, `new_main/mod_subs/do_var_cont.f`, its Makefile; [details](cmfgen-moment-limits.md) |
| 26 | Monotone cubic evaluation cancels small positive radiation values to zero near nodes across extreme ranges. | Return exact stored nodes and reevaluate cancellation-prone intervals with the same cubic in stable Bezier form; preserve endpoint bounds and ordinary arithmetic. | `subs/mon_interp.f` |
| 27 | Requested X-ray normalization only raises deficient emission; a changed source can reach the final-output pass without a new solve. | Apply bounded square-root scaling in both directions, retain intrinsic-emission/iteration eligibility, reject invalid luminosities, and require a fresh solved update after source changes. Log the multiplier for runner handoff. | `new_main/cmfgen_sub.f` |
| 28 | Dissolution contributions overwrite the collision temperature Jacobian. | Accumulate each contribution while preserving forward rates. | `newsubs/subcol_multi_v6.f` |
| 29 | Dense model-grid projection multiplies many exactly zero local-support weights. | Skip rows only when all three weights are exactly zero; retain nonzero summation order. Performance optimization for finite transport data. | `plane/var_mom_j_cmf_v12.f` |
| 30 | Independent whole-slice remapping copies run serially. | Parallelize complete disjoint slices with OpenMP and a private inner index. Performance optimization. | `new_main/mod_subs/do_var_cont.f` |
| 31 | Native flux-only output omits `MOD_SUM`/`RVTJ`; a zero-iteration writer gives zero mean opacities. Flux-only uses a different inner temperature gradient from an ordinary solve. | Add default-off `FINAL_OUTPUT_ONLY` in `IN_ITS` for coherent stationary continuation: use the existing ordinary luminosity boundary, bypass population updates and write standard complete outputs. Reject unsupported modes and label summaries as output-only. | `new_main/cmfgen_sub.f` |
| 32 | `SRCE_CHK` can choose a nonpositive opacity floor when continuum absorption is negative; the formal solver then takes `LOG(CHI)`, trapping or propagating NaNs. | Stop before transfer with an explicit frequency/depth/opacity diagnostic. The runner can select the existing positive `ESEC_CHK` limiter once, without reseeding or bypassing safeguards. | `new_main/cmfgen_sub.f`; [investigation](bstar3513-opacity-investigation.md) |
| 33 | Source release identity was absent from patched binaries; local module leftovers and a missing partial-build module export could mask build problems. | Add a shared dated patch revision and fast --version query, stamp outputs, clean source-local modules and export the variation module during partial builds. Runtime remedies use minimum dated revisions; build audits remain separate. | `new_main/cmfgen_version.inc`, `cmfgen.f`, `cmfgen_sub.f`, Makefiles; [versioning](cmfgen-versioning.md) |


The complete diff for all groups is
[cmfgen-current.patch](patches/cmfgen-current.patch), with the release baseline,
capture time, patch SHA-256, installed executable hashes and before/after file
SHA-256 values in [cmfgen-current.json](patches/cmfgen-current.json). It captures
**52 files**, including the new population-initialization module which ordinary
`git diff` would omit while untracked in the external checkout.

The full diff also preserves local macOS and Ubuntu compiler/linker settings
in `Makefile_definitions`, local directory aliases in `com/aliases_for_cmfgen.sh`,
and FORMAT separator corrections in `new_main/cmfgen_sub.f`,
`obs/cmf_flux_sub_v5.f`, and `opac/par_opac_sub.f`. These adaptations retain their existing patch hunks; the older validation
below describes the original platform. The
Linux fix-25 build and native tests are documented in the
[limiter repair record](cmfgen-moment-limits.md).
Generated modules, binaries, logs, save files, and scratch patches are excluded.

Patch application and reversal were checked against the recovered release
contents in a fresh temporary directory. All **52 files** matched their expected
SHA-256 hashes, including the three files updated for fix 25. Updater regression
checks also verify that compiler settings and directory aliases remain
unchanged. Use the updater to identify and
upgrade already patched sources; do not reapply the cumulative diff blindly.

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
| Native stellar-atmosphere same-grid R and POP startup, with rounded RMAX | Outer T is `1843.602800 K`, compared with saved `1843.602811 K`; the broken startup had selected `1952.959100 K`. |
| Native stellar-atmosphere same-grid population round trip, current text export | Maximum relative discrepancy is `4.35e-5` (0.00435%), versus the earlier 8.74% high-level discrepancy. Median discrepancy is about `1.37e-7`. |
| Native 125-depth POP startup using the same current text export | At depth 6, N III/N IV/N VI fractions are about 62.144%/35.005%/0.02848%; the earlier log-b startup had 99.99818% N VI. All population variables agree with the independently constructed 125-depth estimate within `4.35e-5` relative; at depth 6 the maximum is `1.69e-5`. |
| Conservation in the native refined POP startup | Ne matches the charge sum within `1.34e-15` relative. Element densities match the independently specified target densities within `4.0e-9` relative. |

The asserting isolated drivers run with bounds checks at `-O0`/one OpenMP thread
and `-O2`/five threads. The optional one-depth N I frequency integration uses
one thread. Native atmosphere tests verify initialization and text reconstruction,
not radiation iterations or final convergence. Non-GRID grey iteration, SN/dust
models and arbitrary changes in atomic data have not been certified by these tests.

## Line-Jacobian validation and automatic population/radiation remedies

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
negative-luminosity ray-transport collapse while retaining the configured moment grid. The
successful recovery includes fresh-process continuation and full variable-T,
fresh-BA steps with positive populations and conservation near machine precision.
The Ng guard fix was tested separately: its effect on the retained native
acceleration proposal was small, so it is not claimed as the cause of that
recovery. Rebuilding and installing the executable does not itself demonstrate
convergence of a new atmosphere.

The automatic workflow now registers these additional remedies, also exposed
as read-only recommendations outside auto mode:

- `ray_refinement`: fresh negative normalized luminosities after the native
  luminosity safeguard, coarse formal rays and fixed structure/original moment
  grid. Try finer rays without bypassing guards; require two guarded fresh-BA
  solves. Native Lambda steps may settle populations before full verification.
- `superlevel_temperature`: measured persistent T oscillation with superlevel
  T derivatives disabled. Enable the derivatives and fresh BA before damping.
- `population_bootstrap`: extreme finite population increases with fresh BA,
  a dated supported patched runtime, `SCALE_OPT=MAJOR` and a physically auditable
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

Bootstrap recognition now queries the actual executable for
`CMFGEN_VIEWER_PATCH` at revision `2026-10-31.1` or later. The optional JSON build
record is no longer read for remedy eligibility; unidentified binaries are
declined. See [versioning](cmfgen-versioning.md).

These are numerical controls, not changes to stellar parameters, atomic data,
Rmax or population floors. They never raise `EPS_TERM` or bypass the luminosity
or `MAX_CHNG` safeguards. The original instability is resolved in the tested
recovery branch; formal final model convergence is a separate task. See
[rule conditions and limits](../main-computation.md#automatic-convergence-and-recovery-rules)
and the [source investigation](cmfgen-line-jacobian-cancellation.md).

**Inserted moment grids and related families are repaired.** The active
ordinary nonrelativistic, relativistic, time-dependent and `INC_GRID` variation
paths retain the actual final-grid operator and its frequency history. The
ordinary unrefined Jacobian also has matching quadrature/boundary derivatives.
Nonrelativistic forward transport remains unchanged; optional DDT forward
boundary/homology corrections are explicit in the
[related moment repair report](cmfgen-related-moment-repairs.md).

Failure-triggered automatic ray recovery requires CMFGEN viewer patches
≥2026-10-31.1 for inserted moment grids, REL, DDT or INC_GRID. That rule retains
VFRAC_MOM. The separate guarded small-stall remedy can refine it with the same
minimum dated revision; neither rule enables optional solver families. Experimental log-radius `QFROMF` integration and
diagnostic-only instrumentation remain excluded.

## Reproduce and rebuild

Use the bundled updater from the viewer checkout with CMFGEN **version 18jun25**
sources or a recognized previously patched installation:

```sh
python3 cmfgen_patch.py /path/to/cur_cmf --check
python3 cmfgen_patch.py /path/to/cur_cmf
```

The cumulative patch includes all listed groups and added modules. The updater
preserves `Makefile_definitions` and `com/aliases_for_cmfgen.sh`, validates source
hashes, and backs up changed files. See [source updates and versioning](cmfgen-versioning.md)
for conflict handling, rollback, and release maintenance. When publishing a new
patch set, include newly added source files and refresh the manifest hashes
alongside the patch.

Additional investigation regressions:

```sh
python3 doc/developer/cmfgen-review-tests/check_convergence_repairs.py /path/to/cur_cmf/ --optimization O0
python3 doc/developer/cmfgen-review-tests/check_convergence_repairs.py /path/to/cur_cmf/ --optimization O2
```

Run the source-level regressions:

```sh
python doc/developer/cmfgen-review-tests/run_review.py /path/to/cur_cmf/
python doc/developer/cmfgen-review-tests/check_line_jacobian_branches.py --shared-check physical
python doc/developer/cmfgen-review-tests/check_ba_restart_flags.py
python doc/developer/cmfgen-review-tests/check_ng_temperature_guard.py
python doc/developer/cmfgen-review-tests/check_moment_grid_jacobian.py --cmfgen-root /path/to/cur_cmf
python doc/developer/cmfgen-review-tests/check_moment_grid_jacobian.py --cmfgen-root /path/to/cur_cmf --optimization O2 --threads 5
python doc/developer/cmfgen-review-tests/check_moment_families.py --cmfgen-root /path/to/cur_cmf
python doc/developer/cmfgen-review-tests/check_moment_families.py --cmfgen-root /path/to/cur_cmf --optimization O2 --threads 5
python3 doc/developer/cmfgen-review-tests/check_moment_limits.py --cmfgen-root /path/to/cur_cmf/
python3 doc/developer/cmfgen-review-tests/check_moment_limits.py --cmfgen-root /path/to/cur_cmf/ --optimization O2 --threads 5
python3 doc/developer/cmfgen-review-tests/check_moment_limit_grids.py --cmfgen-root /path/to/cur_cmf/
python3 doc/developer/cmfgen-review-tests/check_moment_limit_grids.py --cmfgen-root /path/to/cur_cmf/ --optimization O2 --threads 5
python doc/developer/cmfgen-review-tests/run_review.py /path/to/cur_cmf/ \
  --optimization O2 --threads 5 --atomic-data /path/to/atomic/
```

The optional photo test needs compatible existing `mod/` and `lib/` products;
it compiles the edited reader explicitly ahead of the library copy. Core tests
compile the affected source directly. The saved-atmosphere initialization driver is
`doc/developer/cmfgen-review-tests/run_bstar_initialization_checks.py`; its
`--help` lists the required prepared templates and reference arrays from the
reconstruction investigation. It needs NumPy and invokes the native program
only in fresh temporary model directories.

For production use, rebuild serially in the external checkout:

```sh
cd /path/to/cur_cmf/
make -j1 clean all
./exe/cmfgen_dev.exe --version
```

The updated top-level all target performs the final three links after all
recursive library updates. No recording command is required. Build in an
isolated checkout while model jobs are active.

For selective incremental builds, the optional recorder performs the final
three links if shared libraries are newer than an executable. A newer library
is expected when a later recursive target updates a shared archive; it does
not require another full rebuild. Scientific source and captured Makefile hashes are checked first, and an
executable older than the patched scientific sources still requires rebuilding
before recording. Use `--relink` to force the final links, or `--no-relink` to
require an already current build without relinking.

The helper links fresh executable files and atomically replaces their paths,
preserving an existing run's mapped executable. An isolated checkout keeps intermediate recursive links away from installed
binaries.
The helper performs the three final links after both recursive builds have
finished updating shared archives; it then checks source hashes and executable
ordering before writing optional audit metadata. Rebuild other affected executables if used. The latest installation preserved source, library, module and executable backups in the build record's `build_evidence` directory under `installed-before/`. Keep pre-fix executables and binary checkpoints separate
for comparisons. Do not run a parallel make: the archives and module directories
are shared by recursive targets. The updater changes source contents without changing the receiving checkout's
Git history.

Regression invocations report their own isolated output locations, including
source hashes, commands and logs. Historical installation and investigation
records preserve the original artifact locations. They are background evidence,
not additional instructions required to use these fixes.


## Nonpositive source-opacity diagnostic and recovery

The added diagnostic guard does not change a valid opacity or Jacobian. It turns
an invalid `SRCE_CHK` floor into a nonzero native stop with measurements before
this solve can write poisoned populations. The automatic `source_opacity` policy
can then select the existing electron-scattering limiter, while retaining the
normal radiation, luminosity, and convergence checks. The incremental upgrade is
[cmfgen-source-opacity-guard.patch](patches/cmfgen-source-opacity-guard.patch);
it is already included in the consolidated patch.

Run the extracted-native-limiter regression after applying/rebuilding:

```bash
python3 doc/developer/cmfgen-review-tests/check_source_opacity_guard.py /path/to/cur_cmf --optimization O0
python3 doc/developer/cmfgen-review-tests/check_source_opacity_guard.py /path/to/cur_cmf --optimization O2
```

Both optimizations pass seven cases, including the reproduced invalid floor,
a zero source floor, positive ordinary source limiting, unchanged positive
opacity, the native scattering floor, and its existing derivative-control flags.
The historical Linux build described above predates this additive diagnostic.
See the linked investigation record for captured installation and native-run evidence.

The runner also adds a narrowly scoped fresh-POP/LTE radiation-seed recipe. If a
negative-luminosity safeguard remains before the first population solve, it can
initialize from a validated matching LTE/hydro temperature profile, run the
existing three-step Lambda population bootstrap and verify guarded full
continuation. This needs no further scientific source changes beyond the
already consolidated LTE-charge/line/BA repairs. The entire recipe remains
provisional and retains strict conservation checks. See
[main computation](../main-computation.md#fresh-pop-radiation-initialization) for
eligibility, temporary controls and rollback, and
[source-opacity investigation](bstar3513-opacity-investigation.md) for native evidence.


The current dated revision and build workflow are documented in
[CMFGEN versioning](cmfgen-versioning.md). Runtime remedies no longer depend on
the optional JSON build record. Existing installation records above describe
their historical builds.
