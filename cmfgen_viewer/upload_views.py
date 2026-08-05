"""Observed-spectrum upload persistence and photometry-editing routes."""

from __future__ import annotations

import math
from pathlib import Path
import time

from flask import abort, redirect, request, url_for
from werkzeug.utils import secure_filename

from .observed_spectrum import (
    generate_upload_token,
    is_valid_upload_token,
    list_upload_manifests,
    parse_uploaded_spectrum,
    remove_upload_bundle,
    write_upload_manifest,
)
from .parsers.common import format_number, parse_float_token
from .view_common import _spectrum_lambda_bounds, _upload_root, _viewer_config, bp
from .vizier_photometry import (
    DEFAULT_VIZIER_RADIUS_ARCSEC,
    format_photometry_table_rows,
    normalize_catalog_keys,
    normalize_radius_arcsec,
    parse_source_ids_text,
    query_vizier_photometry_points,
)

def _format_upload_time(timestamp: object) -> str:
    try:
        value = float(timestamp)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(value))


def _upload_entry_for_display(entry: dict[str, object]) -> dict[str, object]:
    return {
        "token": str(entry.get("token", "")),
        "filename": str(entry.get("filename", "")),
        "format": str(entry.get("format", "")),
        "observation_type": str(entry.get("observation_type", "spectrum")),
        "flux_mode": str(entry.get("resolved_flux_mode", entry.get("requested_flux_mode", ""))),
        "detected_flux_mode": str(entry.get("detected_flux_mode", "")),
        "points": int(entry.get("points", 0) or 0),
        "size": int(entry.get("size", 0) or 0),
        "exists": bool(entry.get("exists", False)),
        "created_at": _format_upload_time(entry.get("created_at", 0)),
    }


def _format_upload_size(size: object) -> str:
    try:
        total_bytes = int(size)
    except (TypeError, ValueError):
        return ""
    if total_bytes < 0:
        return ""
    if total_bytes < 1024:
        return f"{total_bytes} B"

    value = float(total_bytes)
    unit = "B"
    for candidate in ("KB", "MB", "GB", "TB"):
        value = value / 1024.0
        unit = candidate
        if value < 1024.0:
            break
    return f"{format_number(value)} {unit} ({total_bytes} B)"


def _upload_format_description(format_name: str) -> str:
    descriptions = {
        "fits-table": "FITS table with wavelength/flux columns.",
        "fits-1d-primary": "1D FITS array; wavelength derived from CRVAL1/CDELT1 (or CD1_1).",
        "fits-2d-singleton": "2D FITS with singleton axis flattened to 1D; wavelength from header WCS.",
        "fits-2d-columns": "2D FITS array; first two columns interpreted as wavelength and flux.",
        "fits-2d-rows": "2D FITS array; first two rows interpreted as wavelength and flux.",
        "photometry-text": "Plain-text photometry table: lambda_eff_A, band_width_A, flux, optional enabled flag.",
    }
    key = format_name.strip().lower()
    return descriptions.get(key, "Custom/unknown FITS layout.")


def _upload_spectrum_summary_rows(
    entry: dict[str, object],
    parsed: dict[str, object],
    *,
    lambda_min: float,
    lambda_max: float,
) -> list[list[str]]:
    format_name = str(parsed.get("format", entry.get("format", "")))
    observation_type = str(parsed.get("observation_type", entry.get("observation_type", "spectrum")))
    flux_mode = str(parsed.get("flux_mode", entry.get("resolved_flux_mode", entry.get("requested_flux_mode", ""))))
    detected_flux_mode = str(parsed.get("detected_flux_mode", entry.get("detected_flux_mode", "")))
    requested_flux_mode = str(entry.get("requested_flux_mode", ""))
    token = str(entry.get("token", ""))

    wavelength = parsed.get("wavelength")
    span_label = ""
    if isinstance(wavelength, list):
        finite = [float(value) for value in wavelength if isinstance(value, int | float) and math.isfinite(float(value))]
        if finite:
            span_label = f"{format_number(min(finite))} .. {format_number(max(finite))}"

    band_width = parsed.get("band_width")
    band_span_label = ""
    if isinstance(band_width, list):
        finite_width = [float(value) for value in band_width if isinstance(value, int | float) and math.isfinite(float(value))]
        if finite_width:
            band_span_label = f"{format_number(min(finite_width))} .. {format_number(max(finite_width))}"

    flux_err = parsed.get("flux_err")
    flux_err_span_label = ""
    if isinstance(flux_err, list):
        finite_flux_err = [float(value) for value in flux_err if isinstance(value, int | float) and math.isfinite(float(value))]
        if finite_flux_err:
            flux_err_span_label = f"{format_number(min(finite_flux_err))} .. {format_number(max(finite_flux_err))}"

    rows = [
        ["File", str(entry.get("filename", ""))],
        ["Upload token", token],
        ["Stored format", format_name],
        ["Format details", _upload_format_description(format_name)],
        ["Observation type", observation_type],
        ["Flux mode", flux_mode],
        ["Detected flux mode", detected_flux_mode],
        ["Requested flux mode", requested_flux_mode],
        ["Parsed points", str(len(parsed.get("wavelength", [])))],
        ["Raw points", str(parsed.get("raw_points", ""))],
        ["Skipped invalid points", str(parsed.get("skipped_points", 0))],
        ["Disabled rows", str(parsed.get("disabled_points", 0))],
        ["Skipped by wavelength window", str(parsed.get("range_skipped_points", 0))],
        ["Wavelength span (Å)", span_label],
        ["Band width span (Å)", band_span_label],
        ["Flux error span", flux_err_span_label],
        ["Configured wavelength window (Å)", f"{format_number(lambda_min)} .. {format_number(lambda_max)}"],
        ["File size", _format_upload_size(entry.get("size", 0))],
        ["Uploaded at", _format_upload_time(entry.get("created_at", 0))],
    ]
    return [[label, value] for label, value in rows if value not in {"", None}]


def _merge_photometry_table_text(base_table: str, appended_rows: str) -> tuple[str, int, int]:
    """
    Merge text blocks while removing fully repeated appended rows textually.

    Deduplication is intentionally minimal and only applies to rows being appended:
    - duplicate vs existing base rows,
    - duplicate within the appended batch.
    Existing duplicates already present in base_table are preserved.

    Dedup comparison ignores the optional enabled/disabled flag column so that
    appending an enabled row does not duplicate an already existing disabled row.
    """

    base = base_table.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    extra = appended_rows.replace("\r\n", "\n").replace("\r", "\n").strip("\n")

    if not extra:
        return base, 0, 0

    base_keys: set[str] = set()
    if base:
        for line in base.split("\n"):
            key = _photometry_row_dedup_key(line)
            if key:
                base_keys.add(key)

    unique_appended: list[str] = []
    appended_keys: set[str] = set()
    skipped_duplicates = 0
    for line in extra.split("\n"):
        normalized_line = line.strip()
        if not normalized_line:
            continue
        key = _photometry_row_dedup_key(normalized_line)
        if not key:
            key = normalized_line
        if key in base_keys or key in appended_keys:
            skipped_duplicates += 1
            continue
        appended_keys.add(key)
        unique_appended.append(normalized_line)

    added_count = len(unique_appended)
    if not unique_appended:
        return base, 0, skipped_duplicates

    if not base:
        return "\n".join(unique_appended), added_count, skipped_duplicates
    return f"{base}\n" + "\n".join(unique_appended), added_count, skipped_duplicates


def _photometry_row_dedup_key(raw_line: str) -> str:
    line = str(raw_line or "").strip()
    if not line:
        return ""

    data_part = line
    comment_part = ""
    if "#" in line:
        data_part, comment_part = line.split("#", 1)
        data_part = data_part.strip()
        comment_part = comment_part.strip()

    if data_part:
        tokens = data_part.split()
        if len(tokens) >= 5 and _is_photometry_enabled_token(tokens[4]):
            # Ignore enabled flag (0/1) in dedup comparisons.
            tokens = tokens[:4] + tokens[5:]
        data_part = " ".join(tokens)

    if data_part and comment_part:
        return f"{data_part} # {comment_part}"
    if data_part:
        return data_part
    if comment_part:
        return f"# {comment_part}"
    return line


def _is_photometry_enabled_token(raw_token: object) -> bool:
    parsed = parse_float_token(str(raw_token or ""))
    if parsed is None:
        return False
    value = float(parsed)
    return math.isfinite(value) and (math.isclose(value, 0.0) or math.isclose(value, 1.0))


def _checkbox_enabled(raw_value: object) -> bool:
    value = str(raw_value or "").strip().lower()
    return value in {"1", "true", "yes", "on", "y"}


def _photometry_filename_from_form(
    *,
    entry: dict[str, object],
    fallback: str = "photometry-points.txt",
) -> str:
    filename_raw = str(request.form.get("photometry_name", "")).strip()
    filename = secure_filename(filename_raw) if filename_raw else str(entry.get("filename", "")).strip()
    if not filename:
        filename = fallback
    return filename


def _vizier_state_query_from_form() -> dict[str, object]:
    query: dict[str, object] = {}

    center = str(request.form.get("vizier_center", "")).strip()
    if center:
        query["vizier_center"] = center

    radius = str(request.form.get("vizier_radius_arcsec", "")).strip()
    if radius:
        query["vizier_radius_arcsec"] = radius

    table_ids = str(request.form.get("vizier_table_ids", "")).strip()
    if table_ids:
        query["vizier_table_ids"] = table_ids

    selected_catalogs = normalize_catalog_keys(request.form.getlist("vizier_catalog"))
    if selected_catalogs:
        query["vizier_catalog"] = selected_catalogs

    if _checkbox_enabled(request.form.get("vizier_all_catalogs")):
        query["vizier_all_catalogs"] = "1"
    return query


def _upload_view_redirect_with_vizier_state(
    token: str,
    *,
    message: str = "",
    error: str = "",
):
    query = _vizier_state_query_from_form()
    if message:
        query["message"] = message
    if error:
        query["error"] = error
    return redirect(url_for("viewer.upload_view", token=token, **query))


@bp.route("/uploads/upload", methods=["POST"])
def uploads_upload():
    config = _viewer_config()
    upload_root = _upload_root(config)
    lambda_min, lambda_max = _spectrum_lambda_bounds(config)

    uploaded = request.files.get("observed_file")
    if uploaded is None or not uploaded.filename:
        return redirect(url_for("viewer.uploads", error="No file selected for upload."))

    requested_flux_mode = str(request.form.get("flux_mode", "auto")).strip().lower()
    token = generate_upload_token()
    token_dir = upload_root / token
    token_dir.mkdir(parents=True, exist_ok=False)

    safe_name = secure_filename(uploaded.filename) or "observed-spectrum"
    suffix = Path(safe_name).suffix.lower()
    stored_name = f"source{suffix}" if suffix else "source.dat"
    stored_path = token_dir / stored_name

    try:
        uploaded.save(stored_path)
        parsed = parse_uploaded_spectrum(
            stored_path,
            flux_mode=requested_flux_mode,
            lambda_min=lambda_min,
            lambda_max=lambda_max,
        )
    except Exception as exc:
        remove_upload_bundle(upload_root, token)
        return redirect(url_for("viewer.uploads", error=f"Upload failed: {exc}"))

    manifest = {
        "token": token,
        "filename": safe_name,
        "stored_name": stored_name,
        "requested_flux_mode": requested_flux_mode,
        "detected_flux_mode": str(parsed.get("detected_flux_mode", "")),
        "resolved_flux_mode": str(parsed.get("flux_mode", "")),
        "format": str(parsed.get("format", "")),
        "observation_type": str(parsed.get("observation_type", "spectrum")),
        "points": len(parsed.get("wavelength", [])),
        "created_at": time.time(),
    }
    write_upload_manifest(upload_root, token, manifest)
    return redirect(url_for("viewer.uploads", message=f"Uploaded {safe_name}."))


@bp.route("/uploads/upload-photometry", methods=["POST"])
def uploads_upload_photometry():
    config = _viewer_config()
    upload_root = _upload_root(config)
    lambda_min, lambda_max = _spectrum_lambda_bounds(config)

    photometry_table = str(request.form.get("photometry_table", ""))
    has_rows = bool(photometry_table.strip())

    filename_raw = str(request.form.get("photometry_name", "")).strip()
    safe_name = secure_filename(filename_raw) or "photometry-points.txt"

    token = generate_upload_token()
    token_dir = upload_root / token
    token_dir.mkdir(parents=True, exist_ok=False)
    stored_name = "source.phot"
    stored_path = token_dir / stored_name
    requested_flux_mode = "absolute"

    try:
        stored_path.write_text(photometry_table, encoding="utf-8")
        if has_rows:
            parsed = parse_uploaded_spectrum(
                stored_path,
                flux_mode=requested_flux_mode,
                lambda_min=lambda_min,
                lambda_max=lambda_max,
            )
        else:
            parsed = {
                "detected_flux_mode": "absolute",
                "flux_mode": "absolute",
                "format": "photometry-text",
                "observation_type": "photometry",
                "wavelength": [],
            }
    except Exception as exc:
        remove_upload_bundle(upload_root, token)
        return redirect(url_for("viewer.uploads", error=f"Photometry upload failed: {exc}"))

    manifest = {
        "token": token,
        "filename": safe_name,
        "stored_name": stored_name,
        "requested_flux_mode": requested_flux_mode,
        "detected_flux_mode": str(parsed.get("detected_flux_mode", "")),
        "resolved_flux_mode": str(parsed.get("flux_mode", "")),
        "format": str(parsed.get("format", "")),
        "observation_type": str(parsed.get("observation_type", "photometry")),
        "points": len(parsed.get("wavelength", [])),
        "created_at": time.time(),
    }
    write_upload_manifest(upload_root, token, manifest)
    return redirect(url_for("viewer.uploads", message=f"Uploaded photometry {safe_name}."))


@bp.route("/uploads/update-photometry/<token>", methods=["POST"])
def uploads_update_photometry(token: str):
    if not is_valid_upload_token(token):
        abort(404)

    config = _viewer_config()
    upload_root = _upload_root(config)
    lambda_min, lambda_max = _spectrum_lambda_bounds(config)

    entries = {str(item.get("token", "")): item for item in list_upload_manifests(upload_root)}
    entry = entries.get(token)
    if entry is None:
        return redirect(url_for("viewer.uploads", error="Uploaded photometry token is not available."))

    stored_name = str(entry.get("stored_name", "")).strip()
    source_path = upload_root / token / stored_name if stored_name else None
    if source_path is None or not source_path.is_file():
        return redirect(url_for("viewer.uploads", error="Uploaded photometry file is missing."))

    observation_type = str(entry.get("observation_type", "")).strip().lower()
    if observation_type != "photometry" and source_path.suffix.lower() != ".phot":
        return _upload_view_redirect_with_vizier_state(token, error="Only photometry uploads can be edited here.")

    photometry_table = str(request.form.get("photometry_table", ""))
    has_rows = bool(photometry_table.strip())

    previous_content = ""
    try:
        previous_content = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        previous_content = ""

    requested_flux_mode = "absolute"
    try:
        source_path.write_text(photometry_table, encoding="utf-8")
        if has_rows:
            parsed = parse_uploaded_spectrum(
                source_path,
                flux_mode=requested_flux_mode,
                lambda_min=lambda_min,
                lambda_max=lambda_max,
            )
        else:
            parsed = {
                "detected_flux_mode": "absolute",
                "flux_mode": "absolute",
                "format": "photometry-text",
                "observation_type": "photometry",
                "wavelength": [],
            }
    except Exception as exc:
        try:
            source_path.write_text(previous_content, encoding="utf-8")
        except OSError:
            pass
        return _upload_view_redirect_with_vizier_state(token, error=f"Could not update photometry data: {exc}")

    filename = _photometry_filename_from_form(entry=entry)

    created_at_raw = entry.get("created_at", time.time())
    try:
        created_at = float(created_at_raw)
    except (TypeError, ValueError):
        created_at = time.time()
    if not math.isfinite(created_at):
        created_at = time.time()

    manifest = {
        "token": token,
        "filename": filename,
        "stored_name": stored_name,
        "requested_flux_mode": requested_flux_mode,
        "detected_flux_mode": str(parsed.get("detected_flux_mode", "")),
        "resolved_flux_mode": str(parsed.get("flux_mode", "")),
        "format": str(parsed.get("format", "")),
        "observation_type": str(parsed.get("observation_type", "photometry")),
        "points": len(parsed.get("wavelength", [])),
        "created_at": created_at,
        "updated_at": time.time(),
    }
    write_upload_manifest(upload_root, token, manifest)
    return _upload_view_redirect_with_vizier_state(token, message="Photometry data updated.")


@bp.route("/uploads/append-vizier-photometry/<token>", methods=["POST"])
def uploads_append_vizier_photometry(token: str):
    if not is_valid_upload_token(token):
        abort(404)

    config = _viewer_config()
    upload_root = _upload_root(config)
    lambda_min, lambda_max = _spectrum_lambda_bounds(config)

    entries = {str(item.get("token", "")): item for item in list_upload_manifests(upload_root)}
    entry = entries.get(token)
    if entry is None:
        return redirect(url_for("viewer.uploads", error="Uploaded photometry token is not available."))

    stored_name = str(entry.get("stored_name", "")).strip()
    source_path = upload_root / token / stored_name if stored_name else None
    if source_path is None or not source_path.is_file():
        return redirect(url_for("viewer.uploads", error="Uploaded photometry file is missing."))

    observation_type = str(entry.get("observation_type", "")).strip().lower()
    if observation_type != "photometry" and source_path.suffix.lower() != ".phot":
        return redirect(url_for("viewer.upload_view", token=token, error="Only photometry uploads can be edited here."))

    center_raw = str(request.form.get("vizier_center", "")).strip()
    if not center_raw:
        return _upload_view_redirect_with_vizier_state(token, error="VizieR center coordinates are required.")

    radius_raw = str(request.form.get("vizier_radius_arcsec", "")).strip()
    try:
        radius_arcsec = normalize_radius_arcsec(radius_raw, default=DEFAULT_VIZIER_RADIUS_ARCSEC)
    except ValueError as exc:
        return _upload_view_redirect_with_vizier_state(token, error=f"Invalid VizieR radius: {exc}")

    include_all_catalogs = _checkbox_enabled(request.form.get("vizier_all_catalogs"))
    selected_catalog_keys = normalize_catalog_keys(request.form.getlist("vizier_catalog"))
    selected_source_ids = parse_source_ids_text(request.form.get("vizier_table_ids"))
    if not include_all_catalogs and not selected_catalog_keys and not selected_source_ids:
        return _upload_view_redirect_with_vizier_state(
            token,
            error="Select at least one VizieR catalog or specify VizieR table IDs.",
        )

    provided_table = request.form.get("photometry_table")
    if provided_table is None:
        try:
            photometry_table = source_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            photometry_table = ""
    else:
        # Always start from the current textarea content, including an intentionally empty one.
        photometry_table = str(provided_table)

    try:
        points = query_vizier_photometry_points(
            center=center_raw,
            radius_arcsec=radius_arcsec,
            catalog_keys=selected_catalog_keys,
            source_ids=selected_source_ids,
            include_all_catalogs=include_all_catalogs,
        )
    except Exception as exc:
        return _upload_view_redirect_with_vizier_state(token, error=f"VizieR query failed: {exc}")

    if not points:
        return _upload_view_redirect_with_vizier_state(
            token,
            error="No VizieR photometry points were found in the search region.",
        )

    rows_text = format_photometry_table_rows(points)
    if not rows_text.strip():
        return _upload_view_redirect_with_vizier_state(token, error="VizieR query returned no usable photometry rows.")
    merged_table, added_rows, skipped_duplicates = _merge_photometry_table_text(photometry_table, rows_text)

    previous_content = ""
    try:
        previous_content = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        previous_content = ""

    if added_rows <= 0 and merged_table == previous_content:
        return _upload_view_redirect_with_vizier_state(
            token,
            message=f"No new rows appended. Skipped {skipped_duplicates} duplicate VizieR row(s).",
        )

    requested_flux_mode = "absolute"
    try:
        source_path.write_text(merged_table, encoding="utf-8")
        parsed = parse_uploaded_spectrum(
            source_path,
            flux_mode=requested_flux_mode,
            lambda_min=lambda_min,
            lambda_max=lambda_max,
        )
    except Exception as exc:
        try:
            source_path.write_text(previous_content, encoding="utf-8")
        except OSError:
            pass
        return _upload_view_redirect_with_vizier_state(token, error=f"Could not append VizieR photometry: {exc}")

    created_at_raw = entry.get("created_at", time.time())
    try:
        created_at = float(created_at_raw)
    except (TypeError, ValueError):
        created_at = time.time()
    if not math.isfinite(created_at):
        created_at = time.time()

    manifest = {
        "token": token,
        "filename": _photometry_filename_from_form(entry=entry),
        "stored_name": stored_name,
        "requested_flux_mode": requested_flux_mode,
        "detected_flux_mode": str(parsed.get("detected_flux_mode", "")),
        "resolved_flux_mode": str(parsed.get("flux_mode", "")),
        "format": str(parsed.get("format", "")),
        "observation_type": str(parsed.get("observation_type", "photometry")),
        "points": len(parsed.get("wavelength", [])),
        "created_at": created_at,
        "updated_at": time.time(),
    }
    write_upload_manifest(upload_root, token, manifest)
    if added_rows > 0:
        message = f"Appended {added_rows} VizieR photometry point(s)."
        if skipped_duplicates > 0:
            message = f"{message} Skipped {skipped_duplicates} duplicate row(s)."
    else:
        message = f"Photometry data updated. No new rows appended. Skipped {skipped_duplicates} duplicate VizieR row(s)."
    return _upload_view_redirect_with_vizier_state(
        token,
        message=message,
    )


@bp.route("/uploads/delete/<token>", methods=["POST"])
def uploads_delete(token: str):
    if not is_valid_upload_token(token):
        abort(404)
    config = _viewer_config()
    upload_root = _upload_root(config)
    remove_upload_bundle(upload_root, token)
    return redirect(url_for("viewer.uploads", message="Upload removed."))


