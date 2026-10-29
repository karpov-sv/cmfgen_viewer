# CMFGEN source regression drivers

Run the core tests against a CMFGEN source checkout:

```sh
python3 run_review.py ~/CMFGEN2023/cur_cmf/
python3 run_review.py ~/CMFGEN2023/cur_cmf/ --optimization O2 --threads 5
```

The runner builds in a new temporary directory and asserts corrected behavior.
It does not modify the supplied checkout. Test fixtures mock data readers,
the automatic-ion interfaces, and the matrix solver where needed; the routines
under test and the precision selection are compiled from the checkout.
See the [consolidated summary](../cmfgen-source-fixes.md) for implementation
status, controls, validation, and test limits.

To include the actual N I photoionization reader and integrated recombination
rate, use:

```sh
python3 run_review.py ~/CMFGEN2023/cur_cmf/ --atomic-data ~/CMFGEN2023/atomic/
```

This optional test needs existing `mod/` modules and `lib/libsubs.a` and
`lib/libmod.a` archives built with a compatible compiler. The edited photo
reader is explicitly compiled and linked ahead of those archives. The atomic
data paths are `NIT/I/19apr23/phot_data_{A,B,C,D}` and the two hydrogen tables
under `HYD/I/5dec96/`. No atomic cross-section files are copied into this repo.
The `data/` files contain the N I/N II level names, energies, mappings and outer
depth populations extracted for the Bstar3000 investigation. The one-depth
photo test runs with one thread even when `--threads` is set, to avoid repeated
parallel startup during frequency quadrature. macOS gets the main-thread stack
reservation required by this reader.

The optional test checks returned superlevel IDs, preserved internal full-level
IDs, and a corrected recombination coefficient within a relative tolerance of
1e-6. Core derivative tests compare with finite differences to 1e-7, departure
ratios to 1e-10, and temperature updates to 1e-12.

The initialization drivers additionally test endpoint rounding, genuine grid
extensions, single-point overlap, disjoint grids, consistent occupation
probabilities, the three modern departure-file formats, exact zeros, disabled
level dissolution, elemental normalization and charge conservation. The
new module's metadata is taken from the actual `MOD_CMFGEN` source; these tests
do not require existing module files or libraries.

`run_bstar_initialization_checks.py --help` describes the optional native
zero-iteration tests. Supply the prepared 115-depth/current-export and
125-depth/refined templates, saved binary-population array, and independently
constructed refined-population array from the earlier Bstar investigation.
This driver requires NumPy and a built atmosphere executable, copies inputs
and atomic links into fresh temporary folders, and checks same-grid R,
same-grid POP and refined-grid POP against the saved references. It neither
runs the templates' shell scripts nor writes to the templates.

`check_moment_grid_jacobian.py` verifies inserted moment grids using actual native
transport and finite differences, including the production variation wrapper's
clumping, frequency history, scattering, line-level and temperature transforms.
It requires NumPy and compatible built CMFGEN modules/libraries. Use
`--optimization O2 --threads 5` for the threaded check and `--baseline-root` for
bit-for-bit comparisons with saved pre-fix source. See the
[repair report](../cmfgen-inserted-moment-grid.md) for scope and instrumentation.

`check_related_moment_paths.py` is an audit driver for unresolved related paths.
It reports native `GET_MOMS_REL` bounds/initialization observations and unrefined
finite-difference discrepancies; it is not a pass/fail certificate. See the
[related-path audit](../cmfgen-related-moment-paths-audit.md) for reachability and scope.


`check_moment_families.py` validates the related REL, DDT and two-level
`INC_GRID` repairs, the actual production variation prefix, angular values and
bounds, native old-time cache resizing, full line-slot reuse, and first-frequency
OpenMP-private history. Run both the default O0/one-thread configuration and
`--optimization O2 --threads 5`. It writes source/fixture hashes, commands and
finite-difference evidence into a fresh isolated directory. See
[scope and forward changes](../cmfgen-related-moment-repairs.md).

`check_convergence_repairs.py` tests the Bstar3010 interpolation, collision
Jacobian and X-ray normalization repairs using production routines and extracted
native control branches. It builds in a separate directory and needs compatible
built modules/libraries. Run with `--optimization O0` and `O2`; optionally pass
`--baseline-interpolation` to compare ordinary interpolation output byte-for-byte.
See [repair scope and automatic remedies](../cmfgen-convergence-repairs.md).
