"""Model summary and multi-model spectrum routes."""

from __future__ import annotations

from pathlib import Path
import time

from flask import abort, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from .browser import is_model_context_path, make_breadcrumb, resolve_path
from .final_spectrum import (
    build_both_plot,
    build_normalized_plot,
    build_observed_overlay_trace,
    discover_final_spectrum_files,
    load_obs_spectrum,
    read_model,
)
from .observed_spectrum import (
    generate_upload_token,
    list_upload_manifests,
    parse_uploaded_spectrum,
    remove_upload_bundle,
    write_upload_manifest,
)
from .summary_cache import list_model_summaries, upsert_model_summary
from .upload_views import _upload_entry_for_display
from .view_common import (
    SUMMARY_COLUMNS,
    _build_summary_row,
    _bulk_spectra_redirect,
    _bulk_spectra_url,
    _collect_obs_tokens,
    _collect_quick_links,
    _collect_rel_paths,
    _load_mamajek_hr_overlay,
    _normalize_spectrum_mode,
    _resolve_selected_model_dirs,
    _spectrum_lambda_bounds,
    _spectrum_link_context,
    _upload_root,
    _viewer_config,
    bp,
)

@bp.route("/bulk/summarize/", defaults={"path": ""}, methods=["POST"])
@bp.route("/bulk/summarize/<path:path>", methods=["POST"])
def bulk_summarize(path: str):
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))
    summary_cache_db = str(config.get("summary_cache_db", "model_summary_cache.sqlite"))

    try:
        directory = resolve_path(basepath, path)
    except FileNotFoundError:
        abort(404)
    if not directory.is_dir():
        abort(404)

    if is_model_context_path(str(directory)):
        abort(400)

    selected_paths = _collect_rel_paths(request.form.getlist("selected_models"))
    if not selected_paths:
        return redirect(url_for("viewer.view", path=path))

    rows: list[dict[str, object]] = []
    skipped: list[list[str]] = []
    cache_update_errors = 0
    for rel in selected_paths:
        try:
            target = resolve_path(basepath, rel)
        except FileNotFoundError:
            skipped.append([rel, "Not found"])
            continue
        if not target.is_dir():
            skipped.append([rel, "Not a directory"])
            continue
        try:
            target.relative_to(directory)
        except ValueError:
            skipped.append([rel, "Outside current folder"])
            continue

        vadat_file = target / "VADAT"
        mod_sum_file = target / "MOD_SUM"
        if not vadat_file.is_file() or not mod_sum_file.is_file():
            skipped.append([rel, "Missing VADAT or MOD_SUM"])
            continue

        model = read_model(target)
        mod_sum_mtime = mod_sum_file.stat().st_mtime
        row_values = _build_summary_row(model, mod_sum_mtime=mod_sum_mtime)
        rows.append(
            {
                "values": row_values,
                "path": rel,
            }
        )
        try:
            upsert_model_summary(
                summary_cache_db,
                basepath=basepath,
                relpath=rel,
                model_dir=target,
                model_name=str(model.get("name", target.name)),
                values=row_values,
                vadat_mtime=vadat_file.stat().st_mtime,
                mod_sum_mtime=mod_sum_mtime,
            )
        except Exception:
            cache_update_errors += 1

    breadcrumb = make_breadcrumb(path)
    if breadcrumb:
        breadcrumb[-1]["path"] = path
        breadcrumb.append({"name": "Summarize", "path": None})
    context = {
        "path": path,
        "breadcrumb": breadcrumb,
        "basepath": basepath,
        "show_all": bool(config.get("show_all", False)),
        "view_query": {},
        "quick_links": _collect_quick_links(basepath, path),
        "spectrum_view": _spectrum_link_context(basepath, path),
    }
    cache_notice = ""
    if cache_update_errors:
        cache_notice = f"Summary cache update failed for {cache_update_errors} model(s)."
    return render_template(
        "models_summary.html",
        columns=SUMMARY_COLUMNS,
        rows=rows,
        skipped=skipped,
        selected_count=len(selected_paths),
        summary_scope="bulk",
        cache_notice=cache_notice,
        hr_overlay=_load_mamajek_hr_overlay(),
        **context,
    )


@bp.route("/models/")
def global_models_summary():
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))
    summary_cache_db = str(config.get("summary_cache_db", "model_summary_cache.sqlite"))

    rows: list[dict[str, object]] = []
    cache_notice = ""
    try:
        rows = list_model_summaries(
            summary_cache_db,
            basepath=basepath,
            expected_columns=len(SUMMARY_COLUMNS),
        )
    except Exception:
        cache_notice = "Failed to read summary cache."

    context = {
        "path": "",
        "breadcrumb": [
            {"name": "ROOT", "path": ""},
            {"name": "Models", "path": None},
        ],
        "basepath": basepath,
        "show_all": bool(config.get("show_all", False)),
        "view_query": {},
        "quick_links": [],
        "spectrum_view": None,
    }
    return render_template(
        "models_summary.html",
        columns=SUMMARY_COLUMNS,
        rows=rows,
        skipped=[],
        selected_count=len(rows),
        summary_scope="global",
        cache_notice=cache_notice,
        hr_overlay=_load_mamajek_hr_overlay(),
        **context,
    )


@bp.route("/bulk/spectra/", defaults={"path": ""}, methods=["GET", "POST"])
@bp.route("/bulk/spectra/<path:path>", methods=["GET", "POST"])
def bulk_spectra(path: str):
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))
    lambda_min, lambda_max = _spectrum_lambda_bounds(config)

    try:
        directory = resolve_path(basepath, path)
    except FileNotFoundError:
        abort(404)
    if not directory.is_dir():
        abort(404)

    if is_model_context_path(str(directory)):
        abort(400)

    selected_paths = _collect_rel_paths(request.values.getlist("selected_models"))
    if not selected_paths:
        return redirect(url_for("viewer.view", path=path))

    view_mode = _normalize_spectrum_mode(request.values.get("mode"))
    selected_obs_tokens = _collect_obs_tokens(request.values.getlist("obs"))

    warnings: list[str] = []
    upload_error = request.values.get("upload_error", "").strip()
    if upload_error:
        warnings.append(upload_error)

    valid_dirs, skipped = _resolve_selected_model_dirs(basepath, directory, selected_paths)

    combined_traces: list[dict[str, object]] = []
    plotted_models: list[dict[str, str]] = []
    plot_layout: dict[str, object] | None = None
    plot_config: dict[str, object] | None = None
    default_x_scale = "log"
    default_y_scale = "log" if view_mode == "both" else "linear"

    for rel, target in valid_dirs:
        spectrum_files = discover_final_spectrum_files(target)
        if spectrum_files is None:
            skipped.append([rel, "Missing obs_cont and/or obs_fin* files"])
            continue

        fin_files = spectrum_files.get("fin_files")
        if not isinstance(fin_files, list) or not fin_files:
            skipped.append([rel, "No obs_fin* files found"])
            continue
        first_fin = fin_files[0]
        if not isinstance(first_fin, Path):
            skipped.append([rel, "Invalid obs_fin selection"])
            continue

        try:
            continuum = load_obs_spectrum(
                Path(spectrum_files["obs_cont"]),
                lambda_min=lambda_min,
                lambda_max=lambda_max,
            )
            final = load_obs_spectrum(
                first_fin,
                lambda_min=lambda_min,
                lambda_max=lambda_max,
            )
        except Exception as exc:
            skipped.append([rel, f"Spectrum parse failed: {exc}"])
            continue

        model_plot = build_both_plot(continuum, final) if view_mode == "both" else build_normalized_plot(continuum, final)
        if model_plot is None:
            skipped.append([rel, "Insufficient overlapping points for plotting"])
            continue

        traces = model_plot.get("data")
        if not isinstance(traces, list) or not traces:
            skipped.append([rel, "No plot traces were produced"])
            continue

        if plot_layout is None:
            layout_raw = model_plot.get("layout")
            config_raw = model_plot.get("config")
            plot_layout = dict(layout_raw) if isinstance(layout_raw, dict) else {}
            plot_config = dict(config_raw) if isinstance(config_raw, dict) else {}
            default_x_scale = str(model_plot.get("default_x_scale", default_x_scale))
            default_y_scale = str(model_plot.get("default_y_scale", default_y_scale))

        before_count = len(combined_traces)
        model_name = target.name
        for trace_index, trace in enumerate(traces):
            if not isinstance(trace, dict):
                continue

            cloned = dict(trace)
            x_values = trace.get("x")
            y_values = trace.get("y")
            if isinstance(x_values, list):
                cloned["x"] = x_values[:]
            if isinstance(y_values, list):
                cloned["y"] = y_values[:]

            line = cloned.get("line")
            if isinstance(line, dict):
                line = dict(line)
            else:
                line = {}
            line.pop("color", None)
            meta = cloned.get("meta")
            if isinstance(meta, dict):
                meta = dict(meta)
            else:
                meta = {}
            meta["transform_target"] = "model"

            if view_mode == "both":
                if trace_index == 0:
                    cloned["name"] = f"{model_name} final ({first_fin.name})"
                    line["width"] = 1.4
                    meta["plot_role"] = "final"
                else:
                    cloned["name"] = f"{model_name} continuum"
                    line["width"] = 1.1
                    line["dash"] = "dot"
                    meta["plot_role"] = "continuum"
            else:
                cloned["name"] = f"{model_name} ({first_fin.name}/obs_cont)"
                line["width"] = 1.4
                meta["plot_role"] = "final"

            cloned["line"] = line
            cloned["meta"] = meta
            combined_traces.append(cloned)

        if len(combined_traces) > before_count:
            plotted_models.append({"name": model_name, "path": rel, "fin": first_fin.name})

    upload_root = _upload_root(config)
    upload_entries = list_upload_manifests(upload_root)
    available_by_token = {str(entry.get("token", "")): entry for entry in upload_entries}

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

        selected_parsed.append(parsed)
        selected_observed_uploads.append(_upload_entry_for_display(entry))
        for warning in parsed.get("warnings", []):
            warnings.append(f"Uploaded {entry.get('filename', source_path.name)}: {warning}")

    plot_data: dict[str, object] | None = None
    if combined_traces:
        plot_data = {
            "data": combined_traces,
            "layout": plot_layout or {},
            "config": plot_config or {},
            "default_x_scale": default_x_scale,
            "default_y_scale": default_y_scale,
        }
        for observed_data in selected_parsed:
            observed_trace, observed_warning = build_observed_overlay_trace(observed_data, mode=view_mode)
            if observed_warning:
                warnings.append(observed_warning)
                continue
            if observed_trace is not None:
                plot_data["data"].append(observed_trace)
    else:
        warnings.append("No selected models produced plottable final spectra.")

    selected_lookup = set(selected_obs_tokens)
    available_uploads = []
    for entry in upload_entries:
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
        "both": _bulk_spectra_url(path, selected_models=selected_paths, mode="both", obs_tokens=selected_obs_tokens),
        "normalized": _bulk_spectra_url(path, selected_models=selected_paths, mode="normalized", obs_tokens=selected_obs_tokens),
    }
    clear_overlay_url = _bulk_spectra_url(path, selected_models=selected_paths, mode=view_mode, obs_tokens=[])

    breadcrumb = make_breadcrumb(path)
    if breadcrumb:
        breadcrumb[-1]["path"] = path
        breadcrumb.append({"name": "Bulk Spectra", "path": None})

    context = {
        "path": path,
        "breadcrumb": breadcrumb,
        "basepath": basepath,
        "show_all": bool(config.get("show_all", False)),
        "view_query": {},
        "quick_links": _collect_quick_links(basepath, path),
        "spectrum_view": _spectrum_link_context(basepath, path),
    }
    return render_template(
        "bulk_spectrum_view.html",
        selected_models=selected_paths,
        selected_count=len(selected_paths),
        plotted_count=len(plotted_models),
        plotted_models=plotted_models,
        skipped=skipped,
        mode=view_mode,
        plot_data=plot_data,
        warnings=warnings,
        obs_tokens=selected_obs_tokens,
        available_uploads=available_uploads,
        selected_observed_uploads=selected_observed_uploads,
        upload_flux_mode="auto",
        mode_urls=mode_urls,
        clear_overlay_url=clear_overlay_url,
        **context,
    )


@bp.route("/bulk/spectrum-upload/", defaults={"path": ""}, methods=["POST"])
@bp.route("/bulk/spectrum-upload/<path:path>", methods=["POST"])
def bulk_spectrum_upload(path: str):
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))
    lambda_min, lambda_max = _spectrum_lambda_bounds(config)

    try:
        directory = resolve_path(basepath, path)
    except FileNotFoundError:
        abort(404)
    if not directory.is_dir():
        abort(404)
    if is_model_context_path(str(directory)):
        abort(400)

    selected_paths = _collect_rel_paths(request.form.getlist("selected_models"))
    if not selected_paths:
        return redirect(url_for("viewer.view", path=path))

    view_mode = _normalize_spectrum_mode(request.form.get("mode"))
    current_obs_tokens = _collect_obs_tokens(request.form.getlist("obs"))

    uploaded = request.files.get("observed_file")
    if uploaded is None or not uploaded.filename:
        return _bulk_spectra_redirect(
            path,
            selected_models=selected_paths,
            mode=view_mode,
            obs_tokens=current_obs_tokens,
            upload_error="No observed spectrum file was selected.",
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
        return _bulk_spectra_redirect(
            path,
            selected_models=selected_paths,
            mode=view_mode,
            obs_tokens=current_obs_tokens,
            upload_error=f"Uploaded spectrum could not be parsed: {exc}",
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
    return _bulk_spectra_redirect(path, selected_models=selected_paths, mode=view_mode, obs_tokens=selected_tokens)


