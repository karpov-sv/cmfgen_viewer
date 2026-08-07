"""Routes for reviewing and saving allowlisted model control-file edits."""

from __future__ import annotations

from flask import abort, current_app, redirect, render_template, request, url_for

from .browser import make_breadcrumb
from .model_editor import (
    ModelEditorError,
    list_model_parameter_checkpoints,
    list_model_parameter_files,
    load_model_parameter_checkpoint,
    load_model_parameter_file,
    review_model_parameter_edit,
    save_model_parameter_edit,
)
from .model_quick_editor import (
    load_quick_model_parameter_cards,
    review_quick_model_parameter_edit,
    save_quick_model_parameter_edit,
)
from .summary_cache import delete_model_summary_entries
from .view_common import _viewer_config, bp


def _editor_breadcrumb(source_relpath: str, action_name: str) -> list[dict[str, str | None]]:
    breadcrumb = make_breadcrumb(source_relpath)
    if breadcrumb:
        breadcrumb[-1]["path"] = source_relpath
    breadcrumb.append({"name": action_name, "path": None})
    return breadcrumb


def _after_parameter_save(
    config: dict[str, object],
    *,
    basepath: str,
    source_path: str,
    file_relpath: str,
    saved: dict[str, object],
) -> None:
    if saved.get("marker_error"):
        current_app.logger.warning(
            "Saved %s/%s but could not write the modified-input marker: %s",
            source_path,
            file_relpath,
            saved["marker_error"],
        )
    if not bool(saved.get("affects_solution", False)):
        return
    try:
        delete_model_summary_entries(
            str(config.get("summary_cache_db", "model_summary_cache.sqlite")),
            basepath=basepath,
            relpaths=[source_path],
        )
    except Exception:
        current_app.logger.warning(
            "Failed to invalidate the model summary cache after editing %s/%s",
            source_path,
            file_relpath,
            exc_info=True,
        )


def _submitted_quick_values(card: dict[str, object]) -> dict[str, object]:
    values: dict[str, object] = {}
    for field in card["fields"]:
        field_name = str(field["field_name"])
        if field_name in request.form:
            values[str(field["key"])] = request.form[field_name]
    return values


def _show_submitted_quick_values(
    card: dict[str, object],
    values: dict[str, object],
) -> None:
    for field in card["fields"]:
        key = str(field["key"])
        if key in values:
            field["value"] = str(values[key])


@bp.route("/model-actions/edit/<path:source_path>", methods=["GET", "POST"])
def model_parameters(source_path: str):
    config = _viewer_config()
    if not bool(config.get("read_write_enabled", False)):
        abort(403)
    basepath = str(config.get("basepath", "."))
    try:
        parameter_files = list_model_parameter_files(basepath, model_relpath=source_path)
    except ModelEditorError:
        abort(404)

    file_relpath = str(
        request.form.get("file_relpath", "")
        if request.method == "POST"
        else request.args.get("file", "")
    ).strip()
    if not file_relpath:
        quick_cards = load_quick_model_parameter_cards(
            basepath,
            model_relpath=source_path,
        )
        quick_review: dict[str, object] | None = None
        quick_error = ""
        if request.method == "POST":
            action = str(request.form.get("action", "")).strip().lower()
            if action not in {"quick_preview", "quick_save"}:
                abort(400)
            quick_file_relpath = str(request.form.get("quick_file_relpath", "")).strip()
            card = next(
                (item for item in quick_cards if item["file_relpath"] == quick_file_relpath),
                None,
            )
            if card is None:
                abort(400)
            values = _submitted_quick_values(card)
            expected_digest = str(request.form.get("expected_digest", ""))
            try:
                quick_review = review_quick_model_parameter_edit(
                    basepath,
                    model_relpath=source_path,
                    file_relpath=quick_file_relpath,
                    expected_digest=expected_digest,
                    values=values,
                )
                reviewed_card = quick_review["card"]
                quick_cards[quick_cards.index(card)] = reviewed_card
                if action == "quick_save":
                    saved = save_quick_model_parameter_edit(
                        basepath,
                        model_relpath=source_path,
                        file_relpath=quick_file_relpath,
                        expected_digest=expected_digest,
                        reviewed_digest=str(request.form.get("reviewed_digest", "")),
                        values=values,
                    )
                    _after_parameter_save(
                        config,
                        basepath=basepath,
                        source_path=source_path,
                        file_relpath=quick_file_relpath,
                        saved=saved,
                    )
                    return redirect(
                        url_for(
                            "viewer.model_parameters",
                            source_path=source_path,
                            quick_saved=quick_file_relpath,
                            backup=str(saved["backup_relpath"]),
                        )
                    )
            except ModelEditorError as exc:
                quick_error = str(exc)
                _show_submitted_quick_values(card, values)
        return render_template(
            "model_parameters.html",
            source_path=source_path,
            parameter_files=parameter_files,
            quick_cards=quick_cards,
            quick_review=quick_review,
            quick_error=quick_error,
            quick_saved=str(request.args.get("quick_saved", "")).strip(),
            backup_relpath=str(request.args.get("backup", "")).strip(),
            breadcrumb=_editor_breadcrumb(source_path, "Edit parameters"),
        )

    error = ""
    review: dict[str, object] | None = None
    submitted_contents: str | None = None
    try:
        file_record = load_model_parameter_file(
            basepath,
            model_relpath=source_path,
            file_relpath=file_relpath,
        )
    except ModelEditorError as exc:
        return render_template(
            "model_parameter_edit.html",
            source_path=source_path,
            file_relpath=file_relpath,
            file=None,
            contents="",
            expected_digest="",
            checkpoints=[],
            loaded_checkpoint=None,
            review=None,
            error=str(exc),
            saved=False,
            backup_relpath="",
            backup_view_path="",
            breadcrumb=_editor_breadcrumb(source_path, "Edit parameters"),
        ), 400

    expected_digest = str(file_record["digest"])
    try:
        checkpoints = list_model_parameter_checkpoints(
            basepath,
            model_relpath=source_path,
            file_relpath=file_relpath,
        )
    except ModelEditorError as exc:
        checkpoints = []
        error = str(exc)
    loaded_checkpoint: dict[str, object] | None = None
    if request.method == "GET":
        checkpoint_name = str(request.args.get("checkpoint", "")).strip()
        if checkpoint_name:
            try:
                loaded_checkpoint = load_model_parameter_checkpoint(
                    basepath,
                    model_relpath=source_path,
                    file_relpath=file_relpath,
                    checkpoint_name=checkpoint_name,
                )
            except ModelEditorError as exc:
                error = str(exc)
    if request.method == "POST":
        action = str(request.form.get("action", "preview")).strip().lower()
        if action not in {"preview", "save"}:
            abort(400)
        submitted_contents = str(request.form.get("contents", ""))
        expected_digest = str(request.form.get("expected_digest", ""))
        try:
            review = review_model_parameter_edit(
                basepath,
                model_relpath=source_path,
                file_relpath=file_relpath,
                expected_digest=expected_digest,
                contents=submitted_contents,
            )
            if action == "save":
                if request.form.get("reviewed_digest") != str(review["proposed_digest"]):
                    raise ModelEditorError(
                        "The proposed content changed after review. Preview it again before saving."
                    )
                saved = save_model_parameter_edit(
                    basepath,
                    model_relpath=source_path,
                    file_relpath=file_relpath,
                    expected_digest=expected_digest,
                    contents=submitted_contents,
                )
                _after_parameter_save(
                    config,
                    basepath=basepath,
                    source_path=source_path,
                    file_relpath=file_relpath,
                    saved=saved,
                )
                return redirect(
                    url_for(
                        "viewer.model_parameters",
                        source_path=source_path,
                        file=file_relpath,
                        saved="1",
                        backup=str(saved["backup_relpath"]),
                    )
                )
            file_record = review["file"]
        except ModelEditorError as exc:
            error = str(exc)

    if submitted_contents is not None:
        contents = submitted_contents
    elif loaded_checkpoint is not None:
        contents = str(loaded_checkpoint["contents"])
    else:
        contents = str(file_record["contents"])
    backup_relpath = str(request.args.get("backup", "")).strip() if request.method == "GET" else ""
    backup_view_path = f"{source_path.rstrip('/')}/{backup_relpath}" if backup_relpath else ""
    return render_template(
        "model_parameter_edit.html",
        source_path=source_path,
        file_relpath=file_relpath,
        file=file_record,
        contents=contents,
        expected_digest=expected_digest,
        checkpoints=checkpoints,
        loaded_checkpoint=loaded_checkpoint,
        review=review,
        error=error,
        saved=request.args.get("saved", "").strip() == "1",
        backup_relpath=backup_relpath,
        backup_view_path=backup_view_path,
        breadcrumb=_editor_breadcrumb(source_path, f"Edit {file_relpath}"),
    )
