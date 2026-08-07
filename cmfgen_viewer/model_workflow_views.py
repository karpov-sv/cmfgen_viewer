"""Routes for guarded, externally executed LTE/hydro workflows."""

from __future__ import annotations

from flask import abort, current_app, redirect, render_template, request, url_for

from .browser import make_breadcrumb
from .model_workflow import (
    LTE_QUICK_CONTROLS,
    RESULT_QUICK_CONTROLS,
    ModelWorkflowError,
    inspect_lte_hydro_workflow,
    prepare_lte_hydro_workspace,
    promote_lte_hydro_results,
    save_lte_quick_controls,
    save_result_quick_controls,
)
from .summary_cache import delete_model_summary_entries
from .view_common import _viewer_config, bp


def _breadcrumb(source_path: str) -> list[dict[str, str | None]]:
    breadcrumb = make_breadcrumb(source_path)
    if breadcrumb:
        breadcrumb[-1]["path"] = source_path
    breadcrumb.append({"name": "LTE / hydro workflow", "path": None})
    return breadcrumb


@bp.route("/model-actions/lte-hydro/<path:source_path>", methods=["GET", "POST"])
def model_lte_hydro(source_path: str):
    config = _viewer_config()
    if not bool(config.get("read_write_enabled", False)):
        abort(403)
    basepath = str(config.get("basepath", "."))
    error = ""
    message = str(request.args.get("message", "")).strip()
    submitted_controls: dict[str, str] = {}
    submitted_filename = ""
    submitted_card_key = "lte_quick_control_cards"
    try:
        if request.method == "POST":
            action = str(request.form.get("action", "")).strip().lower()
            if action == "prepare":
                prepare_lte_hydro_workspace(basepath, model_relpath=source_path)
                return redirect(
                    url_for(
                        "viewer.model_lte_hydro",
                        source_path=source_path,
                        message="LTE workspace prepared. No calculation was started.",
                    )
                )
            if action == "configure_lte":
                submitted_filename = str(request.form.get("control_file", "")).strip().upper()
                definitions = LTE_QUICK_CONTROLS.get(submitted_filename)
                if definitions is None:
                    abort(400)
                submitted_controls = {
                    definition["key"]: str(request.form.get(f"lte_value:{definition['key']}", ""))
                    for definition in definitions
                }
                saved = save_lte_quick_controls(
                    basepath,
                    model_relpath=source_path,
                    filename=submitted_filename,
                    expected_digest=str(request.form.get("expected_digest", "")),
                    values=submitted_controls,
                )
                return redirect(
                    url_for(
                        "viewer.model_lte_hydro",
                        source_path=source_path,
                        message=(
                            f"Saved LTE controls in {submitted_filename}; checkpoint: "
                            f"lte/{saved['backup_relpath']}."
                        ),
                    )
                )
            if action == "configure_results":
                submitted_filename = str(request.form.get("control_file", "")).strip().upper()
                submitted_card_key = "result_quick_control_cards"
                definitions = RESULT_QUICK_CONTROLS.get(submitted_filename)
                if definitions is None:
                    abort(400)
                submitted_controls = {
                    definition["key"]: str(
                        request.form.get(f"result_value:{definition['key']}", "")
                    )
                    for definition in definitions
                }
                saved = save_result_quick_controls(
                    basepath,
                    model_relpath=source_path,
                    filename=submitted_filename,
                    expected_digest=str(request.form.get("expected_digest", "")),
                    values=submitted_controls,
                )
                return redirect(
                    url_for(
                        "viewer.model_lte_hydro",
                        source_path=source_path,
                        message=(
                            f"Saved result-review control in {submitted_filename}; checkpoint: "
                            f"lte/{saved['backup_relpath']}."
                        ),
                        _anchor="result-review",
                    )
                )
            if action == "promote":
                if request.form.get("results_checked") != "1":
                    raise ModelWorkflowError(
                        "Confirm that RVSIG_COL_NEW has the intended luminosity and VADAT contains the final RMAX."
                    )
                result = promote_lte_hydro_results(basepath, model_relpath=source_path)
                try:
                    delete_model_summary_entries(
                        str(config.get("summary_cache_db", "model_summary_cache.sqlite")),
                        basepath=basepath,
                        relpaths=[source_path],
                    )
                except Exception:
                    current_app.logger.warning(
                        "Failed to invalidate the model summary cache after promoting LTE/hydro outputs for %s",
                        source_path,
                        exc_info=True,
                    )
                return redirect(
                    url_for(
                        "viewer.model_lte_hydro",
                        source_path=source_path,
                        message=f"Results promoted; previous files are in {result['backup_relpath']}.",
                    )
                )
            abort(400)
        state = inspect_lte_hydro_workflow(basepath, model_relpath=source_path)
    except ModelWorkflowError as exc:
        if request.method == "GET":
            abort(404)
        error = str(exc)
        try:
            state = inspect_lte_hydro_workflow(basepath, model_relpath=source_path)
        except ModelWorkflowError:
            abort(404)
        for card in state.get(submitted_card_key, []):
            if card["file_relpath"] != submitted_filename:
                continue
            for field in card["fields"]:
                key = str(field["key"])
                if key in submitted_controls:
                    field["value"] = submitted_controls[key]

    return render_template(
        "model_lte_hydro.html",
        source_path=source_path,
        state=state,
        message=message,
        error=error,
        breadcrumb=_breadcrumb(source_path),
    )
