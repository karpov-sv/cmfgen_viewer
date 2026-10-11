#!/bin/sh
# Run from the prepared lte/ workspace. Installation/data roots are explicit.
set -eu
: "${CMFDIST:?Set CMFDIST to the CMFGEN installation root}"
: "${ATOMIC:?Set ATOMIC to the atomic-data root}"
../batch.sh ass
exec "$CMFDIST/exe/main_lte.exe" > ltebat.log 2>&1
