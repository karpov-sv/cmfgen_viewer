# Getting started

The viewer helps you inspect CMFGEN model folders, compare spectra, and prepare model workflows. Start with a model in the file browser; the compact model toolbar stays available across its file, editor, spectrum, and workflow pages.

## Browse a model

Use the file filters to narrow the listing by filename or role. **Quick links** collect common controls, outputs, and workspace files. Open a file in **Parsed** mode for structured tables and plots, or **Raw** mode to inspect its original text. Downloads preserve the original file.

For a first look at a computed atmosphere, open `MOD_SUM` for a summary, `RVTJ` for the depth structure, and `OUTGEN` for iteration history and numerical diagnostics. Use the model's final spectrum view to inspect observer spectra and continuum together.

## Inspect and compare spectra

Choose the available spectrum, adjust zoom and axis scales, and enable overlays as needed. Shared spectrum controls also appear in model comparisons and uploaded-data views. See [Spectrum viewer](/documentation/spectrum-viewer) for transformations, reference lines, and display detail.

Upload an observed spectrum or photometry through **Uploads** to compare it with models. Review imported units and points before fitting. Grid fitting uses the selected model grid and fit settings; a good fit still requires checking the data and model assumptions.

## Edit and run a model

Workspace changes require startup with `--read-write`. Model parameter and text editors retain recovery checkpoints. Copy a model when you want to explore different controls while preserving the original solution.

For a new LTE/hydro structure, follow [LTE / Hydro](/documentation/lte-hydro): prepare the workspace, run LTE, run hydro, review the result, then promote it. Promotion updates the root structure and archives incompatible old solution files. Continue to [Main computation](/documentation/main-computation) after the handoff is ready.

The viewer displays commands for execution in your terminal and offers **Model runner** for supported stage sequences. UI-launched jobs run independently and remain available after app restarts. Its workflow pages receive live process status and refresh results when a monitored calculation stops. Unsaved edits defer the reload. The separate [Command-line runner](/documentation/command-line-runner) can execute supported stages directly.

## Setup and reference

Use [Templates and configuration](/documentation/templates-and-configuration) for installation roots, reusable workspace defaults, workflow previews, and write protection. **System** shows effective settings and filesystem details.

[File reference](/documentation/file-reference) explains model controls, outputs, restart files, and observer products. Successful execution, fresh files, and completed counters do not by themselves establish convergence or scientific acceptance.
