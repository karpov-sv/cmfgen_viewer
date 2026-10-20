# Getting started

The viewer helps you inspect CMFGEN model folders, compare spectra, and prepare model workflows. Start with a model in the file browser; the compact model toolbar stays available across its file, editor, spectrum, and workflow pages.

## Browse a model

Use the file filters to narrow the listing by filename or role. **Quick links** collect common controls, outputs, and workspace files. Open a file in **Parsed** mode for structured tables and plots, or **Raw** mode to inspect its original text. Downloads preserve the original file.

For a first look at a computed atmosphere, open `MOD_SUM` for a summary, `RVTJ` for the depth structure, and `OUTGEN` for iteration history and numerical diagnostics. Use the model's final spectrum view to inspect observer spectra and continuum together.

## Inspect and compare spectra

Choose the available spectrum, adjust zoom and axis scales, and enable overlays as needed. Shared spectrum controls also appear in model comparisons and uploaded-data views. See [Spectrum viewer](/documentation/spectrum-viewer) for transformations, reference lines, and display detail.

Upload an observed spectrum or photometry through **Uploads** to compare it with models. Review imported units and points before fitting. Grid fitting uses the selected model grid and fit settings; a good fit still requires checking the data and model assumptions.

## Edit and run a model

Workspace changes require read-write mode, enabled with `--read-write`, viewer configuration `read_write = true`, or `read_write = true` in `.cmfgenrc`. `--read-only` overrides configured defaults. Model parameter and text editors retain recovery checkpoints. Copy a model when you want to explore different controls while preserving the original solution.

In **Edit parameters → Quick parameters**, enable **Keep effective temperature and log g fixed** to change luminosity while scaling the saved `RSTAR` by `sqrt(LSTAR / original LSTAR)` and `MASS` by the luminosity ratio. Radius, mass, and log g become read-only while selected; `TEFF` and `LOGG` are retained. Review the derived changes before saving. Every preview uses the original saved values, and saving creates the usual recovery checkpoint and marks the solution stale. The option requires unique, valid `LSTAR`, `RSTAR`, `MASS`, `TEFF`, and `LOGG` controls, with positive luminosity, radius, mass, and temperature. A review warning flags an existing mass/gravity discrepancy greater than 0.05 dex at the LTE/hydro reference radius; scaling preserves that discrepancy. This edits controls; it does not regenerate the LTE/hydro structure.


For a new LTE/hydro structure, follow [LTE / Hydro](/documentation/lte-hydro): prepare the workspace, run LTE, run hydro, review the result, then promote it. Promotion updates the root structure and archives incompatible old solution files. Continue to [Main computation](/documentation/main-computation) after the handoff is ready.

The viewer displays commands for execution in your terminal and offers **Model runner** for supported stage sequences. UI-launched jobs run independently and remain available after app restarts. Its workflow pages receive live process status and refresh results when a monitored calculation stops. Unsaved edits defer the reload. The separate [Command-line runner](/documentation/command-line-runner) can execute supported stages directly.

## Setup and reference

Use [Templates and configuration](/documentation/templates-and-configuration) for installation roots, reusable workspace defaults, workflow previews, and write protection. **System** shows effective settings and filesystem details.

[File reference](/documentation/file-reference) explains model controls, outputs, restart files, and observer products. Successful execution, fresh files, and completed counters do not by themselves establish convergence or scientific acceptance.

## History and recovery

The model toolbar's **History** button opens saved runner journals, editor checkpoints, and workflow recovery archives, including archives inside `lte/` and `obs/`. Each entry shows its date, size, status, and recorded retention policy. Open an entry to view or download individual files and compare archived controls with their current versions. An unrecorded policy means the archive has no retention metadata; it does not imply a complete backup.

The full control-file editor always shows **Saved versions** above the file contents. This includes editor backups and recognized control copies from runner and workflow archives. The quick-parameter page links to **Saved versions and recovery**. Choose a version and **Load into Editor**, review the displayed diff, and **Save Reviewed Changes** to restore it. Loading does not modify the model; saving backs up the current control and uses the usual stale-solution handling.

Archives are retained indefinitely. Filter by minimum age, select archives, and **Preview cleanup** to either remove calculated state and scratch files while keeping complete input files, JSON history, and diagnostic excerpts, or delete complete archives. Confirmation is required; changed archives invalidate the preview. Cleanup and recovery writes require read-write mode and an idle model with available process visibility. Read-only browsing remains available during runs. Deleting an archive removes its recovery evidence permanently and can leave older job-detail links without their underlying journal.


In a main/test journal with a complete fresh-input bundle, **Preview input restoration** reviews **Restore inputs for a fresh run**. It restores the saved pre-run controls and population inputs as one set, retires incompatible binary checkpoints, atmosphere and observer results, and atomic links, and marks the solution stale. No calculation starts. Current files are backed up before replacement; failed installation rolls back before any compaction. Required seed inputs are retained even above 2 MiB. Main/test archives with missing seed inputs, changed archive contents, unsafe paths, or changed external atomic/template dependencies cannot be restored as a complete set. Archives without a fresh-input manifest remain available for individual control review. Temporary runner iteration and LTE-initialization overrides are recorded in the run plan and are not reapplied by this action. Review main preflight after restoration.

Recovery preserves inputs and run evidence, rather than a resumable iteration state. Native checkpoint restoration is not offered; normal continuation still uses the live model checkpoints. Existing archives are changed only by explicit History compaction or deletion; the new policy applies automatically only to newly completed operations.
