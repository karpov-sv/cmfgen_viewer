# Packaged workflow defaults

Files mirror their destination in a model workspace, including `lte/` and
`obs/`. They are read-only fallback sources: preparation
copies them before applying model parameters. Local templates take precedence.

See `doc/templates-and-configuration.md` in the repository for resolution rules and
which physical inputs must come from the source model.

`atomic_links.json` supplies data-only ostar atomic declarations for the native
runner when no local declarations are available. Paths are relative to the
configured atomic-data root; no shell script is executed.
