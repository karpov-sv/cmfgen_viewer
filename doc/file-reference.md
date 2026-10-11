# File reference

Use this page to identify a model file or follow its role in a calculation. The viewer's parsed file pages provide the available summaries, tables, and plots alongside raw text and downloads.

## Common files

| Files | Purpose |
| --- | --- |
| `VADAT`, `MODEL_SPEC`, `IN_ITS` | Physical controls, dimensions/ions, and iteration settings |
| `RVTJ`, `MODEL`, `MOD_SUM` | Atmosphere structure, model state, and final summary |
| `OUTGEN`, `WARNINGS`, `TIMING` | Iteration history, run diagnostics, and timing |
| `HYDRO`, `MEANOPAC`, `OBSFLUX` | Structure consistency, opacities/optical depth, and comoving flux |
| `POINT1`, `POINT2`, `SCRTEMP` | Restart pointers and binary checkpoint state |
| `lte/GRID_PARAMS`, `lte/HYDRO_PARAMS` | LTE grid and hydro controls |
| `lte/ROSSELAND_LTE_TAB`, `lte/RVSIG_COL_NEW` | Generated LTE opacity table and hydro structure |
| `obs/CMF_FLUX_PARAM_INIT`, `obs/IN_FILE` | Observer synthesis setup |
| `obs/obs_fin*`, `obs/obs_cont*` | Named observer spectra and continuum products |

## Detailed reference

The [Comprehensive file inventory](/documentation/reference/cmfgen-comprehensive-file-inventory) is the main lookup reference. It groups files by role, producer/consumer, and format, including optional diagnostics, atomic-data families, and binary sidecars.

The following investigations retain deeper source-level detail for troubleshooting:

- [Input files](/documentation/reference/cmfgen-input-files): startup, continuation, atomic data, and conditional inputs.
- [Output files](/documentation/reference/cmfgen-output-files): science products, diagnostics, binary outputs, and aliases.
- [CMF_FLUX files](/documentation/reference/cmfgen-cmf-flux-files): observer synthesis inputs and outputs.
- [Processing pipeline and file I/O map](/documentation/reference/cmfgen-end-to-end-processing-pipeline): file flow through native programs and helper scripts.

These investigations describe the recorded CMFGEN source snapshot and script variants. Source line numbers and optional file behavior may differ in another installation. For current viewer/runner instructions, use [LTE / Hydro](/documentation/lte-hydro), [Main computation](/documentation/main-computation), and [Command-line runner](/documentation/command-line-runner).
