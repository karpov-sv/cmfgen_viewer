#!/usr/bin/env python3
"""Losslessly compact existing BOSZ/PHOENIX caches in place; safe to resume.

Each spectrum is compared against the reconstructed file before replacement.
Legacy and compact files can coexist during migration. Index and quality
metadata are retained; raw downloads are never touched.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cmfgen_viewer.grid_storage import STORAGE_FORMAT, load_spectrum, write_compact_spectrum


def compact_grid(root, *, workers=4, log=print):
    root = Path(root).resolve()
    if not 1 <= workers <= 32:
        raise ValueError("Workers must be between 1 and 32")
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    rows = manifest["models"]
    if not rows:
        raise ValueError("Empty grid")
    grids = {row["grid"] for row in rows}
    if len(grids) != 1 or not grids <= {"bosz", "phoenix"}:
        raise ValueError("Expected a BOSZ or PHOENIX grid")
    grid = grids.pop()
    paths = [(root / row["spectrum_relpath"]).resolve() for row in rows]
    if len(set(paths)) != len(paths) or any(path.parent != root / "spectra" for path in paths):
        raise ValueError("Duplicate or unsafe spectrum paths")
    before = sum(path.stat().st_size for path in (root / "spectra").glob("*.npz"))
    started = time.monotonic()

    def convert(path):
        # Re-running verifies compact inputs too. Logical arrays include raw
        # negative BOSZ flux, so its archival copy is checked as well.
        arrays = load_spectrum(path)
        write_compact_spectrum(path, arrays, grid)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for start in range(0, len(paths), workers):
            list(pool.map(convert, paths[start:start + workers]))
            done = min(start + workers, len(paths))
            if done % 100 == 0 or done == len(paths):
                log(f"{grid}: verified and compacted {done}/{len(paths)} spectra", flush=True)
    # models.csv and every per-model field remain byte-for-byte unchanged.
    manifest["spectrum_storage"] = STORAGE_FORMAT
    fd, temporary = tempfile.mkstemp(prefix=".manifest-", dir=root)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
        os.chmod(temporary, manifest_path.stat().st_mode & 0o777)
        os.replace(temporary, manifest_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    after = sum(path.stat().st_size for path in (root / "spectra").glob("*.npz"))
    return dict(grid=grid, models=len(paths), before_bytes=before, after_bytes=after,
                saved_fraction=1 - after / before, seconds=time.monotonic() - started,
                verification="Every logical array compared exactly, including NaNs, before replacement")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("grids", nargs="+", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    reports = [compact_grid(root, workers=args.workers) for root in args.grids]
    result = json.dumps(reports, indent=2) + "\n"
    if args.report:
        args.report.write_text(result)
    print(result)


if __name__ == "__main__":
    main()
