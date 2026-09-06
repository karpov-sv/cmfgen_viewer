#!/usr/bin/env python3
"""Import a local BOSZ resampled download into the viewer's CSV/NPZ format.

No network access or resampling. Both columns retain the published Eddington
flux per Angstrom, matching the existing TLUSTY storage convention.
"""

from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

import numpy as np


DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "bosz"
REFERENCE = "https://archive.stsci.edu/hlsp/bosz"
MODEL_RE = re.compile(
    r"bosz(?P<release>\d+)_"
    r"(?P<atmosphere>ap|mp|ms)_t(?P<teff>\d+)_g(?P<logg>[+-]\d+(?:\.\d+)?)_"
    r"m(?P<metallicity>[+-]\d+(?:\.\d+)?)_a(?P<alpha>[+-]\d+(?:\.\d+)?)_"
    r"c(?P<carbon>[+-]\d+(?:\.\d+)?)_v(?P<micro>\d+)_"
    r"r(?P<resolution>\d+)_resam\.txt\.gz"
)


def read_spectrum(path: Path, wavelength: np.ndarray) -> dict[str, np.ndarray]:
    with gzip.open(path, "rt", encoding="ascii") as handle:
        values = np.loadtxt(handle, ndmin=2)
    if values.shape != (len(wavelength), 2):
        raise ValueError(f"{path.name}: expected {len(wavelength)} rows and two columns")
    if not np.isfinite(values).all():
        raise ValueError(f"{path.name}: non-finite flux/continuum")
    flux, continuum = values.T
    valid = (continuum > 0) & (flux >= 0)
    if np.count_nonzero(valid & (flux > 0)) < 2:
        raise ValueError(f"{path.name}: too few usable flux/continuum samples")
    normalized = np.full(len(wavelength), np.nan)
    np.divide(flux, continuum, out=normalized, where=valid)
    arrays = {
        "wavelength_angstrom": wavelength,
        "flux_lambda_cgs": np.where(flux >= 0, flux, np.nan),
        "continuum_lambda_cgs": continuum,
        "normalized_flux_candidate": normalized,
    }
    if (flux < 0).any():
        arrays["raw_flux_lambda_cgs"] = flux.copy()
    return arrays


def import_grid(source: Path, output: Path, *, resolution: int = 2000, workers: int = 4, log=print) -> int:
    """Publish a complete new grid atomically; never overwrite an existing grid."""
    source = source.expanduser().resolve()
    output = output.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}; choose a new output directory")
    if resolution <= 0:
        raise ValueError("Resolution must be positive")
    if not 1 <= workers <= 32:
        raise ValueError("Workers must be between 1 and 32")
    files = []
    for path in sorted(source.rglob(f"bosz*_r{resolution}_resam.txt.gz")):
        match = MODEL_RE.fullmatch(path.name)
        if match is None:
            raise ValueError(f"Unrecognized BOSZ filename: {path.name}")
        if match['release'] != '2024':
            raise ValueError(f"Unsupported BOSZ release: {match['release']}")
        files.append((path, match.groupdict()))
    if not files:
        raise ValueError(f"No BOSZ R={resolution} spectra under {source}")
    names = [path.name for path, _ in files]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate model filenames in source tree")
    wavelength_path = source / f"bosz2024_wave_r{resolution}.txt"
    wavelength = np.loadtxt(wavelength_path)
    if (wavelength.ndim != 1 or len(wavelength) < 2
            or not np.isfinite(wavelength).all() or (wavelength <= 0).any()
            or (np.diff(wavelength) <= 0).any()):
        raise ValueError("Wavelength axis must be a finite, positive, increasing vector")

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-import-", dir=output.parent))
    try:
        (staging / "spectra").mkdir()
        rows = []
        def convert(entry):
            path, params = entry
            arrays = read_spectrum(path, wavelength)
            name = path.name.removesuffix(".txt.gz")
            relative = Path("spectra") / f"{name}.npz"
            np.savez_compressed(staging / relative, **arrays)
            usable = np.isfinite(arrays["normalized_flux_candidate"])
            return {
                "grid": "bosz",
                "model_name": name,
                "teff_k": int(params["teff"]),
                "log_g": float(params["logg"]),
                "vturb_km_s": int(params["micro"]),
                "z_over_zsun": 10 ** float(params["metallicity"]),
                "metallicity_dex": float(params["metallicity"]),
                "alpha_dex": float(params["alpha"]),
                "carbon_dex": float(params["carbon"]),
                "atmosphere_family": params["atmosphere"],
                "resolving_power": resolution,
                "spectrum_relpath": relative.as_posix(),
                "points": len(wavelength),
                "wavelength_min_angstrom": float(wavelength[usable][0]),
                "wavelength_max_angstrom": float(wavelength[usable][-1]),
                "masked_flux_points": int(np.count_nonzero(~np.isfinite(arrays["flux_lambda_cgs"]))),
                "masked_normalized_points": int(np.count_nonzero(~usable)),
                "member_products": ["optical", "uv", "flux"],
                "archive_products": ["optical", "uv", "flux"],
                "available_arrays": list(arrays),
                "flux_convention": "eddington_h_lambda",
                "flux_unit": "erg s-1 cm-2 Angstrom-1",
                "source_relpath": path.relative_to(source).as_posix(),
                "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        # Bound outstanding work and memory, and stop promptly on malformed input.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for start in range(0, len(files), workers):
                for row in pool.map(convert, files[start:start + workers]):
                    rows.append(row)
                    if len(rows) % 250 == 0 or len(rows) == len(files):
                        log(f"Imported {len(rows)}/{len(files)} BOSZ spectra")
        with (staging / "models.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: json.dumps(v) if isinstance(v, list) else v for k, v in row.items()})
        manifest = {
            "schema_version": 1,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_directory": str(source),
            "reference": REFERENCE,
            "source_release": "BOSZ 2024; correction revision not identified by filenames",
            "wavelength_source_sha256": hashlib.sha256(wavelength_path.read_bytes()).hexdigest(),
            "resolving_power": resolution,
            "flux_convention": "eddington_h_lambda",
            "flux_unit": "erg s-1 cm-2 Angstrom-1",
            "surface_flux_factor": float(4 * np.pi),
            "quality_policy": "Negative flux is masked with NaN; originals retained in raw_flux_lambda_cgs. "
                              "Normalization masks non-positive continuum. Coverage excludes invalid edge samples.",
            "total_models": len(rows),
            "models": rows,
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        if output.exists():
            raise FileExistsError(f"Output appeared during import: {output}")
        staging.rename(output)
        return len(rows)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Local BOSZ download with wavelength file and model subdirectories")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--resolution", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=4, help="Parallel conversions (1-32; default: 4)")
    args = parser.parse_args()
    try:
        count = import_grid(
            args.source, args.output_dir, resolution=args.resolution, workers=args.workers,
            log=lambda message: print(message, flush=True),
        )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Import failed: {exc}\n")
    print(f"Wrote {count} models to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
