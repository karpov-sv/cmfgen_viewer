# Model Grids

This guide covers preparing TLUSTY, BOSZ, and PHOENIX spectra for the viewer's
uploaded-spectrum and photometry fitting tools, including data conventions,
quality checks, and fitting performance. Run the commands from the repository
root after following the [installation instructions](README.md#installation).

The upload viewer reads resolution labels and velocity FWHM tooltips from each
installed grid's catalogue. Mixed resolutions and missing resolution metadata
are identified; TLUSTY SED binning is listed separately from spectral broadening.

The System page reuses imported-grid inventory counts for up to 30 seconds.
Catalogue and spectrum-directory changes invalidate the affected grid immediately;
maintenance-job status and model-summary cache results are read live.

For browsing models, viewer configuration, and the command-line CMFGEN runner,
see the [README](README.md).

- [TLUSTY download and fitting workflow](#tlusty-grid-workflow)
- [Local BOSZ import](#local-bosz-import)
- [Local PHOENIX R10000 import](#local-phoenix-r10000-import)
- [Lossless BOSZ and PHOENIX storage](#lossless-bosz-and-phoenix-storage)
- [Fitting performance](#fitting-performance)

## TLUSTY Grid Workflow

### 1. Download and preprocess TLUSTY spectra

Use the helper script to download OSTAR2002/BSTAR2006 archives and build reusable `.npz` spectra plus a CSV index:

```bash
python scripts/download_tlusty_spectra.py
```

Useful options:

- `--grid ostar --grid bstar` select one or both TLUSTY grids.
- `--product flux --product uv --product optical --product continuum` limit archive classes (default already includes all four).
- `--archive-pattern "<glob>"` limit archive names using shell-style patterns.
- `--crawl-depth <n>` set HTML link crawl depth (default: `2`).
- `--force-download` and `--force-process` refresh cached archives / processed `.npz` outputs.
- `--local-only` use only existing archives under `data/tlusty/raw/`, without network requests.
- `--workers 4` convert independent archives in four processes (1–32; default 1).
- `--resolving-power 50000` add Gaussian instrumental broadening and resample detailed `.7` spectra at R=50,000.
- `--samples-per-resolution 3` set output samples per Gaussian FWHM (default 3, minimum 2).
- `--sed-binning-power 3000` rebin broad `.flux` SEDs into flux-conserving log-wavelength bins at lambda/bin-width=3,000 (default: native SEDs).

By default, output is written under `data/tlusty/`:

- `data/tlusty/models.csv`: model index used by viewer-side TLUSTY discovery.
- `data/tlusty/manifest.json`: run metadata and archive-level processing summary.
- `data/tlusty/spectra/.../*.npz`: processed spectrum arrays used during fitting/overlay.

By default, converted files retain the full wavelength coverage, sampling, and
float64 precision of the processed spectra. They store wavelength and per-Angstrom flux,
plus continuum/normalized flux when available, and small source-axis metadata.
Unused original columns and frequency-space copies are omitted; the original
downloaded archives remain under `raw/`.

To compact an existing cache without downloading or parsing the archives again:

```bash
python scripts/compact_tlusty_spectra.py
# Optional: --root /path/to/tlusty --workers 4
```

The command preserves every fitting array exactly, verifies each replacement
before installing it, and updates both indexes. It can be rerun after an
interruption. The viewer reads both the older and compact formats.

SYNSPEC detailed wavelength tables use **air above 2000 Å**, with vacuum below
that threshold; frequency-based TLUSTY `.flux` SEDs use vacuum throughout.
The importer preserves these source coordinates and records `wavelength_medium`.
The viewer converts Air model coordinates to vacuum on loading, before applying
source redshift and converting to the upload's convention. Older caches are
recognized through `x_axis_kind=wavelength_input`, so redownloading is unnecessary.
Explicit `wavelength_medium=vacuum` overrides the default for all-vacuum runs.
See [SYNSPEC's wavelength convention](https://arxiv.org/pdf/1706.01859#page=20).

To rebuild the detailed spectra at a chosen instrumental resolution from the
existing raw archives:

```bash
python scripts/download_tlusty_spectra.py --local-only \
  --resolving-power 50000 --samples-per-resolution 3
```

R means `wavelength / instrumental FWHM`. Conversion adds a Gaussian in log
wavelength to the native stellar profiles, using an oversampled working grid
before resampling at constant velocity spacing. It retains the wavelength
endpoints and float64 precision. This broadening is additional to the physical
line widths already present in the model. Edges use constant extension for the
convolution, so avoid relying on features within a few instrumental widths of
the spectrum boundaries.

The Gaussian resolution setting applies to detailed `.7` spectra. Continua
retain their native sampling. Broad `.flux` SEDs use the separate binning option
described below; all settings retain complete wavelength coverage.

Changing R or samples per resolution element automatically rebuilds affected
spectra from raw archives; matching files are reused. To restore native detailed
spectra, omit `--resolving-power`:

```bash
python scripts/download_tlusty_spectra.py --local-only
```

Resolution and sampling settings are recorded per spectrum and in both indexes.
Resolution-controlled spectra bypass the viewer's legacy 20,000-point fitting
limit, retaining the chosen sampling; this can increase fit time compared with
the legacy limit. Fitted Gaussian broadening is additional to the stored
instrumental broadening. A reduced grid cannot fit narrower instrumental
profiles by sharpening itself. Native spectral fits retain the existing
20,000-point limit. All TLUSTY photometric fits now use every stored sample,
including native SEDs: index-based thinning can discard sparsely sampled IR
points and bias band-integrated fluxes.

Disk savings depend on compressed values as well as the number of points.
Smoothed float64 fluxes can compress less efficiently than the original
tabulated values, so reducing point counts by half need not halve file sizes.
Higher R or denser sampling can even increase file sizes.

#### Rebin broad SEDs for photometry

After any currently running conversion finishes, this command keeps detailed
spectra at R=50,000 and also rebins broad SEDs:

```bash
python scripts/download_tlusty_spectra.py --local-only \
  --resolving-power 50000 --samples-per-resolution 3 \
  --sed-binning-power 3000
```

Matching detailed spectra are reused. SEDs are rebuilt from raw archives when
the binning setting changes. Binning integrates the native piecewise-linear
F-lambda spectrum over logarithmic wavelength bins and stores bin means at their
centers, with the original endpoints retained. Float64 precision and the entire
wavelength range are preserved. Already-sparse models keep their native samples
when binning would not reduce the number of stored points.

SED binning power is `lambda / bin width`, not Gaussian instrumental resolving
power; `--samples-per-resolution` applies only to detailed spectra. The binning
power, method, and whether rebinning was applied are recorded in each NPZ and
both model indexes. The lossless compaction command preserves this metadata.

Rebinned SEDs are selected for **photometric fits only**, and bypass the legacy
20,000-point limit. Detailed spectra remain available for spectral fits. SEDs
whose native sampling was retained remain ordinary candidates.

The full-cache investigation measured a reduction from 6.24 to 0.92 GiB at
binning power 3,000. In the tested broadband passbands, the 73-model reddening
and redshift study found maximum flux errors below 0.05%. Narrow bands near
strong UV edges showed percent-level errors, so this option is intended for
broadband photometry. See the [investigation and limitations](doc/developer/tlusty-sed-rebinning.md).

To restore native SEDs while keeping detailed spectra at R=50,000, omit the SED
option but retain the detailed-spectrum settings:

```bash
python scripts/download_tlusty_spectra.py --local-only \
  --resolving-power 50000 --samples-per-resolution 3
```

Omitting both resolution/binning options restores both products to native
sampling. Keep all desired conversion settings in each command; no
`--force-process` is needed when they change. Do not run two conversions against
the same output directory concurrently.

#### Parallel conversion

The converter's Python text parsing uses most of a single CPU core. Separate
processes can convert different archives concurrently:

```bash
python scripts/download_tlusty_spectra.py --local-only \
  --resolving-power 50000 --samples-per-resolution 3 \
  --sed-binning-power 3000 --workers 4
```

Four workers are a useful starting point on a multicore machine; each worker
needs its own parsing memory. The default remains one worker. Downloads and
final index writing happen in the parent process; each worker owns a separate
archive output directory. If archive names would produce overlapping output
directories, the converter falls back to serial processing. Only metadata is
returned from workers, not full spectrum arrays.

An interrupted serial conversion can be resumed with `--workers 4`: stop the
old process first, keep the same conversion settings, and omit `--force-process`.
Completed files are reused after checking their stored settings. Conversion
errors leave the previous indexes in place, and individual NPZ replacements
are atomic. Changing worker count does not change spectrum values or index order.

On 2026-11-10, a 16-spectrum BSTAR UV benchmark at R=50,000 took 14.47 s serially,
16.66 s with four threads, and 4.23 s with four processes (3.4x faster). A live
single-process run used 99.8% of one core while the 16-logical-CPU machine was
90.3% idle with 0.1% I/O wait. One representative conversion spent about 0.71 s
parsing, 0.13 s compressing, 0.035 s decompressing, 0.030 s resampling, and 0.007 s
reading the raw archive. This is a CPU bottleneck. Whole-grid speedup depends on
archive sizes, remaining work, CPU availability, and memory; a single remaining
archive cannot use multiple archive workers.

Further reductions involve different tradeoffs:

- Store flux as float32: potentially useful, but compare fitted parameters and
  chi-square against float64 first. Keeping wavelength as float64 avoids reducing
  wavelength precision for narrow lines and velocity fits. Very small SED fluxes
  can underflow in float32; compressed size savings also depend on the source
  precision and may be small.
- Reduce sampling/resolution: use a separate cache matched to the observations,
  with appropriate smoothing before resampling. Dropping every nth point can
  distort line profiles and equivalent widths.
- Restrict wavelength coverage: preserve the full filter passbands used for
  photometry and margins for redshift and broadening around spectral fit ranges.
  An optical-only cache cannot support UV/infrared photometry.
- Restrict atmosphere parameters or archive products: useful for a specialized
  grid, but may exclude the best-fitting model or a needed continuum counterpart.

Lossless compaction applies none of these lossy reductions. Choosing an
instrumental R or SED binning power is a separate, opt-in conversion step.

### 2. Run TLUSTY grid fitting in the upload viewer

After uploading an observed spectrum (`/uploads/view/<token>`):

- choose `TLUSTY grid` as the fit source and start the grid search;
- optionally restrict candidates with `model_name_pattern` (shell-style `fnmatch` rules);
- use the same fit controls as CMFGEN fitting: parameter bounds, optional wavelength fit range, progress polling, and `Stop Search`;
- see real-time best-so-far updates and overplot of the best current/final TLUSTY model.

Flux handling:

- absolute observed spectra are fitted against TLUSTY UV/optical/SED spectra with a free multiplicative normalization (distance is ignored);
- absolute photometry requires every enabled band to be covered, preventing partial UV/optical segments from competing with full-range TLUSTY SEDs;
- rebinned broad SEDs participate only in photometric fits, which retain all stored samples;
- normalized observed spectra are fitted against TLUSTY spectra normalized by matched continuum counterparts.

## Local BOSZ Import

Convert a downloaded BOSZ 2024 resampled subset into the same CSV/NPZ storage
format, without downloading or resampling anything:

```bash
python3 scripts/import_bosz_spectra.py ~/tmp/grids/bosz
```

The source must contain `bosz2024_wave_r2000.txt` and matching
`bosz2024_*_r2000_resam.txt.gz` files (subdirectories are supported). Use
`--resolution N` for another downloaded resolution and `--output-dir PATH`
to change the default `data/bosz/` destination.
Conversion uses four workers by default (`--workers N` to change this).

The importer writes `models.csv`, `manifest.json`, one compressed NPZ per
model, and shared wavelength NPZs. It preserves both the flux and continuum
columns and calculates their ratio on load for normalized fitting, using the
original validity mask. Published wavelength samples are retained exactly. Flux and
continuum remain Eddington H-lambda in erg/s/cm²/Å, matching the TLUSTY storage
convention; multiply by 4π when a physical surface flux is required.
Atmosphere family (`ap`, `mp`, `ms`), metallicity, alpha/carbon abundance,
microturbulence, and the existing instrumental resolving power are recorded
in the catalogue. Full model names distinguish overlapping atmosphere families.
Source checksums are retained, but filenames alone do not identify whether a
download contains the publisher's corrected revision.

BOSZ **2024** uses **air wavelengths above 2000 Å**, and vacuum below, as
specified in [Mészáros et al. (2024), §3.3](https://arxiv.org/pdf/2407.10872#page=5).
This differs from the older BOSZ 2017 vacuum grid. The viewer converts the
2024 source axis to vacuum on loading, before redshift and the upload convention
are applied. Existing imported caches are recognized by their `bosz2024_`
filenames; reimporting is unnecessary. New imports record the native convention
in both indexes. PHOENIX-ACES retains its published vacuum axis.

An R=2000 import remains an R=2000 product, even though its sampling is finer
than one resolution element. It is not a replacement for detailed TLUSTY line
spectra. The imported catalogue remains separate from TLUSTY.

In the upload viewer, click **Find Best BOSZ Model** to search the imported grid.
Normalized spectra use the flux/continuum ratio; absolute spectra and
photometry use a free normalization per model, with no distance parameter.
Photometry candidates must cover every enabled band. Model-name patterns can
select a subset, for example `*_ap_*` for ATLAS9 or `*_t8000_*` for 8000 K.
The fit uses all native BOSZ samples. Its Gaussian broadening parameter is
**additional** broadening, not the total instrumental width: an R=2000 input
grid cannot fit narrower instrumental profiles by sharpening itself.
Progress, cancellation, best-fit overlays, and parameter confidence summaries
work as for the other grids. Results retain the atmosphere family and native
resolving power. The default catalogue is `data/bosz/`; an application embedding
the viewer can override `app.config["CMFGEN_VIEWER"]["bosz_root"]`.

Existing output directories are never overwritten. The importer publishes the
new directory only after all files validate and convert successfully; failed
imports clean up their temporary output. Original downloads are never changed.
Generated data are gitignored.
Negative source fluxes are masked with NaN in fitting arrays, with their
original values retained in `raw_flux_lambda_cgs`. Non-positive continua are
excluded from normalization. Per-model mask counts are recorded, and catalogue
wavelength coverage excludes unusable edge samples. Non-finite source values
or malformed arrays stop the import rather than silently dropping a model.

## Local PHOENIX R10000 Import

```bash
python3 scripts/import_phoenix_spectra.py ~/tmp/grids/R10000FITS
```

Reads local `PHOENIX-ACES-AGSS-COND-2011_R10000FITS_Z*.zip` archives without
extracting or modifying them. Output is `data/phoenix/` by default; use
`--output-dir PATH` or `--workers N` (default four) as needed. Existing output
is never overwritten; publication is atomic, with failed staging data removed.
Generated CSV, manifest, and NPZ data are gitignored.

The installed subset has 7,559 spectra: Teff 2300–12000 K, log g 0–6,
[M/H] −4 to +1, and [alpha/M] = 0 (not every parameter combination exists).
Each spectrum retains all 212,027 samples, spanning approximately 3000–25000 Å.
The logarithmic sampling is ten points per resolution element, **not R=100000**:
the actual product is broadened to R=10000, about 30 km/s FWHM.

This product needs explicit convention handling, following
[Husser et al. (2013)](https://arxiv.org/abs/1303.5632):

- Wavelengths are `exp(CRVAL1 + (pixel - CRPIX1)*CDELT1)` in Å, using
  one-based pixels and CRPIX1 = 1 when absent. The published **vacuum** convention
  overrides these archives' misleading `AWAV-LOG` header; no air-to-vacuum shift
  is applied. The source header and override are recorded in provenance.
- Surface F-lambda per cm is multiplied by `1e-8 / (4*pi)` on load to obtain
  Eddington H-lambda per Å, matching the existing TLUSTY/BOSZ convention.
  Compact files retain original float32 source flux and an exact float64 scale.
  This encoding is used only when it reproduces the previous float64 fitting
  values exactly; other inputs retain their scaled float64 precision.
- The 51 `INTERPOL` spectra remain available and are labelled in fit results.
  Missing BUNIT on these files uses the published product convention and is
  flagged. Fractional microturbulence is retained as a **derived property**,
  not treated as an independent fit axis or rounded to integer km/s.
- Six spectra contain 144 negative samples in interior wavelength intervals.
  Their data are retained unchanged apart from unit conversion, but those six
  whole models are excluded from fitting; corrupt intervals are not bridged.
  This leaves **7,553 eligible fitting models**. Source/member SHA-256 checksums
  and per-model quality flags are recorded in `manifest.json` and `models.csv`.

Use **Find Best PHOENIX Model** on an absolute-flux spectrum or photometry upload.
There are no supplied continua, so normalized-spectrum fitting is disabled in
the UI and rejected by the server. Absolute fits solve a free normalization;
distance is not fitted. Photometry requires every enabled band to be covered,
including any allowed redshift range (optical and JHKs can fit, UV/WISE cannot).
The Gaussian broadening parameter adds to native broadening; use observed
spectra at comparable or lower resolution. Declare the upload Air/Vacuum property;
the fitting and display pipelines convert vacuum models to that convention.
Progress, cancellation, confidence summaries, and best-fit overlays use the
shared grid workflow. Model-name patterns such as `lte06000*` restrict searches.
Full-grid fits use more CPU and storage than BOSZ. Embedders can override
`app.config["CMFGEN_VIEWER"]["phoenix_root"]`.

## Lossless BOSZ and PHOENIX storage

Both importers use compact storage by default, without changing resolution,
sampling, wavelength coverage, fitting values, or quality flags. Wavelength
axes are stored once as `spectra/_wavelength_<sha256>.npz`, with a content key
in each model file. The reader verifies and caches shared axes in memory.
BOSZ omits the redundant normalized array; PHOENIX retains source precision
with the exact conversion described above. `available_arrays` in the indices
describes logical arrays returned by the reader, including reconstructed ones.
The manifest's `spectrum_storage` identifies `shared-wavelength-v1`.

Keep the whole `spectra/` directory together when copying a grid. For scripts
that read converted spectra directly, use
`cmfgen_viewer.grid_storage.load_spectrum(path)` to obtain logical arrays.
Legacy standalone NPZ files remain readable, including mixed caches during
migration. Existing caches can be compacted in place:

```bash
python3 scripts/compact_imported_grids.py data/bosz data/phoenix --workers 4
```

Every logical array is compared exactly (including NaN masks and retained raw
negative BOSZ flux) before its file is atomically replaced. An interruption
leaves a readable mixed cache; rerunning completes it. Per-model metadata and
`models.csv` are preserved. Raw source files and archives are untouched.
The installed BOSZ cache occupies 1.16 GiB (previously 3.10 GiB), and PHOENIX
4.80 GiB (previously 19.10 GiB), including shared axes. Restart an already
running viewer before using compacted grids so it loads the updated reader.

## Fitting performance

NPZ grid fits keep NumPy arrays in their existing F-lambda/normalized convention,
without converting through Jy or Python lists. Uniform logarithmic grids are
cropped to the enabled observations with margins for the full redshift bounds,
Gaussian kernel, and photometric band edges. Native sampling is retained;
nonuniform grids keep their original convolution lattice.

CMFGEN spectra use validated bulk numeric parsing, with the legacy parser as a
fallback for missing-E Fortran exponents and punctuation. Grid fits request
read-only NumPy arrays directly; viewer callers continue to receive lists.
Nonuniform-grid broadening prepares its native-size logarithmic lattice and
interpolation mappings once per fit and reuses them across redshift, extinction,
distance, and width trials. The native axis, transform order, discrete Gaussian
kernel, and edge extension are retained. All caches remain memory-only.

Fits cache reddening-law values by redshift. Unbroadened point-spectrum trials
transform only the model samples needed for interpolation (reddening still
precedes interpolation); photometry continues to integrate full bands. Wide
Gaussian kernels use FFT convolution with the same discrete four-sigma kernel
and nearest-edge extension as the direct implementation. Small kernels use
direct convolution. These optimizations do not modify imported spectra or
introduce additional downsampling for spectral fits; the legacy TLUSTY point
cap is unchanged.

Unbroadened absolute photometry fits prepare compact band quadrature, preserving
native line fluxes and interpolated band edges. Logarithmic grouping starts at
approximately R=300 and refines until a conservative extinction-averaging bound
limits relative band-flux error to 0.01% over the fitted E(B-V) range. Signed
fluxes or bands that cannot meet the bound retain native quadrature. Redshift
and broadening remain available; trials with nonzero smoothing use native
spectra. Band integration uses sorted slices rather than scanning the whole
spectrum per band. Final scores and the zero-broadening comparison use native
integration. Absolute CMFGEN grid fits skip loading the unused continuum
and convert Jy to F-lambda directly in NumPy. Fixing redshift and broadening
to zero also avoids repeating the same extinction/distance optimization stage.

The default free-broadening seed starts above the no-smoothing threshold, uses a 1% relative
finite-difference step, and explicitly checks the zero-width boundary. Unlike
the former zero seed, this lets absolute fits explore nonzero widths. Results
and iteration counts can therefore change; not every free-parameter fit gets
the same speedup. A narrow model-name pattern remains useful for exploratory
searches before evaluating thousands of atmospheres.

## Uploaded wavelength convention

Uploads default to **Air**; choose Vacuum for vacuum-wavelength observations.
The property can be corrected later on the upload page without rewriting the
source. Old uploads without a saved property also default to Air. Rerun fits
after editing it. VizieR-generated photometry is recorded as Vacuum.

Models use vacuum internally, including converted SYNSPEC air tables. For Air observations the pipeline applies source
redshift in vacuum, broadens the native model, then converts to air and samples
onto the unchanged observed pixels. Absolute F-lambda includes the coordinate
Jacobian; normalized flux is unchanged by the medium conversion. Both fitting
and plotting use this convention. The source velocity keeps the optical
convention v = c z; positive velocity shifts predictions redward.

Fit ranges, diagnostic windows, exclusions, observed noise and bad pixels all
remain in the uploaded coordinate system. Stellar markers follow the model
redshift and medium conversion; telluric guides remain fixed. See
[spectrum-viewer.md](doc/spectrum-viewer.md) for controls and frame details.
