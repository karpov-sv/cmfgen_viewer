"""Guarded routes for operations that create or modify CMFGEN models."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json

from flask import abort, current_app, redirect, render_template, request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .model_full_cleanup import FullCleanupError, build_full_cleanup_plan, run_full_cleanup
from .model_reseed import build_reseed_plan, run_reseed_plan

from .browser import is_model_directory, make_breadcrumb, resolve_path
from .model_staging import (
    ModelStagingError,
    cleanup_model_directory,
    create_model_from_solution,
    is_sn_model_directory,
    plan_model_cleanup,
    plan_model_from_solution,
    rename_model_directory,
)
from .summary_cache import delete_model_summary_entries, relocate_model_summary_entry
from .view_common import _notification_url, _viewer_config, bp


def _default_model_destination(basepath: str, source_relpath: str) -> str:
    source_rel = Path(source_relpath)
    parent = source_rel.parent
    base = Path(basepath).expanduser().resolve()
    for index in range(1, 1000):
        suffix = "_new" if index == 1 else f"_new_{index}"
        candidate = parent / f"{source_rel.name}{suffix}"
        target = base.joinpath(*candidate.parts)
        if not target.exists() and not target.is_symlink():
            return candidate.as_posix()
    return (parent / f"{source_rel.name}_new").as_posix()


def _create_model_breadcrumb(source_relpath: str) -> list[dict[str, str | None]]:
    breadcrumb = make_breadcrumb(source_relpath)
    if breadcrumb:
        breadcrumb[-1]["path"] = source_relpath
    breadcrumb.append({"name": "Create new model", "path": None})
    return breadcrumb


def _model_action_breadcrumb(source_relpath: str, action_name: str) -> list[dict[str, str | None]]:
    breadcrumb = make_breadcrumb(source_relpath)
    if breadcrumb:
        breadcrumb[-1]["path"] = source_relpath
    breadcrumb.append({"name": action_name, "path": None})
    return breadcrumb


@bp.route("/model-actions/out2in/<path:source_path>", methods=["GET", "POST"])
def model_out2in(source_path: str):
    config = _viewer_config()
    if not config.get("read_write_enabled", False):
        abort(403)
    try:
        source = resolve_path(str(config.get("basepath", ".")), source_path)
    except FileNotFoundError:
        abort(404)
    if not is_model_directory(source):
        abort(404)
    values = request.form if request.method == "POST" else request.args
    keep = (values.get("keep_large_files") == "1" if "recovery_setting" in values
            else bool(config.get("keep_large_files", False)))
    signer = URLSafeTimedSerializer(current_app.secret_key, salt="model-out2in")

    def review_data(plan):
        signature = hashlib.sha256(json.dumps({key: plan[key] for key in
            ("entries", "checkpoints", "keep_large_files")}, sort_keys=True).encode()).hexdigest()
        return {"model": str(source), "signature": signature}

    plan = build_reseed_plan(source, keep_large_files=keep)
    error = ""
    if request.method == "POST":
        try:
            if values.get("confirm_out2in") != "1":
                raise ValueError("Confirm replacing the initial inputs and retiring the listed checkpoints.")
            try:
                reviewed = signer.loads(values.get("review_token", ""), max_age=1800)
            except BadSignature as exc:
                raise ValueError("Out2in preview expired or is invalid; review the list again.") from exc
            if reviewed != review_data(plan):
                raise ValueError("Out2in files or recovery settings changed, or the preview belongs to another model; review again.")
            result = run_reseed_plan(plan)
            warnings = result["recovery"]["warnings"]
            return redirect(_notification_url("viewer.model_main_computation", source_path=source_path,
                message=f"Out2in refreshed {len(result['updated_inputs'])} initial inputs and retired "
                        f"{len(result['retired_checkpoints'])} binary checkpoints. The next main run starts from text inputs.",
                warning=" ".join(warnings)))
        except (ValueError, OSError) as exc:
            error = str(exc)
            plan = build_reseed_plan(source, keep_large_files=keep)
    token = signer.dumps(review_data(plan)) if plan["ready"] else ""
    return render_template("model_out2in.html", source_path=source_path, plan=plan,
        error=error, review_token=token,
        breadcrumb=_model_action_breadcrumb(source_path, "Outputs to inputs (out2in)"))


@bp.route("/model-actions/create/<path:source_path>", methods=["GET", "POST"])
def model_create_from_solution(source_path: str):
    config = _viewer_config()
    if not bool(config.get("read_write_enabled", False)):
        abort(403)
    basepath = str(config.get("basepath", "."))
    try:
        source = resolve_path(basepath, source_path)
    except FileNotFoundError:
        abort(404)
    if not is_model_directory(source):
        abort(404)

    source_error = ""
    if is_sn_model_directory(source):
        source_error = "Creating a model from an SN solution is not supported yet."

    destination_relpath = str(
        request.form.get("destination_relpath", "")
        if request.method == "POST"
        else request.args.get("destination", "")
    ).strip()
    if not destination_relpath:
        destination_relpath = _default_model_destination(basepath, source_path)

    action = str(request.form.get("action", "preview")).strip().lower()
    if request.method == "POST" and action not in {"preview", "create"}:
        abort(400)

    plan: dict[str, object] | None = None
    error = source_error
    if not error:
        try:
            plan = plan_model_from_solution(
                basepath,
                source_relpath=source_path,
                destination_relpath=destination_relpath,
                template_root=config.get("template_root"),
            )
            if request.method == "POST" and action == "create":
                created = create_model_from_solution(
                    basepath,
                    source_relpath=source_path,
                    destination_relpath=destination_relpath,
                    template_root=config.get("template_root"),
                )
                created_relpath = str(created["destination_relpath"])
                try:
                    delete_model_summary_entries(
                        str(config.get("summary_cache_db", "model_summary_cache.sqlite")),
                        basepath=basepath,
                        relpaths=[created_relpath],
                    )
                except Exception:
                    current_app.logger.warning(
                        "Failed to invalidate the model summary cache after creating %s",
                        created_relpath,
                        exc_info=True,
                    )
                return redirect(_notification_url("viewer.view", path=created_relpath, message="New model created from the selected solution."))
        except ModelStagingError as exc:
            error = str(exc)

    return render_template(
        "model_create.html",
        source_path=source_path,
        destination_relpath=destination_relpath,
        plan=plan,
        error=error,
        breadcrumb=_create_model_breadcrumb(source_path),
    )


@bp.route("/model-actions/rename/<path:source_path>", methods=["GET", "POST"])
def model_rename(source_path: str):
    config = _viewer_config()
    if not bool(config.get("read_write_enabled", False)):
        abort(403)
    basepath = str(config.get("basepath", "."))
    try:
        source = resolve_path(basepath, source_path)
    except FileNotFoundError:
        abort(404)
    if not is_model_directory(source):
        abort(404)

    if request.method == "POST":
        destination_relpath = str(request.form.get("destination_relpath", "")).strip()
    else:
        destination_relpath = source_path
    error = ""
    if request.method == "POST":
        try:
            renamed = rename_model_directory(
                basepath,
                source_relpath=source_path,
                destination_relpath=destination_relpath,
            )
            source_relpath = str(renamed["source_relpath"])
            destination_relpath = str(renamed["destination_relpath"])
            destination = Path(str(renamed["destination_path"]))
            summary_cache_db = str(config.get("summary_cache_db", "model_summary_cache.sqlite"))
            try:
                if (destination / "VADAT").is_file() and (destination / "MOD_SUM").is_file():
                    relocate_model_summary_entry(
                        summary_cache_db,
                        basepath=basepath,
                        source_relpath=source_relpath,
                        destination_relpath=destination_relpath,
                        model_dir=destination,
                        model_name=str(renamed["model_name"]),
                    )
                else:
                    delete_model_summary_entries(
                        summary_cache_db,
                        basepath=basepath,
                        relpaths=[source_relpath, destination_relpath],
                    )
            except Exception:
                current_app.logger.warning(
                    "Failed to update the model summary cache after renaming %s to %s",
                    source_relpath,
                    destination_relpath,
                    exc_info=True,
                )
            return redirect(_notification_url("viewer.view", path=destination_relpath, message="Model directory renamed or moved successfully."))
        except ModelStagingError as exc:
            error = str(exc)

    return render_template(
        "model_rename.html",
        source_path=source_path,
        destination_relpath=destination_relpath,
        error=error,
        breadcrumb=_model_action_breadcrumb(source_path, "Rename or move model"),
    )


@bp.route("/model-actions/cleanup/<path:source_path>", methods=["GET", "POST"])
def model_cleanup(source_path: str):
    config = _viewer_config()
    if not bool(config.get("read_write_enabled", False)):
        abort(403)
    basepath = str(config.get("basepath", "."))
    try:
        source = resolve_path(basepath, source_path)
    except FileNotFoundError:
        abort(404)
    if not is_model_directory(source):
        abort(404)

    error = ""
    result: dict[str, object] | None = None
    values = request.form if request.method == "POST" else request.args
    full_cleanup = values.get("full") == "1"
    signer = URLSafeTimedSerializer(current_app.secret_key, salt="model-full-cleanup")

    def current_plan():
        if full_cleanup:
            return {**build_full_cleanup_plan(source), "model_path": str(source)}
        return plan_model_cleanup(basepath, model_relpath=source_path)

    def signature(plan):
        return hashlib.sha256(json.dumps(plan["entries"], sort_keys=True).encode()).hexdigest()

    try:
        plan = current_plan()
        if request.method == "POST":
            if request.form.get("confirm_cleanup") != "1":
                raise ModelStagingError("Confirm that the selected files may be permanently deleted.")
            if full_cleanup:
                try:
                    reviewed = signer.loads(request.form.get("review_token", ""), max_age=1800)
                except BadSignature as exc:
                    raise FullCleanupError("Full cleanup preview expired or is invalid; review the list again.") from exc
                if reviewed.get("model") != str(source) or reviewed.get("signature") != signature(plan):
                    raise FullCleanupError("Full cleanup targets changed or belong to another model; review the list again.")
                result = run_full_cleanup(plan)
                result["failed_count"] = len(result["failures"])
            else:
                result = cleanup_model_directory(
                    basepath,
                    model_relpath=source_path,
                    selected_names=request.form.getlist("entries"),
                )
            try:
                if not (source / "VADAT").is_file() or not (source / "MOD_SUM").is_file():
                    delete_model_summary_entries(
                        str(config.get("summary_cache_db", "model_summary_cache.sqlite")),
                        basepath=basepath,
                        relpaths=[source_path],
                    )
            except Exception:
                current_app.logger.warning(
                    "Failed to update the model summary cache after cleaning %s",
                    source_path,
                    exc_info=True,
                )
            failed_count = int(result.get("failed_count", 0))
            if failed_count == 0:
                return redirect(
                    _notification_url(
                        "viewer.view",
                        path=source_path,
                        message=f"Model cleanup removed {int(result.get('removed_count', 0))} item(s).",
                    )
                )
            failures = result.get("failures", [])
            failed_names = ", ".join(
                str(item.get("name", "")) for item in failures if isinstance(item, dict)
            )
            error = f"Some files could not be removed: {failed_names}."
            plan = current_plan()
    except (ModelStagingError, FullCleanupError, OSError) as exc:
        error = str(exc)
        plan = current_plan()

    review_token = signer.dumps({"model": str(source), "signature": signature(plan)}) if full_cleanup and plan["ready"] else ""
    return render_template(
        "model_cleanup.html",
        source_path=source_path,
        plan=plan,
        full_cleanup=full_cleanup,
        review_token=review_token,
        result=result,
        error=error,
        breadcrumb=_model_action_breadcrumb(source_path, "Cleanup model"),
    )
