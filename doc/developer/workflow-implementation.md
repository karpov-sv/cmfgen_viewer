# Workflow implementation notes

`workflow_plan.py` defines stage contracts independently of Flask routes; `workflow_preflight.py` supplies read-only checks; `model_activity.py` owns cooperative mutation guards. The separate `runner_recipe.py` and `runner.py` implement explicit, reviewed ostar operations, bounded child execution, validation, and per-pass journals. The runner does not execute the viewer's opaque workflow plans. See [Standalone CMFGEN Runner](/documentation/command-line-runner) for its supported subset and limitations. No plan-execution endpoint exists yet.

## Script inspection and snapshots

Workflow previews inspect literal commands and local sourced includes without executing a shell. Control flow, substitutions, glob expansion, arbitrary helper calls, and aliases are not interpreted. Inspection is bounded to 16 included scripts of at most 2 MiB each. A recognized direct `batobs.sh` call in `batch.sh` adds a dependent flux stage marked as already invoked by main, rather than a second launch command.

Plans are GET-only endpoints gated by read-write mode and are not cached. JSON responses use schema version 1. Small input files have SHA-256 snapshots; larger inputs use metadata only. Output freshness remains timestamp-based. Plans do not change external script behavior or provide complete shell translation or immutable provenance.

Writers acquire the model advisory lock without waiting and recheck activity after acquisition. Symlinked or hard-linked lock files are refused. Unsupported locking or unavailable process visibility blocks mutations. External scripts do not share the lock, so it cannot exclude a calculation launched after a writer's activity check.
