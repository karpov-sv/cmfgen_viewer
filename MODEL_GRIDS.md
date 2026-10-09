# Model Grids

This guide covers preparing TLUSTY, BOSZ, and PHOENIX spectra for the viewer's
uploaded-spectrum and photometry fitting tools, including data conventions,
quality checks, and fitting performance. Run the commands from the repository
root after following the [installation instructions](README.md#installation).

For browsing models, viewer configuration, and the command-line CMFGEN runner,
see the [README](README.md).

- [TLUSTY download and fitting workflow](#tlusty-grid-workflow)
- [Local BOSZ import](#local-bosz-import)
- [Local PHOENIX R10000 import](#local-phoenix-r10000-import)
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

By default, output is written under `data/tlusly/`:

- `data/tlusly/models.csv`: model index used by viewer-side TLUSTY discovery.
- `data/tlusly/manifest.json`: run metadata and archive-level processing summary.
- `data/tlusly/spectra/.../*.npz`: processed spectrum arrays used during fitting/overlay.

### 2. Run TLUSTY grid fitting in the upload viewer

After uploading an observed spectrum (`/uploads/view/<token>`):

- choose `TLUSTY grid` as the fit source and start the grid search;
- optionally restrict candidates with `model_name_pattern` (shell-style `fnmatch` rules);
- use the same fit controls as CMFGEN fitting: parameter bounds, optional wavelength fit range, progress polling, and `Stop Search`;
- see real-time best-so-far updates and overplot of the best current/final TLUSTY model.

Flux handling:

- absolute observed spectra are fitted against TLUSTY UV/optical/SED spectra with a free multiplicative normalization (distance is ignored);
- absolute photometry requires every enabled band to be covered, preventing partial UV/optical segments from competing with full-range TLUSTY SEDs;
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

The importer writes `models.csv`, `manifest.json`, and one compressed NPZ per
model. It preserves both the flux and continuum columns, adds their ratio for
normalized fitting, and retains the published wavelength samples. Flux and
continuum remain Eddington H-lambda in erg/s/cm²/Å, matching the TLUSTY storage
convention; multiply by 4π when a physical surface flux is required.
Atmosphere family (`ap`, `mp`, `ms`), metallicity, alpha/carbon abundance,
microturbulence, and the existing instrumental resolving power are recorded
in the catalogue. Full model names distinguish overlapping atmosphere families.
Source checksums are retained, but filenames alone do not identify whether a
download contains the publisher's corrected revision.

An R=2000 import remains an R=2000 product, even though its sampling is finer
than one resolution element. It is not a replacement for detailed TLUSTY line
spectra. The imported catalogue remains separate from TLUSTY.

In the upload viewer, click **Find Best BOSZ Model** to search the imported grid.
Normalized spectra use the stored flux/continuum ratio; absolute spectra and
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
- Surface F-lambda per cm is multiplied by `1e-8 / (4*pi)` to store Eddington
  H-lambda per Å, matching the existing TLUSTY/BOSZ convention.
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
spectra at comparable or lower resolution and on a compatible vacuum axis.
Progress, cancellation, confidence summaries, and best-fit overlays use the
shared grid workflow. Model-name patterns such as `lte06000*` restrict searches.
Full-grid fits use more CPU and storage than BOSZ; the installed NPZ grid is
about 20.5 GB. Embedders can override
`app.config["CMFGEN_VIEWER"]["phoenix_root"]`.

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

