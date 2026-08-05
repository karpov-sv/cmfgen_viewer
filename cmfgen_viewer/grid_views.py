"""Upload viewer, grid-search API, and best-fit overlay routes."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from threading import Thread
import time

from flask import abort, jsonify, redirect, render_template, request, url_for

from .browser import resolve_path
from .final_spectrum import (
    apply_spectrum_transform,
    build_final_model_series,
    build_uploaded_spectrum_plot,
    discover_final_spectrum_files,
    load_obs_spectrum,
)
from .grid_catalog import _discover_grid_fit_candidates
from .grid_fitting import (
    _build_tlusty_model_series,
    _fit_bounds_payload,
    _fit_wavelength_range_from_payload,
    _fit_wavelength_range_payload,
)
from .grid_jobs import (
    _grid_search_active_job_for_upload,
    _grid_search_job_create,
    _grid_search_job_snapshot,
    _run_upload_grid_search_job,
)
from .observed_spectrum import (
    is_valid_upload_token,
    list_upload_manifests,
    parse_uploaded_spectrum,
)
from .parsers.common import downsample_xy
from .upload_views import (
    _checkbox_enabled,
    _upload_entry_for_display,
    _upload_spectrum_summary_rows,
)
from .view_common import (
    GRID_FIT_SOURCE_CMFGEN,
    GRID_FIT_SOURCE_TLUSTY,
    GRID_SEARCH_JOBS,
    GRID_SEARCH_JOBS_LOCK,
    _format_query_float,
    _grid_fit_source_label,
    _normalize_fit_bounds,
    _normalize_fit_wavelength_range,
    _normalize_grid_fit_source,
    _normalize_spectrum_mode,
    _normalize_transform_params,
    _spectrum_lambda_bounds,
    _spectrum_url,
    _tlusty_root,
    _upload_root,
    _viewer_config,
    bp,
)
from .vizier_photometry import (
    DEFAULT_CATALOG_KEYS as DEFAULT_VIZIER_CATALOG_KEYS,
    DEFAULT_VIZIER_RADIUS_ARCSEC,
    normalize_catalog_keys,
    vizier_catalog_options_payload,
)


def _vizier_form_context() -> dict[str, object]:
    selected_catalogs = normalize_catalog_keys(request.args.getlist("vizier_catalog"))
    has_preserved_state = _checkbox_enabled(request.args.get("vizier_state"))
    if not selected_catalogs and not has_preserved_state:
        selected_catalogs = list(DEFAULT_VIZIER_CATALOG_KEYS)
    return {
        "vizier_center": str(request.args.get("vizier_center", "")).strip(),
        "vizier_radius_arcsec": str(
            request.args.get("vizier_radius_arcsec", f"{DEFAULT_VIZIER_RADIUS_ARCSEC:g}")
        ).strip(),
        "vizier_table_ids": str(request.args.get("vizier_table_ids", "")).strip(),
        "vizier_catalog_options": vizier_catalog_options_payload(),
        "vizier_selected_catalogs": selected_catalogs,
        "vizier_all_catalogs": _checkbox_enabled(request.args.get("vizier_all_catalogs")),
        "vizier_state": has_preserved_state,
    }

@bp.route("/uploads/")
def uploads():
    config = _viewer_config()
    upload_root = _upload_root(config)
    uploads_all = list_upload_manifests(upload_root)

    upload_items: list[dict[str, object]] = []
    for entry in uploads_all:
        display = _upload_entry_for_display(entry)
        upload_items.append(display)

    return render_template(
        "uploads.html",
        upload_root=str(upload_root),
        uploads=upload_items,
        message=request.args.get("message", "").strip(),
        error=request.args.get("error", "").strip(),
        vizier_photometry_name=request.args.get("photometry_name", "").strip(),
        **_vizier_form_context(),
    )


@bp.route("/uploads/view/<token>")
def upload_view(token: str):
    if not is_valid_upload_token(token):
        abort(404)

    config = _viewer_config()
    upload_root = _upload_root(config)
    lambda_min, lambda_max = _spectrum_lambda_bounds(config)

    entries = {str(item.get("token", "")): item for item in list_upload_manifests(upload_root)}
    entry = entries.get(token)
    if entry is None:
        return redirect(url_for("viewer.uploads", error=f"Uploaded spectrum token '{token}' is not available."))

    display_entry = _upload_entry_for_display(entry)
    filename = str(display_entry.get("filename", token))
    stored_name = str(entry.get("stored_name", ""))
    source_path = upload_root / token / stored_name if stored_name else None
    if source_path is None or not source_path.is_file():
        return redirect(url_for("viewer.uploads", error=f"Uploaded spectrum '{filename}' file is missing."))

    source_text = ""
    try:
        source_text = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        source_text = ""

    upload_flux_mode = str(entry.get("requested_flux_mode", "auto")).strip().lower() or "auto"
    try:
        parsed = parse_uploaded_spectrum(
            source_path,
            flux_mode=upload_flux_mode,
            lambda_min=lambda_min,
            lambda_max=lambda_max,
        )
    except Exception as exc:
        observation_type = str(entry.get("observation_type", "")).strip().lower()
        if observation_type == "photometry" and not source_text.strip():
            parsed = {
                "name": filename,
                "format": "photometry-text",
                "observation_type": "photometry",
                "wavelength": [],
                "band_width": [],
                "flux_err": [],
                "point_comment": [],
                "flux": [],
                "lambda_min": lambda_min,
                "lambda_max": lambda_max,
                "flux_mode": "absolute",
                "detected_flux_mode": "absolute",
                "raw_points": 0,
                "skipped_points": 0,
                "range_skipped_points": 0,
                "disabled_points": 0,
                "warnings": ["No photometry points yet. Add rows manually or append from VizieR."],
            }
        else:
            return redirect(url_for("viewer.uploads", error=f"Uploaded spectrum '{filename}' failed to load: {exc}"))
    parsed["name"] = filename
    parsed["token"] = token

    photometry_text = ""
    if str(parsed.get("observation_type", "spectrum")).strip().lower() == "photometry":
        photometry_text = source_text

    warnings: list[str] = []
    upload_error = request.args.get("error", "").strip()
    if upload_error:
        warnings.append(upload_error)
    upload_message = request.args.get("message", "").strip()
    warnings.extend(str(item) for item in parsed.get("warnings", []))

    plot_data, plot_warning = build_uploaded_spectrum_plot(parsed)
    if plot_warning:
        warnings.append(plot_warning)

    spectrum_mode = "both" if str(parsed.get("flux_mode", "")).strip().lower() == "absolute" else "normalized"
    transform_params = _normalize_transform_params(request.args.to_dict(flat=True))
    fit_wavelength_inputs = {
        "min": str(request.args.get("fit_lambda_min", "")).strip(),
        "max": str(request.args.get("fit_lambda_max", "")).strip(),
    }
    model_name_pattern = str(request.args.get("model_name_pattern", "")).strip()
    fit_source = _normalize_grid_fit_source(request.args.get("fit_source"))
    active_job = _grid_search_active_job_for_upload(token)
    if not model_name_pattern and isinstance(active_job, dict):
        model_name_pattern = str(active_job.get("model_name_pattern", "")).strip()
    if isinstance(active_job, dict) and fit_source == GRID_FIT_SOURCE_CMFGEN:
        fit_source = _normalize_grid_fit_source(active_job.get("fit_source", fit_source))
    fit_bounds = _normalize_fit_bounds(
        request.args.to_dict(flat=True),
        mode=spectrum_mode,
        fit_source=fit_source,
    )
    if isinstance(active_job, dict):
        active_fit_wavelength_range = _fit_wavelength_range_from_payload(active_job.get("fit_wavelength_range"))
        if active_fit_wavelength_range is not None:
            if not fit_wavelength_inputs["min"]:
                fit_wavelength_inputs["min"] = _format_query_float(active_fit_wavelength_range[0])
            if not fit_wavelength_inputs["max"]:
                fit_wavelength_inputs["max"] = _format_query_float(active_fit_wavelength_range[1])

    active_grid_job: dict[str, object] | None = None
    if isinstance(active_job, dict):
        total = int(active_job.get("total", 0) or 0)
        processed = int(active_job.get("processed", 0) or 0)
        progress_percent = 0.0
        if total > 0:
            progress_percent = min(100.0, max(0.0, 100.0 * processed / total))
        best_so_far_payload: dict[str, object] = {}
        best_so_far = active_job.get("best_so_far")
        if isinstance(best_so_far, dict) and best_so_far:
            best_so_far_payload = _grid_search_model_links(
                best_so_far,
                mode=spectrum_mode,
                upload_token=token,
            )
        active_fit_wavelength_range = _fit_wavelength_range_from_payload(active_job.get("fit_wavelength_range"))
        active_grid_job = {
            "job_id": str(active_job.get("job_id", "")),
            "status": str(active_job.get("status", "")),
            "processed": processed,
            "total": total,
            "successful": int(active_job.get("successful", 0) or 0),
            "failed": int(active_job.get("failed", 0) or 0),
            "current_model": str(active_job.get("current_model", "")),
            "cancel_requested": bool(active_job.get("cancel_requested", False)),
            "progress_percent": progress_percent,
            "model_name_pattern": str(active_job.get("model_name_pattern", "")).strip(),
            "fit_source": _normalize_grid_fit_source(active_job.get("fit_source", fit_source)),
            "fit_source_label": str(active_job.get("fit_source_label", _grid_fit_source_label(fit_source))),
            "fit_wavelength_range": _fit_wavelength_range_payload(active_fit_wavelength_range),
            "best_so_far": best_so_far_payload,
        }

    return render_template(
        "upload_spectrum_view.html",
        upload=display_entry,
        upload_summary_rows=_upload_spectrum_summary_rows(
            entry,
            parsed,
            lambda_min=lambda_min,
            lambda_max=lambda_max,
        ),
        mode=spectrum_mode,
        transform_params=transform_params,
        fit_bounds=fit_bounds,
        fit_wavelength_inputs=fit_wavelength_inputs,
        fit_source=fit_source,
        model_name_pattern=model_name_pattern,
        active_grid_job=active_grid_job,
        plot_data=plot_data,
        upload_message=upload_message,
        photometry_text=photometry_text,
        warnings=warnings,
        **_vizier_form_context(),
    )


@bp.route("/uploads/fit-grid/<token>", methods=["POST"])
def upload_fit_grid(token: str):
    if not is_valid_upload_token(token):
        abort(404)

    config = _viewer_config()
    basepath = str(config.get("basepath", "."))
    summary_cache_db = str(config.get("summary_cache_db", "model_summary_cache.sqlite"))
    fit_pool_size_raw = config.get("fit_pool_size_max", 0)
    try:
        fit_pool_size = int(fit_pool_size_raw)
    except (TypeError, ValueError):
        fit_pool_size = 0
    fit_pool_size = max(0, fit_pool_size)
    upload_root = _upload_root(config)
    lambda_min, lambda_max = _spectrum_lambda_bounds(config)
    fit_wavelength_range, fit_wavelength_error = _normalize_fit_wavelength_range(
        request.form.to_dict(flat=True),
        configured_min=lambda_min,
        configured_max=lambda_max,
    )
    if fit_wavelength_error:
        return jsonify({"ok": False, "error": fit_wavelength_error}), 400
    effective_lambda_min = fit_wavelength_range[0] if fit_wavelength_range is not None else lambda_min
    effective_lambda_max = fit_wavelength_range[1] if fit_wavelength_range is not None else lambda_max

    entries = {str(item.get("token", "")): item for item in list_upload_manifests(upload_root)}
    entry = entries.get(token)
    if entry is None:
        return jsonify({"ok": False, "error": "Uploaded spectrum token is not available."}), 404

    stored_name = str(entry.get("stored_name", ""))
    source_path = upload_root / token / stored_name if stored_name else None
    if source_path is None or not source_path.is_file():
        return jsonify({"ok": False, "error": "Uploaded spectrum file is missing."}), 404

    upload_flux_mode = str(entry.get("requested_flux_mode", "auto")).strip().lower() or "auto"
    try:
        observed = parse_uploaded_spectrum(
            source_path,
            flux_mode=upload_flux_mode,
            lambda_min=effective_lambda_min,
            lambda_max=effective_lambda_max,
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Could not parse uploaded spectrum: {exc}"}), 400
    observed["name"] = str(entry.get("filename", source_path.name))

    mode = "both" if str(observed.get("flux_mode", "")).strip().lower() == "absolute" else "normalized"
    model_name_pattern = str(request.form.get("model_name_pattern", "")).strip()
    fit_source = _normalize_grid_fit_source(request.form.get("fit_source"))
    fit_bounds = _normalize_fit_bounds(
        request.form.to_dict(flat=True),
        mode=mode,
        fit_source=fit_source,
    )
    fit_source_label = _grid_fit_source_label(fit_source)

    active_job = _grid_search_active_job_for_upload(token)
    if isinstance(active_job, dict):
        active_job_id = str(active_job.get("job_id", "")).strip()
        total_models = int(active_job.get("total", 0) or 0)
        return jsonify(
            {
                "ok": True,
                "job_id": active_job_id,
                "mode": str(active_job.get("mode", mode)),
                "total_models": total_models,
                "fit_source": _normalize_grid_fit_source(active_job.get("fit_source", fit_source)),
                "fit_source_label": str(active_job.get("fit_source_label", fit_source_label)),
                "fit_bounds": active_job.get("fit_bounds", _fit_bounds_payload(fit_bounds)),
                "fit_wavelength_range": active_job.get(
                    "fit_wavelength_range",
                    _fit_wavelength_range_payload(fit_wavelength_range),
                ),
                "model_name_pattern": str(active_job.get("model_name_pattern", model_name_pattern)),
                "existing_job": True,
            }
        )

    model_candidates, discover_error = _discover_grid_fit_candidates(
        config,
        fit_source=fit_source,
        mode=mode,
        basepath=basepath,
        summary_cache_db=summary_cache_db,
        model_name_pattern=model_name_pattern,
    )
    if discover_error:
        return jsonify({"ok": False, "error": discover_error}), 400
    if not model_candidates:
        return jsonify({"ok": False, "error": f"No {_grid_fit_source_label(fit_source)} candidates were available for grid search."}), 400

    job_id = _grid_search_job_create(
        upload_token=token,
        fit_source=fit_source,
        mode=mode,
        fit_bounds=fit_bounds,
        fit_wavelength_range=fit_wavelength_range,
        model_name_pattern=model_name_pattern,
        total_models=len(model_candidates),
    )

    worker = Thread(
        target=_run_upload_grid_search_job,
        kwargs={
            "job_id": job_id,
            "upload_token": token,
            "fit_source": fit_source,
            "mode": mode,
            "observed": observed,
            "fit_bounds": fit_bounds,
            "fit_wavelength_range": fit_wavelength_range,
            "model_name_pattern": model_name_pattern,
            "model_candidates": model_candidates,
            "lambda_min": effective_lambda_min,
            "lambda_max": effective_lambda_max,
            "max_pool_size": fit_pool_size,
        },
        daemon=True,
    )
    worker.start()

    return jsonify(
        {
            "ok": True,
            "job_id": job_id,
            "mode": mode,
            "fit_source": fit_source,
            "fit_source_label": fit_source_label,
            "total_models": len(model_candidates),
            "fit_bounds": _fit_bounds_payload(fit_bounds),
            "fit_wavelength_range": _fit_wavelength_range_payload(fit_wavelength_range),
            "model_name_pattern": model_name_pattern,
        }
    )


def _grid_search_model_links(
    model_entry: dict[str, object],
    *,
    mode: str,
    upload_token: str,
) -> dict[str, object]:
    enriched = copy.deepcopy(model_entry)
    fit_source = _normalize_grid_fit_source(enriched.get("fit_source", GRID_FIT_SOURCE_CMFGEN))
    best_path = str(enriched.get("model_path", ""))
    best_fin = str(enriched.get("fin", ""))
    fit_params = enriched.get("fit_params")
    if fit_source == GRID_FIT_SOURCE_CMFGEN and isinstance(fit_params, dict) and best_path and best_fin and upload_token:
        enriched["spectrum_url"] = _spectrum_url(
            best_path,
            fin=best_fin,
            mode=mode,
            obs_tokens=[upload_token],
            transform_params=fit_params,
        )
    if fit_source == GRID_FIT_SOURCE_CMFGEN and best_path:
        enriched["browse_url"] = url_for("viewer.view", path=best_path)
    enriched["fit_source"] = fit_source
    return enriched


def _finite_wavelength_bounds(values: object) -> tuple[float, float] | None:
    if not isinstance(values, list):
        return None
    min_value = math.inf
    max_value = -math.inf
    count = 0
    for raw in values:
        if not isinstance(raw, int | float):
            continue
        numeric = float(raw)
        if not math.isfinite(numeric) or numeric <= 0:
            continue
        count += 1
        if numeric < min_value:
            min_value = numeric
        if numeric > max_value:
            max_value = numeric
    if count < 2 or not math.isfinite(min_value) or not math.isfinite(max_value) or min_value >= max_value:
        return None
    return min_value, max_value


def _observed_overlay_wavelength_bounds(observed: dict[str, object]) -> tuple[float, float] | None:
    base_bounds = _finite_wavelength_bounds(observed.get("wavelength"))
    if base_bounds is None:
        return None

    observation_type = str(observed.get("observation_type", "")).strip().lower()
    if observation_type != "photometry":
        return base_bounds

    wavelength = observed.get("wavelength")
    band_width = observed.get("band_width")
    if not isinstance(wavelength, list) or not isinstance(band_width, list):
        return base_bounds

    min_value = math.inf
    max_value = -math.inf
    count = 0
    for index, wave_raw in enumerate(wavelength):
        if not isinstance(wave_raw, int | float):
            continue
        center = float(wave_raw)
        if not math.isfinite(center) or center <= 0.0:
            continue
        width = 0.0
        if index < len(band_width):
            width_raw = band_width[index]
            if isinstance(width_raw, int | float):
                width_value = float(width_raw)
                if math.isfinite(width_value) and width_value > 0.0:
                    width = width_value
        half_width = 0.5 * width
        lo = max(0.0, center - half_width)
        hi = center + half_width
        if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
            continue
        count += 1
        if lo < min_value:
            min_value = lo
        if hi > max_value:
            max_value = hi

    if count > 0 and math.isfinite(min_value) and math.isfinite(max_value) and min_value < max_value:
        return min_value, max_value
    return base_bounds


def _build_tlusty_overlay_trace(
    *,
    config: dict[str, object],
    model_entry: dict[str, object],
    mode: str,
    fit_params: dict[str, float],
    observed_min: float,
    observed_max: float,
) -> tuple[dict[str, object] | None, str | None]:
    tlusty_root = _tlusty_root(config)
    spectrum_relpath = str(model_entry.get("tlusty_spectrum_relpath", "")).strip().strip("/")
    if not spectrum_relpath:
        return None, "Best-fit TLUSTY model is missing spectrum path metadata."
    spectrum_path = tlusty_root / spectrum_relpath
    continuum_relpath = str(model_entry.get("tlusty_continuum_relpath", "")).strip().strip("/")
    continuum_path = (tlusty_root / continuum_relpath) if continuum_relpath else None

    model_x, model_y, series_error = _build_tlusty_model_series(
        mode=mode,
        spectrum_path=spectrum_path,
        continuum_path=continuum_path,
        max_points=0,
    )
    if series_error:
        return None, series_error
    if not isinstance(model_x, list) or not isinstance(model_y, list):
        return None, "Could not prepare TLUSTY model series for overlay."

    transformed = apply_spectrum_transform(
        model_x,
        model_y,
        mode=mode,
        redshift=fit_params["redshift"],
        broadening_km_s=fit_params["broadening_km_s"],
        ebv=fit_params["ebv"],
        distance_kpc=fit_params["distance_kpc"],
        normalization=fit_params.get("normalization", 1.0),
    )
    if transformed is None:
        return None, "Could not transform TLUSTY model spectrum for overlay."
    transformed_x, transformed_y = transformed

    clipped_x: list[float] = []
    clipped_y: list[float] = []
    for wavelength, flux in zip(transformed_x, transformed_y):
        if not isinstance(wavelength, int | float) or not isinstance(flux, int | float):
            continue
        x_value = float(wavelength)
        y_value = float(flux)
        if not math.isfinite(x_value) or not math.isfinite(y_value):
            continue
        if x_value < observed_min or x_value > observed_max:
            continue
        clipped_x.append(x_value)
        clipped_y.append(y_value)

    clipped_x, clipped_y = downsample_xy(clipped_x, clipped_y, max_points=5000)
    if len(clipped_x) < 2 or len(clipped_y) < 2:
        return None, "No transformed TLUSTY points overlap the observed wavelength range."

    rmse_raw = model_entry.get("rmse")
    rmse = float(rmse_raw) if isinstance(rmse_raw, int | float) and math.isfinite(float(rmse_raw)) else None
    model_path = str(model_entry.get("model_path", ""))
    fin_name = str(model_entry.get("fin", ""))
    return (
        {
            "fit_source": GRID_FIT_SOURCE_TLUSTY,
            "mode": mode,
            "model_name": str(model_entry.get("model_name", "")),
            "model_path": model_path,
            "fin": fin_name,
            "rmse": rmse,
            "fit_params": fit_params,
            "x": clipped_x,
            "y": clipped_y,
            "observed_lambda_min": observed_min,
            "observed_lambda_max": observed_max,
        },
        None,
    )


def _build_upload_grid_overlay_trace(
    *,
    config: dict[str, object],
    snapshot: dict[str, object],
    model_entry: dict[str, object],
) -> tuple[dict[str, object] | None, str | None]:
    upload_token = str(snapshot.get("upload_token", "")).strip()
    if not is_valid_upload_token(upload_token):
        return None, "Grid search upload token is invalid."

    upload_root = _upload_root(config)
    entries = {str(item.get("token", "")): item for item in list_upload_manifests(upload_root)}
    entry = entries.get(upload_token)
    if entry is None:
        return None, "Uploaded spectrum is no longer available."

    stored_name = str(entry.get("stored_name", ""))
    source_path = upload_root / upload_token / stored_name if stored_name else None
    if source_path is None or not source_path.is_file():
        return None, "Uploaded spectrum file is missing."

    lambda_min, lambda_max = _spectrum_lambda_bounds(config)
    upload_flux_mode = str(entry.get("requested_flux_mode", "auto")).strip().lower() or "auto"
    try:
        observed = parse_uploaded_spectrum(
            source_path,
            flux_mode=upload_flux_mode,
            lambda_min=lambda_min,
            lambda_max=lambda_max,
        )
    except Exception as exc:
        return None, f"Could not parse uploaded spectrum: {exc}"
    observed_range = _observed_overlay_wavelength_bounds(observed)
    if observed_range is None:
        return None, "Uploaded spectrum does not have enough valid wavelength points."
    observed_min, observed_max = observed_range

    mode = "both" if str(snapshot.get("mode", "")).strip().lower() == "both" else "normalized"
    fit_params_raw = model_entry.get("fit_params")
    if not isinstance(fit_params_raw, dict):
        return None, "Best-fit model is missing fit parameters."
    fit_params = _normalize_transform_params(fit_params_raw)

    fit_source = _normalize_grid_fit_source(model_entry.get("fit_source", GRID_FIT_SOURCE_CMFGEN))
    if fit_source == GRID_FIT_SOURCE_TLUSTY:
        return _build_tlusty_overlay_trace(
            config=config,
            model_entry=model_entry,
            mode=mode,
            fit_params=fit_params,
            observed_min=observed_min,
            observed_max=observed_max,
        )

    model_relpath = str(model_entry.get("model_path", "")).strip()
    fin_name = str(model_entry.get("fin", "")).strip()
    if not model_relpath or not fin_name:
        return None, "Best-fit model entry is incomplete."

    basepath = str(config.get("basepath", "."))
    try:
        model_dir = resolve_path(basepath, model_relpath)
    except FileNotFoundError:
        return None, f"Best-fit model path '{model_relpath}' is not available."
    if not model_dir.is_dir():
        return None, f"Best-fit model path '{model_relpath}' is not available."

    spectrum_files = discover_final_spectrum_files(model_dir)
    if spectrum_files is None:
        return None, f"Final spectrum files are missing for model '{model_relpath}'."

    obs_dir = spectrum_files.get("obs_dir")
    obs_cont = spectrum_files.get("obs_cont")
    if not isinstance(obs_dir, Path) or not isinstance(obs_cont, Path):
        return None, f"Final spectrum paths are invalid for model '{model_relpath}'."
    fin_path = obs_dir / fin_name
    if not fin_path.is_file():
        return None, f"Final spectrum '{fin_name}' is missing for model '{model_relpath}'."

    try:
        continuum = load_obs_spectrum(
            obs_cont,
            lambda_min=lambda_min,
            lambda_max=lambda_max,
        )
        final = load_obs_spectrum(
            fin_path,
            lambda_min=lambda_min,
            lambda_max=lambda_max,
        )
    except Exception as exc:
        return None, f"Could not load model spectrum data: {exc}"

    model_series = build_final_model_series(continuum, final, mode=mode)
    if model_series is None:
        return None, "Could not prepare final model series for overlay."
    model_x, model_y = model_series

    transformed = apply_spectrum_transform(
        model_x,
        model_y,
        mode=mode,
        redshift=fit_params["redshift"],
        broadening_km_s=fit_params["broadening_km_s"],
        ebv=fit_params["ebv"],
        distance_kpc=fit_params["distance_kpc"],
        normalization=fit_params.get("normalization", 1.0),
    )
    if transformed is None:
        return None, "Could not transform model spectrum for overlay."
    transformed_x, transformed_y = transformed

    clipped_x: list[float] = []
    clipped_y: list[float] = []
    for wavelength, flux in zip(transformed_x, transformed_y):
        if not isinstance(wavelength, int | float) or not isinstance(flux, int | float):
            continue
        x_value = float(wavelength)
        y_value = float(flux)
        if not math.isfinite(x_value) or not math.isfinite(y_value):
            continue
        if x_value < observed_min or x_value > observed_max:
            continue
        clipped_x.append(x_value)
        clipped_y.append(y_value)

    clipped_x, clipped_y = downsample_xy(clipped_x, clipped_y, max_points=5000)
    if len(clipped_x) < 2 or len(clipped_y) < 2:
        return None, "No transformed model points overlap the observed wavelength range."

    rmse_raw = model_entry.get("rmse")
    rmse = float(rmse_raw) if isinstance(rmse_raw, int | float) and math.isfinite(float(rmse_raw)) else None

    return (
        {
            "mode": mode,
            "model_name": str(model_entry.get("model_name", "")),
            "model_path": model_relpath,
            "fin": fin_name,
            "rmse": rmse,
            "fit_params": fit_params,
            "x": clipped_x,
            "y": clipped_y,
            "observed_lambda_min": observed_min,
            "observed_lambda_max": observed_max,
        },
        None,
    )


@bp.route("/uploads/fit-grid/status/<job_id>")
def upload_fit_grid_status(job_id: str):
    snapshot = _grid_search_job_snapshot(job_id)
    if snapshot is None:
        return jsonify({"ok": False, "error": "Grid search job is not available."}), 404

    fit_source = _normalize_grid_fit_source(snapshot.get("fit_source", GRID_FIT_SOURCE_CMFGEN))
    fit_source_label = str(snapshot.get("fit_source_label", _grid_fit_source_label(fit_source)))
    status = str(snapshot.get("status", ""))
    processed = int(snapshot.get("processed", 0) or 0)
    total = int(snapshot.get("total", 0) or 0)
    successful = int(snapshot.get("successful", 0) or 0)
    failed = int(snapshot.get("failed", 0) or 0)
    cancel_requested = bool(snapshot.get("cancel_requested", False))

    progress_percent = 0.0
    if total > 0:
        progress_percent = min(100.0, max(0.0, 100.0 * processed / total))
    if status in {"completed", "canceled"}:
        progress_percent = 100.0

    payload: dict[str, object] = {
        "ok": True,
        "status": status,
        "fit_source": fit_source,
        "fit_source_label": fit_source_label,
        "processed": processed,
        "total": total,
        "successful": successful,
        "failed": failed,
        "current_model": str(snapshot.get("current_model", "")),
        "progress_percent": progress_percent,
        "cancel_requested": cancel_requested,
        "can_cancel": status == "running" and not cancel_requested,
        "fit_wavelength_range": snapshot.get("fit_wavelength_range", {}),
    }

    upload_token = str(snapshot.get("upload_token", ""))
    running_mode = str(snapshot.get("mode", "both"))
    best_so_far = snapshot.get("best_so_far")
    if isinstance(best_so_far, dict) and best_so_far:
        payload["best_so_far"] = _grid_search_model_links(
            best_so_far,
            mode=running_mode,
            upload_token=upload_token,
        )

    if status == "failed":
        payload["error"] = str(snapshot.get("error", "Grid search failed."))
        return jsonify(payload), 500

    if status in {"completed", "canceled"}:
        result = snapshot.get("result")
        if isinstance(result, dict):
            result_payload = copy.deepcopy(result)
            best_model = result_payload.get("best_model")
            if isinstance(best_model, dict):
                result_payload["best_model"] = _grid_search_model_links(
                    best_model,
                    mode=str(result_payload.get("mode", snapshot.get("mode", "both"))),
                    upload_token=upload_token,
                )
            payload["result"] = result_payload
        if status == "canceled":
            payload["message"] = "Grid search canceled."

    return jsonify(payload)


@bp.route("/uploads/fit-grid/overlay/<job_id>")
def upload_fit_grid_overlay(job_id: str):
    snapshot = _grid_search_job_snapshot(job_id)
    if snapshot is None:
        return jsonify({"ok": False, "error": "Grid search job is not available."}), 404

    which = str(request.args.get("which", "best_so_far")).strip().lower()
    model_entry: dict[str, object] | None = None
    if which == "final":
        result = snapshot.get("result")
        if isinstance(result, dict):
            best_model = result.get("best_model")
            if isinstance(best_model, dict) and best_model:
                model_entry = best_model

    if model_entry is None:
        best_so_far = snapshot.get("best_so_far")
        if isinstance(best_so_far, dict) and best_so_far:
            model_entry = best_so_far
            if which != "final":
                which = "best_so_far"

    if model_entry is None:
        return jsonify({"ok": False, "error": "No best-fit model is available yet."}), 404

    trace_payload, overlay_error = _build_upload_grid_overlay_trace(
        config=_viewer_config(),
        snapshot=snapshot,
        model_entry=model_entry,
    )
    if overlay_error:
        return jsonify({"ok": False, "error": overlay_error}), 400
    if trace_payload is None:
        return jsonify({"ok": False, "error": "Could not prepare best-fit overlay trace."}), 400
    return jsonify({"ok": True, "which": which, "trace": trace_payload})


@bp.route("/uploads/fit-grid/cancel/<job_id>", methods=["POST"])
def upload_fit_grid_cancel(job_id: str):
    with GRID_SEARCH_JOBS_LOCK:
        job = GRID_SEARCH_JOBS.get(job_id)
        if not isinstance(job, dict):
            return jsonify({"ok": False, "error": "Grid search job is not available."}), 404
        status = str(job.get("status", ""))
        if status != "running":
            return jsonify({"ok": True, "status": status, "cancel_requested": bool(job.get("cancel_requested", False))})
        job["cancel_requested"] = True
        job["cancel_requested_at"] = time.time()
        return jsonify({"ok": True, "status": status, "cancel_requested": True})


@bp.route("/uploads/fit-grid/match-count/<token>")
def upload_fit_grid_match_count(token: str):
    if not is_valid_upload_token(token):
        abort(404)

    config = _viewer_config()
    basepath = str(config.get("basepath", "."))
    summary_cache_db = str(config.get("summary_cache_db", "model_summary_cache.sqlite"))
    upload_root = _upload_root(config)

    entries = {str(item.get("token", "")): item for item in list_upload_manifests(upload_root)}
    if token not in entries:
        return jsonify({"ok": False, "error": "Uploaded spectrum token is not available.", "total_models": 0}), 404

    fit_source = _normalize_grid_fit_source(request.args.get("fit_source"))
    mode = _normalize_spectrum_mode(request.args.get("mode"))
    model_name_pattern = str(request.args.get("model_name_pattern", "")).strip()
    model_candidates, discover_error = _discover_grid_fit_candidates(
        config,
        fit_source=fit_source,
        mode=mode,
        basepath=basepath,
        summary_cache_db=summary_cache_db,
        model_name_pattern=model_name_pattern,
    )
    if discover_error:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": discover_error,
                    "fit_source": fit_source,
                    "fit_source_label": _grid_fit_source_label(fit_source),
                    "model_name_pattern": model_name_pattern,
                    "total_models": 0,
                }
            ),
            400,
        )

    return jsonify(
        {
            "ok": True,
            "fit_source": fit_source,
            "fit_source_label": _grid_fit_source_label(fit_source),
            "model_name_pattern": model_name_pattern,
            "total_models": len(model_candidates),
        }
    )

