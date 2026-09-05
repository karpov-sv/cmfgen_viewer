"""Shared blueprint, constants, and request/URL helpers for viewer routes."""

from __future__ import annotations

import math
from pathlib import Path
from urllib.parse import urlencode

from flask import Blueprint, current_app, redirect, url_for

from .browser import is_model_context_path, resolve_path
from .job_store import JobStore
from .observed_spectrum import (
    is_valid_upload_token,
)
from .spectrum_io import discover_final_spectrum_files
from .spectrum_options import _normalize_spectrum_mode as _normalize_spectrum_mode
from .spectrum_options import _normalize_transform_params as _normalize_transform_params

bp = Blueprint("viewer", __name__)
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
    "GAMFLUX",
    "GAMFLUX_NEW",
    "GAMRAY_E_DEP",
    "GAMRAY_E_DEP_MOD",
    "ENERGY_COMP",
    "SPECIES_MASSES",
    "GENCOOL",
)
QUICK_LINK_GLOBS = (
    "obs_fin*",
    "obs_cont*",
    "obs/obs_fin*",
    "obs/obs_cont*",
    "obs/hydro_fin*",
    "obs/hydro_cont*",
    "obs/meanopac_fin*",
    "obs/ewdata_fin*",
    "obs/full_timing*",
    "obs/cont_timing*",
)


def _viewer_config() -> dict[str, object]:
    return dict(current_app.config.get("CMFGEN_VIEWER", {}))


def _upload_root(config: dict[str, object]) -> Path:
    root = str(config.get("upload_root", "/tmp/cmfgen_viewer_uploads"))
    return Path(root).expanduser().resolve()


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


def _model_root_relpath(relpath: str, basepath: str | None = None) -> str | None:
    parts = [part for part in Path(relpath).parts if part not in ("", ".")]
    for index, part in enumerate(parts):
        lowered = part.lower()
        if lowered.startswith("model") and lowered != "models":
            return "/".join(parts[: index + 1])
        if basepath is not None:
            candidate_relpath = "/".join(parts[: index + 1])
            try:
                candidate = resolve_path(basepath, candidate_relpath)
            except (FileNotFoundError, NotADirectoryError):
                continue
            if candidate.is_dir() and is_model_context_path(str(candidate)):
                return candidate_relpath
    return None


def _spectrum_link_context(basepath: str, relpath: str) -> dict[str, object] | None:
    model_root = _model_root_relpath(relpath, basepath)
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


def _grid_jobs() -> JobStore:
    return current_app.extensions["cmfgen_jobs"]["grid"]


def _cache_jobs() -> JobStore:
    return current_app.extensions["cmfgen_jobs"]["cache"]
