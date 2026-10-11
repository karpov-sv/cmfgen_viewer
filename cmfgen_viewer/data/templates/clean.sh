#!/bin/sh
# Conservative top-level scratch cleanup. Checkpoints and products are retained.
# The Python runner's cleanup stage additionally archives files for recovery.
set -eu
rm -f -- BAION BAMAT BAIONPNT BAMATPNT BA_STEQ BA_ASCI_N_D* \
  JEW EWDATA STEQ_VALS LINEHEAT NETRATE TOTRATE TRANS_INFO \
  CFDAT_OUT CONT_FREQ *SCRATCH* fort.63 fort.88 fort.53
for entry in ./*; do
  if [ -L "$entry" ]; then
    rm -f -- "$entry"
  fi
done
