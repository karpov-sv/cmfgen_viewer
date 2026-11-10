#!/usr/bin/env python3
"""Remove unused TLUSTY cache arrays without changing any fitting samples."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import json
import os
from pathlib import Path
import tempfile

import numpy as np


FIT_ARRAYS = (
    "wavelength_angstrom", "flux_lambda_cgs", "continuum_lambda_cgs",
    "normalized_flux_candidate",
)
SOURCE_METADATA = ("input_columns", "x_axis_kind", "x_unit_guess")
RESOLUTION_METADATA = (
    "resolving_power", "samples_per_resolution", "sed_binning_power",
    "sed_binning_method", "sed_rebin_applied",
)
DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "data" / "tlusty"


def compact_spectrum(root: Path, row: dict) -> tuple[int, int, list[str]]:
    path = (root / row["spectrum_relpath"]).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Spectrum path escapes grid root: {path}")
    before = path.stat().st_size
    with np.load(path, allow_pickle=False) as source:
        arrays = {key: source[key] for key in FIT_ARRAYS if key in source}
        if not {"wavelength_angstrom", "flux_lambda_cgs"} <= arrays.keys():
            raise ValueError(f"Missing required fitting arrays: {path}")
        for key in SOURCE_METADATA:
            value = int(row[key]) if key == "input_columns" else str(row[key])
            arrays[key] = np.asarray(value)
        for key in RESOLUTION_METADATA:
            if key in source:
                arrays[key] = source[key]
        if set(source.files) == set(arrays):
            return before, before, sorted(arrays)

    # Keep the old file available to readers until its verified replacement is ready.
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".npz", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            np.savez_compressed(handle, **arrays)
        with np.load(temporary, allow_pickle=False) as check:
            for key, original in arrays.items():
                saved = check[key]
                equal = (np.array_equal(original, saved, equal_nan=True)
                         if original.dtype.kind in "fc" else np.array_equal(original, saved))
                if original.dtype != saved.dtype or not equal:
                    raise ValueError(f"Verification failed for {path}: {key}")
        os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return before, path.stat().st_size, sorted(arrays)


def _replace_text(path: Path, write) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            write(handle)
        os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def compact_grid(root: Path, *, workers: int = 4, log=print) -> tuple[int, int]:
    root = root.resolve()
    with (root / "models.csv").open(newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    # Load metadata before modifying spectra. Interrupted runs can safely be rerun:
    # old readers ignore removed arrays, and fitting arrays are always preserved.
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    before = after = 0
    available = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, (row, result) in enumerate(zip(rows, pool.map(lambda row: compact_spectrum(root, row), rows)), 1):
            old_size, new_size, keys = result
            before += old_size
            after += new_size
            row["available_arrays"] = json.dumps(keys, separators=(",", ":"))
            available[row["spectrum_relpath"]] = keys
            if index % 250 == 0 or index == len(rows):
                log(f"{index}/{len(rows)} spectra; saved {(before - after) / 1024**3:.2f} GiB", flush=True)

    for row in manifest["models"]:
        row["available_arrays"] = available[row["spectrum_relpath"]]
    manifest.setdefault("format", {})["optional_arrays"] = list(FIT_ARRAYS[2:] + SOURCE_METADATA + RESOLUTION_METADATA)
    manifest["format"]["storage"] = "Stored fitting arrays preserved exactly; unused source arrays omitted"

    def write_csv(handle):
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    _replace_text(root / "models.csv", write_csv)
    _replace_text(manifest_path, lambda handle: json.dump(manifest, handle, indent=2))
    log(f"Total: {before / 1024**3:.2f} -> {after / 1024**3:.2f} GiB", flush=True)
    return before, after


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    compact_grid(args.root, workers=args.workers)
