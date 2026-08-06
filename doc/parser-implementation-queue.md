# Parser Support and Remaining Queue

## Current Structured Support

### Core model products

- `RVTJ`, `OBSFLUX`, `OBSFRAME`, `MOD_SUM`
- `MEANOPAC`, `HYDRO`, `GAMMAS`, `CORRECTION_SUM`
- `POP*`, ion `*OUT`, and ion `*PRRR` families
- `J_COMP`, `NETRATE`, `TOTRATE`, `EWDATA`, `LINEHEAT`

### Workflow aliases

Aliases retain the parser used by their canonical producer:

- `obs_fin*`, `obs_cont*` -> observer spectrum parser
- `hydro_fin*`, `hydro_cont*` -> `HYDRO`
- `meanopac_fin*` -> `MEANOPAC`
- `ewdata_fin*`, `EWDATA_xtgrid*` -> `EWDATA`
- `GAMFLUX_NEW` -> `GAMFLUX`
- `GAMRAY_E_DEP`, `GAMRAY_E_DEP_MOD` -> gamma deposition parser
- `full_timing*`, `cont_timing*` -> timing log parser
- `corrections.<iteration>` -> correction-summary parser

### Post-processed spectra

Two-column wavelength/flux viewers are available for:

- `cmf.sed`
- model `*.uv`, `*.vis`, `*.ir` products
- continuum `*.cuv`, `*.cvis`, `*.cir` products
- `sp.dat`, `spc.dat`

### Stable CMFGEN and SN diagnostics

- `ADIABAT_CHK`, `AUTO_CHK_*`, `COLLISION_SUMMARY`
- `GENCOOL`, `TWO_PHOT_SUM`, `STEQ_VALS`
- `ENERGY_COMP`, `SPECIES_MASSES`
- `GAMMA_MODEL`, `GAMRAY_PARAMS`
- `NON_THERM_COOL`, `NON_THERM_ION_SUM`, `NON_THERM_SPEC_INFO`
- `NEW_SN_R_GRID`, `OLD_SN_R_GRID`, `SN_HYDRO_FOR_NEXT_MODEL`
- decay, charge-exchange, SN grey, and energy-deposition check files
- `GREY_SCL_FACOUT`, `NEW_CALC_GRID`, `NEG_OPAC`
- `OUTGEN`, `WARNINGS`, `TIMING`, `MOM_J_ERRORS`, and related logs

### Verbose gamma-transport diagnostics

Generic table/plot support is available for the `data/` products observed in the
SN models, including:

- `ETA_ISO_<depth>.dat`
- `ETA_MUAVG_<angle>_<depth>.dat`
- `GAMMA_J_<angle>_<depth>.dat`
- gamma frequency, optical-depth, scattering, luminosity, and emission tables

These are implementation/debug products rather than a stable CMFGEN interface.
They use bounded table rendering and downsampled plots to keep the browser usable.

### Direct-access and restart binaries

The viewer reads current six-field and legacy four-field `_INFO` sidecars and
shows record length, word size, endianness when recorded, depth count, and the
record count implied by file size. This covers observed `EDDFACTOR`, `IP_DATA`,
`IP_DATA_NEW`, `SOB_FORCE_DATA`, and `JH_AT_*_TIME` files. Sequential state files
without a compatible sidecar receive a safe metadata-only view.

The binary record payload is deliberately not decoded yet; its record schema is
product-specific even when the storage metadata is shared.

## Remaining Work

1. Add product-specific binary payload schemas for `ETA_DATA`, `CHI_DATA`,
   `RAY_DATA`, `FLUX_FILE`, `CMF_FORCE_DATA`, `SOB_FORCE_DATA`, `IP_DATA`,
   `RTAU_DATA`, `ZTAU_DATA`, and `dFR_DATA` when representative files are
   available.
2. Add richer domain-specific column labels to unstable gamma debug tables as
   their producer formats are documented.
3. Treat `fort.*`, editor backups, `.sve` plotting state, scheduler logs, and
   helper-script scratch files as artifacts. They remain available through raw
   preview/download but are not CMFGEN parser APIs.

## Parser Definition of Done

- parser is registered by canonical name or an explicit family/alias rule;
- summary and meaningful tables/plots are shown when data permits;
- malformed, partial, empty, or oversized inputs fail safely with warnings;
- raw view/download remains available;
- representative real model files and focused fixtures are exercised.
