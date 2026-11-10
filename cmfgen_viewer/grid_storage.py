"""Lossless imported-grid storage, with shared immutable wavelength axes.

Legacy standalone NPZs remain readable. Compact files and their sibling
``_wavelength_<sha256>.npz`` files must be copied together.
"""

from functools import lru_cache
import hashlib
import os
from pathlib import Path
import re
import tempfile
from threading import Lock
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np


PHOENIX_FLUX_FACTOR = 1e-8 / (4 * np.pi)
STORAGE_FORMAT = "shared-wavelength-v1"
_AXIS_LOCK = Lock()


def _axis_key(wavelength):
    return hashlib.sha256(np.asarray(wavelength, dtype="<f8").tobytes()).hexdigest()


def _write_npz(path, arrays):
    with ZipFile(path, "w", ZIP_DEFLATED, compresslevel=1) as target:
        for key, value in arrays.items():
            with target.open(f"{key}.npy", "w") as member:
                np.lib.format.write_array(member, np.asarray(value), allow_pickle=False)


def atomic_npz(path, arrays, *, validate=None):
    """Publish only a complete, optionally verified file; leave old data on failure."""
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".npz", dir=path.parent)
    os.close(fd)
    temporary = Path(temporary)
    try:
        _write_npz(temporary, arrays)
        if validate is not None:
            validate(temporary)
        if path.exists():
            temporary.chmod(path.stat().st_mode & 0o777)
        else:
            temporary.chmod(0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@lru_cache(maxsize=16)
def _cached_axis(path, signature, key):
    # Signature invalidates the cache if a file is replaced or edited.
    with np.load(path, allow_pickle=False) as payload:
        wave = np.asarray(payload["wavelength_angstrom"], dtype=np.float64)
    if (wave.ndim != 1 or len(wave) < 2 or not np.isfinite(wave).all()
            or (wave <= 0).any() or (np.diff(wave) <= 0).any()
            or _axis_key(wave) != key):
        raise ValueError("Invalid shared wavelength axis")
    wave.setflags(write=False)
    return wave


def _shared_axis(directory, key):
    if not re.fullmatch(r"[0-9a-f]{64}", key):
        raise ValueError("Invalid shared wavelength key")
    path = directory / f"_wavelength_{key}.npz"
    if path.resolve().parent != directory.resolve():
        raise ValueError("Shared wavelength must remain beside its spectrum")
    stat = path.stat()
    return _cached_axis(str(path.resolve()), (stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns), key)


def load_spectrum(path, *, keys=None):
    """Return logical arrays with the same numerical values as legacy caches.

    ``keys`` avoids decompressing unused legacy arrays. Compact BOSZ normalization
    uses the original importer mask, including non-positive continuum samples.
    """
    path = Path(path)
    with np.load(path, allow_pickle=False) as payload:
        compact = "storage_format" in payload
        if compact and str(payload["storage_format"].item()) != STORAGE_FORMAT:
            raise ValueError("Unknown spectrum storage format")
        metadata = {"storage_format", "storage_grid", "wavelength_key", "source_flux", "flux_scale"}
        arrays = {key: payload[key] for key in payload.files
                  if key not in metadata and (keys is None or key in keys)}
        if compact:
            grid = str(payload["storage_grid"].item())
            if grid not in {"bosz", "phoenix"}:
                raise ValueError("Unknown compact grid")
            arrays["wavelength_angstrom"] = _shared_axis(path.parent, str(payload["wavelength_key"].item()))
            if "source_flux" in payload:
                scale = np.asarray(payload["flux_scale"], dtype=np.float64).item()
                if grid != "phoenix" or scale != PHOENIX_FLUX_FACTOR:
                    raise ValueError("Invalid PHOENIX flux scale")
                arrays["flux_lambda_cgs"] = np.asarray(payload["source_flux"], dtype=np.float64) * scale
            if grid == "bosz" and (keys is None or "normalized_flux_candidate" in keys):
                flux = np.asarray(arrays["flux_lambda_cgs"] if "flux_lambda_cgs" in arrays
                                  else payload["flux_lambda_cgs"], dtype=np.float64)
                continuum = np.asarray(arrays["continuum_lambda_cgs"] if "continuum_lambda_cgs" in arrays
                                       else payload["continuum_lambda_cgs"], dtype=np.float64)
                normalized = np.full(flux.shape, np.nan)
                np.divide(flux, continuum, out=normalized, where=(continuum > 0) & (flux >= 0))
                arrays["normalized_flux_candidate"] = normalized
            wave = arrays["wavelength_angstrom"]
            if any(np.asarray(value).shape != wave.shape for value in arrays.values()):
                raise ValueError("Spectrum and shared wavelength shapes differ")
    return arrays


def write_compact_spectrum(path, arrays, grid):
    """Encode losslessly and verify every logical array before atomic replacement.

    PHOENIX float32 encoding is accepted only when scaling it restores the exact
    existing float64 flux. Other inputs retain their original scaled precision.
    """
    path = Path(path)
    if grid not in {"bosz", "phoenix"}:
        raise ValueError("Unsupported compact grid")
    wavelength = np.asarray(arrays["wavelength_angstrom"], dtype=np.float64)
    key = _axis_key(wavelength)
    with _AXIS_LOCK:
        axis_path = path.parent / f"_wavelength_{key}.npz"
        if not axis_path.exists():
            atomic_npz(axis_path, {"wavelength_angstrom": wavelength})
        if not np.array_equal(_shared_axis(path.parent, key), wavelength):
            raise ValueError("Shared wavelength differs from original")
    stored = {k: v for k, v in arrays.items() if k != "wavelength_angstrom"}
    stored.update(storage_format=np.array(STORAGE_FORMAT), storage_grid=np.array(grid), wavelength_key=np.array(key))
    if grid == "bosz":
        stored.pop("normalized_flux_candidate", None)
    else:
        flux = np.asarray(arrays["flux_lambda_cgs"], dtype=np.float64)
        with np.errstate(over="ignore", invalid="ignore"):
            source = (flux / PHOENIX_FLUX_FACTOR).astype(np.float32)
        if np.array_equal(source.astype(np.float64) * PHOENIX_FLUX_FACTOR, flux, equal_nan=True):
            stored.pop("flux_lambda_cgs")
            stored.update(source_flux=source, flux_scale=np.array(PHOENIX_FLUX_FACTOR, dtype=np.float64))

    def validate(temporary):
        restored = load_spectrum(temporary)
        if set(restored) != set(arrays) or any(
            not np.array_equal(restored[key], value, equal_nan=True) for key, value in arrays.items()
        ):
            raise ValueError(f"Lossless verification failed: {path}")

    atomic_npz(path, stored, validate=validate)
