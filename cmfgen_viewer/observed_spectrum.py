from __future__ import annotations

from functools import lru_cache
import json
import math
from pathlib import Path
import re
import secrets
import shutil
import time
from typing import Any

from .parsers.common import parse_float_token

try:
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover - runtime dependency
    np = None  # type: ignore[assignment]

try:
    from astropy.io import fits
except ModuleNotFoundError:  # pragma: no cover - runtime dependency
    fits = None  # type: ignore[assignment]


SUPPORTED_FITS_SUFFIXES = {".fits", ".fit", ".fts"}
UPLOAD_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
DEFAULT_UPLOAD_TTL_SECONDS = 2 * 24 * 60 * 60


def generate_upload_token() -> str:
    return secrets.token_urlsafe(18)


def is_valid_upload_token(token: str) -> bool:
    return bool(UPLOAD_TOKEN_RE.match(token))


def cleanup_upload_root(upload_root: Path, *, ttl_seconds: int = DEFAULT_UPLOAD_TTL_SECONDS) -> None:
    upload_root.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for entry in upload_root.iterdir():
        if not entry.is_dir():
            continue
        try:
            meta = read_upload_manifest(upload_root, entry.name)
            created = float(meta.get("created_at", 0.0)) if meta else 0.0
        except (OSError, ValueError, TypeError):
            created = 0.0
        if created <= 0:
            created = entry.stat().st_mtime
        if now - created > ttl_seconds:
            shutil.rmtree(entry, ignore_errors=True)


def write_upload_manifest(upload_root: Path, token: str, payload: dict[str, Any]) -> None:
    if not is_valid_upload_token(token):
        raise ValueError("Invalid upload token.")
    target_dir = upload_root / token
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = target_dir / "meta.json"
    manifest_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def read_upload_manifest(upload_root: Path, token: str) -> dict[str, Any] | None:
    if not is_valid_upload_token(token):
        return None
    manifest_path = upload_root / token / "meta.json"
    if not manifest_path.is_file():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def remove_upload_bundle(upload_root: Path, token: str) -> None:
    if not is_valid_upload_token(token):
        return
    shutil.rmtree(upload_root / token, ignore_errors=True)


def list_upload_manifests(upload_root: Path) -> list[dict[str, Any]]:
    upload_root.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for entry in upload_root.iterdir():
        if not entry.is_dir():
            continue
        token = entry.name
        if not is_valid_upload_token(token):
            continue
        meta = read_upload_manifest(upload_root, token)
        if meta is None:
            continue
        stored_name = str(meta.get("stored_name", ""))
        source_path = upload_root / token / stored_name if stored_name else None
        exists = bool(source_path and source_path.is_file())
        size = int(source_path.stat().st_size) if exists and source_path is not None else 0
        created_default = entry.stat().st_mtime
        try:
            created_at = float(meta.get("created_at", created_default))
        except (TypeError, ValueError):
            created_at = created_default

        item = dict(meta)
        item["token"] = token
        item["exists"] = exists
        item["size"] = size
        item["created_at"] = created_at
        items.append(item)

    items.sort(key=lambda item: float(item.get("created_at", 0.0)), reverse=True)
    return items


def parse_uploaded_spectrum(path: Path, *, flux_mode: str = "auto") -> dict[str, Any]:
    mode = flux_mode.strip().lower()
    if mode not in {"auto", "normalized", "absolute"}:
        raise ValueError(f"Unsupported flux mode: {flux_mode}")

    stat = path.stat()
    return _parse_uploaded_spectrum_cached(str(path.resolve()), stat.st_mtime_ns, stat.st_size, mode)


@lru_cache(maxsize=32)
def _parse_uploaded_spectrum_cached(path_str: str, mtime_ns: int, size: int, flux_mode: str) -> dict[str, Any]:
    del mtime_ns, size
    path = Path(path_str)
    suffix = path.suffix.lower()

    if suffix in SUPPORTED_FITS_SUFFIXES:
        return _parse_uploaded_fits(path, flux_mode=flux_mode)

    raise ValueError(f"Unsupported uploaded spectrum format: {path.suffix or path.name}")


def _parse_uploaded_fits(path: Path, *, flux_mode: str) -> dict[str, Any]:
    if fits is None or np is None:
        raise ValueError("FITS parsing requires astropy and numpy.")

    warnings: list[str] = []
    with fits.open(path, memmap=False) as hdul:
        hdu = _first_hdu_with_data(hdul)
        if hdu is None:
            raise ValueError("FITS file has no data HDU.")

        header = hdu.header
        data = hdu.data
        if data is None:
            raise ValueError("FITS file has an empty data block.")

        wavelength, flux, format_name, parser_warnings = _extract_wave_flux_from_fits_data(data, header)
        warnings.extend(parser_warnings)

    if np is None:
        raise ValueError("numpy is not available.")

    wavelength_arr = np.asarray(wavelength, dtype=np.float64).reshape(-1)
    flux_arr = np.asarray(flux, dtype=np.float64).reshape(-1)
    if wavelength_arr.size != flux_arr.size or wavelength_arr.size < 2:
        raise ValueError("Uploaded spectrum does not contain matching wavelength/flux vectors.")

    raw_points = int(min(wavelength_arr.size, flux_arr.size))
    valid_mask = np.isfinite(wavelength_arr) & np.isfinite(flux_arr) & (wavelength_arr > 0)
    skipped_points = int(raw_points - int(valid_mask.sum()))
    wavelength_arr = wavelength_arr[valid_mask]
    flux_arr = flux_arr[valid_mask]
    if wavelength_arr.size < 2:
        raise ValueError("Uploaded spectrum has too few finite samples after filtering.")

    if wavelength_arr[0] > wavelength_arr[-1]:
        order = np.argsort(wavelength_arr)
        wavelength_arr = wavelength_arr[order]
        flux_arr = flux_arr[order]

    detected_mode = _detect_flux_mode(flux_arr.tolist())
    resolved_mode = detected_mode if flux_mode == "auto" else flux_mode
    if flux_mode != "auto" and flux_mode != detected_mode:
        warnings.append(f"Requested flux mode '{flux_mode}' overrides detected mode '{detected_mode}'.")

    return {
        "name": path.name,
        "format": format_name,
        "wavelength": wavelength_arr.tolist(),
        "flux": flux_arr.tolist(),
        "flux_mode": resolved_mode,
        "detected_flux_mode": detected_mode,
        "raw_points": raw_points,
        "skipped_points": skipped_points,
        "warnings": warnings,
    }


def _first_hdu_with_data(hdul) -> Any | None:
    for hdu in hdul:
        if getattr(hdu, "data", None) is not None:
            return hdu
    return None


def _extract_wave_flux_from_fits_data(data: Any, header: Any) -> tuple[Any, Any, str, list[str]]:
    if np is None:
        raise ValueError("numpy is not available.")

    warnings: list[str] = []
    array = np.asarray(data)

    if array.dtype.names:
        wave, flux, table_warnings = _extract_from_structured_table(array, header)
        warnings.extend(table_warnings)
        return wave, flux, "fits-table", warnings

    if array.ndim == 1:
        flux = array.astype(np.float64, copy=False)
        wavelength = _header_wavelength_axis(header, flux.size)
        return wavelength, flux, "fits-1d-primary", warnings

    if array.ndim == 2 and 1 in array.shape:
        flux = array.reshape(-1).astype(np.float64, copy=False)
        wavelength = _header_wavelength_axis(header, flux.size)
        warnings.append("Flattened 2D FITS data with singleton axis into a 1D spectrum.")
        return wavelength, flux, "fits-2d-singleton", warnings

    if array.ndim == 2 and array.shape[1] >= 2:
        wave = array[:, 0].astype(np.float64, copy=False)
        flux = array[:, 1].astype(np.float64, copy=False)
        warnings.append("Using first two columns of 2D FITS data as wavelength and flux.")
        return wave, flux, "fits-2d-columns", warnings

    if array.ndim == 2 and array.shape[0] >= 2:
        wave = array[0, :].astype(np.float64, copy=False)
        flux = array[1, :].astype(np.float64, copy=False)
        warnings.append("Using first two rows of 2D FITS data as wavelength and flux.")
        return wave, flux, "fits-2d-rows", warnings

    raise ValueError(f"Unsupported FITS data shape: {array.shape!r}")


def _extract_from_structured_table(array, header: Any) -> tuple[Any, Any, list[str]]:
    if np is None:
        raise ValueError("numpy is not available.")

    warnings: list[str] = []
    names = list(array.dtype.names or [])
    lowered = {name.lower(): name for name in names}

    wave_col = _pick_column(lowered, ("wavelength", "lambda", "lam", "wave", "wl", "angstrom", "ang"))
    flux_col = _pick_column(lowered, ("flux", "flx", "f_lambda", "flambda", "spec", "spectrum", "norm", "normalized"))

    if wave_col and flux_col and wave_col != flux_col:
        return (
            np.asarray(array[wave_col], dtype=np.float64),
            np.asarray(array[flux_col], dtype=np.float64),
            warnings,
        )

    numeric_names: list[str] = []
    for name in names:
        values = np.asarray(array[name])
        if values.ndim != 1:
            continue
        if np.issubdtype(values.dtype, np.number):
            numeric_names.append(name)

    if len(numeric_names) >= 2:
        warnings.append("No explicit wavelength/flux column names found; using first two numeric columns.")
        return (
            np.asarray(array[numeric_names[0]], dtype=np.float64),
            np.asarray(array[numeric_names[1]], dtype=np.float64),
            warnings,
        )

    if len(numeric_names) == 1:
        flux = np.asarray(array[numeric_names[0]], dtype=np.float64)
        wavelength = _header_wavelength_axis(header, flux.size)
        warnings.append("Using single numeric table column as flux and deriving wavelength from FITS WCS.")
        return wavelength, flux, warnings

    raise ValueError("FITS table has no usable numeric columns.")


def _pick_column(lowered: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    for name_lower, original in lowered.items():
        for candidate in candidates:
            if candidate in name_lower:
                return original
    return None


def _header_wavelength_axis(header: Any, count: int):
    if np is None:
        raise ValueError("numpy is not available.")

    crval = _header_float(header, ("CRVAL1",))
    cdelt = _header_float(header, ("CDELT1", "CD1_1"))
    crpix = _header_float(header, ("CRPIX1",), default=1.0)
    if crval is None or cdelt is None or crpix is None:
        raise ValueError("FITS header must define CRVAL1 and CDELT1 (or CD1_1) for 1D flux-only data.")

    pixel_index = np.arange(count, dtype=np.float64) + 1.0
    return (pixel_index - crpix) * cdelt + crval


def _header_float(header: Any, keys: tuple[str, ...], default: float | None = None) -> float | None:
    for key in keys:
        if key not in header:
            continue
        value = parse_float_token(str(header[key]))
        if value is None:
            continue
        numeric = float(value)
        if math.isfinite(numeric):
            return numeric
    return default


def _detect_flux_mode(flux: list[float]) -> str:
    if np is None:
        return "absolute"

    values = np.asarray(flux, dtype=np.float64)
    if values.size < 16:
        return "absolute"

    finite = values[np.isfinite(values)]
    if finite.size < 16:
        return "absolute"

    p10, median, p90 = np.percentile(finite, [10, 50, 90])
    if 0.2 <= median <= 2.5 and p10 > -1.0 and p90 < 3.5:
        return "normalized"
    return "absolute"
