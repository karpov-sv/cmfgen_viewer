"""Reviewed UI launches and persistent detached runner job pages."""
import math
from pathlib import Path

from flask import abort, current_app, jsonify, redirect, render_template, request, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .browser import is_model_directory, make_breadcrumb, resolve_path
from .model_activity import model_workspace_root
from .model_navigation import model_navigation_context
from .detached_jobs import cancel_job, fingerprint, launch_job, list_jobs, snapshot_job, job_directory, STAGE_LABELS, STATUS_LABELS, STATUS_CLASSES
from .runner import STAGE_CHOICES, NATIVE_STAGES, _build_requested_stage_plan, build_sequence_plan
from .runner_config import resolve_runner_config
from .runner_recipe import RunnerError
from .view_common import _viewer_config, bp


def signer():
    return URLSafeTimedSerializer(current_app.secret_key, salt="runner-launch")


@bp.app_context_processor
def workflow_runner_context():
    return {"workflow_runner_token": lambda source_path, stage: signer().dumps(
        {"start_model": source_path, "start_stage": stage})}


def require_write():
    config = _viewer_config()
    if not config.get("read_write_enabled"):
        abort(403)
    return config


def model_path(config, source_path):
    try:
        model = resolve_path(config["basepath"], source_path)
        if not is_model_directory(model):
            abort(404)
        model = model_workspace_root(model)
        if not model.is_relative_to(Path(config["basepath"]).resolve()):
            abort(404)
        return model
    except (FileNotFoundError, NotADirectoryError):
        abort(404)


def parse_options(form, defaults, *, keep_large_files_default=False):
    sequence = form.get("stage_order", "").strip() or form.get("stage_sequence", "").strip()
    stages = [stage.strip() for stage in sequence.split(",")] if sequence else form.getlist("stage") or defaults
    if not stages or len(set(stages)) != len(stages) or any(stage not in STAGE_CHOICES for stage in stages):
        raise RunnerError("Choose supported stages without duplicates")
    options = {"stages": stages, "fresh_start": form.get("fresh_start") == "1",
               "no_core_dumps": form.get("no_core_dumps") == "1",
               "keep_large_files": (form.get("keep_large_files") == "1" if "recovery_setting" in form else keep_large_files_default),
               "lte_initialization": form.get("lte_initialization") == "1", "t_exc": 1.0}
    for name in ("iterations", "threads", "timeout", "memory_mib"):
        raw = form.get(name, "").strip()
        try:
            value = (float(raw) if name == "timeout" else int(raw)) if raw else None
        except ValueError as exc:
            raise RunnerError(f"Invalid {name}") from exc
        if value is not None and (not math.isfinite(value) or value <= 0 or (name == "memory_mib" and value < 128)):
            raise RunnerError(f"{name} must be positive (memory minimum: 128 MiB)")
        options[name] = value
    if options["lte_initialization"]:
        if not any(stage in {"main", "test"} for stage in stages):
            raise RunnerError("LTE initialization applies only to main/test")
        try:
            options["t_exc"] = float(form.get("t_exc", "1.0"))
        except ValueError as exc:
            raise RunnerError("T_EXC must be positive and finite") from exc
        if not math.isfinite(options["t_exc"]) or options["t_exc"] <= 0:
            raise RunnerError("T_EXC must be positive and finite")
    if options["iterations"] is not None and "main" not in stages:
        raise RunnerError("Iteration overrides apply only to main")
    if options["fresh_start"] and not any(stage in {"main", "test"} for stage in stages):
        raise RunnerError("Fresh start applies only to main/test")
    if not any(stage in NATIVE_STAGES for stage in stages) and any(options[name] for name in ("threads", "timeout", "memory_mib", "no_core_dumps")):
        raise RunnerError("Resource options apply only to executable stages")
    return options


def runner_plan(config, model, options):
    native, sources = ({}, {})
    if any(stage in NATIVE_STAGES for stage in options["stages"]):
        native, sources = resolve_runner_config(cmfgen_root=config.get("cmfgen_root"), atomic_root=config.get("atomic_root"),
            threads=options["threads"] if options["threads"] is not None else config.get("cmfgen_runner_threads"))
    kwargs = dict(native_config=native, configuration_sources=sources, timeout=options["timeout"],
        memory_mib=options["memory_mib"], iterations=options["iterations"], fresh_start=options["fresh_start"],
        no_core_dumps=options["no_core_dumps"], cleanup_files=None,
        keep_large_files=options.get("keep_large_files", config.get("keep_large_files", False)),
        lte_initialization=options.get("lte_initialization", False), t_exc=options.get("t_exc", 1.0),
        template_root=Path(config["template_root"]) if config.get("template_root") and "prepare-lte" in options["stages"] else None)
    if len(options["stages"]) == 1:
        return _build_requested_stage_plan(model, options["stages"][0], **kwargs)
    return build_sequence_plan(model, options["stages"], **kwargs)


@bp.route("/model-actions/run/<path:source_path>", methods=["GET", "POST"])
def model_runner_launch(source_path):
    config = require_write()
    model = model_path(config, source_path)
    defaults = ["main"]
    suggested = request.args.get("stages", "main").split(",")
    if all(stage in STAGE_CHOICES for stage in suggested):
        defaults = suggested
    error, plan, token = "", None, None
    inline = request.args.get("format") == "json"
    options = {"stages": defaults, "iterations": None, "threads": None, "timeout": None,
               "memory_mib": None, "keep_large_files": config.get("keep_large_files", False), "fresh_start": False, "no_core_dumps": False, "lte_initialization": False, "t_exc": 1.0}
    try:
        if request.method == "POST" and inline and request.form.get("action") == "start":
            signed = signer().loads(request.form.get("start_token", ""), max_age=86400)
            if not isinstance(signed.get("start_model"), str) or not isinstance(signed.get("start_stage"), str):
                raise RunnerError("Invalid run confirmation")
            if model_path(config, signed["start_model"]) != model:
                raise RunnerError("Run confirmation belongs to another model")
            options = parse_options(request.form, defaults, keep_large_files_default=config.get("keep_large_files", False))
            if options["stages"] != signed["start_stage"].split(",") or signed["start_stage"] not in {"main", "main,flux", "flux", "lte", "hydro"}:
                raise RunnerError("Run confirmation belongs to another stage")
            plan = runner_plan(config, model, options)
            if not plan["ready"]:
                raise RunnerError("; ".join(plan["errors"]) or "Stage preflight is blocked")
            job_id = launch_job(config["basepath"], model, options,
                lambda: runner_plan(config, model, options), fingerprint(plan))
            current_app.extensions["cmfgen_changes"].notify()
            return jsonify(job_id=job_id, status_url=url_for("viewer.runner_job", job_id=job_id, format="json"))
        if request.method == "POST" and request.form.get("action") == "launch":
            reviewed = signer().loads(request.form.get("review_token", ""), max_age=1800)
            if reviewed["model"] != str(model):
                abort(400)
            options = reviewed["options"]
            job_id = launch_job(config["basepath"], model, options,
                lambda: runner_plan(config, model, options), reviewed["fingerprint"])
            current_app.extensions["cmfgen_changes"].notify()
            if inline:
                return jsonify(job_id=job_id, status_url=url_for("viewer.runner_job", job_id=job_id, format="json"))
            return redirect(url_for("viewer.runner_job", job_id=job_id))
        if request.method == "POST":
            if inline:
                raise RunnerError("Use the Model runner page to preview runs")
            options = parse_options(request.form, defaults, keep_large_files_default=config.get("keep_large_files", False))
            plan = runner_plan(config, model, options)
            if plan["ready"]:
                token = signer().dumps({"model": str(model), "options": options, "fingerprint": fingerprint(plan)})
    except (RunnerError, OSError, ValueError, BadSignature) as exc:
        error = str(exc)
    if inline:
        if request.method == "GET":
            jobs = [job for job in list_jobs(config["basepath"]) if job["model"] == str(model)][:10]
            response = jsonify(jobs=jobs)
        else:
            response = jsonify(error=error)
            if error:
                response.status_code = 409
        response.headers["Cache-Control"] = "no-store"
        return response
    breadcrumb = make_breadcrumb(source_path)
    breadcrumb[-1]["path"] = source_path
    breadcrumb.append({"name": "Model runner", "path": None})
    jobs = [job for job in list_jobs(config["basepath"]) if job["model"] == str(model)][:10]
    return render_template("runner_launch.html", source_path=source_path, breadcrumb=breadcrumb,
        stages=STAGE_CHOICES, options=options, plan=plan, review_token=token, error=error, jobs=jobs, stage_labels=STAGE_LABELS, status_labels=STATUS_LABELS, status_classes=STATUS_CLASSES)


@bp.route("/runner-jobs/<job_id>")
def runner_job(job_id):
    config = require_write()
    try:
        job = snapshot_job(config["basepath"], job_id)
    except (RunnerError, OSError, ValueError):
        abort(404)
    if request.args.get("format") == "json":
        response = jsonify({**job, "cancel_token": signer().dumps({"cancel_job": job_id})})
        response.headers["Cache-Control"] = "no-store"
        return response
    breadcrumb = make_breadcrumb(job["model_relpath"])
    breadcrumb[-1]["path"] = job["model_relpath"]
    breadcrumb.append({"name": "Runner job", "path": None})
    navigation = model_navigation_context(config, "viewer.model_runner_launch", {"source_path": job["model_relpath"]})
    return render_template("runner_job.html", job=job, breadcrumb=breadcrumb, model_navigation=navigation,
                           cancel_token=signer().dumps({"cancel_job": job_id}), stage_labels=STAGE_LABELS, status_labels=STATUS_LABELS, status_classes=STATUS_CLASSES)


@bp.route("/runner-jobs/<job_id>/cancel", methods=["POST"])
def runner_job_cancel(job_id):
    config = require_write()
    try:
        signed = signer().loads(request.form.get("cancel_token", ""), max_age=86400)
        if signed.get("cancel_job") != job_id:
            abort(400)
        cancel_job(config["basepath"], job_id)
        current_app.extensions["cmfgen_changes"].notify()
    except (RunnerError, OSError, BadSignature) as exc:
        if request.args.get("format") == "json":
            return jsonify(error=str(exc)), 409
        abort(409, str(exc))
    if request.args.get("format") == "json":
        return jsonify(stopping=True)
    return redirect(url_for("viewer.runner_job", job_id=job_id))


@bp.route("/runner-jobs/<job_id>/log")
def runner_job_log(job_id):
    config = require_write()
    try:
        directory = job_directory(config["basepath"], job_id)
        job = snapshot_job(config["basepath"], job_id)
        if request.args.get("native") == "1":
            path = Path(job.get("native_log", ""))
            if not path.resolve().is_relative_to(Path(job["model"]) / ".cmfgen-runs"):
                abort(404)
        else:
            path = directory / ("events.jsonl" if request.args.get("events") == "1" else "worker.log")
        if path.is_symlink():
            abort(404)
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 128 * 1024))
            content = stream.read().decode("utf-8", errors="replace")
    except (RunnerError, OSError, ValueError):
        abort(404)
    return current_app.response_class(content, mimetype="text/plain", headers={"Cache-Control": "no-store"})
