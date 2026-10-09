from __future__ import annotations

import csv
import json
import math
import os
import re
import secrets
import shlex
import shutil
import tempfile
import time
import warnings as python_warnings
from functools import lru_cache
from pathlib import Path
from typing import Any

from .parsers.common import parse_float_token

try:
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover - runtime dependency
    np = None  # type: ignore[assignment]

try:
    from astropy import units as u
    from astropy.io import fits
    from astropy.table import Table
except ModuleNotFoundError:  # pragma: no cover - runtime dependency
    fits = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment,misc]
    u = None  # type: ignore[assignment]


SUPPORTED_FITS_SUFFIXES = {".fits", ".fit", ".fts"}
SUPPORTED_VOTABLE_SUFFIXES = {".vot", ".votable"}
SUPPORTED_TEXT_SUFFIXES = {".csv", ".txt", ".dat"}
UPLOAD_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
DEFAULT_UPLOAD_TTL_SECONDS = 2 * 24 * 60 * 60
PHOTOMETRY_SUFFIXES = {".phot"}
PHOTOMETRY_SPLIT_RE = re.compile(r"[,\s;]+")
PHOTOMETRY_TRUE_TOKENS = {"1", "true", "t", "yes", "y", "on", "enable", "enabled"}
PHOTOMETRY_FALSE_TOKENS = {"0", "false", "f", "no", "n", "off", "disable", "disabled"}
CANONICAL_PHOTOMETRY_HEADER = "# wavelength_A band_width_A flux flux_error enabled # comment"


def _photometry_columns(names: list[str]) -> dict[str, str] | None:
    """Require explicit column names; generic width and positional data are ambiguous."""
    aliases = {
        "wave": ("wavelength", "lambda", "lam", "wave", "wl", "lambda_eff"),
        "width": ("bandwidth", "band_width", "bandpass_width", "filter_width"),
        "flux": ("flux", "flx", "f_lambda", "flambda"),
        "error": ("flux_error", "flux_err", "fluxerror", "eflux", "e_flux", "uncertainty"),
        "enabled": ("enabled",),
        "comment": ("comment", "comments"),
    }
    lowered = {_normalize_column_name(name): name for name in names}
    columns = {}
    for role, candidates in aliases.items():
        for candidate in candidates:
            for suffix in ("", "_a", "_angstrom", "_angstroms"):
                if candidate + suffix in lowered:
                    columns[role] = lowered[candidate + suffix]
                    break
            if role in columns:
                break
    return columns if all(role in columns for role in ("wave", "width", "flux")) else None


def _canonical_named_photometry(rows: list[dict[str, Any]], columns: dict[str, str]) -> str:
    lines = []
    for index, row in enumerate(rows, start=1):
        def value(role: str, default: Any = "") -> Any:
            result = row.get(columns.get(role, ""), default)
            return default if np is not None and np.ma.is_masked(result) else result

        numeric = [parse_float_token(str(value(role))) for role in ("wave", "width", "flux")]
        if (
            any(number is None or not math.isfinite(number) for number in numeric)
            or numeric[0] <= 0 or numeric[1] < 0
        ):
            raise ValueError(f"Invalid photometry row at row {index}: expected positive wavelength, non-negative bandwidth, and finite flux.")
        enabled = _parse_enabled_token(str(value("enabled", "1")))
        if enabled is None:
            raise ValueError(f"Invalid photometry enabled flag at row {index}.")
        comment = " ".join(str(value("comment")).splitlines()).strip()
        line = (
            f"{numeric[0]} {numeric[1]} {numeric[2]} "
            f"{value('error', '0') or '0'} {int(enabled)}"
        )
        if comment:
            line += f" # {comment}"
        lines.append(line)
    return normalize_photometry_table("\n".join(lines))


def _photometry_from_text(content: str) -> str | None:
    header = None
    columns = None
    delimiter = None
    rows = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        commented = line.startswith(("#", "!"))
        if commented:
            if header is not None:
                continue
            line = line.lstrip("#! ")
        try:
            row_delimiter = delimiter
            if header is None:
                row_delimiter = "," if "," in line else ";" if ";" in line else None
            if row_delimiter:
                tokens = [token.strip() for token in next(csv.reader([line], delimiter=row_delimiter))]
            else:
                tokens = shlex.split(line, comments=True)
        except (ValueError, csv.Error) as exc:
            if header is not None:
                raise ValueError(f"Invalid photometry table row: {exc}") from exc
            continue
        if header is None:
            candidate = _photometry_columns(tokens)
            if candidate is not None:
                header, columns = tokens, candidate
                delimiter = row_delimiter
            elif not commented:
                return None
        else:
            if len(tokens) < len(header):
                raise ValueError("Photometry row has fewer columns than its header.")
            if len(tokens) > len(header):
                raise ValueError("Photometry row has more columns than its header; quote comments containing spaces or delimiters.")
            rows.append(dict(zip(header, tokens)))
    if columns is None:
        return None
    if not rows:
        raise ValueError("Photometry table contains a header but no data rows.")
    return _canonical_named_photometry(rows, columns)


def _photometry_from_astropy_table(table: Any) -> str | None:
    columns = _photometry_columns(list(table.colnames))
    if columns is None:
        return None
    values = {role: table[name] for role, name in columns.items()}
    # Wavelength and bandwidth must use the same physical units in canonical data.
    for role in ("wave", "width"):
        column = values[role]
        if column.unit is not None:
            try:
                values[role] = column.quantity.to_value("Angstrom")
            except Exception as exc:
                raise ValueError(f"Cannot convert photometry {role} unit '{column.unit}' to Å.") from exc
    for role in ("flux", "error"):
        column = values.get(role)
        if column is not None and column.unit is not None:
            try:
                values[role] = column.quantity.to_value(
                    "erg / (s cm2 Angstrom)",
                    equivalencies=u.spectral_density(values["wave"] * u.Angstrom),
                )
            except Exception as exc:
                raise ValueError(f"Cannot convert photometry {role} unit '{column.unit}' to flux per Å.") from exc
    rows = [
        {
            columns[role]: np.ma.masked if np.ma.is_masked(table[columns[role]][index]) else vector[index]
            for role, vector in values.items()
        }
        for index in range(len(table))
    ]
    if not rows:
        raise ValueError("Photometry table contains no data rows.")
    return _canonical_named_photometry(rows, columns)


def uploaded_photometry_table(path: Path) -> str | None:
    """Return canonical photometry for explicitly named text/VOTable band tables."""
    if path.suffix.lower() in SUPPORTED_TEXT_SUFFIXES:
        return _photometry_from_text(path.read_text(encoding="utf-8-sig", errors="replace"))
    if path.suffix.lower() in SUPPORTED_VOTABLE_SUFFIXES:
        if Table is None or np is None:
            raise ValueError("VOTable parsing requires astropy and numpy.")
        with python_warnings.catch_warnings():
            python_warnings.filterwarnings("ignore", message=".*has been deprecated in the VOUnit standard.*")
            table = Table.read(path, format="votable")
        return _photometry_from_astropy_table(table)
    return None


def _uses_legacy_photometry_schema(content: str) -> bool:
    header_text = " ".join(
        line.lstrip("#! ").lower()
        for line in str(content or "").splitlines()
        if line.lstrip().startswith(("#", "!"))
    )
    return (
        "wavelength" in header_text
        and "flux" in header_text
        and "flux_error" in header_text
        and "width" not in header_text
        and "bandwidth" not in header_text
    )


def normalize_photometry_table(content: str) -> str:
    """Serialize submitted and legacy photometry into one stable on-disk schema."""
    normalized_lines = str(content or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    legacy_without_width = _uses_legacy_photometry_schema(content)

    rows: list[str] = []
    invalid_lines: list[int] = []
    for line_no, raw_line in enumerate(normalized_lines, start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(("#", "!")):
            continue
        data_part, separator, hash_comment = stripped.partition("#")
        try:
            tokens = shlex.split(data_part, comments=False, posix=True)
        except ValueError:
            invalid_lines.append(line_no)
            continue
        if legacy_without_width:
            if len(tokens) < 2:
                invalid_lines.append(line_no)
                continue
            wavelength_token = tokens[0]
            width_token = "0"
            flux_token = tokens[1]
            error_token = tokens[2] if len(tokens) >= 3 else "0"
            enabled_token = "1"
            trailing_comment = " ".join(tokens[3:])
        else:
            if len(tokens) < 3:
                invalid_lines.append(line_no)
                continue
            wavelength_token, width_token, flux_token = tokens[:3]
            error_token = "0"
            enabled_token = "1"
            trailing_comment = ""
            if len(tokens) >= 4:
                fourth_enabled = _parse_enabled_token(tokens[3])
                if len(tokens) == 4 and fourth_enabled is not None:
                    enabled_token = "1" if fourth_enabled else "0"
                else:
                    error_token = tokens[3]
            if len(tokens) >= 5:
                fifth_enabled = _parse_enabled_token(tokens[4])
                if fifth_enabled is not None:
                    enabled_token = "1" if fifth_enabled else "0"
                    trailing_comment = " ".join(tokens[5:])
                else:
                    trailing_comment = " ".join(tokens[4:])

        wavelength = parse_float_token(wavelength_token)
        width = parse_float_token(width_token)
        flux = parse_float_token(flux_token)
        error = parse_float_token(error_token)
        if (
            wavelength is None or not math.isfinite(float(wavelength)) or float(wavelength) <= 0
            or width is None or not math.isfinite(float(width)) or float(width) < 0
            or flux is None or not math.isfinite(float(flux))
        ):
            invalid_lines.append(line_no)
            continue
        error_text = "0"
        if error is not None and math.isfinite(float(error)) and float(error) >= 0:
            error_text = f"{float(error):.15g}"
        comment = hash_comment.strip() if separator else trailing_comment.strip()
        row = (
            f"{float(wavelength):.15g} {float(width):.15g} {float(flux):.15g} "
            f"{error_text} {enabled_token}"
        )
        if comment:
            row += f" # {comment}"
        rows.append(row)

    if invalid_lines:
        labels = ", ".join(str(value) for value in invalid_lines[:5])
        raise ValueError(f"Invalid photometry row(s) at line(s): {labels}.")
    if not rows:
        return ""
    return CANONICAL_PHOTOMETRY_HEADER + "\n" + "\n".join(rows) + "\n"


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


def write_upload_manifest(
    upload_root: Path, token: str, payload: dict[str, Any]
) -> None:
    if not is_valid_upload_token(token):
        raise ValueError("Invalid upload token.")
    target_dir = upload_root / token
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = target_dir / "meta.json"
    serialized = json.dumps(payload, sort_keys=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target_dir, delete=False
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, manifest_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


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
    observation_type: str | None = None,
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
        str(observation_type or "").strip().lower(),
    )


@lru_cache(maxsize=32)
def _parse_uploaded_spectrum_cached(
    path_str: str,
    mtime_ns: int,
    size: int,
    flux_mode: str,
    lambda_min: float | None,
    lambda_max: float | None,
    observation_type: str,
) -> dict[str, Any]:
    del mtime_ns, size
    path = Path(path_str)
    suffix = path.suffix.lower()

    if observation_type == "photometry" or suffix in PHOTOMETRY_SUFFIXES:
        return _parse_uploaded_photometry(path, flux_mode=flux_mode, lambda_min=lambda_min, lambda_max=lambda_max)
    if suffix in SUPPORTED_FITS_SUFFIXES:
        return _parse_uploaded_fits(path, flux_mode=flux_mode, lambda_min=lambda_min, lambda_max=lambda_max)
    if suffix in SUPPORTED_VOTABLE_SUFFIXES:
        return _parse_uploaded_votable(path, flux_mode=flux_mode, lambda_min=lambda_min, lambda_max=lambda_max)
    if suffix in SUPPORTED_TEXT_SUFFIXES:
        return _parse_uploaded_text(path, flux_mode=flux_mode, lambda_min=lambda_min, lambda_max=lambda_max)

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

    return _finalize_uploaded_spectrum(
        path,
        wavelength,
        flux,
        format_name=format_name,
        flux_mode=flux_mode,
        lambda_min=lambda_min,
        lambda_max=lambda_max,
        warnings=warnings,
    )


def _parse_uploaded_votable(
    path: Path,
    *,
    flux_mode: str,
    lambda_min: float | None,
    lambda_max: float | None,
) -> dict[str, Any]:
    if Table is None or np is None:
        raise ValueError("VOTable parsing requires astropy and numpy.")

    try:
        with python_warnings.catch_warnings():
            python_warnings.filterwarnings(
                "ignore",
                message=".*has been deprecated in the VOUnit standard.*",
            )
            table = Table.read(path, format="votable")
    except Exception as exc:
        raise ValueError(f"Could not read VOTable: {exc}") from exc

    warnings: list[str] = []
    canonical = _photometry_from_astropy_table(table)
    if canonical is not None:
        return _parse_photometry_content(
            path, canonical, flux_mode=flux_mode, lambda_min=lambda_min, lambda_max=lambda_max
        )
    wavelength, flux, flux_err, table_warnings = _extract_from_astropy_table(table)
    warnings.extend(table_warnings)
    return _finalize_uploaded_spectrum(
        path,
        wavelength,
        flux,
        flux_err=flux_err,
        format_name="votable",
        flux_mode=flux_mode,
        lambda_min=lambda_min,
        lambda_max=lambda_max,
        warnings=warnings,
    )


def _parse_uploaded_text(
    path: Path,
    *,
    flux_mode: str,
    lambda_min: float | None,
    lambda_max: float | None,
) -> dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise ValueError(f"Could not read text spectrum upload: {exc}") from exc

    canonical = _photometry_from_text(content)
    if canonical is not None:
        return _parse_photometry_content(
            path, canonical, flux_mode=flux_mode, lambda_min=lambda_min, lambda_max=lambda_max
        )

    rows: list[tuple[int, list[str]]] = []
    for line_no, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("!"):
            continue
        if "," in line:
            try:
                tokens = [token.strip() for token in next(csv.reader([line]))]
            except csv.Error:
                tokens = []
        else:
            tokens = [token for token in re.split(r"[;\s]+", line) if token]
        rows.append((line_no, tokens))

    if not rows:
        raise ValueError("Text spectrum is empty. Expected wavelength and flux columns.")

    first_tokens = rows[0][1]
    has_header = len(first_tokens) < 2 or any(parse_float_token(token) is None for token in first_tokens[:2])
    warnings: list[str] = []
    if has_header:
        header = first_tokens
        data_rows = rows[1:]
        lowered = {_normalize_column_name(name): name for name in header}
        wave_name = _pick_column(lowered, ("wavelength", "lambda", "lam", "wave", "wl", "angstrom", "ang"))
        flux_name = _pick_column(
            lowered,
            ("flux", "flx", "f_lambda", "flambda", "spec", "spectrum", "norm", "normalized"),
        )
        if wave_name is not None and flux_name is not None and wave_name != flux_name:
            wave_index = header.index(wave_name)
            flux_index = header.index(flux_name)
        elif len(header) >= 2:
            wave_index, flux_index = 0, 1
            warnings.append("No explicit wavelength/flux column names found; using first two columns.")
        else:
            raise ValueError("Text spectrum header must contain wavelength and flux columns.")

        error_name = _pick_column(
            lowered,
            ("flux_error", "flux_err", "fluxerror", "eflux", "e_flux", "sigma", "uncertainty", "error", "err"),
        )
        error_index = header.index(error_name) if error_name is not None else None
    else:
        data_rows = rows
        wave_index, flux_index = 0, 1
        error_index = 2 if len(first_tokens) >= 3 else None

    if not data_rows:
        raise ValueError("Text spectrum contains a header but no data rows.")

    wavelength: list[float] = []
    flux: list[float] = []
    flux_err: list[float] | None = [] if error_index is not None else None
    invalid_lines: list[int] = []
    required_index = max(wave_index, flux_index)
    for line_no, tokens in data_rows:
        wave_value = parse_float_token(tokens[wave_index]) if len(tokens) > required_index else None
        flux_value = parse_float_token(tokens[flux_index]) if len(tokens) > required_index else None
        wavelength.append(float(wave_value) if wave_value is not None else math.nan)
        flux.append(float(flux_value) if flux_value is not None else math.nan)
        if wave_value is None or flux_value is None:
            if len(invalid_lines) < 5:
                invalid_lines.append(line_no)
        if flux_err is not None:
            err_value = (
                parse_float_token(tokens[error_index])
                if error_index is not None and len(tokens) > error_index
                else None
            )
            flux_err.append(float(err_value) if err_value is not None else math.nan)

    if invalid_lines:
        warnings.append(f"Invalid wavelength/flux values were found on line(s): {', '.join(map(str, invalid_lines))}.")

    return _finalize_uploaded_spectrum(
        path,
        wavelength,
        flux,
        flux_err=flux_err,
        format_name="csv-table" if path.suffix.lower() == ".csv" else "text-table",
        flux_mode=flux_mode,
        lambda_min=lambda_min,
        lambda_max=lambda_max,
        warnings=warnings,
    )


def _finalize_uploaded_spectrum(
    path: Path,
    wavelength: Any,
    flux: Any,
    *,
    format_name: str,
    flux_mode: str,
    lambda_min: float | None,
    lambda_max: float | None,
    warnings: list[str] | None = None,
    flux_err: Any | None = None,
) -> dict[str, Any]:
    if np is None:
        raise ValueError("numpy is not available.")

    result_warnings = list(warnings or [])
    wavelength_arr = np.ma.asarray(wavelength, dtype=np.float64).filled(np.nan).reshape(-1)
    flux_arr = np.ma.asarray(flux, dtype=np.float64).filled(np.nan).reshape(-1)
    if wavelength_arr.size != flux_arr.size or wavelength_arr.size < 2:
        raise ValueError("Uploaded spectrum does not contain matching wavelength/flux vectors.")

    flux_err_arr = None
    if flux_err is not None:
        candidate = np.ma.asarray(flux_err, dtype=np.float64).filled(np.nan).reshape(-1)
        if candidate.size == wavelength_arr.size:
            flux_err_arr = candidate
        else:
            result_warnings.append("Ignored flux-error column because its length does not match the spectrum.")

    raw_points = int(min(wavelength_arr.size, flux_arr.size))
    valid_mask = np.isfinite(wavelength_arr) & np.isfinite(flux_arr) & (wavelength_arr > 0)
    skipped_points = int(raw_points - int(valid_mask.sum()))
    wavelength_arr = wavelength_arr[valid_mask]
    flux_arr = flux_arr[valid_mask]
    if flux_err_arr is not None:
        flux_err_arr = flux_err_arr[valid_mask]
    if wavelength_arr.size < 2:
        raise ValueError("Uploaded spectrum has too few finite samples after filtering.")

    if np.any(np.diff(wavelength_arr) < 0):
        order = np.argsort(wavelength_arr)
        wavelength_arr = wavelength_arr[order]
        flux_arr = flux_arr[order]
        if flux_err_arr is not None:
            flux_err_arr = flux_err_arr[order]

    detected_mode = _detect_flux_mode(flux_arr.tolist())
    resolved_mode = detected_mode if flux_mode == "auto" else flux_mode
    if flux_mode != "auto" and flux_mode != detected_mode:
        result_warnings.append(f"Requested flux mode '{flux_mode}' overrides detected mode '{detected_mode}'.")

    negative_flux_skipped = 0
    if resolved_mode == "normalized":
        non_negative_mask = flux_arr >= 0
        negative_flux_skipped = int(flux_arr.size - int(non_negative_mask.sum()))
        if negative_flux_skipped > 0:
            wavelength_arr = wavelength_arr[non_negative_mask]
            flux_arr = flux_arr[non_negative_mask]
            if flux_err_arr is not None:
                flux_err_arr = flux_err_arr[non_negative_mask]
            skipped_points += negative_flux_skipped
            result_warnings.append(f"Filtered {negative_flux_skipped} normalized point(s) with negative flux.")
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
        if flux_err_arr is not None:
            flux_err_arr = flux_err_arr[range_mask]
        if range_skipped_points > 0:
            min_label = f"{lambda_min:g}" if lambda_min is not None else "-inf"
            max_label = f"{lambda_max:g}" if lambda_max is not None else "inf"
            result_warnings.append(
                f"Filtered {range_skipped_points} point(s) outside wavelength window {min_label}..{max_label} Å."
            )
        if wavelength_arr.size < 2:
            raise ValueError("Uploaded spectrum has too few samples within configured wavelength range.")

    result = {
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
        "warnings": result_warnings,
    }
    if flux_err_arr is not None:
        result["flux_err"] = [
            float(value) if math.isfinite(float(value)) and float(value) >= 0.0 else None
            for value in flux_err_arr
        ]
    return result


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
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        if _uses_legacy_photometry_schema(content):
            content = normalize_photometry_table(content)
    except OSError as exc:
        raise ValueError(f"Could not read photometry upload: {exc}") from exc

    return _parse_photometry_content(
        path, content, flux_mode=flux_mode, lambda_min=lambda_min, lambda_max=lambda_max
    )


def _parse_photometry_content(
    path: Path,
    content: str,
    *,
    flux_mode: str,
    lambda_min: float | None,
    lambda_max: float | None,
) -> dict[str, Any]:
    warnings: list[str] = []
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


def _extract_from_astropy_table(table: Any) -> tuple[Any, Any, Any | None, list[str]]:
    if np is None:
        raise ValueError("numpy is not available.")

    warnings: list[str] = []
    names = list(getattr(table, "colnames", []))
    lowered = {_normalize_column_name(name): name for name in names}
    wave_col = _pick_column(lowered, ("wavelength", "lambda", "lam", "wave", "wl", "angstrom", "ang"))
    flux_col = _pick_column(
        lowered,
        ("flux", "flx", "f_lambda", "flambda", "spec", "spectrum", "norm", "normalized"),
    )

    numeric_names: list[str] = []
    for name in names:
        try:
            values = np.asarray(table[name])
        except (TypeError, ValueError):
            continue
        if values.ndim == 1 and np.issubdtype(values.dtype, np.number):
            numeric_names.append(name)

    if wave_col is None or flux_col is None or wave_col == flux_col:
        if len(numeric_names) < 2:
            raise ValueError("VOTable has no usable wavelength and flux columns.")
        wave_col, flux_col = numeric_names[:2]
        warnings.append("No explicit wavelength/flux column names found; using first two numeric columns.")

    error_col = _pick_column(
        lowered,
        ("flux_error", "flux_err", "fluxerror", "eflux", "e_flux", "sigma", "uncertainty", "error", "err"),
    )
    if error_col in {wave_col, flux_col}:
        error_col = None

    wave_column = table[wave_col]
    wavelength: Any = wave_column
    wave_unit = getattr(wave_column, "unit", None)
    if wave_unit is not None:
        try:
            wavelength = wave_column.quantity.to_value("Angstrom")
        except Exception:
            warnings.append(f"Could not convert wavelength unit '{wave_unit}' to Å; using values unchanged.")

    flux_error = table[error_col] if error_col is not None else None
    return wavelength, table[flux_col], flux_error, warnings


def _normalize_column_name(name: object) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")
    return normalized


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
