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
PHOTOMETRY_SUFFIXES = {".phot"}
PHOTOMETRY_SPLIT_RE = re.compile(r"[,\s;]+")
PHOTOMETRY_TRUE_TOKENS = {"1", "true", "t", "yes", "y", "on", "enable", "enabled"}
PHOTOMETRY_FALSE_TOKENS = {"0", "false", "f", "no", "n", "off", "disable", "disabled"}


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


def remove_all_upload_bundles(upload_root: Path) -> tuple[int, int]:
    """Remove viewer-managed upload bundles, leaving unrelated entries intact."""
    removed = 0
    failed = 0
    for item in list_upload_manifests(upload_root):
        token = str(item.get("token", ""))
        if not is_valid_upload_token(token):
            continue
        bundle_path = upload_root / token
        remove_upload_bundle(upload_root, token)
        if bundle_path.exists():
            failed += 1
        else:
            removed += 1
    return removed, failed


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


def parse_uploaded_spectrum(
    path: Path,
    *,
    flux_mode: str = "auto",
    lambda_min: float | None = None,
    lambda_max: float | None = None,
) -> dict[str, Any]:
    mode = flux_mode.strip().lower()
    if mode not in {"auto", "normalized", "absolute"}:
        raise ValueError(f"Unsupported flux mode: {flux_mode}")
    bound_min, bound_max = _normalize_wavelength_bounds(lambda_min, lambda_max)

    stat = path.stat()
    return _parse_uploaded_spectrum_cached(
        str(path.resolve()),
        stat.st_mtime_ns,
        stat.st_size,
        mode,
        bound_min,
        bound_max,
    )


@lru_cache(maxsize=32)
def _parse_uploaded_spectrum_cached(
    path_str: str,
    mtime_ns: int,
    size: int,
    flux_mode: str,
    lambda_min: float | None,
    lambda_max: float | None,
) -> dict[str, Any]:
    del mtime_ns, size
    path = Path(path_str)
    suffix = path.suffix.lower()

    if suffix in PHOTOMETRY_SUFFIXES:
        return _parse_uploaded_photometry(path, flux_mode=flux_mode, lambda_min=lambda_min, lambda_max=lambda_max)
    if suffix in SUPPORTED_FITS_SUFFIXES:
        return _parse_uploaded_fits(path, flux_mode=flux_mode, lambda_min=lambda_min, lambda_max=lambda_max)

    raise ValueError(f"Unsupported uploaded spectrum format: {path.suffix or path.name}")


def _parse_uploaded_fits(
    path: Path,
    *,
    flux_mode: str,
    lambda_min: float | None,
    lambda_max: float | None,
) -> dict[str, Any]:
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

    negative_flux_skipped = 0
    if resolved_mode == "normalized":
        non_negative_mask = flux_arr >= 0
        negative_flux_skipped = int(flux_arr.size - int(non_negative_mask.sum()))
        if negative_flux_skipped > 0:
            wavelength_arr = wavelength_arr[non_negative_mask]
            flux_arr = flux_arr[non_negative_mask]
            skipped_points += negative_flux_skipped
            warnings.append(f"Filtered {negative_flux_skipped} normalized point(s) with negative flux.")
            if wavelength_arr.size < 2:
                raise ValueError("Uploaded normalized spectrum has too few non-negative samples after filtering.")

    range_skipped_points = 0
    if lambda_min is not None or lambda_max is not None:
        range_mask = np.ones(wavelength_arr.shape, dtype=bool)
        if lambda_min is not None:
            range_mask &= wavelength_arr >= lambda_min
        if lambda_max is not None:
            range_mask &= wavelength_arr <= lambda_max
        range_skipped_points = int(wavelength_arr.size - int(range_mask.sum()))
        wavelength_arr = wavelength_arr[range_mask]
        flux_arr = flux_arr[range_mask]
        if range_skipped_points > 0:
            min_label = f"{lambda_min:g}" if lambda_min is not None else "-inf"
            max_label = f"{lambda_max:g}" if lambda_max is not None else "inf"
            warnings.append(
                f"Filtered {range_skipped_points} point(s) outside wavelength window {min_label}..{max_label} Å."
            )
        if wavelength_arr.size < 2:
            raise ValueError("Uploaded spectrum has too few samples within configured wavelength range.")

    return {
        "name": path.name,
        "format": format_name,
        "observation_type": "spectrum",
        "wavelength": wavelength_arr.tolist(),
        "flux": flux_arr.tolist(),
        "lambda_min": lambda_min,
        "lambda_max": lambda_max,
        "flux_mode": resolved_mode,
        "detected_flux_mode": detected_mode,
        "raw_points": raw_points,
        "skipped_points": skipped_points,
        "range_skipped_points": range_skipped_points,
        "warnings": warnings,
    }


def _parse_enabled_token(token: str) -> bool | None:
    normalized = token.strip().lower()
    if not normalized:
        return None
    if normalized in PHOTOMETRY_TRUE_TOKENS:
        return True
    if normalized in PHOTOMETRY_FALSE_TOKENS:
        return False
    return None


def _parse_uploaded_photometry(
    path: Path,
    *,
    flux_mode: str,
    lambda_min: float | None,
    lambda_max: float | None,
) -> dict[str, Any]:
    warnings: list[str] = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ValueError(f"Could not read photometry upload: {exc}") from exc

    wavelength: list[float] = []
    flux: list[float] = []
    band_width: list[float] = []
    flux_err: list[float | None] = []
    point_comment: list[str] = []
    raw_points = 0
    invalid_points = 0
    invalid_lines: list[int] = []
    disabled_points = 0

    for line_no, raw_line in enumerate(content.splitlines(), start=1):
        comment_text = ""
        line = raw_line
        if "#" in raw_line:
            data_part, comment_part = raw_line.split("#", 1)
            line = data_part
            comment_text = comment_part.strip()
        line = line.strip()
        if not line or line.startswith("!"):
            continue
        tokens = [token for token in PHOTOMETRY_SPLIT_RE.split(line) if token]
        if len(tokens) < 3:
            invalid_points += 1
            if len(invalid_lines) < 5:
                invalid_lines.append(line_no)
            continue

        lambda_token = parse_float_token(tokens[0])
        width_token = parse_float_token(tokens[1])
        flux_token = parse_float_token(tokens[2])
        if lambda_token is None or width_token is None or flux_token is None:
            invalid_points += 1
            if len(invalid_lines) < 5:
                invalid_lines.append(line_no)
            continue

        lambda_value = float(lambda_token)
        width_value = float(width_token)
        flux_value = float(flux_token)
        if not math.isfinite(lambda_value) or lambda_value <= 0.0:
            invalid_points += 1
            if len(invalid_lines) < 5:
                invalid_lines.append(line_no)
            continue
        if not math.isfinite(width_value) or width_value < 0.0:
            invalid_points += 1
            if len(invalid_lines) < 5:
                invalid_lines.append(line_no)
            continue
        if not math.isfinite(flux_value):
            invalid_points += 1
            if len(invalid_lines) < 5:
                invalid_lines.append(line_no)
            continue

        enabled = True
        flux_err_value: float | None = None
        token4_mode = "none"

        # Positional rule:
        # 1) token[3] (if present) is preferred as flux_err when numeric.
        # 2) token[4] (if present) is preferred as enabled state when token[3] is flux_err.
        # This prevents flux_err=0 from being interpreted as "disabled".
        if len(tokens) >= 4:
            token4 = tokens[3]
            token4_enabled = _parse_enabled_token(token4)
            token4_numeric = parse_float_token(token4)
            if len(tokens) == 4 and token4_enabled is not None:
                enabled = token4_enabled
                token4_mode = "enabled"
            elif token4_numeric is not None:
                err_value = float(token4_numeric)
                if math.isfinite(err_value) and err_value >= 0.0:
                    flux_err_value = err_value
                    token4_mode = "flux_err"
            else:
                if token4_enabled is not None:
                    enabled = token4_enabled
                    token4_mode = "enabled"

        if len(tokens) >= 5:
            token5 = tokens[4]
            token5_enabled = _parse_enabled_token(token5)
            token5_numeric = parse_float_token(token5)
            if token4_mode == "flux_err":
                if token5_enabled is not None:
                    enabled = token5_enabled
            elif token4_mode == "enabled":
                if flux_err_value is None and token5_numeric is not None:
                    err_value = float(token5_numeric)
                    if math.isfinite(err_value) and err_value >= 0.0:
                        flux_err_value = err_value
                elif token5_enabled is not None:
                    enabled = token5_enabled
            else:
                if flux_err_value is None and token5_numeric is not None:
                    err_value = float(token5_numeric)
                    if math.isfinite(err_value) and err_value >= 0.0:
                        flux_err_value = err_value
                elif token5_enabled is not None:
                    enabled = token5_enabled

        raw_points += 1
        if not enabled:
            disabled_points += 1
            continue

        wavelength.append(lambda_value)
        band_width.append(width_value)
        flux.append(flux_value)
        flux_err.append(flux_err_value)
        point_comment.append(comment_text)

    if invalid_points > 0:
        line_text = ", ".join(str(value) for value in invalid_lines)
        suffix = f" (line(s): {line_text})" if line_text else ""
        warnings.append(f"Skipped {invalid_points} invalid photometry row(s){suffix}.")
    if disabled_points > 0:
        warnings.append(f"Skipped {disabled_points} disabled photometry row(s).")

    if raw_points <= 0:
        raise ValueError(
            "No usable photometry rows were found. Expected columns: "
            "lambda_eff_A width_A flux [flux_err] [enabled]."
        )

    range_skipped_points = 0
    if lambda_min is not None or lambda_max is not None:
        filtered_wave: list[float] = []
        filtered_flux: list[float] = []
        filtered_width: list[float] = []
        filtered_flux_err: list[float | None] = []
        filtered_comment: list[str] = []
        for wave_value, flux_value, width_value, err_value, comment_value in zip(
            wavelength,
            flux,
            band_width,
            flux_err,
            point_comment,
        ):
            if lambda_min is not None and wave_value < lambda_min:
                range_skipped_points += 1
                continue
            if lambda_max is not None and wave_value > lambda_max:
                range_skipped_points += 1
                continue
            filtered_wave.append(wave_value)
            filtered_flux.append(flux_value)
            filtered_width.append(width_value)
            filtered_flux_err.append(err_value)
            filtered_comment.append(comment_value)
        wavelength = filtered_wave
        flux = filtered_flux
        band_width = filtered_width
        flux_err = filtered_flux_err
        point_comment = filtered_comment
        if range_skipped_points > 0:
            min_label = f"{lambda_min:g}" if lambda_min is not None else "-inf"
            max_label = f"{lambda_max:g}" if lambda_max is not None else "inf"
            warnings.append(
                f"Filtered {range_skipped_points} photometry point(s) outside wavelength window {min_label}..{max_label} Å."
            )

    if not wavelength:
        raise ValueError("No enabled photometry points remain after filtering.")

    detected_mode = "absolute"
    resolved_mode = "absolute"
    if flux_mode == "normalized":
        warnings.append("Photometric uploads are treated as absolute-flux data; requested normalized mode was ignored.")

    return {
        "name": path.name,
        "format": "photometry-text",
        "observation_type": "photometry",
        "wavelength": wavelength,
        "band_width": band_width,
        "flux_err": flux_err,
        "point_comment": point_comment,
        "flux": flux,
        "lambda_min": lambda_min,
        "lambda_max": lambda_max,
        "flux_mode": resolved_mode,
        "detected_flux_mode": detected_mode,
        "raw_points": raw_points,
        "skipped_points": int(invalid_points + disabled_points + range_skipped_points),
        "range_skipped_points": range_skipped_points,
        "disabled_points": disabled_points,
        "warnings": warnings,
    }


def _normalize_wavelength_bounds(
    lambda_min: float | None,
    lambda_max: float | None,
) -> tuple[float | None, float | None]:
    min_value = float(lambda_min) if isinstance(lambda_min, int | float) else None
    max_value = float(lambda_max) if isinstance(lambda_max, int | float) else None
    if min_value is not None and (not math.isfinite(min_value) or min_value <= 0):
        min_value = None
    if max_value is not None and (not math.isfinite(max_value) or max_value <= 0):
        max_value = None
    if min_value is not None and max_value is not None and min_value > max_value:
        min_value, max_value = max_value, min_value
    return min_value, max_value


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

    # Spectra are commonly stored either as N rows x 2 columns or as
    # 2 rows x N columns.  Treat the longer dimension as the sample axis;
    # this also keeps the two-column interpretation for the ambiguous 2x2
    # case.  Checking columns unconditionally first would make the row branch
    # unreachable for every useful 2xN array.
    if array.ndim == 2 and array.shape[0] >= 2 and array.shape[1] > array.shape[0]:
        wave = array[0, :].astype(np.float64, copy=False)
        flux = array[1, :].astype(np.float64, copy=False)
        warnings.append("Using first two rows of 2D FITS data as wavelength and flux.")
        return wave, flux, "fits-2d-rows", warnings

    if array.ndim == 2 and array.shape[1] >= 2:
        wave = array[:, 0].astype(np.float64, copy=False)
        flux = array[:, 1].astype(np.float64, copy=False)
        warnings.append("Using first two columns of 2D FITS data as wavelength and flux.")
        return wave, flux, "fits-2d-columns", warnings

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
