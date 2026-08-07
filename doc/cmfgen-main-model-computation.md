# Main Model Computation

Main CMFGEN computation is intentionally separate from LTE/hydro structure preparation. Open **Main Computation** from a model's workflow actions, or continue there from the final LTE/hydro handoff guard.

The viewer never starts or supervises CMFGEN. It checks the model inputs and displays the exact terminal command:

```bash
cd /absolute/path/to/model && ./batch.sh
```

The initial guard checks for `batch.sh`, `VADAT`, `MODEL_SPEC`, `IN_ITS`, and either `GAMMAS_IN` or `GAMMAS`. LTE/hydro-derived models are handed off only after `RVSIG_COL` and `ROSSELAND_LTE_TAB` have been promoted to the model root.

After an external run, the workflow links to available `MOD_SUM`, `OUTGEN`, `batch.log`, `MODEL`, and `RVTJ` files. `MOD_SUM` is current only when it is newer than the relevant model inputs and no newer modified-input marker exists.
