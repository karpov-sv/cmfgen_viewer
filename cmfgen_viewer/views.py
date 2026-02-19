from __future__ import annotations

import copy
from datetime import datetime, timezone
import fnmatch
from functools import lru_cache
import math
import multiprocessing as mp
import os
from pathlib import Path
import re
import secrets
from threading import Lock, Thread
import time
from urllib.parse import urlencode

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, send_file, url_for
from markupsafe import Markup
from pygments.formatters import HtmlFormatter
from werkzeug.utils import secure_filename

from .browser import describe_file, is_model_context_path, list_directory, make_breadcrumb, resolve_path
from .final_spectrum import (
    FIT_CANCELED_MESSAGE,
    LIGHT_SPEED_KM_PER_S,
    apply_spectrum_transform,
    build_final_model_series,
    build_observed_overlay_trace,
    build_both_plot,
    build_model_summary_sections,
    build_normalized_plot,
    build_uploaded_spectrum_plot,
    discover_final_spectrum_files,
    fit_model_to_observed,
    fin_file_label,
    load_obs_spectrum,
    read_model,
    spectrum_fit_bounds,
    spectrum_data_rows,
)
from .parsers.common import downsample_xy, format_number, parse_float_token
from .observed_spectrum import (
    generate_upload_token,
    is_valid_upload_token,
    list_upload_manifests,
    parse_uploaded_spectrum,
    remove_upload_bundle,
    write_upload_manifest,
)
from .summary_cache import list_model_summaries, upsert_model_summary
from .syntax import highlight_text, syntax_css

try:
    import markdown as md
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    md = None

bp = Blueprint("viewer", __name__)
DOCS_DIR = Path(__file__).resolve().parent.parent / "doc"
HR_AUX_DIR = Path(__file__).resolve().parent.parent / "data"
MAMAJEK_TABLE_PATH = HR_AUX_DIR / "EEM_dwarf_UBVIJHK_colors_Teff.txt"
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
    "CORRECTION_SUM",
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
    "Last updated",
]

SPECTRUM_TRANSFORM_DEFAULTS = {
    "redshift": 0.0,
    "broadening_km_s": 0.0,
    "ebv": 0.0,
    "distance_kpc": 1.0,
}

GRID_SEARCH_JOB_TTL_SECONDS = 6 * 60 * 60
GRID_SEARCH_MAX_JOBS = 32
GRID_SEARCH_TOP_RESULTS = 12
GRID_SEARCH_JOBS: dict[str, dict[str, object]] = {}
GRID_SEARCH_JOBS_LOCK = Lock()


@lru_cache(maxsize=1)
def _load_mamajek_hr_overlay() -> dict[str, object] | None:
    """
    Load Mamajek dwarf sequence points as Teff-L pairs for HR overlay plotting.

    Source file is kept verbatim under data/ and parsed here on demand.
    """
    if not MAMAJEK_TABLE_PATH.is_file():
        return None

    try:
        lines = MAMAJEK_TABLE_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None

    header_index: int | None = None
    teff_index: int | None = None
    logl_index: int | None = None
    version = ""
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# Version"):
            version = stripped.replace("#", "", 1).strip()
        if not stripped.startswith("#SpT"):
            continue
        columns = stripped.lstrip("#").split()
        try:
            teff_index = columns.index("Teff")
            logl_index = columns.index("logL")
        except ValueError:
            continue
        header_index = idx
        break

    if header_index is None or teff_index is None or logl_index is None:
        return None

    points: list[dict[str, object]] = []
    for line in lines[header_index + 1 :]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#SpT"):
            break
        if stripped.startswith("#"):
            continue

        parts = stripped.split()
        if len(parts) <= max(teff_index, logl_index):
            continue

        teff_value = parse_float_token(parts[teff_index])
        logl_value = parse_float_token(parts[logl_index])
        if teff_value is None or logl_value is None:
            continue

        teff = float(teff_value)
        log_l = float(logl_value)
        if not math.isfinite(teff) or not math.isfinite(log_l) or teff <= 0:
            continue

        luminosity = 10.0 ** log_l
        if not math.isfinite(luminosity) or luminosity <= 0:
            continue

        points.append(
            {
                "spt": parts[0],
                "teff": teff,
                "log_l": log_l,
                "luminosity": luminosity,
            }
        )

    if len(points) < 2:
        return None

    return {
        "name": "Mamajek Dwarf Sequence",
        "source": "https://www.pas.rochester.edu/~emamajek/EEM_dwarf_UBVIJHK_colors_Teff.txt",
        "version": version,
        "file": str(MAMAJEK_TABLE_PATH.name),
        "points": points,
    }


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


def _spectrum_lambda_bounds(config: dict[str, object]) -> tuple[float, float]:
    default_min = 800.0
    default_max = 20000.0
    try:
        lambda_min = float(config.get("lambda_min_angstrom", default_min))
    except (TypeError, ValueError):
        lambda_min = default_min
    try:
        lambda_max = float(config.get("lambda_max_angstrom", default_max))
    except (TypeError, ValueError):
        lambda_max = default_max

    if not math.isfinite(lambda_min) or lambda_min <= 0:
        lambda_min = default_min
    if not math.isfinite(lambda_max) or lambda_max <= 0:
        lambda_max = default_max
    if lambda_min > lambda_max:
        lambda_min, lambda_max = lambda_max, lambda_min
    return lambda_min, lambda_max


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


def _format_summary_timestamp(timestamp: float | None) -> str:
    if timestamp is None or not math.isfinite(timestamp):
        return ""
    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _build_summary_row(model: dict[str, object], *, mod_sum_mtime: float | None = None) -> list[str]:
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
        _format_summary_timestamp(mod_sum_mtime),
    ]


def _normalize_transform_params(params: dict[str, object] | None = None) -> dict[str, float]:
    redshift = SPECTRUM_TRANSFORM_DEFAULTS["redshift"]
    broadening = SPECTRUM_TRANSFORM_DEFAULTS["broadening_km_s"]
    ebv = SPECTRUM_TRANSFORM_DEFAULTS["ebv"]
    distance = SPECTRUM_TRANSFORM_DEFAULTS["distance_kpc"]
    values = params or {}

    redshift_raw = _parse_summary_float(values.get("redshift"))
    if redshift_raw is None:
        redshift_raw = _parse_summary_float(values.get("z"))
    if redshift_raw is not None and math.isfinite(redshift_raw):
        redshift = max(redshift_raw, -0.999999)

    broadening_raw = _parse_summary_float(values.get("broadening_km_s"))
    if broadening_raw is None:
        broadening_raw = _parse_summary_float(values.get("broadening"))
    if broadening_raw is None:
        broadening_raw = _parse_summary_float(values.get("sigma"))
    if broadening_raw is not None and math.isfinite(broadening_raw):
        broadening = max(0.0, broadening_raw)

    ebv_raw = _parse_summary_float(values.get("ebv"))
    if ebv_raw is not None and math.isfinite(ebv_raw):
        ebv = ebv_raw

    distance_raw = _parse_summary_float(values.get("distance_kpc"))
    if distance_raw is None:
        distance_raw = _parse_summary_float(values.get("distance"))
    if distance_raw is not None and math.isfinite(distance_raw) and distance_raw > 0:
        distance = distance_raw

    return {
        "redshift": redshift,
        "velocity_km_s": redshift * LIGHT_SPEED_KM_PER_S,
        "broadening_km_s": broadening,
        "ebv": ebv,
        "distance_kpc": distance,
    }


def _normalize_fit_bounds(params: dict[str, object] | None = None, *, mode: str) -> dict[str, tuple[float, float]]:
    defaults = spectrum_fit_bounds(mode)
    values = params or {}
    normalized: dict[str, tuple[float, float]] = {}
    for name, (default_min, default_max) in defaults.items():
        min_raw = _parse_summary_float(values.get(f"fit_{name}_min"))
        max_raw = _parse_summary_float(values.get(f"fit_{name}_max"))

        min_value = float(min_raw) if min_raw is not None and math.isfinite(min_raw) else float(default_min)
        max_value = float(max_raw) if max_raw is not None and math.isfinite(max_raw) else float(default_max)
        if min_value > max_value:
            min_value, max_value = max_value, min_value

        if name == "broadening_km_s":
            min_value = max(0.0, min_value)
            max_value = max(min_value + 1e-9, max_value)
        elif name == "distance_kpc":
            min_value = max(1e-6, min_value)
            max_value = max(min_value + 1e-9, max_value)
        elif abs(max_value - min_value) < 1e-12:
            min_value = float(default_min)
            max_value = float(default_max)

        normalized[name] = (min_value, max_value)
    return normalized


def _normalize_fit_wavelength_range(
    params: dict[str, object] | None = None,
    *,
    configured_min: float,
    configured_max: float,
) -> tuple[tuple[float, float] | None, str | None]:
    values = params or {}
    min_text = str(values.get("fit_lambda_min", "")).strip()
    max_text = str(values.get("fit_lambda_max", "")).strip()

    min_value: float | None = None
    max_value: float | None = None

    if min_text:
        min_raw = _parse_summary_float(min_text)
        if min_raw is None or not math.isfinite(min_raw) or min_raw <= 0:
            return None, "Fit wavelength minimum must be a positive number."
        min_value = float(min_raw)

    if max_text:
        max_raw = _parse_summary_float(max_text)
        if max_raw is None or not math.isfinite(max_raw) or max_raw <= 0:
            return None, "Fit wavelength maximum must be a positive number."
        max_value = float(max_raw)

    if min_value is None and max_value is None:
        return None, None

    try:
        window_min = float(configured_min)
        window_max = float(configured_max)
    except (TypeError, ValueError):
        return None, "Configured wavelength window is invalid."
    if not math.isfinite(window_min) or not math.isfinite(window_max):
        return None, "Configured wavelength window is invalid."
    if window_min > window_max:
        window_min, window_max = window_max, window_min

    effective_min = min_value if min_value is not None else window_min
    effective_max = max_value if max_value is not None else window_max
    if effective_min > effective_max:
        effective_min, effective_max = effective_max, effective_min

    effective_min = max(window_min, effective_min)
    effective_max = min(window_max, effective_max)
    if effective_min >= effective_max:
        return (
            None,
            "Fit wavelength range does not overlap the configured window "
            f"{format_number(window_min)} .. {format_number(window_max)} Å.",
        )
    return (effective_min, effective_max), None


def _format_query_float(value: float, *, digits: int = 12) -> str:
    if not math.isfinite(value):
        return "0"
    return f"{value:.{digits}g}"


def _append_transform_query(query: list[tuple[str, str]], transform_params: dict[str, object] | None) -> None:
    if transform_params is None:
        return
    params = _normalize_transform_params(transform_params)
    default = _normalize_transform_params()
    if (
        abs(params["redshift"] - default["redshift"]) < 1e-18
        and abs(params["broadening_km_s"] - default["broadening_km_s"]) < 1e-18
        and abs(params["ebv"] - default["ebv"]) < 1e-18
        and abs(params["distance_kpc"] - default["distance_kpc"]) < 1e-18
    ):
        return
    query.append(("redshift", _format_query_float(params["redshift"])))
    query.append(("broadening_km_s", _format_query_float(params["broadening_km_s"])))
    query.append(("ebv", _format_query_float(params["ebv"])))
    query.append(("distance_kpc", _format_query_float(params["distance_kpc"])))


def _spectrum_url(
    model_root: str,
    *,
    fin: str,
    mode: str,
    obs_tokens: list[str] | None = None,
    upload_error: str = "",
    transform_params: dict[str, object] | None = None,
    fit_notice: str = "",
    fit_wavelength_inputs: dict[str, str] | None = None,
) -> str:
    base = url_for("viewer.spectrum", path=model_root)
    query: list[tuple[str, str]] = [("fin", fin), ("mode", _normalize_spectrum_mode(mode))]
    for token in obs_tokens or []:
        if is_valid_upload_token(token):
            query.append(("obs", token))
    _append_transform_query(query, transform_params)
    if isinstance(fit_wavelength_inputs, dict):
        fit_min = str(fit_wavelength_inputs.get("min", "")).strip()
        fit_max = str(fit_wavelength_inputs.get("max", "")).strip()
        if fit_min:
            query.append(("fit_lambda_min", fit_min))
        if fit_max:
            query.append(("fit_lambda_max", fit_max))
    if upload_error:
        query.append(("upload_error", upload_error))
    if fit_notice:
        query.append(("fit_notice", fit_notice))
    encoded = urlencode(query, doseq=True)
    return f"{base}?{encoded}" if encoded else base


def _spectrum_redirect(
    model_root: str,
    *,
    fin: str,
    mode: str,
    obs_tokens: list[str] | None = None,
    upload_error: str = "",
    transform_params: dict[str, object] | None = None,
    fit_notice: str = "",
    fit_wavelength_inputs: dict[str, str] | None = None,
):
    return redirect(
        _spectrum_url(
            model_root,
            fin=fin,
            mode=mode,
            obs_tokens=obs_tokens or [],
            upload_error=upload_error,
            transform_params=transform_params,
            fit_notice=fit_notice,
            fit_wavelength_inputs=fit_wavelength_inputs,
        )
    )


def _bulk_spectra_url(
    path: str,
    *,
    selected_models: list[str],
    mode: str,
    obs_tokens: list[str] | None = None,
    upload_error: str = "",
) -> str:
    base = url_for("viewer.bulk_spectra", path=path)
    query: list[tuple[str, str]] = [("mode", _normalize_spectrum_mode(mode))]
    for rel in selected_models:
        query.append(("selected_models", rel))
    for token in obs_tokens or []:
        if is_valid_upload_token(token):
            query.append(("obs", token))
    if upload_error:
        query.append(("upload_error", upload_error))
    encoded = urlencode(query, doseq=True)
    return f"{base}?{encoded}" if encoded else base


def _bulk_spectra_redirect(
    path: str,
    *,
    selected_models: list[str],
    mode: str,
    obs_tokens: list[str] | None = None,
    upload_error: str = "",
):
    return redirect(
        _bulk_spectra_url(
            path,
            selected_models=selected_models,
            mode=mode,
            obs_tokens=obs_tokens or [],
            upload_error=upload_error,
        )
    )


def _resolve_selected_model_dirs(
    basepath: str,
    directory: Path,
    selected_paths: list[str],
) -> tuple[list[tuple[str, Path]], list[list[str]]]:
    valid: list[tuple[str, Path]] = []
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
        valid.append((rel, target))
    return valid, skipped


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
    summary_cache_db = str(config.get("summary_cache_db", "model_summary_cache.sqlite"))

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

    if is_model_context_path(path):
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
        created_label = str(display.get("created_at", ""))
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
    if is_model_context_path(path):
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
        "points": len(parsed.get("wavelength", [])),
        "created_at": time.time(),
    }
    write_upload_manifest(upload_root, token, manifest)

    selected_tokens = _collect_obs_tokens(current_obs_tokens + [token])
    return _bulk_spectra_redirect(path, selected_models=selected_paths, mode=view_mode, obs_tokens=selected_tokens)


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

    rows = [
        ["File", str(entry.get("filename", ""))],
        ["Upload token", token],
        ["Stored format", format_name],
        ["Format details", _upload_format_description(format_name)],
        ["Flux mode", flux_mode],
        ["Detected flux mode", detected_flux_mode],
        ["Requested flux mode", requested_flux_mode],
        ["Parsed points", str(len(parsed.get("wavelength", [])))],
        ["Raw points", str(parsed.get("raw_points", ""))],
        ["Skipped invalid points", str(parsed.get("skipped_points", 0))],
        ["Skipped by wavelength window", str(parsed.get("range_skipped_points", 0))],
        ["Wavelength span (Å)", span_label],
        ["Configured wavelength window (Å)", f"{format_number(lambda_min)} .. {format_number(lambda_max)}"],
        ["File size", _format_upload_size(entry.get("size", 0))],
        ["Uploaded at", _format_upload_time(entry.get("created_at", 0))],
    ]
    return [[label, value] for label, value in rows if value not in {"", None}]


def _fit_bounds_payload(bounds: dict[str, tuple[float, float]]) -> dict[str, list[float]]:
    return {
        name: [float(min_value), float(max_value)]
        for name, (min_value, max_value) in bounds.items()
    }


def _fit_wavelength_range_payload(bounds: tuple[float, float] | None) -> dict[str, float]:
    if bounds is None:
        return {}
    return {"min": float(bounds[0]), "max": float(bounds[1])}


def _fit_wavelength_range_from_payload(payload: object) -> tuple[float, float] | None:
    if not isinstance(payload, dict):
        return None
    min_raw = payload.get("min")
    max_raw = payload.get("max")
    if not isinstance(min_raw, int | float) or not isinstance(max_raw, int | float):
        return None
    min_value = float(min_raw)
    max_value = float(max_raw)
    if not math.isfinite(min_value) or not math.isfinite(max_value):
        return None
    if min_value > max_value:
        min_value, max_value = max_value, min_value
    if min_value <= 0 or min_value >= max_value:
        return None
    return min_value, max_value


def _resolve_grid_fit_pool_size(max_pool_size: int, total_models: int) -> int:
    if total_models <= 1:
        return 1
    resolved = int(max_pool_size) if isinstance(max_pool_size, int | float) else 0
    if resolved <= 0:
        cpu_count = os.cpu_count()
        resolved = cpu_count if isinstance(cpu_count, int) and cpu_count > 0 else 1
    resolved = max(1, resolved)
    return min(int(total_models), resolved)


def _fit_single_model_candidate(
    *,
    model_name: str,
    model_relpath: str,
    model_path_str: str,
    observed: dict[str, object],
    mode: str,
    fit_bounds: dict[str, tuple[float, float]],
    lambda_min: float,
    lambda_max: float,
    should_cancel: object | None = None,
) -> dict[str, object]:
    model_dir = Path(model_path_str)
    spectrum_files = discover_final_spectrum_files(model_dir)
    if spectrum_files is None:
        return {"status": "failed"}

    fin_files = spectrum_files.get("fin_files")
    if not isinstance(fin_files, list) or not fin_files:
        return {"status": "failed"}
    selected_fin = fin_files[0]
    if not isinstance(selected_fin, Path):
        return {"status": "failed"}

    try:
        continuum = load_obs_spectrum(
            Path(spectrum_files["obs_cont"]),
            lambda_min=lambda_min,
            lambda_max=lambda_max,
        )
        final = load_obs_spectrum(
            selected_fin,
            lambda_min=lambda_min,
            lambda_max=lambda_max,
        )
    except Exception:
        return {"status": "failed"}

    best_params, metrics, fit_error = fit_model_to_observed(
        continuum,
        final,
        observed,
        mode=mode,
        initial_params=SPECTRUM_TRANSFORM_DEFAULTS,
        bounds_override=fit_bounds,
        should_cancel=should_cancel,
    )
    if fit_error == FIT_CANCELED_MESSAGE:
        return {"status": "canceled"}
    if fit_error or best_params is None or not isinstance(metrics, dict):
        return {"status": "failed"}

    rmse_raw = metrics.get("rmse")
    if not isinstance(rmse_raw, int | float) or not math.isfinite(float(rmse_raw)):
        return {"status": "failed"}

    points_raw = metrics.get("points", 0)
    points = int(points_raw) if isinstance(points_raw, int | float) else 0
    return {
        "status": "success",
        "item": {
            "model_name": model_name,
            "model_path": model_relpath,
            "fin": selected_fin.name,
            "rmse": float(rmse_raw),
            "points": points,
            "fit_params": {
                "redshift": float(best_params.get("redshift", 0.0)),
                "broadening_km_s": float(best_params.get("broadening_km_s", 0.0)),
                "ebv": float(best_params.get("ebv", 0.0)),
                "distance_kpc": float(best_params.get("distance_kpc", 1.0)),
            },
        },
    }


_GRID_FIT_WORKER_CONTEXT: dict[str, object] = {}


def _grid_fit_worker_init(
    observed: dict[str, object],
    mode: str,
    fit_bounds: dict[str, tuple[float, float]],
    lambda_min: float,
    lambda_max: float,
) -> None:
    global _GRID_FIT_WORKER_CONTEXT
    _GRID_FIT_WORKER_CONTEXT = {
        "observed": observed,
        "mode": mode,
        "fit_bounds": fit_bounds,
        "lambda_min": float(lambda_min),
        "lambda_max": float(lambda_max),
    }


def _grid_fit_worker_task(model_candidate: tuple[str, str, str]) -> dict[str, object]:
    observed = _GRID_FIT_WORKER_CONTEXT.get("observed")
    mode = _GRID_FIT_WORKER_CONTEXT.get("mode")
    fit_bounds = _GRID_FIT_WORKER_CONTEXT.get("fit_bounds")
    lambda_min = _GRID_FIT_WORKER_CONTEXT.get("lambda_min")
    lambda_max = _GRID_FIT_WORKER_CONTEXT.get("lambda_max")
    if not isinstance(observed, dict):
        return {"status": "failed"}
    if not isinstance(mode, str):
        return {"status": "failed"}
    if not isinstance(fit_bounds, dict):
        return {"status": "failed"}
    if not isinstance(lambda_min, int | float) or not isinstance(lambda_max, int | float):
        return {"status": "failed"}
    model_name, model_relpath, model_path_str = model_candidate
    return _fit_single_model_candidate(
        model_name=model_name,
        model_relpath=model_relpath,
        model_path_str=model_path_str,
        observed=observed,
        mode=mode,
        fit_bounds=fit_bounds,
        lambda_min=float(lambda_min),
        lambda_max=float(lambda_max),
        should_cancel=None,
    )


def _discover_model_grid_from_cache(
    basepath: str,
    *,
    summary_cache_db: str,
    model_name_pattern: str,
) -> tuple[list[tuple[str, str, Path]], str | None]:
    try:
        cache_rows = list_model_summaries(
            summary_cache_db,
            basepath=basepath,
            expected_columns=len(SUMMARY_COLUMNS),
        )
    except Exception as exc:
        return [], f"Failed to read model summary cache: {exc}"

    if not cache_rows:
        return [], "Model summary cache is empty; build model summaries first."

    pattern = str(model_name_pattern or "").strip()
    candidates: list[tuple[str, str, Path]] = []
    seen_relpaths: set[str] = set()
    missing_entries = 0
    for row in cache_rows:
        relpath = str(row.get("path", "")).strip().strip("/")
        if not relpath or relpath in seen_relpaths:
            continue
        seen_relpaths.add(relpath)

        values = row.get("values")
        model_name = str(values[0]).strip() if isinstance(values, list) and values else ""
        if not model_name:
            model_name = Path(relpath).name

        if pattern and not fnmatch.fnmatch(model_name, pattern):
            continue

        try:
            model_dir = resolve_path(basepath, relpath)
        except FileNotFoundError:
            missing_entries += 1
            continue
        if not model_dir.is_dir():
            missing_entries += 1
            continue

        candidates.append((model_name, relpath, model_dir))

    candidates.sort(key=lambda item: (item[0].lower(), item[1].lower()))
    if candidates:
        return candidates, None

    if pattern:
        if missing_entries > 0:
            return [], (
                f"No cached models matched pattern '{pattern}' with an accessible directory. "
                f"{missing_entries} cached entry(ies) were missing on disk."
            )
        return [], f"No cached models matched pattern '{pattern}'."

    if missing_entries > 0:
        return [], (
            "No cached models with accessible directories were found. "
            f"{missing_entries} cached entry(ies) were missing on disk."
        )
    return [], "No cached models are available for grid search."


def _grid_search_prune_locked(now: float) -> None:
    expired_ids: list[str] = []
    for job_id, job in GRID_SEARCH_JOBS.items():
        if str(job.get("status", "")) == "running":
            continue
        finished_at_raw = job.get("finished_at", job.get("created_at", 0.0))
        try:
            finished_at = float(finished_at_raw)
        except (TypeError, ValueError):
            finished_at = 0.0
        if finished_at > 0 and (now - finished_at) > GRID_SEARCH_JOB_TTL_SECONDS:
            expired_ids.append(job_id)
    for job_id in expired_ids:
        GRID_SEARCH_JOBS.pop(job_id, None)

    if len(GRID_SEARCH_JOBS) <= GRID_SEARCH_MAX_JOBS:
        return

    finished_jobs = [
        (
            job_id,
            float(job.get("finished_at", job.get("created_at", 0.0)) or 0.0),
        )
        for job_id, job in GRID_SEARCH_JOBS.items()
        if str(job.get("status", "")) != "running"
    ]
    finished_jobs.sort(key=lambda item: item[1])
    while len(GRID_SEARCH_JOBS) > GRID_SEARCH_MAX_JOBS and finished_jobs:
        job_id, _timestamp = finished_jobs.pop(0)
        GRID_SEARCH_JOBS.pop(job_id, None)


def _grid_search_job_update(job_id: str, **fields: object) -> bool:
    with GRID_SEARCH_JOBS_LOCK:
        job = GRID_SEARCH_JOBS.get(job_id)
        if not isinstance(job, dict):
            return False
        for key, value in fields.items():
            job[key] = value
    return True


def _grid_search_job_cancel_requested(job_id: str) -> bool:
    with GRID_SEARCH_JOBS_LOCK:
        job = GRID_SEARCH_JOBS.get(job_id)
        if not isinstance(job, dict):
            return False
        return bool(job.get("cancel_requested", False))


def _grid_search_job_snapshot(job_id: str) -> dict[str, object] | None:
    with GRID_SEARCH_JOBS_LOCK:
        job = GRID_SEARCH_JOBS.get(job_id)
        if not isinstance(job, dict):
            return None
        return copy.deepcopy(job)


def _grid_search_active_job_for_upload(upload_token: str) -> dict[str, object] | None:
    with GRID_SEARCH_JOBS_LOCK:
        latest: tuple[str, dict[str, object]] | None = None
        latest_created = -1.0
        for job_id, job in GRID_SEARCH_JOBS.items():
            if not isinstance(job, dict):
                continue
            if str(job.get("upload_token", "")) != upload_token:
                continue
            if str(job.get("status", "")) != "running":
                continue
            try:
                created_at = float(job.get("created_at", 0.0))
            except (TypeError, ValueError):
                created_at = 0.0
            if latest is None or created_at > latest_created:
                latest = (job_id, copy.deepcopy(job))
                latest_created = created_at

    if latest is None:
        return None
    job_id, payload = latest
    payload["job_id"] = job_id
    return payload


def _grid_search_job_create(
    *,
    upload_token: str,
    mode: str,
    fit_bounds: dict[str, tuple[float, float]],
    fit_wavelength_range: tuple[float, float] | None,
    model_name_pattern: str,
    total_models: int,
) -> str:
    job_id = secrets.token_urlsafe(12)
    now = time.time()
    payload: dict[str, object] = {
        "job_id": job_id,
        "status": "running",
        "upload_token": upload_token,
        "mode": mode,
        "model_name_pattern": str(model_name_pattern or "").strip(),
        "fit_bounds": _fit_bounds_payload(fit_bounds),
        "fit_wavelength_range": _fit_wavelength_range_payload(fit_wavelength_range),
        "total": int(total_models),
        "processed": 0,
        "successful": 0,
        "failed": 0,
        "current_model": "",
        "best_so_far": {},
        "created_at": now,
        "started_at": now,
        "finished_at": 0.0,
        "cancel_requested": False,
        "cancel_requested_at": 0.0,
        "error": "",
        "result": {},
    }
    with GRID_SEARCH_JOBS_LOCK:
        _grid_search_prune_locked(now)
        GRID_SEARCH_JOBS[job_id] = payload
    return job_id


def _run_upload_grid_search_job(
    job_id: str,
    *,
    upload_token: str,
    mode: str,
    observed: dict[str, object],
    fit_bounds: dict[str, tuple[float, float]],
    fit_wavelength_range: tuple[float, float] | None,
    model_name_pattern: str,
    model_candidates: list[tuple[str, str, str]],
    lambda_min: float,
    lambda_max: float,
    max_pool_size: int,
) -> None:
    try:
        def update_iteration_progress(processed: int, *, current_model: str | None = None) -> None:
            fields: dict[str, object] = {
                "processed": processed,
                "successful": successful,
                "failed": failed,
                "best_so_far": copy.deepcopy(best_model) if best_model is not None else {},
            }
            if current_model is not None:
                fields["current_model"] = current_model
            _grid_search_job_update(job_id, **fields)

        def finish_canceled(
            *,
            processed: int,
            successful: int,
            failed: int,
            elapsed_seconds: float,
            top_models: list[dict[str, object]],
            best_model: dict[str, object] | None,
        ) -> None:
            result_payload: dict[str, object] = {
                "mode": mode,
                "upload_token": upload_token,
                "model_name_pattern": str(model_name_pattern or "").strip(),
                "fit_bounds": _fit_bounds_payload(fit_bounds),
                "fit_wavelength_range": _fit_wavelength_range_payload(fit_wavelength_range),
                "elapsed_seconds": elapsed_seconds,
                "best_model": best_model,
                "top_models": top_models,
            }
            _grid_search_job_update(
                job_id,
                status="canceled",
                processed=processed,
                successful=successful,
                failed=failed,
                current_model="",
                best_so_far=copy.deepcopy(best_model) if best_model is not None else {},
                result=result_payload,
                finished_at=time.time(),
                error="Grid search canceled by user.",
            )

        total = len(model_candidates)
        successful = 0
        failed = 0
        best_model: dict[str, object] | None = None
        top_models: list[dict[str, object]] = []
        started_at = time.time()
        worker_count = _resolve_grid_fit_pool_size(max_pool_size, total)

        def apply_candidate_result(candidate_result: dict[str, object], *, processed: int) -> bool:
            nonlocal successful, failed, best_model, top_models
            status = str(candidate_result.get("status", "failed"))
            if status == "canceled":
                finish_canceled(
                    processed=max(0, processed - 1),
                    successful=successful,
                    failed=failed,
                    elapsed_seconds=max(0.0, time.time() - started_at),
                    top_models=top_models,
                    best_model=best_model,
                )
                return True

            item = candidate_result.get("item")
            if status != "success" or not isinstance(item, dict):
                failed += 1
                update_iteration_progress(processed, current_model="")
                return False

            successful += 1
            top_models.append(item)
            top_models.sort(key=lambda candidate: float(candidate.get("rmse", math.inf)))
            if len(top_models) > GRID_SEARCH_TOP_RESULTS:
                top_models = top_models[:GRID_SEARCH_TOP_RESULTS]

            if best_model is None or float(item["rmse"]) < float(best_model.get("rmse", math.inf)):
                best_model = dict(item)
            update_iteration_progress(processed, current_model="")
            return False

        if worker_count <= 1:
            for index, (model_name, model_relpath, model_path_str) in enumerate(model_candidates, start=1):
                _grid_search_job_update(
                    job_id,
                    current_model=f"{model_name} ({model_relpath})",
                    processed=index - 1,
                    successful=successful,
                    failed=failed,
                )
                if _grid_search_job_cancel_requested(job_id):
                    finish_canceled(
                        processed=index - 1,
                        successful=successful,
                        failed=failed,
                        elapsed_seconds=max(0.0, time.time() - started_at),
                        top_models=top_models,
                        best_model=best_model,
                    )
                    return

                candidate_result = _fit_single_model_candidate(
                    model_name=model_name,
                    model_relpath=model_relpath,
                    model_path_str=model_path_str,
                    observed=observed,
                    mode=mode,
                    fit_bounds=fit_bounds,
                    lambda_min=lambda_min,
                    lambda_max=lambda_max,
                    should_cancel=lambda: _grid_search_job_cancel_requested(job_id),
                )
                was_canceled = apply_candidate_result(candidate_result, processed=index)
                if was_canceled:
                    return
        else:
            _grid_search_job_update(
                job_id,
                current_model=f"Parallel fitting across {worker_count} workers.",
                processed=0,
                successful=successful,
                failed=failed,
            )
            pool: object | None = None
            try:
                context = mp.get_context("spawn")
                pool = context.Pool(
                    processes=worker_count,
                    initializer=_grid_fit_worker_init,
                    initargs=(observed, mode, fit_bounds, lambda_min, lambda_max),
                )
                iterator = pool.imap_unordered(_grid_fit_worker_task, model_candidates, chunksize=1)
                processed = 0
                while processed < total:
                    if _grid_search_job_cancel_requested(job_id):
                        pool.terminate()
                        pool.join()
                        pool = None
                        finish_canceled(
                            processed=processed,
                            successful=successful,
                            failed=failed,
                            elapsed_seconds=max(0.0, time.time() - started_at),
                            top_models=top_models,
                            best_model=best_model,
                        )
                        return
                    try:
                        candidate_result = iterator.next(timeout=0.25)
                    except mp.TimeoutError:
                        continue
                    except StopIteration:
                        break
                    processed += 1
                    was_canceled = apply_candidate_result(candidate_result, processed=processed)
                    if was_canceled:
                        pool.terminate()
                        pool.join()
                        pool = None
                        return
                pool.close()
                pool.join()
                pool = None
            finally:
                if pool is not None:
                    pool.terminate()
                    pool.join()

        if _grid_search_job_cancel_requested(job_id):
            finish_canceled(
                processed=total,
                successful=successful,
                failed=failed,
                elapsed_seconds=max(0.0, time.time() - started_at),
                top_models=top_models,
                best_model=best_model,
            )
            return

        elapsed_seconds = max(0.0, time.time() - started_at)
        result_payload: dict[str, object] = {
            "mode": mode,
            "upload_token": upload_token,
            "model_name_pattern": str(model_name_pattern or "").strip(),
            "fit_bounds": _fit_bounds_payload(fit_bounds),
            "fit_wavelength_range": _fit_wavelength_range_payload(fit_wavelength_range),
            "elapsed_seconds": elapsed_seconds,
            "best_model": best_model,
            "top_models": top_models,
        }

        _grid_search_job_update(
            job_id,
            status="completed",
            processed=total,
            successful=successful,
            failed=failed,
            current_model="",
            best_so_far=copy.deepcopy(best_model) if best_model is not None else {},
            result=result_payload,
            finished_at=time.time(),
            error="",
        )
    except Exception as exc:
        _grid_search_job_update(
            job_id,
            status="failed",
            finished_at=time.time(),
            error=f"Grid search failed: {exc}",
        )


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

    upload_flux_mode = str(entry.get("requested_flux_mode", "auto")).strip().lower() or "auto"
    try:
        parsed = parse_uploaded_spectrum(
            source_path,
            flux_mode=upload_flux_mode,
            lambda_min=lambda_min,
            lambda_max=lambda_max,
        )
    except Exception as exc:
        return redirect(url_for("viewer.uploads", error=f"Uploaded spectrum '{filename}' failed to load: {exc}"))
    parsed["name"] = filename

    warnings: list[str] = []
    upload_error = request.args.get("error", "").strip()
    if upload_error:
        warnings.append(upload_error)
    warnings.extend(str(item) for item in parsed.get("warnings", []))

    plot_data, plot_warning = build_uploaded_spectrum_plot(parsed)
    if plot_warning:
        warnings.append(plot_warning)

    spectrum_mode = "both" if str(parsed.get("flux_mode", "")).strip().lower() == "absolute" else "normalized"
    transform_params = _normalize_transform_params(request.args.to_dict(flat=True))
    fit_bounds = _normalize_fit_bounds(request.args.to_dict(flat=True), mode=spectrum_mode)
    fit_wavelength_inputs = {
        "min": str(request.args.get("fit_lambda_min", "")).strip(),
        "max": str(request.args.get("fit_lambda_max", "")).strip(),
    }
    model_name_pattern = str(request.args.get("model_name_pattern", "")).strip()
    active_job = _grid_search_active_job_for_upload(token)
    if not model_name_pattern and isinstance(active_job, dict):
        model_name_pattern = str(active_job.get("model_name_pattern", "")).strip()
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
        model_name_pattern=model_name_pattern,
        active_grid_job=active_grid_job,
        plot_data=plot_data,
        warnings=warnings,
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
    fit_bounds = _normalize_fit_bounds(request.form.to_dict(flat=True), mode=mode)
    model_name_pattern = str(request.form.get("model_name_pattern", "")).strip()

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
                "fit_bounds": active_job.get("fit_bounds", _fit_bounds_payload(fit_bounds)),
                "fit_wavelength_range": active_job.get(
                    "fit_wavelength_range",
                    _fit_wavelength_range_payload(fit_wavelength_range),
                ),
                "model_name_pattern": str(active_job.get("model_name_pattern", model_name_pattern)),
                "existing_job": True,
            }
        )

    model_dirs, discover_error = _discover_model_grid_from_cache(
        basepath,
        summary_cache_db=summary_cache_db,
        model_name_pattern=model_name_pattern,
    )
    if discover_error:
        return jsonify({"ok": False, "error": discover_error}), 400
    if not model_dirs:
        return jsonify({"ok": False, "error": "No cached models were available for grid search."}), 400

    serialized_candidates = [
        (model_name, relpath, str(path.resolve()))
        for model_name, relpath, path in model_dirs
    ]
    job_id = _grid_search_job_create(
        upload_token=token,
        mode=mode,
        fit_bounds=fit_bounds,
        fit_wavelength_range=fit_wavelength_range,
        model_name_pattern=model_name_pattern,
        total_models=len(serialized_candidates),
    )

    worker = Thread(
        target=_run_upload_grid_search_job,
        kwargs={
            "job_id": job_id,
            "upload_token": token,
            "mode": mode,
            "observed": observed,
            "fit_bounds": fit_bounds,
            "fit_wavelength_range": fit_wavelength_range,
            "model_name_pattern": model_name_pattern,
            "model_candidates": serialized_candidates,
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
            "total_models": len(serialized_candidates),
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
    best_path = str(enriched.get("model_path", ""))
    best_fin = str(enriched.get("fin", ""))
    fit_params = enriched.get("fit_params")
    if isinstance(fit_params, dict) and best_path and best_fin and upload_token:
        enriched["spectrum_url"] = _spectrum_url(
            best_path,
            fin=best_fin,
            mode=mode,
            obs_tokens=[upload_token],
            transform_params=fit_params,
        )
    if best_path:
        enriched["browse_url"] = url_for("viewer.view", path=best_path)
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
    observed_range = _finite_wavelength_bounds(observed.get("wavelength"))
    if observed_range is None:
        return None, "Uploaded spectrum does not have enough valid wavelength points."
    observed_min, observed_max = observed_range

    mode = "both" if str(snapshot.get("mode", "")).strip().lower() == "both" else "normalized"
    fit_params_raw = model_entry.get("fit_params")
    if not isinstance(fit_params_raw, dict):
        return None, "Best-fit model is missing fit parameters."
    fit_params = _normalize_transform_params(fit_params_raw)

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

    model_name_pattern = str(request.args.get("model_name_pattern", "")).strip()
    model_dirs, discover_error = _discover_model_grid_from_cache(
        basepath,
        summary_cache_db=summary_cache_db,
        model_name_pattern=model_name_pattern,
    )
    if discover_error:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": discover_error,
                    "model_name_pattern": model_name_pattern,
                    "total_models": 0,
                }
            ),
            400,
        )

    return jsonify(
        {
            "ok": True,
            "model_name_pattern": model_name_pattern,
            "total_models": len(model_dirs),
        }
    )


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
    lambda_min, lambda_max = _spectrum_lambda_bounds(config)

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
    transform_params = _normalize_transform_params(request.form.to_dict(flat=True))
    fit_wavelength_inputs = {
        "min": str(request.form.get("fit_lambda_min", "")).strip(),
        "max": str(request.form.get("fit_lambda_max", "")).strip(),
    }

    token = request.form.get("token", "").strip() or request.form.get("obs", "").strip()
    upload_root = _upload_root(config)
    if is_valid_upload_token(token):
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
        created_label = str(display.get("created_at", ""))
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
        if view_mode == "both" and flux_mode != "absolute":
            continue
        if view_mode == "normalized" and flux_mode != "normalized":
            continue
        label = str(parsed.get("name", token))
        fit_candidates.append({"token": token, "label": f"{label} [{flux_mode}]"})

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
