#!/usr/bin/env python3
"""Zero-iteration tests in fresh copies of the earlier Bstar3000 fixtures.

Requires NumPy, prepared templates with atomic-data links, and the reference
.npy arrays from the Bstar reconstruction investigation. No user model or
installed executable is modified. The native checkpoint layout defaults to
this installation's REAL(8), 16376-byte records.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import numpy as np


def override(text, key, value):
    pattern = re.compile(r"^([^!\n]*?)\[" + re.escape(key) + r"\]", re.MULTILINE)
    if len(pattern.findall(text)) != 1:
        raise ValueError(f"Expected exactly one [{key}]")
    return pattern.sub(lambda match: f"{value} [{key}]", text)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--cmfgen-root", type=Path, required=True)
parser.add_argument("--atomic-data", type=Path, required=True)
parser.add_argument("--same-grid-template", type=Path, required=True)
parser.add_argument("--refined-template", type=Path, required=True)
parser.add_argument("--reference-pops", type=Path, required=True)
parser.add_argument("--refined-reference", type=Path, required=True)
parser.add_argument("--record-bytes", type=int, default=16376)
args = parser.parse_args()
root = args.cmfgen_root.expanduser().resolve()
atomic = args.atomic_data.expanduser().resolve()
base = args.same_grid_template.expanduser().resolve()
refined = args.refined_template.expanduser().resolve()
reference = np.load(args.reference_pops)
refined_reference = np.load(args.refined_reference)
work = Path(tempfile.mkdtemp(prefix="cmfgen-bstar-init-checks-"))
results = {}
for name, template, method, expected in [
    ("same-grid-R", base, "R", reference),
    ("same-grid-POP", base, "POP", reference),
    ("refined-POP", refined, "POP", refined_reference),
]:
    case = work / name
    case.mkdir()
    for filename in ("VADAT", "MODEL_SPEC", "IN_ITS", "RVSIG_COL", "HYDRO_DEFAULTS", "MODEL"):
        shutil.copyfile(template / filename, case / filename)
    # All three cases use the same saved estimates; only the target grid differs.
    for source in base.glob("*_IN"):
        if source.name != "T_IN" and not source.name.startswith("."):
            shutil.copyfile(source, case / source.name)
    for source in template.iterdir():
        if source.is_symlink() and source.name != "T_IN" and source.resolve().is_relative_to(atomic):
            (case / source.name).symlink_to(source.resolve())
    (case / "T_IN").symlink_to("He2_IN")
    vadat = override((case / "VADAT").read_text(), "DC_METH", method)
    # Deliberately use the rounded RMAX that previously replaced depth-1 T.
    (case / "VADAT").write_text(override(vadat, "RMAX", "109.68209305"))
    (case / "IN_ITS").write_text(override((case / "IN_ITS").read_text(), "NUM_ITS", "0"))
    with (case / "native.log").open("w") as output:
        subprocess.run([str(root / "exe/cmfgen_dev.exe")], cwd=case, stdin=subprocess.DEVNULL,
                       stdout=output, stderr=subprocess.STDOUT, check=True, timeout=120,
                       env=dict(os.environ, OMP_NUM_THREADS="1"))
    with (case / "SCRTEMP").open("rb") as checkpoint:
        checkpoint.seek(3 * args.record_bytes)
        values = np.frombuffer(checkpoint.read(expected.size * 8), dtype="<f8").reshape(expected.shape)
    if not np.isfinite(values).all() or not (values > 0).all():
        raise AssertionError(f"{name}: invalid population vector")
    error = np.abs(values / expected - 1)
    if error[:, :-2].max() >= 1e-4 or error[:, -1].max() >= 1e-6:
        raise AssertionError(f"{name}: reconstruction exceeded tolerance: {error.max()}")
    np.save(case / "populations.npy", values)
    results[name] = {"maximum_population_relative_error": float(error[:, :-2].max()),
                     "maximum_temperature_relative_error": float(error[:, -1].max()),
                     "outer_temperature_K": float(values[0, -1] * 1e4)}
    print(name, results[name], flush=True)
(work / "results.json").write_text(json.dumps(results, indent=2) + "\n")
print("Artifacts:", work)
