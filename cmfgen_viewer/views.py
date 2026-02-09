from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
import time
from urllib.parse import urlencode

from flask import Blueprint, abort, current_app, redirect, render_template, request, send_file, url_for
from markupsafe import Markup
from pygments.formatters import HtmlFormatter
from werkzeug.utils import secure_filename

from .browser import describe_file, is_model_context_path, list_directory, make_breadcrumb, resolve_path
from .final_spectrum import (
    build_observed_overlay_trace,
    build_both_plot,
    build_model_summary_sections,
    build_normalized_plot,
    discover_final_spectrum_files,
    fin_file_label,
    load_obs_spectrum,
    read_model,
    spectrum_data_rows,
)
from .parsers.common import format_number, parse_float_token
from .observed_spectrum import (
    generate_upload_token,
    is_valid_upload_token,
    list_upload_manifests,
    parse_uploaded_spectrum,
    remove_upload_bundle,
    write_upload_manifest,
)
from .syntax import highlight_text, syntax_css

try:
    import markdown as md
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    md = None

bp = Blueprint("viewer", __name__)
DOCS_DIR = Path(__file__).resolve().parent.parent / "doc"
QUICK_LINK_FILES = (
    "VADAT",
    "MODEL_SPEC",
    "IN_ITS",
    "MOD_SUM",
    "RVTJ",
    "OBSFLUX",
    "MEANOPAC",
    "HYDRO",
    "GAMMAS",
    "OUTGEN",
    "WARNINGS",
)
QUICK_LINK_GLOBS = (
    "obs_fin*",
    "obs_cont*",
    "obs/obs_fin*",
    "obs/obs_cont*",
)

_MD_FENCE_RE = re.compile(r"^\s*```")
_MD_LIST_RE = re.compile(r"^(\s*)(?:[-*+]\s+|\d+[.)]\s+)")
_MD_ORDERED_PAREN_RE = re.compile(r"^(\s*)(\d+)\)\s+(.*)$")
_MD_ATX_HEADING_RE = re.compile(r"^\s*#{1,6}\s+")
_MD_SETEXT_RE = re.compile(r"^\s*[=-]{3,}\s*$")
_MD_QUOTE_RE = re.compile(r"^\s*>")

SUMMARY_COLUMNS = [
    "MODEL",
    "LSTAR",
    "MDOT",
    "T_*",
    "RSTAR",
    "RMAX",
    "T_2/3",
    "R_2/3",
    "Eta",
    "f",
    "f_beg",
    "TAU",
    "Vinf",
    "Beta",
    "HYD/X",
    "NIT/X",
    "IRON/X",
    "logg",
    "OXY/X",
    "CAR/X",
]


def _normalize_markdown_lists(source: str) -> str:
    """
    Normalize legacy investigation-note list style into markdown-friendly form.

    The source docs use many `1)` markers and list starts directly after text
    lines. Python-Markdown does not reliably recognize those as lists without
    canonical markers and a separating blank line.
    """
    lines = source.splitlines()
    out: list[str] = []
    in_fence = False

    for line in lines:
        if _MD_FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue

        normalized = line
        if not in_fence:
            ordered_match = _MD_ORDERED_PAREN_RE.match(normalized)
            if ordered_match:
                normalized = f"{ordered_match.group(1)}{ordered_match.group(2)}. {ordered_match.group(3)}"

            if _MD_LIST_RE.match(normalized):
                prev = out[-1] if out else ""
                prev_is_blank = not prev.strip()
                prev_is_list = bool(_MD_LIST_RE.match(prev))
                prev_is_heading = bool(_MD_ATX_HEADING_RE.match(prev))
                prev_is_setext = bool(_MD_SETEXT_RE.match(prev))
                prev_is_quote = bool(_MD_QUOTE_RE.match(prev))
                if not (prev_is_blank or prev_is_list or prev_is_heading or prev_is_setext or prev_is_quote):
                    out.append("")

        out.append(normalized)

    normalized_source = "\n".join(out)
    if source.endswith("\n"):
        normalized_source += "\n"
    return normalized_source


def _viewer_config() -> dict[str, object]:
    return dict(current_app.config.get("CMFGEN_VIEWER", {}))


def _upload_root(config: dict[str, object]) -> Path:
    root = str(config.get("upload_root", "/tmp/cmfgen_viewer_uploads"))
    return Path(root).expanduser().resolve()


def _normalize_spectrum_mode(raw_mode: str | None) -> str:
    mode = (raw_mode or "both").strip().lower()
    if mode not in {"both", "normalized"}:
        return "both"
    return mode


def _collect_obs_tokens(raw_values: list[str]) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        for part in str(raw).split(","):
            token = part.strip()
            if not token or not is_valid_upload_token(token) or token in seen:
                continue
            tokens.append(token)
            seen.add(token)
    return tokens


def _collect_rel_paths(raw_values: list[str]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        rel = str(raw).strip().strip("/")
        if not rel or rel in seen:
            continue
        paths.append(rel)
        seen.add(rel)
    return paths


def _parse_summary_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        numeric = float(value)
        return numeric if numeric == numeric else None

    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("D", "E").replace("d", "e")
    parsed = parse_float_token(normalized)
    if parsed is not None:
        numeric = float(parsed)
        return numeric if numeric == numeric else None

    match = re.match(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))([+-]\d+)$", normalized)
    if not match:
        return None
    try:
        numeric = float(f"{match.group(1)}E{match.group(2)}")
    except ValueError:
        return None
    return numeric if numeric == numeric else None


def _format_summary_value(value: object, *, default: str = "") -> str:
    if value in (None, ""):
        return default
    numeric = _parse_summary_float(value)
    if numeric is not None:
        return format_number(numeric)
    text = str(value).strip()
    return text if text else default


def _build_summary_row(model: dict[str, object]) -> list[str]:
    params = model.get("params")
    vadat = model.get("vadat")
    if not isinstance(params, dict):
        params = {}
    if not isinstance(vadat, dict):
        vadat = {}

    cl_p_1 = params.get("CL_P_1")
    if cl_p_1 in (None, ""):
        cl_p_1 = "-"

    return [
        _format_summary_value(model.get("name")),
        _format_summary_value(vadat.get("LSTAR")),
        _format_summary_value(vadat.get("MDOT")),
        _format_summary_value(params.get("T*(K)")),
        _format_summary_value(vadat.get("RSTAR")),
        _format_summary_value(vadat.get("RMAX")),
        _format_summary_value(params.get("Teff(K)")),
        _format_summary_value(params.get("R_/Rsun")),
        _format_summary_value(params.get("Eta")),
        _format_summary_value(cl_p_1, default="-"),
        _format_summary_value(params.get("CL_P_2")),
        _format_summary_value(params.get("Tau")),
        _format_summary_value(params.get("Vinf1")),
        _format_summary_value(params.get("Beta1")),
        _format_summary_value(vadat.get("HYD/X")),
        _format_summary_value(vadat.get("NIT/X")),
        _format_summary_value(vadat.get("IRON/X")),
        _format_summary_value(params.get("Log_g")),
        _format_summary_value(vadat.get("OXY/X")),
        _format_summary_value(vadat.get("CARB/X")),
    ]


def _spectrum_url(
    model_root: str,
    *,
    fin: str,
    mode: str,
    obs_tokens: list[str] | None = None,
    upload_error: str = "",
) -> str:
    base = url_for("viewer.spectrum", path=model_root)
    query: list[tuple[str, str]] = [("fin", fin), ("mode", _normalize_spectrum_mode(mode))]
    for token in obs_tokens or []:
        if is_valid_upload_token(token):
            query.append(("obs", token))
    if upload_error:
        query.append(("upload_error", upload_error))
    encoded = urlencode(query, doseq=True)
    return f"{base}?{encoded}" if encoded else base


def _spectrum_redirect(
    model_root: str,
    *,
    fin: str,
    mode: str,
    obs_tokens: list[str] | None = None,
    upload_error: str = "",
):
    return redirect(
        _spectrum_url(
            model_root,
            fin=fin,
            mode=mode,
            obs_tokens=obs_tokens or [],
            upload_error=upload_error,
        )
    )


def _join_relpath(parent: str, child: str) -> str:
    if not parent:
        return child
    return f"{parent.rstrip('/')}/{child}"


def _collect_quick_links(basepath: str, directory_relpath: str) -> list[dict[str, str]]:
    try:
        directory = resolve_path(basepath, directory_relpath)
    except (FileNotFoundError, NotADirectoryError):
        return []
    if not directory.is_dir():
        return []

    links: list[dict[str, str]] = []
    seen_paths: set[str] = set()

    def add_link(path_obj: Path, *, label: str | None = None) -> None:
        rel = _join_relpath(directory_relpath, path_obj.relative_to(directory).as_posix())
        if rel in seen_paths:
            return
        seen_paths.add(rel)
        links.append(
            {
                "name": label or path_obj.name,
                "path": rel,
            }
        )

    for name in QUICK_LINK_FILES:
        candidate = directory / name
        if candidate.is_file():
            add_link(candidate, label=name)

    for pattern in QUICK_LINK_GLOBS:
        for candidate in sorted(directory.glob(pattern), key=lambda p: p.name.lower()):
            if candidate.is_file():
                add_link(candidate)
    return links


def _model_root_relpath(relpath: str) -> str | None:
    parts = [part for part in Path(relpath).parts if part not in ("", ".")]
    for index, part in enumerate(parts):
        lowered = part.lower()
        if lowered.startswith("model") and lowered != "models":
            return "/".join(parts[: index + 1])
    return None


def _spectrum_link_context(basepath: str, relpath: str) -> dict[str, object] | None:
    model_root = _model_root_relpath(relpath)
    if not model_root:
        return None
    try:
        model_dir = resolve_path(basepath, model_root)
    except (FileNotFoundError, NotADirectoryError):
        return None
    files = discover_final_spectrum_files(model_dir)
    if files is None:
        return None
    return {
        "model_path": model_root,
        "fin_count": len(files["fin_files"]),
    }


def _doc_title(path: Path) -> str:
    fallback = path.stem.replace("-", " ").replace("_", " ").title()
    try:
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if line.startswith("#"):
                    title = line.lstrip("#").strip()
                    if title:
                        return title
    except OSError:
        return fallback
    return fallback


def _discover_docs() -> list[dict[str, object]]:
    if not DOCS_DIR.is_dir():
        return []

    docs: list[dict[str, object]] = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        docs.append(
            {
                "slug": path.stem,
                "title": _doc_title(path),
                "path": path,
            }
        )
    return docs


@bp.app_context_processor
def inject_docs_nav():
    docs = _discover_docs()
    return {
        "docs_nav": [
            {
                "slug": str(item["slug"]),
                "title": str(item["title"]),
            }
            for item in docs
        ]
    }


@lru_cache(maxsize=1)
def _docs_markdown_css() -> str:
    formatter = HtmlFormatter(cssclass="codehilite")
    return formatter.get_style_defs(".doc-content .codehilite")


@bp.route("/")
def index():
    return redirect(url_for("viewer.view", path=""))


@bp.route("/documentation/", defaults={"slug": None})
@bp.route("/documentation/<slug>")
def documentation(slug: str | None):
    docs = _discover_docs()
    if not docs:
        return render_template(
            "documentation.html",
            docs=[],
            active_doc=None,
            doc_html=Markup(""),
            doc_highlight_css="",
        )

    docs_by_slug = {str(item["slug"]): item for item in docs}
    if slug is None:
        first = str(docs[0]["slug"])
        return redirect(url_for("viewer.documentation", slug=first))

    active_doc = docs_by_slug.get(slug)
    if active_doc is None:
        abort(404)

    doc_path = Path(active_doc["path"])
    source = doc_path.read_text(encoding="utf-8", errors="replace")
    if md is not None:
        normalized_source = _normalize_markdown_lists(source)
        doc_html = md.markdown(
            normalized_source,
            extensions=["fenced_code", "tables", "sane_lists", "codehilite"],
            extension_configs={
                "codehilite": {
                    "guess_lang": False,
                    "css_class": "codehilite",
                }
            },
        )
        doc_highlight_css = _docs_markdown_css()
    else:
        highlighted_html, _lexer = highlight_text(
            source,
            filename=doc_path.name,
            mime="text/markdown",
        )
        doc_html = f"<div class=\"syntax-preview\">{highlighted_html}</div>"
        doc_highlight_css = syntax_css()
    return render_template(
        "documentation.html",
        docs=docs,
        active_doc=active_doc,
        doc_html=Markup(doc_html),
        doc_highlight_css=doc_highlight_css,
    )


@bp.route("/bulk/summarize/", defaults={"path": ""}, methods=["POST"])
@bp.route("/bulk/summarize/<path:path>", methods=["POST"])
def bulk_summarize(path: str):
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))

    try:
        directory = resolve_path(basepath, path)
    except FileNotFoundError:
        abort(404)
    if not directory.is_dir():
        abort(404)

    if is_model_context_path(path):
        abort(400)

    selected_paths = _collect_rel_paths(request.form.getlist("selected_models"))
    if not selected_paths:
        return redirect(url_for("viewer.view", path=path))

    rows: list[dict[str, object]] = []
    skipped: list[list[str]] = []
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

        if not (target / "VADAT").is_file() or not (target / "MOD_SUM").is_file():
            skipped.append([rel, "Missing VADAT or MOD_SUM"])
            continue

        model = read_model(target)
        rows.append(
            {
                "values": _build_summary_row(model),
                "path": rel,
            }
        )

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
    return render_template(
        "models_summary.html",
        columns=SUMMARY_COLUMNS,
        rows=rows,
        skipped=skipped,
        selected_count=len(selected_paths),
        **context,
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
        "flux_mode": str(entry.get("resolved_flux_mode", entry.get("requested_flux_mode", ""))),
        "detected_flux_mode": str(entry.get("detected_flux_mode", "")),
        "points": int(entry.get("points", 0) or 0),
        "size": int(entry.get("size", 0) or 0),
        "exists": bool(entry.get("exists", False)),
        "created_at": _format_upload_time(entry.get("created_at", 0)),
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
    )


@bp.route("/uploads/upload", methods=["POST"])
def uploads_upload():
    config = _viewer_config()
    upload_root = _upload_root(config)

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
        parsed = parse_uploaded_spectrum(stored_path, flux_mode=requested_flux_mode)
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
        "points": len(parsed.get("wavelength", [])),
        "created_at": time.time(),
    }
    write_upload_manifest(upload_root, token, manifest)
    return redirect(url_for("viewer.uploads", message=f"Uploaded {safe_name}."))


@bp.route("/uploads/delete/<token>", methods=["POST"])
def uploads_delete(token: str):
    if not is_valid_upload_token(token):
        abort(404)
    config = _viewer_config()
    upload_root = _upload_root(config)
    remove_upload_bundle(upload_root, token)
    return redirect(url_for("viewer.uploads", message="Upload removed."))


@bp.route("/spectrum-upload/<path:path>", methods=["POST"])
def spectrum_upload(path: str):
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))

    try:
        target = resolve_path(basepath, path)
    except FileNotFoundError:
        abort(404)
    if not target.is_dir():
        abort(404)

    model_root = _model_root_relpath(path)
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

    uploaded = request.files.get("observed_file")
    if uploaded is None or not uploaded.filename:
        return _spectrum_redirect(
            model_root,
            fin=selected_fin,
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
        parsed = parse_uploaded_spectrum(stored_path, flux_mode=requested_flux_mode)
    except Exception as exc:
        remove_upload_bundle(upload_root, token)
        return _spectrum_redirect(
            model_root,
            fin=selected_fin,
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
        "points": len(parsed.get("wavelength", [])),
        "created_at": time.time(),
    }
    write_upload_manifest(upload_root, token, manifest)

    selected_tokens = _collect_obs_tokens(current_obs_tokens + [token])
    return _spectrum_redirect(model_root, fin=selected_fin, mode=view_mode, obs_tokens=selected_tokens)


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

    model_root = _model_root_relpath(path)
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

    token = request.form.get("token", "").strip() or request.form.get("obs", "").strip()
    upload_root = _upload_root(config)
    if is_valid_upload_token(token):
        remove_upload_bundle(upload_root, token)

    remaining = _collect_obs_tokens(request.form.getlist("obs"))
    remaining = [item for item in remaining if item != token]
    return _spectrum_redirect(model_root, fin=selected_fin, mode=view_mode, obs_tokens=remaining)


@bp.route("/spectrum/<path:path>")
def spectrum(path: str):
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))

    try:
        target = resolve_path(basepath, path)
    except FileNotFoundError:
        abort(404)
    if not target.is_dir():
        abort(404)

    model_root = _model_root_relpath(path)
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
    selected_obs_tokens = _collect_obs_tokens(request.args.getlist("obs"))

    warnings: list[str] = []
    upload_error = request.args.get("upload_error", "").strip()
    if upload_error:
        warnings.append(upload_error)

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
            parsed = parse_uploaded_spectrum(source_path, flux_mode=upload_flux_mode)
        except Exception as exc:
            warnings.append(f"Uploaded spectrum '{entry.get('filename', source_path.name)}' failed to load: {exc}")
            continue
        parsed["name"] = str(entry.get("filename", source_path.name))

        selected_parsed.append(parsed)
        selected_observed_uploads.append(_upload_entry_for_display(entry))
        for warning in parsed.get("warnings", []):
            warnings.append(f"Uploaded {entry.get('filename', source_path.name)}: {warning}")

    continuum = load_obs_spectrum(Path(spectrum_files["obs_cont"]))
    final = load_obs_spectrum(Path(spectrum_files["obs_dir"]) / selected_fin)
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
        created_label = str(display.get("created_at", ""))
        display["label"] = f"{label} [{mode_label}] {created_label}".strip()
        display["selected"] = token in selected_lookup
        available_uploads.append(display)

    mode_urls = {
        "both": _spectrum_url(model_root, fin=selected_fin, mode="both", obs_tokens=selected_obs_tokens),
        "normalized": _spectrum_url(model_root, fin=selected_fin, mode="normalized", obs_tokens=selected_obs_tokens),
    }
    clear_overlay_url = _spectrum_url(model_root, fin=selected_fin, mode=view_mode, obs_tokens=[])

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
        obs_tokens=selected_obs_tokens,
        available_uploads=available_uploads,
        selected_observed_uploads=selected_observed_uploads,
        upload_flux_mode="auto",
        mode_urls=mode_urls,
        clear_overlay_url=clear_overlay_url,
        **context,
    )


@bp.route("/view/", defaults={"path": ""})
@bp.route("/view/<path:path>")
def view(path: str):
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))
    symlink_mode = request.args.get("symlinks", "").strip().lower()
    hide_symlink_files = symlink_mode == "hide"
    view_query: dict[str, str] = {"symlinks": "hide"} if hide_symlink_files else {}

    try:
        target = resolve_path(basepath, path)
    except FileNotFoundError:
        abort(404)

    context = {
        "path": path,
        "breadcrumb": make_breadcrumb(path),
        "basepath": basepath,
        "show_all": bool(config.get("show_all", False)),
        "show_role_badges": is_model_context_path(path),
        "view_query": view_query,
        "spectrum_view": _spectrum_link_context(basepath, path),
    }

    if target.is_dir():
        current_dir_name = target.name.lower()
        current_dir_is_model = current_dir_name.startswith("model") and current_dir_name != "models"
        current_path_in_model = is_model_context_path(path) or is_model_context_path(str(target)) or current_dir_is_model
        model_context = current_path_in_model
        show_symlink_toggle = model_context
        show_symlinks = (not hide_symlink_files) or (not show_symlink_toggle)
        symlink_toggle_query: dict[str, str] = {}
        if show_symlink_toggle and show_symlinks:
            symlink_toggle_query = {"symlinks": "hide"}

        files = list_directory(
            basepath,
            path,
            show_all=bool(config.get("show_all", False)),
            show_symlinks=show_symlinks,
        )
        context["show_symlink_toggle"] = show_symlink_toggle
        context["show_symlinks"] = show_symlinks
        context["symlink_toggle_query"] = symlink_toggle_query
        context["quick_links"] = _collect_quick_links(basepath, path)
        context["enable_multi_model_ops"] = not current_path_in_model
        return render_template("files_list.html", files=files, **context)

    if target.is_file():
        details = describe_file(basepath, path)
        parent_path = Path(path).parent.as_posix()
        context["show_role_badges"] = is_model_context_path(parent_path)
        context["quick_links"] = _collect_quick_links(basepath, parent_path)
        context["spectrum_view"] = _spectrum_link_context(basepath, parent_path)
        has_parsed = bool(details.get("parsed"))
        requested_display = request.args.get("display", "").strip().lower()
        if has_parsed:
            if requested_display in {"raw", "parsed"}:
                display_mode = requested_display
            else:
                display_mode = "parsed"
        else:
            display_mode = "raw"
        details["has_parsed"] = has_parsed
        details["display_mode"] = display_mode
        return render_template("file_view.html", **details, **context)

    abort(404)


def _send(path: str, *, attachment: bool):
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))

    try:
        target = resolve_path(basepath, path)
    except FileNotFoundError:
        abort(404)

    if not target.is_file():
        abort(404)

    return send_file(
        target,
        as_attachment=attachment,
        download_name=target.name,
    )


@bp.route("/raw/<path:path>")
def raw_file(path: str):
    return _send(path, attachment=False)


@bp.route("/download/<path:path>")
def download_file(path: str):
    return _send(path, attachment=True)
