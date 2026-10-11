# Packaged workflow defaults

Files mirror their destination in a model workspace, including `lte/` and
`obs/`. They are read-only fallback sources: preparation
copies them before applying model parameters. Local templates take precedence.

See `doc/cmfgen-workflow-templates.md` in the repository for resolution rules and
which physical inputs must come from the source model.
