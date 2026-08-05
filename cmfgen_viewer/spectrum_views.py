"""Single-model spectrum display, upload, and fit routes."""

from __future__ import annotations

import math
from pathlib import Path
import time

from flask import abort, jsonify, render_template, request
from werkzeug.utils import secure_filename

from .browser import make_breadcrumb, resolve_path
from .final_spectrum import (
    build_both_plot,
    build_model_summary_sections,
    build_normalized_plot,
    build_observed_overlay_trace,
    discover_final_spectrum_files,
    fin_file_label,
    fit_model_to_observed,
    load_obs_spectrum,
    read_model,
    spectrum_data_rows,
)
from .observed_spectrum import (
    generate_upload_token,
    is_valid_upload_token,
    list_upload_manifests,
    parse_uploaded_spectrum,
    read_upload_manifest,
    remove_upload_bundle,
    write_upload_manifest,
)
from .parsers.common import format_number
from .upload_views import _upload_entry_for_display
from .view_common import (
    _collect_obs_tokens,
    _collect_quick_links,
    _model_root_relpath,
    _normalize_fit_bounds,
    _normalize_fit_wavelength_range,
    _normalize_spectrum_mode,
    _normalize_transform_params,
    _spectrum_lambda_bounds,
    _spectrum_link_context,
    _spectrum_redirect,
    _spectrum_url,
    _upload_root,
    _viewer_config,
    bp,
)

@bp.route("/spectrum-upload/<path:path>", methods=["POST"])
def spectrum_upload(path: str):
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))
    lambda_min, lambda_max = _spectrum_lambda_bounds(config)

    try:
        target = resolve_path(basepath, path)
    except FileNotFoundError:
        abort(404)
    if not target.is_dir():
        abort(404)

    model_root = _model_root_relpath(path, basepath)
    if not model_root:
        abort(404)
    model_dir = resolve_path(basepath, model_root)
    spectrum_files = discover_final_spectrum_files(model_dir)
    if spectrum_files is None:
        abort(404)

    fin_files = [entry.name for entry in spectrum_files["fin_files"]]
    if not fin_files:
        abort(404)

    selected_fin = request.form.get("fin", "").strip()
    if selected_fin not in fin_files:
        selected_fin = fin_files[0]
    view_mode = _normalize_spectrum_mode(request.form.get("mode"))
    current_obs_tokens = _collect_obs_tokens(request.form.getlist("obs"))
    transform_params = _normalize_transform_params(request.form.to_dict(flat=True))
    fit_wavelength_inputs = {
        "min": str(request.form.get("fit_lambda_min", "")).strip(),
        "max": str(request.form.get("fit_lambda_max", "")).strip(),
    }

    uploaded = request.files.get("observed_file")
    if uploaded is None or not uploaded.filename:
        return _spectrum_redirect(
            model_root,
            fin=selected_fin,
            mode=view_mode,
            obs_tokens=current_obs_tokens,
            upload_error="No observed spectrum file was selected.",
            transform_params=transform_params,
            fit_wavelength_inputs=fit_wavelength_inputs,
        )

    requested_flux_mode = str(request.form.get("flux_mode", "auto")).strip().lower()
    upload_root = _upload_root(config)
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
        return _spectrum_redirect(
            model_root,
            fin=selected_fin,
            mode=view_mode,
            obs_tokens=current_obs_tokens,
            upload_error=f"Uploaded spectrum could not be parsed: {exc}",
            transform_params=transform_params,
            fit_wavelength_inputs=fit_wavelength_inputs,
        )

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

    selected_tokens = _collect_obs_tokens(current_obs_tokens + [token])
    return _spectrum_redirect(
        model_root,
        fin=selected_fin,
        mode=view_mode,
        obs_tokens=selected_tokens,
        transform_params=transform_params,
        fit_wavelength_inputs=fit_wavelength_inputs,
    )


@bp.route("/spectrum-upload/remove/<path:path>", methods=["POST"])
def spectrum_upload_remove(path: str):
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))

    try:
        target = resolve_path(basepath, path)
    except FileNotFoundError:
        abort(404)
    if not target.is_dir():
        abort(404)

    model_root = _model_root_relpath(path, basepath)
    if not model_root:
        abort(404)
    model_dir = resolve_path(basepath, model_root)
    spectrum_files = discover_final_spectrum_files(model_dir)
    if spectrum_files is None:
        abort(404)
    fin_files = [entry.name for entry in spectrum_files["fin_files"]]
    if not fin_files:
        abort(404)

    selected_fin = request.form.get("fin", "").strip()
    if selected_fin not in fin_files:
        selected_fin = fin_files[0]
    view_mode = _normalize_spectrum_mode(request.form.get("mode"))
    transform_params = _normalize_transform_params(request.form.to_dict(flat=True))
    fit_wavelength_inputs = {
        "min": str(request.form.get("fit_lambda_min", "")).strip(),
        "max": str(request.form.get("fit_lambda_max", "")).strip(),
    }

    token = request.form.get("token", "").strip() or request.form.get("obs", "").strip()
    upload_root = _upload_root(config)
    if is_valid_upload_token(token) and read_upload_manifest(upload_root, token) is not None:
        remove_upload_bundle(upload_root, token)

    remaining = _collect_obs_tokens(request.form.getlist("obs"))
    remaining = [item for item in remaining if item != token]
    return _spectrum_redirect(
        model_root,
        fin=selected_fin,
        mode=view_mode,
        obs_tokens=remaining,
        transform_params=transform_params,
        fit_wavelength_inputs=fit_wavelength_inputs,
    )


@bp.route("/spectrum-fit/<path:path>", methods=["POST"])
def spectrum_fit(path: str):
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))
    lambda_min, lambda_max = _spectrum_lambda_bounds(config)

    try:
        target = resolve_path(basepath, path)
    except FileNotFoundError:
        abort(404)
    if not target.is_dir():
        abort(404)

    model_root = _model_root_relpath(path, basepath)
    if not model_root:
        abort(404)
    model_dir = resolve_path(basepath, model_root)
    spectrum_files = discover_final_spectrum_files(model_dir)
    if spectrum_files is None:
        abort(404)
    fin_files = [entry.name for entry in spectrum_files["fin_files"]]
    if not fin_files:
        abort(404)

    selected_fin = request.form.get("fin", "").strip()
    if selected_fin not in fin_files:
        selected_fin = fin_files[0]
    view_mode = _normalize_spectrum_mode(request.form.get("mode"))
    selected_obs_tokens = _collect_obs_tokens(request.form.getlist("obs"))
    transform_params = _normalize_transform_params(request.form.to_dict(flat=True))
    fit_bounds = _normalize_fit_bounds(request.form.to_dict(flat=True), mode=view_mode)
    async_requested = (
        request.form.get("async", "").strip() == "1"
        or request.headers.get("X-Requested-With", "").strip().lower() == "xmlhttprequest"
    )
    fit_wavelength_inputs = {
        "min": str(request.form.get("fit_lambda_min", "")).strip(),
        "max": str(request.form.get("fit_lambda_max", "")).strip(),
    }
    fit_wavelength_range, fit_wavelength_error = _normalize_fit_wavelength_range(
        request.form.to_dict(flat=True),
        configured_min=lambda_min,
        configured_max=lambda_max,
    )
    if fit_wavelength_error:
        if async_requested:
            return jsonify({"ok": False, "error": fit_wavelength_error}), 400
        return _spectrum_redirect(
            model_root,
            fin=selected_fin,
            mode=view_mode,
            obs_tokens=selected_obs_tokens,
            upload_error=fit_wavelength_error,
            transform_params=transform_params,
            fit_wavelength_inputs=fit_wavelength_inputs,
        )
    effective_lambda_min = fit_wavelength_range[0] if fit_wavelength_range is not None else lambda_min
    effective_lambda_max = fit_wavelength_range[1] if fit_wavelength_range is not None else lambda_max

    def fit_error_response(message: str, *, status_code: int = 400):
        if async_requested:
            return jsonify({"ok": False, "error": message}), status_code
        return _spectrum_redirect(
            model_root,
            fin=selected_fin,
            mode=view_mode,
            obs_tokens=selected_obs_tokens,
            upload_error=message,
            transform_params=transform_params,
            fit_wavelength_inputs=fit_wavelength_inputs,
        )

    fit_token = request.form.get("fit_obs_token", "").strip()
    if not is_valid_upload_token(fit_token):
        return fit_error_response("Choose an observed overlay to fit.")
    if fit_token not in selected_obs_tokens:
        return fit_error_response("The selected observed overlay is not currently active.")

    upload_root = _upload_root(config)
    entries = {str(item.get("token", "")): item for item in list_upload_manifests(upload_root)}
    selected_entry = entries.get(fit_token)
    if selected_entry is None:
        return fit_error_response("Selected observed overlay is no longer available.")

    stored_name = str(selected_entry.get("stored_name", ""))
    source_path = upload_root / fit_token / stored_name if stored_name else None
    if source_path is None or not source_path.is_file():
        return fit_error_response("Selected observed overlay file is missing.")

    upload_flux_mode = str(selected_entry.get("requested_flux_mode", "auto")).strip().lower() or "auto"
    try:
        observed = parse_uploaded_spectrum(
            source_path,
            flux_mode=upload_flux_mode,
            lambda_min=effective_lambda_min,
            lambda_max=effective_lambda_max,
        )
    except Exception as exc:
        return fit_error_response(f"Could not load selected observed overlay: {exc}")
    observed["name"] = str(selected_entry.get("filename", source_path.name))

    continuum = load_obs_spectrum(
        Path(spectrum_files["obs_cont"]),
        lambda_min=effective_lambda_min,
        lambda_max=effective_lambda_max,
    )
    final = load_obs_spectrum(
        Path(spectrum_files["obs_dir"]) / selected_fin,
        lambda_min=effective_lambda_min,
        lambda_max=effective_lambda_max,
    )

    initial_params = {
        "redshift": transform_params["redshift"],
        "broadening_km_s": transform_params["broadening_km_s"],
        "ebv": transform_params["ebv"],
        "distance_kpc": transform_params["distance_kpc"],
    }
    best_params, metrics, fit_error = fit_model_to_observed(
        continuum,
        final,
        observed,
        mode=view_mode,
        initial_params=initial_params,
        bounds_override=fit_bounds,
    )
    if fit_error or best_params is None:
        return fit_error_response(f"Fit failed: {fit_error or 'unknown error'}")

    fitted_transform = {
        "redshift": best_params["redshift"],
        "broadening_km_s": best_params["broadening_km_s"],
        "ebv": best_params["ebv"],
        "distance_kpc": best_params["distance_kpc"],
    }
    label = str(observed.get("name", fit_token))
    if view_mode == "both":
        fit_notice = (
            f"Fit completed vs {label}: "
            f"z={format_number(best_params['redshift'])}, "
            f"sigma={format_number(best_params['broadening_km_s'])} km/s, "
            f"E(B-V)={format_number(best_params['ebv'])}, "
            f"d={format_number(best_params['distance_kpc'])} kpc."
        )
    else:
        fit_notice = (
            f"Fit completed vs {label}: "
            f"z={format_number(best_params['redshift'])}, "
            f"sigma={format_number(best_params['broadening_km_s'])} km/s."
        )
    if isinstance(metrics, dict):
        rmse = metrics.get("rmse")
        nfev = metrics.get("nfev")
        if isinstance(rmse, int | float) and math.isfinite(float(rmse)):
            fit_notice += f" RMSE={format_number(float(rmse))}."
        if isinstance(nfev, int):
            fit_notice += f" Iter={nfev}."

    if async_requested:
        payload: dict[str, object] = {
            "ok": True,
            "fit_notice": fit_notice,
            "transform_params": fitted_transform,
        }
        if isinstance(metrics, dict):
            payload["metrics"] = metrics
        return jsonify(payload)

    return _spectrum_redirect(
        model_root,
        fin=selected_fin,
        mode=view_mode,
        obs_tokens=selected_obs_tokens,
        transform_params=fitted_transform,
        fit_notice=fit_notice,
        fit_wavelength_inputs=fit_wavelength_inputs,
    )


@bp.route("/spectrum/<path:path>")
def spectrum(path: str):
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))
    lambda_min, lambda_max = _spectrum_lambda_bounds(config)

    try:
        target = resolve_path(basepath, path)
    except FileNotFoundError:
        abort(404)
    if not target.is_dir():
        abort(404)

    model_root = _model_root_relpath(path, basepath)
    if not model_root:
        abort(404)
    model_dir = resolve_path(basepath, model_root)

    spectrum_files = discover_final_spectrum_files(model_dir)
    if spectrum_files is None:
        abort(404)

    fin_files = [entry.name for entry in spectrum_files["fin_files"]]
    if not fin_files:
        abort(404)

    selected_fin = request.args.get("fin", "").strip()
    if selected_fin not in fin_files:
        selected_fin = fin_files[0]

    view_mode = _normalize_spectrum_mode(request.args.get("mode"))
    transform_params = _normalize_transform_params(request.args.to_dict(flat=True))
    selected_obs_tokens = _collect_obs_tokens(request.args.getlist("obs"))
    fit_wavelength_inputs = {
        "min": str(request.args.get("fit_lambda_min", "")).strip(),
        "max": str(request.args.get("fit_lambda_max", "")).strip(),
    }

    warnings: list[str] = []
    upload_error = request.args.get("upload_error", "").strip()
    if upload_error:
        warnings.append(upload_error)
    fit_notice = request.args.get("fit_notice", "").strip()

    upload_root = _upload_root(config)
    upload_entries = list_upload_manifests(upload_root)
    available_upload_entries = upload_entries

    available_by_token = {str(entry.get("token", "")): entry for entry in available_upload_entries}
    selected_observed_uploads: list[dict[str, object]] = []
    selected_parsed: list[dict[str, object]] = []
    for token in selected_obs_tokens:
        entry = available_by_token.get(token)
        if entry is None:
            warnings.append(f"Uploaded spectrum token '{token}' is not available.")
            continue
        stored_name = str(entry.get("stored_name", ""))
        source_path = upload_root / token / stored_name if stored_name else None
        if source_path is None or not source_path.is_file():
            warnings.append(f"Uploaded spectrum '{entry.get('filename', token)}' file is missing.")
            continue
        upload_flux_mode = str(entry.get("requested_flux_mode", "auto")).strip().lower() or "auto"
        try:
            parsed = parse_uploaded_spectrum(
                source_path,
                flux_mode=upload_flux_mode,
                lambda_min=lambda_min,
                lambda_max=lambda_max,
            )
        except Exception as exc:
            warnings.append(f"Uploaded spectrum '{entry.get('filename', source_path.name)}' failed to load: {exc}")
            continue
        parsed["name"] = str(entry.get("filename", source_path.name))
        parsed["token"] = token

        selected_parsed.append(parsed)
        selected_observed_uploads.append(_upload_entry_for_display(entry))
        for warning in parsed.get("warnings", []):
            warnings.append(f"Uploaded {entry.get('filename', source_path.name)}: {warning}")

    continuum = load_obs_spectrum(
        Path(spectrum_files["obs_cont"]),
        lambda_min=lambda_min,
        lambda_max=lambda_max,
    )
    final = load_obs_spectrum(
        Path(spectrum_files["obs_dir"]) / selected_fin,
        lambda_min=lambda_min,
        lambda_max=lambda_max,
    )
    plot_data = build_both_plot(continuum, final) if view_mode == "both" else build_normalized_plot(continuum, final)

    if plot_data is None:
        warnings.append("Plot generation failed: insufficient overlapping spectrum points.")
    else:
        for observed_data in selected_parsed:
            observed_trace, observed_warning = build_observed_overlay_trace(observed_data, mode=view_mode)
            if observed_warning:
                warnings.append(observed_warning)
                continue
            if observed_trace is not None:
                plot_data["data"].append(observed_trace)

    breadcrumb = make_breadcrumb(model_root)
    if breadcrumb:
        breadcrumb[-1]["path"] = model_root
        breadcrumb.append({"name": "Final Spectrum", "path": None})

    model_summary_sections = build_model_summary_sections(read_model(model_dir))
    fin_options = [{"name": name, "label": fin_file_label(name)} for name in fin_files]
    selected_lookup = set(selected_obs_tokens)
    available_uploads = []
    for entry in available_upload_entries:
        display = _upload_entry_for_display(entry)
        token = str(display.get("token", ""))
        label = str(display.get("filename", token))
        mode_label = str(display.get("flux_mode", ""))
        type_label = str(display.get("observation_type", ""))
        created_label = str(display.get("created_at", ""))
        if type_label:
            display["label"] = f"{label} [{mode_label}, {type_label}] {created_label}".strip()
        else:
            display["label"] = f"{label} [{mode_label}] {created_label}".strip()
        display["selected"] = token in selected_lookup
        available_uploads.append(display)

    mode_urls = {
        "both": _spectrum_url(
            model_root,
            fin=selected_fin,
            mode="both",
            obs_tokens=selected_obs_tokens,
            transform_params=transform_params,
            fit_wavelength_inputs=fit_wavelength_inputs,
        ),
        "normalized": _spectrum_url(
            model_root,
            fin=selected_fin,
            mode="normalized",
            obs_tokens=selected_obs_tokens,
            transform_params=transform_params,
            fit_wavelength_inputs=fit_wavelength_inputs,
        ),
    }
    clear_overlay_url = _spectrum_url(
        model_root,
        fin=selected_fin,
        mode=view_mode,
        obs_tokens=[],
        transform_params=transform_params,
        fit_wavelength_inputs=fit_wavelength_inputs,
    )

    fit_candidates: list[dict[str, str]] = []
    for parsed in selected_parsed:
        token = str(parsed.get("token", ""))
        if not token:
            continue
        flux_mode = str(parsed.get("flux_mode", "")).strip().lower()
        observation_type = str(parsed.get("observation_type", "spectrum")).strip().lower()
        if view_mode == "both" and flux_mode != "absolute":
            continue
        if view_mode == "normalized" and flux_mode != "normalized":
            continue
        label = str(parsed.get("name", token))
        fit_candidates.append({"token": token, "label": f"{label} [{flux_mode}, {observation_type}]"})

    selected_fit_token = request.args.get("fit_obs", "").strip()
    if not any(item["token"] == selected_fit_token for item in fit_candidates):
        selected_fit_token = fit_candidates[0]["token"] if fit_candidates else ""

    fit_bounds = _normalize_fit_bounds(request.args.to_dict(flat=True), mode=view_mode)

    context = {
        "path": model_root,
        "breadcrumb": breadcrumb,
        "basepath": basepath,
        "show_all": bool(config.get("show_all", False)),
        "view_query": {},
        "quick_links": _collect_quick_links(basepath, model_root),
        "spectrum_view": _spectrum_link_context(basepath, model_root),
    }
    return render_template(
        "spectrum_view.html",
        model_name=model_dir.name,
        selected_fin=selected_fin,
        fin_options=fin_options,
        mode=view_mode,
        plot_data=plot_data,
        model_summary_sections=model_summary_sections,
        spectrum_summary_rows=spectrum_data_rows(continuum, final),
        warnings=warnings,
        fit_notice=fit_notice,
        obs_tokens=selected_obs_tokens,
        available_uploads=available_uploads,
        selected_observed_uploads=selected_observed_uploads,
        fit_candidates=fit_candidates,
        selected_fit_token=selected_fit_token,
        fit_bounds=fit_bounds,
        fit_wavelength_inputs=fit_wavelength_inputs,
        upload_flux_mode="auto",
        mode_urls=mode_urls,
        clear_overlay_url=clear_overlay_url,
        transform_params=transform_params,
        **context,
    )

