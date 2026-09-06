#!/usr/bin/env python3
"""Import local PHOENIX-ACES R10000FITS ZIPs into the shared CSV/NPZ format.

This is a product-specific reader, not a generic FITS WCS interpretation.
The published vacuum wavelength convention overrides the misleading AWAV-LOG
header in these archives; CRVAL1 and CDELT1 describe natural log Angstroms.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

from astropy.io import fits
import numpy as np


DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "phoenix"
REFERENCE = "https://arxiv.org/abs/1303.5632"
PRODUCT = "PHOENIX-ACES-AGSS-COND-2011"
MODEL_RE = re.compile(
    r"lte(?P<teff>\d{5})-(?P<logg>\d\.\d{2})(?P<metal>[+-]\d\.\d)"
    r"\.PHOENIX-ACES-AGSS-COND-2011-HiRes\.fits"
)
FLUX_FACTOR = 1e-8 / (4 * np.pi)


def read_spectrum(payload: bytes, name: str) -> tuple[dict, dict]:
    """Validate the known product, retaining negative samples for inspection."""
    match = MODEL_RE.fullmatch(name)
    if match is None:
        raise ValueError(f"Unrecognized PHOENIX member: {name}")
    with fits.open(BytesIO(payload), memmap=False) as hdus:
        if len(hdus) != 1 or hdus[0].data is None:
            raise ValueError(f"{name}: expected a single primary spectrum")
        header = hdus[0].header
        flux = np.asarray(hdus[0].data, dtype=np.float64)
        if flux.ndim != 1 or len(flux) < 2 or not np.isfinite(flux).all() or not (flux > 0).any():
            raise ValueError(f"{name}: invalid flux vector")
        if header.get("CTYPE1") not in {"AWAV-LOG", "WAVE-LOG"}:
            raise ValueError(f"{name}: unsupported wavelength convention")
        start = float(header["CRVAL1"])
        step = float(header["CDELT1"])
        pixel = float(header.get("CRPIX1", 1))
        if not np.isfinite([start, step, pixel]).all() or not np.isclose(step, 1e-5, rtol=1e-7, atol=0):
            raise ValueError(f"{name}: expected R10000 natural-log sampling of 1e-5")
        wavelength = np.exp(start + (np.arange(len(flux)) + 1 - pixel) * step)
        if not np.isfinite(wavelength).all() or wavelength[0] < 2999 or wavelength[-1] > 25001:
            raise ValueError(f"{name}: wavelength coverage outside the known R10000 product")
        interpolated = bool(header.get("INTERPOL", False))
        unit = str(header.get("BUNIT", "")).strip()
        inferred_unit = not unit and interpolated
        if unit != "erg/s/cm^2/cm" and not inferred_unit:
            raise ValueError(f"{name}: unsupported or missing BUNIT: {unit!r}")
        teff, logg, metal, alpha = (float(header[k]) for k in ("PHXTEFF", "PHXLOGG", "PHXM_H", "PHXALPHA"))
        if (not np.isfinite([teff, logg, metal, alpha]).all()
                or not np.allclose([teff, logg, metal], [float(match[k]) for k in ("teff", "logg", "metal")])
                or alpha != 0):
            raise ValueError(f"{name}: inconsistent or unsupported model parameters")
        micro = header.get("PHXXI_L")
        if micro is not None and (not np.isfinite(float(micro)) or float(micro) < 0):
            raise ValueError(f"{name}: invalid microturbulence")
        negative = int(np.count_nonzero(flux < 0))
        arrays = {"wavelength_angstrom": wavelength, "flux_lambda_cgs": flux * FLUX_FACTOR}
        metadata = {
            "grid": "phoenix", "model_name": name.removesuffix(".fits"),
            "teff_k": int(teff), "log_g": logg, "z_over_zsun": 10 ** metal,
            "metallicity_dex": metal, "alpha_dex": alpha,
            # PHXXI_L is a derived property, not an independently sampled fit axis.
            "derived_vturb_km_s": float(micro) if micro is not None else None,
            "atmosphere_family": "phoenix_aces", "resolving_power": 10000,
            "points": len(flux), "wavelength_min_angstrom": float(wavelength[0]),
            "wavelength_max_angstrom": float(wavelength[-1]),
            "wavelength_convention": "vacuum", "source_ctype1": header["CTYPE1"],
            "interpolated": interpolated, "source_unit_inferred": inferred_unit,
            "negative_flux_points": negative, "fit_eligible": negative == 0,
            "quality_flag": "negative_flux" if negative else "ok",
            "available_arrays": list(arrays), "member_products": ["flux"],
            "archive_products": ["flux"], "flux_convention": "eddington_h_lambda",
            "flux_unit": "erg s-1 cm-2 Angstrom-1",
        }
    return arrays, metadata


def import_grid(source: Path, output: Path, *, workers: int = 4, log=print) -> int:
    """Atomically publish a new grid without extracting or modifying source ZIPs."""
    source, output = source.expanduser().resolve(), output.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}; choose a new output directory")
    if not 1 <= workers <= 32:
        raise ValueError("Workers must be between 1 and 32")
    archives = sorted(source.glob(f"{PRODUCT}_R10000FITS_Z*.zip"))
    if not archives:
        raise ValueError(f"No PHOENIX R10000FITS ZIP archives under {source}")
    names = set()
    for archive in archives:
        with ZipFile(archive) as handle:
            for name in handle.namelist():
                if not MODEL_RE.fullmatch(name):
                    raise ValueError(f"Unrecognized or unsafe PHOENIX member: {name}")
                if name in names:
                    raise ValueError(f"Duplicate model: {name}")
                names.add(name)
    if not names:
        raise ValueError("Archives contain no spectra")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-import-", dir=output.parent))
    try:
        (staging / "spectra").mkdir()

        def convert_archive(archive):
            rows = []
            checksum = hashlib.sha256()
            with archive.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    checksum.update(chunk)
            digest = checksum.hexdigest()
            with ZipFile(archive) as handle:
                for name in handle.namelist():
                    payload = handle.read(name)
                    arrays, row = read_spectrum(payload, name)
                    relative = f"spectra/{row['model_name']}.npz"
                    # Standard NPZ, with fast compression for the large native vectors.
                    with ZipFile(staging / relative, "w", ZIP_DEFLATED, compresslevel=1) as target:
                        for key, array in arrays.items():
                            with target.open(f"{key}.npy", "w") as member:
                                np.lib.format.write_array(member, array, allow_pickle=False)
                    row.update(spectrum_relpath=relative, source_archive=archive.name,
                               source_member=name, source_sha256=hashlib.sha256(payload).hexdigest())
                    rows.append(row)
                    if len(rows) % 250 == 0:
                        log(f"{archive.name}: imported {len(rows)} spectra")
            log(f"{archive.name}: completed {len(rows)} spectra")
            return rows, {"filename": archive.name, "sha256": digest}

        rows, archive_metadata = [], []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for converted, metadata in pool.map(convert_archive, archives):
                rows.extend(converted)
                archive_metadata.append(metadata)
        rows.sort(key=lambda row: row["model_name"])
        with (staging / "models.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: json.dumps(v) if isinstance(v, (list, bool)) else v for k, v in row.items()})
        manifest = {
            "schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_directory": str(source), "reference": REFERENCE,
            "source_release": PRODUCT, "archives": archive_metadata,
            "resolving_power": 10000, "wavelength_convention": "vacuum",
            "wavelength_policy": "exp(CRVAL1 + (pixel - CRPIX1)*CDELT1); published vacuum convention "
                                 "overrides misleading AWAV-LOG header (Husser et al. 2013). No resampling.",
            "source_flux_unit": "erg/s/cm^2/cm", "source_flux_convention": "surface_f_lambda",
            "flux_conversion_factor": FLUX_FACTOR, "flux_convention": "eddington_h_lambda",
            "flux_unit": "erg s-1 cm-2 Angstrom-1", "surface_flux_factor": float(4 * np.pi),
            "quality_policy": "Retain negative samples but exclude entire affected models from fitting; "
                              "do not interpolate across corrupt interior intervals. INTERPOL models remain "
                              "eligible; missing units use the published product convention and are flagged.",
            "supported_modes": ["both"], "total_models": len(rows),
            "fit_eligible_models": sum(row["fit_eligible"] for row in rows), "models": rows,
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
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    try:
        count = import_grid(args.source, args.output_dir, workers=args.workers,
                            log=lambda message: print(message, flush=True))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Import failed: {exc}\n")
    print(f"Wrote {count} models to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
