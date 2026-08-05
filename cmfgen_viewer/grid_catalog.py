"""CMFGEN/TLUSTY grid metadata, discovery, and confidence summaries."""

from __future__ import annotations

import csv
import fnmatch
from functools import lru_cache
import json
import math
from pathlib import Path
import re

from .browser import resolve_path
from .summary_cache import list_model_summaries
from .view_common import (
    GRID_FIT_SOURCE_CMFGEN,
    GRID_FIT_SOURCE_TLUSTY,
    SUMMARY_COLUMNS,
    SUMMARY_COLUMN_INDEX,
    TLUSTY_BSTAR_METALLICITY_MAP,
    TLUSTY_CHI2_CONFIDENCE_LEVELS,
    TLUSTY_CONFIDENCE_PARAM_SPECS,
    TLUSTY_CONFIDENCE_PHOTOMETRY_STRICT_REDUCED_CHI2_MAX,
    TLUSTY_MODEL_NAME_RE,
    TLUSTY_MODEL_SUFFIXES,
    TLUSTY_OSTAR_METALLICITY_MAP,
    _normalize_grid_fit_source,
    _parse_summary_float,
    _tlusty_root,
)

def _tlusty_segment_label(products: set[str]) -> str:
    if "optical" in products:
        return "optical"
    if "uv" in products:
        return "uv"
    if "sed" in products:
        return "sed"
    if "flux" in products:
        return "flux"
    if "continuum" in products:
        return "continuum"
    return "spectrum"


def _discover_model_grid_from_cache(
    basepath: str,
    *,
    summary_cache_db: str,
    model_name_pattern: str,
) -> tuple[list[tuple[str, str, Path, dict[str, object]]], str | None]:
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
    candidates: list[tuple[str, str, Path, dict[str, object]]] = []
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

        cmfgen_params = _cmfgen_fit_params_from_summary(values)
        candidates.append((model_name, relpath, model_dir, cmfgen_params))

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


def _parse_json_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip().lower() for item in parsed if str(item).strip()]
    return [part.strip().lower() for part in text.split(",") if part.strip()]


def _parse_float_or_none(value: object) -> float | None:
    parsed = _parse_summary_float(value)
    if parsed is None or not math.isfinite(parsed):
        return None
    return float(parsed)


def _parse_int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return int(value)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _summary_column_value(values: object, column: str) -> object | None:
    if not isinstance(values, list):
        return None
    index = SUMMARY_COLUMN_INDEX.get(column)
    if index is None or index < 0 or index >= len(values):
        return None
    return values[index]


def _cmfgen_fit_params_payload(values: dict[str, object]) -> dict[str, object]:
    return {
        "teff_k": _parse_float_or_none(values.get("teff_k")),
        "log_g": _parse_float_or_none(values.get("log_g")),
        "luminosity": _parse_float_or_none(values.get("luminosity")),
    }


def _cmfgen_fit_params_from_summary(values: object) -> dict[str, object]:
    return _cmfgen_fit_params_payload(
        {
            "teff_k": _summary_column_value(values, "T_2/3"),
            "log_g": _summary_column_value(values, "logg"),
            "luminosity": _summary_column_value(values, "LSTAR"),
        }
    )


def _strip_tlusty_model_suffixes(model_name: object) -> str:
    stem = str(model_name or "").strip()
    if not stem:
        return ""

    changed = True
    while changed and stem:
        changed = False
        if "." in stem:
            maybe_stem, tail = stem.rsplit(".", 1)
            if tail.isdigit():
                stem = maybe_stem
                changed = True
                continue
        lowered = stem.lower()
        for suffix in TLUSTY_MODEL_SUFFIXES:
            if lowered.endswith(suffix):
                stem = stem[: -len(suffix)]
                changed = True
                break
        stem = stem.strip(". ")

    return stem


def _parse_tlusty_model_metadata(model_name: object, *, grid: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "composition_code": "",
        "teff_k": None,
        "log_g": None,
        "vturb_km_s": None,
        "tag": "",
        "z_over_zsun": None,
    }
    stem = _strip_tlusty_model_suffixes(model_name)
    if not stem:
        return payload

    match = TLUSTY_MODEL_NAME_RE.match(stem)
    if not match:
        return payload

    code = match.group("code").upper()
    vturb_raw = match.group("vturb")
    payload["composition_code"] = code
    payload["teff_k"] = int(match.group("teff"))
    payload["log_g"] = int(match.group("logg")) / 100.0
    payload["vturb_km_s"] = int(vturb_raw) if vturb_raw else None
    payload["tag"] = match.group("tag")

    normalized_grid = str(grid or "").strip().lower()
    if normalized_grid == "ostar":
        z_map = TLUSTY_OSTAR_METALLICITY_MAP
    elif normalized_grid == "bstar":
        z_map = TLUSTY_BSTAR_METALLICITY_MAP
    else:
        z_map = {}
    z_value = z_map.get(code)
    if isinstance(z_value, int | float):
        payload["z_over_zsun"] = float(z_value)
    return payload


def _tlusty_fit_params_payload(values: dict[str, object]) -> dict[str, object]:
    return {
        "composition_code": str(values.get("composition_code", "")).strip().upper(),
        "teff_k": _parse_int_or_none(values.get("teff_k")),
        "log_g": _parse_float_or_none(values.get("log_g")),
        "z_over_zsun": _parse_float_or_none(values.get("z_over_zsun")),
        "vturb_km_s": _parse_int_or_none(values.get("vturb_km_s")),
    }


def _parse_tlusty_profile_value(value: object, *, integer: bool) -> int | float | None:
    numeric = _parse_float_or_none(value)
    if numeric is None:
        return None
    if integer:
        return int(round(numeric))
    return float(numeric)


def _empty_tlusty_confidence_profiles() -> dict[str, dict[int | float, dict[str, object]]]:
    profiles: dict[str, dict[int | float, dict[str, object]]] = {}
    for spec in TLUSTY_CONFIDENCE_PARAM_SPECS:
        profiles[str(spec["key"])] = {}
    return profiles


def _chi2_from_fit_item(item: dict[str, object]) -> float | None:
    chi2_raw = item.get("chi2")
    if isinstance(chi2_raw, int | float) and math.isfinite(float(chi2_raw)):
        chi2 = float(chi2_raw)
        if chi2 >= 0.0:
            return chi2

    rmse_raw = item.get("rmse")
    points_raw = item.get("points")
    if not isinstance(rmse_raw, int | float) or not math.isfinite(float(rmse_raw)):
        return None
    if not isinstance(points_raw, int | float):
        return None
    points = int(points_raw)
    if points <= 0:
        return None
    rmse = float(rmse_raw)
    return float(rmse * rmse * points)


def _fit_param_count_for_mode(mode: str) -> int:
    return 4 if str(mode).strip().lower() == "both" else 2


def _update_tlusty_confidence_profiles(
    profiles: dict[str, dict[int | float, dict[str, object]]] | None,
    item: dict[str, object],
) -> None:
    if not isinstance(profiles, dict):
        return
    chi2 = _chi2_from_fit_item(item)
    if chi2 is None:
        return
    points_raw = item.get("points")
    points = int(points_raw) if isinstance(points_raw, int | float) else 0
    tlusty_params = item.get("tlusty_params")
    if not isinstance(tlusty_params, dict):
        return
    for spec in TLUSTY_CONFIDENCE_PARAM_SPECS:
        key = str(spec["key"])
        integer = bool(spec.get("integer", False))
        value = _parse_tlusty_profile_value(tlusty_params.get(key), integer=integer)
        if value is None:
            continue
        profile = profiles.get(key)
        if not isinstance(profile, dict):
            continue
        prev = profile.get(value)
        prev_chi2 = None
        if isinstance(prev, dict):
            prev_chi2_raw = prev.get("chi2")
            if isinstance(prev_chi2_raw, int | float) and math.isfinite(float(prev_chi2_raw)):
                prev_chi2 = float(prev_chi2_raw)
        if prev_chi2 is None or chi2 < prev_chi2:
            profile[value] = {"chi2": chi2, "points": points}


def _summarize_tlusty_confidence_profiles(
    *,
    best_model: dict[str, object] | None,
    profiles: dict[str, dict[int | float, dict[str, object]]] | None,
    mode: str,
) -> dict[str, object]:
    if not isinstance(best_model, dict) or not isinstance(profiles, dict):
        return {}
    best_params = best_model.get("tlusty_params")
    if not isinstance(best_params, dict):
        return {}
    best_chi2 = _chi2_from_fit_item(best_model)
    if best_chi2 is None:
        return {}
    best_points_raw = best_model.get("points")
    best_points = int(best_points_raw) if isinstance(best_points_raw, int | float) and int(best_points_raw) > 0 else 0
    fit_param_count = _fit_param_count_for_mode(mode)
    best_dof = max(1, best_points - fit_param_count)
    best_dof_eff_method_raw = best_model.get("dof_eff_method")
    best_dof_eff_method = str(best_dof_eff_method_raw).strip().lower()
    best_dof_eff_raw = best_model.get("dof_eff")
    if best_dof_eff_method == "nominal_photometry":
        best_dof_eff = best_dof
    else:
        best_dof_eff = int(best_dof_eff_raw) if isinstance(best_dof_eff_raw, int | float) and int(best_dof_eff_raw) > 0 else best_dof
    best_dof_eff = max(1, min(best_dof, best_dof_eff))
    best_reduced_chi2_eff = best_chi2 / max(1, best_dof_eff)

    chi2_weighting_raw = best_model.get("chi2_weighting")
    chi2_weighting = str(chi2_weighting_raw).strip().lower() if isinstance(chi2_weighting_raw, str) else ""
    photometry_error_weighting_raw = best_model.get("photometry_error_weighting")
    photometry_error_weighting = (
        str(photometry_error_weighting_raw).strip().lower()
        if isinstance(photometry_error_weighting_raw, str)
        else ""
    )
    photometry_known_errors_mode = (
        chi2_weighting == "photometry_flux_err_weighted"
        and photometry_error_weighting == "flux_err_or_2pct_fallback"
    )

    sigma2_hat_nominal = best_chi2 / max(1, best_dof)
    sigma2_hat = best_chi2 / max(1, best_dof_eff)
    if not math.isfinite(sigma2_hat) or sigma2_hat <= 0:
        sigma2_hat = sigma2_hat_nominal
    if not math.isfinite(sigma2_hat) or sigma2_hat <= 0:
        sigma2_hat = 1.0
    if not math.isfinite(sigma2_hat_nominal) or sigma2_hat_nominal <= 0:
        sigma2_hat_nominal = sigma2_hat

    confidence_method = "profile_delta_chi2_gaussian_unknown_variance"

    def confidence_score_from_chi2(chi2_value: float) -> float:
        return max(0.0, (chi2_value - best_chi2) / max(1e-12, sigma2_hat))

    if photometry_known_errors_mode:
        if best_reduced_chi2_eff <= TLUSTY_CONFIDENCE_PHOTOMETRY_STRICT_REDUCED_CHI2_MAX:
            confidence_method = "profile_delta_chi2_known_variance"
            sigma2_hat = 1.0
            sigma2_hat_nominal = 1.0

            def confidence_score_from_chi2(chi2_value: float) -> float:
                return max(0.0, chi2_value - best_chi2)

        else:
            confidence_method = "profile_delta_chi2_profile_jitter"

            def confidence_score_from_chi2(chi2_value: float) -> float:
                if chi2_value <= 0.0 or best_chi2 <= 0.0:
                    return math.inf
                return max(0.0, best_dof_eff * math.log(chi2_value / best_chi2))

    parameters: dict[str, object] = {}
    for spec in TLUSTY_CONFIDENCE_PARAM_SPECS:
        key = str(spec["key"])
        integer = bool(spec.get("integer", False))
        profile_raw = profiles.get(key)
        if not isinstance(profile_raw, dict) or not profile_raw:
            continue

        profile_min_by_value: dict[int | float, dict[str, object]] = {}
        for value_raw, payload in profile_raw.items():
            value = _parse_tlusty_profile_value(value_raw, integer=integer)
            if value is None:
                continue
            chi2 = None
            points = None
            if isinstance(payload, dict):
                chi2_raw = payload.get("chi2")
                if isinstance(chi2_raw, int | float) and math.isfinite(float(chi2_raw)):
                    chi2 = float(chi2_raw)
                points_raw = payload.get("points")
                if isinstance(points_raw, int | float):
                    points = int(points_raw)
            elif isinstance(payload, int | float) and math.isfinite(float(payload)):
                chi2 = float(payload)
            if chi2 is None:
                continue
            prev = profile_min_by_value.get(value)
            prev_chi2 = None
            if isinstance(prev, dict):
                prev_raw = prev.get("chi2")
                if isinstance(prev_raw, int | float) and math.isfinite(float(prev_raw)):
                    prev_chi2 = float(prev_raw)
            if prev_chi2 is None or chi2 < prev_chi2:
                profile_min_by_value[value] = {"chi2": chi2, "points": points}
        if not profile_min_by_value:
            continue

        sorted_profile = sorted(
            ((value, float(payload["chi2"]), payload.get("points")) for value, payload in profile_min_by_value.items()),
            key=lambda pair: float(pair[0]),
        )

        best_value = _parse_tlusty_profile_value(best_params.get(key), integer=integer)
        best_value_chi2 = None
        if best_value is not None:
            entry = profile_min_by_value.get(best_value)
            if isinstance(entry, dict):
                chi2_raw = entry.get("chi2")
                if isinstance(chi2_raw, int | float) and math.isfinite(float(chi2_raw)):
                    best_value_chi2 = float(chi2_raw)

        intervals: dict[str, object] = {}
        for level in TLUSTY_CHI2_CONFIDENCE_LEVELS:
            label = str(level.get("label", "")).strip()
            delta_limit_raw = level.get("delta_chi2")
            if not label or not isinstance(delta_limit_raw, int | float):
                continue
            delta_limit = float(delta_limit_raw)
            if not math.isfinite(delta_limit) or delta_limit < 0:
                continue
            allowed_values = [
                value
                for value, chi2, _points in sorted_profile
                if confidence_score_from_chi2(chi2) <= (delta_limit + 1e-12)
            ]
            if not allowed_values:
                continue
            intervals[label] = {
                "min_value": allowed_values[0],
                "max_value": allowed_values[-1],
                "count": len(allowed_values),
                "contains_best": bool(
                    best_value is not None and allowed_values[0] <= best_value <= allowed_values[-1]
                ),
            }
        if not intervals:
            continue

        parameters[key] = {
            "label": str(spec.get("label", key)),
            "unit": str(spec.get("unit", "")),
            "is_integer": integer,
            "samples": len(sorted_profile),
            "best_value": best_value,
            "best_value_chi2": float(best_value_chi2) if isinstance(best_value_chi2, int | float) else None,
            "intervals": intervals,
        }

    if not parameters:
        return {}
    assumptions = ""
    if confidence_method == "profile_delta_chi2_known_variance":
        assumptions = (
            "Gaussian residuals with known per-point photometric errors "
            "(uploaded flux_err or 2% flux fallback when missing). "
            "Confidence intervals use strict profile delta-chi2 likelihood-ratio thresholds."
        )
    elif confidence_method == "profile_delta_chi2_profile_jitter":
        assumptions = (
            "Gaussian residuals with known per-point photometric error shape but unknown global scatter scale. "
            "A profiled jitter scale is used (delta = dof_eff * ln(chi2/chi2_best)) "
            "to keep intervals robust under model misspecification."
        )
    else:
        assumptions = (
            "Gaussian residuals with unknown common variance; "
            "variance is estimated from the best-fit residual sum of squares. "
            "Effective degrees of freedom are estimated from residual autocorrelation "
            "using the initial positive sequence."
        )
    if confidence_method == "profile_delta_chi2_gaussian_unknown_variance" and best_dof_eff_method == "nominal_photometry":
        assumptions = (
            "Gaussian residuals with unknown common variance; "
            "variance is estimated from the best-fit residual sum of squares. "
            "For photometric uploads, effective degrees of freedom are set to nominal "
            "degrees of freedom (independent-band assumption)."
        )
    return {
        "method": confidence_method,
        "assumptions": assumptions,
        "chi2": {
            "best_chi2": best_chi2,
            "best_points": best_points,
            "fit_param_count": fit_param_count,
            "best_dof": best_dof,
            "best_dof_eff": best_dof_eff,
            "best_dof_eff_method": best_dof_eff_method,
            "reduced_chi2_eff": best_reduced_chi2_eff,
            "chi2_weighting": chi2_weighting,
            "photometry_error_weighting": photometry_error_weighting,
            "sigma2_hat": sigma2_hat,
            "sigma2_hat_nominal": sigma2_hat_nominal,
            "strict_reduced_chi2_threshold": TLUSTY_CONFIDENCE_PHOTOMETRY_STRICT_REDUCED_CHI2_MAX,
        },
        "levels": [
            {"label": str(item["label"]), "delta_chi2": float(item["delta_chi2"])}
            for item in TLUSTY_CHI2_CONFIDENCE_LEVELS
        ],
        "parameters": parameters,
    }


def _file_signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=4)
def _load_tlusty_models_csv_cached(path_str: str, mtime_ns: int, size: int) -> list[dict[str, object]]:
    del mtime_ns, size
    path = Path(path_str)
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            grid = str(raw.get("grid", "")).strip().lower()
            model_name = str(raw.get("model_name", "")).strip()
            spectrum_relpath = str(raw.get("spectrum_relpath", "")).strip().strip("/")
            if not grid or not model_name or not spectrum_relpath:
                continue
            parsed_metadata = _parse_tlusty_model_metadata(model_name, grid=grid)
            composition_code = str(raw.get("composition_code", "")).strip().upper()
            if not composition_code:
                composition_code = str(parsed_metadata.get("composition_code", "")).strip().upper()
            tag = str(raw.get("tag", "")).strip()
            if not tag:
                tag = str(parsed_metadata.get("tag", "")).strip()
            teff_k = _parse_int_or_none(raw.get("teff_k"))
            if teff_k is None:
                teff_k = _parse_int_or_none(parsed_metadata.get("teff_k"))
            log_g = _parse_float_or_none(raw.get("log_g"))
            if log_g is None:
                log_g = _parse_float_or_none(parsed_metadata.get("log_g"))
            vturb_km_s = _parse_int_or_none(raw.get("vturb_km_s"))
            if vturb_km_s is None:
                vturb_km_s = _parse_int_or_none(parsed_metadata.get("vturb_km_s"))
            z_over_zsun = _parse_float_or_none(raw.get("z_over_zsun"))
            if z_over_zsun is None:
                z_over_zsun = _parse_float_or_none(parsed_metadata.get("z_over_zsun"))
            rows.append(
                {
                    "grid": grid,
                    "model_name": model_name,
                    "composition_code": composition_code,
                    "teff_k": teff_k,
                    "log_g": log_g,
                    "vturb_km_s": vturb_km_s,
                    "tag": tag,
                    "z_over_zsun": z_over_zsun,
                    "spectrum_relpath": spectrum_relpath,
                    "archive_name": str(raw.get("archive_name", "")).strip(),
                    "archive_member": str(raw.get("archive_member", "")).strip(),
                    "archive_products": _parse_json_string_list(raw.get("archive_products")),
                    "member_products": _parse_json_string_list(raw.get("member_products")),
                    "available_arrays": _parse_json_string_list(raw.get("available_arrays")),
                    "points": _parse_int_or_none(raw.get("points")),
                    "wavelength_min_angstrom": _parse_float_or_none(raw.get("wavelength_min_angstrom")),
                    "wavelength_max_angstrom": _parse_float_or_none(raw.get("wavelength_max_angstrom")),
                }
            )
    return rows


def _load_tlusty_model_rows(tlusty_root: Path) -> tuple[list[dict[str, object]], str | None]:
    models_csv = tlusty_root / "models.csv"
    if not models_csv.is_file():
        return [], f"TLUSTY index file is missing: {models_csv}"
    try:
        mtime_ns, size = _file_signature(models_csv)
        rows = _load_tlusty_models_csv_cached(str(models_csv.resolve()), mtime_ns, size)
    except Exception as exc:
        return [], f"Failed to read TLUSTY model index: {exc}"
    if not rows:
        return [], "TLUSTY model index is empty."
    return rows, None


def _tlusty_row_products(row: dict[str, object]) -> set[str]:
    products: set[str] = set()
    member_products = row.get("member_products")
    if isinstance(member_products, list):
        products.update(str(item).strip().lower() for item in member_products if str(item).strip())
    archive_products = row.get("archive_products")
    if isinstance(archive_products, list):
        products.update(str(item).strip().lower() for item in archive_products if str(item).strip())

    archive_name = str(row.get("archive_name", "")).strip().lower()
    archive_member = str(row.get("archive_member", "")).strip().lower()
    model_name = str(row.get("model_name", "")).strip().lower()
    text_tokens = " ".join([archive_name, archive_member, model_name])
    if "uv" in text_tokens:
        products.add("uv")
    if "vis" in text_tokens or "opt" in text_tokens:
        products.add("optical")
    if "hhe" in text_tokens or ".cont" in text_tokens or "continuum" in text_tokens:
        products.add("continuum")
    if re.search(r"(^|[^a-z0-9])sed([^a-z0-9]|$)", text_tokens):
        products.add("sed")
    if "flux" in text_tokens:
        products.add("flux")
    return products


def _tlusty_pair_key(grid: str, model_name: str) -> tuple[str, str, str]:
    parts = [part for part in str(model_name).strip().split(".") if part]
    if len(parts) >= 3 and parts[-1].isdigit():
        base = ".".join(parts[:-2]).strip().lower()
        if not base:
            base = parts[0].strip().lower()
        return (str(grid).strip().lower(), base, parts[-1])
    return (str(grid).strip().lower(), str(model_name).strip().lower(), "")


def _tlusty_family_key(grid: str, model_name: str) -> tuple[str, str]:
    parts = [part for part in str(model_name).strip().split(".") if part]
    if len(parts) >= 2 and parts[-1].isdigit():
        return (str(grid).strip().lower(), ".".join(parts[:-1]).strip().lower())
    return (str(grid).strip().lower(), str(model_name).strip().lower())


def _tlusty_row_wavelength_bounds(row: dict[str, object]) -> tuple[float, float] | None:
    min_raw = row.get("wavelength_min_angstrom")
    max_raw = row.get("wavelength_max_angstrom")
    if not isinstance(min_raw, int | float) or not isinstance(max_raw, int | float):
        return None
    lo = float(min_raw)
    hi = float(max_raw)
    if not math.isfinite(lo) or not math.isfinite(hi):
        return None
    if lo > hi:
        lo, hi = hi, lo
    if lo <= 0 or lo >= hi:
        return None
    return lo, hi


def _tlusty_select_continuum_row(
    spectrum_row: dict[str, object],
    continuum_rows: list[dict[str, object]],
) -> dict[str, object] | None:
    if not continuum_rows:
        return None

    spectrum_products = _tlusty_row_products(spectrum_row)
    spectrum_bounds = _tlusty_row_wavelength_bounds(spectrum_row)
    best_row: dict[str, object] | None = None
    best_score: tuple[float, float] = (-1.0, -1.0)
    for candidate in continuum_rows:
        candidate_products = _tlusty_row_products(candidate)
        same_band = 1.0 if (("optical" in spectrum_products and "optical" in candidate_products) or ("uv" in spectrum_products and "uv" in candidate_products)) else 0.0
        overlap = 0.0
        candidate_bounds = _tlusty_row_wavelength_bounds(candidate)
        if spectrum_bounds is not None and candidate_bounds is not None:
            overlap_lo = max(spectrum_bounds[0], candidate_bounds[0])
            overlap_hi = min(spectrum_bounds[1], candidate_bounds[1])
            if overlap_hi > overlap_lo:
                overlap = overlap_hi - overlap_lo
        score = (same_band, overlap)
        if score > best_score:
            best_score = score
            best_row = candidate
    return best_row


def _tlusty_select_paired_spectrum_continuum(
    spectrum_row: dict[str, object],
    family_rows: list[dict[str, object]],
) -> dict[str, object] | None:
    if not family_rows:
        return None

    spectrum_name = str(spectrum_row.get("model_name", "")).strip()
    spectrum_points_raw = spectrum_row.get("points")
    spectrum_points = int(spectrum_points_raw) if isinstance(spectrum_points_raw, int | float) else -1

    candidates: list[dict[str, object]] = []
    for row in family_rows:
        row_name = str(row.get("model_name", "")).strip()
        if not row_name or row_name == spectrum_name:
            continue
        candidates.append(row)
    if not candidates:
        return None

    def score(row: dict[str, object]) -> tuple[int, int, float]:
        row_points_raw = row.get("points")
        row_points = int(row_points_raw) if isinstance(row_points_raw, int | float) else -1
        prefer_smaller = 1 if (spectrum_points > 0 and row_points > 0 and row_points < spectrum_points) else 0
        same_band = 0
        row_name = str(row.get("model_name", "")).strip().lower()
        spectrum_lower = spectrum_name.lower()
        if ".uv." in spectrum_lower and ".uv." in row_name:
            same_band = 1
        if ".vis." in spectrum_lower and ".vis." in row_name:
            same_band = 1
        row_bounds = _tlusty_row_wavelength_bounds(row)
        spec_bounds = _tlusty_row_wavelength_bounds(spectrum_row)
        overlap = 0.0
        if row_bounds is not None and spec_bounds is not None:
            lo = max(row_bounds[0], spec_bounds[0])
            hi = min(row_bounds[1], spec_bounds[1])
            if hi > lo:
                overlap = hi - lo
        return (prefer_smaller, same_band, overlap)

    return max(candidates, key=score)


def _discover_tlusty_grid_models(
    config: dict[str, object],
    *,
    mode: str,
    model_name_pattern: str,
) -> tuple[list[dict[str, object]], str | None]:
    tlusty_root = _tlusty_root(config)
    rows, load_error = _load_tlusty_model_rows(tlusty_root)
    if load_error:
        return [], load_error

    pattern = str(model_name_pattern or "").strip()
    if mode == "both":
        spectrum_product_filter = {"uv", "optical", "sed", "flux"}
        spectrum_product_label = "UV/optical/SED"
    else:
        spectrum_product_filter = {"uv", "optical"}
        spectrum_product_label = "UV/optical"

    spectrum_rows: list[dict[str, object]] = []
    continuum_by_key: dict[tuple[str, str], list[dict[str, object]]] = {}
    family_rows: dict[tuple[str, str], list[dict[str, object]]] = {}
    missing_files = 0

    for row in rows:
        model_name = str(row.get("model_name", "")).strip()
        grid = str(row.get("grid", "")).strip().lower()
        relpath = str(row.get("spectrum_relpath", "")).strip().strip("/")
        if not model_name or not grid or not relpath:
            continue
        model_path_label = f"tlusty/{grid}/{model_name}"
        if pattern and not (fnmatch.fnmatch(model_name, pattern) or fnmatch.fnmatch(model_path_label, pattern)):
            continue

        spectrum_path = tlusty_root / relpath
        if not spectrum_path.is_file():
            missing_files += 1
            continue

        products = _tlusty_row_products(row)
        available_arrays_raw = row.get("available_arrays")
        available_arrays: set[str] = set()
        if isinstance(available_arrays_raw, list):
            available_arrays = {str(item).strip() for item in available_arrays_raw if str(item).strip()}
        pair_key = _tlusty_pair_key(grid, model_name)
        if "continuum" in products or "continuum_lambda_cgs" in available_arrays:
            continuum_by_key.setdefault(pair_key, []).append(row)
        if (products & spectrum_product_filter) and ("continuum" not in products):
            spectrum_rows.append(row)
            family_rows.setdefault(_tlusty_family_key(grid, model_name), []).append(row)

    if not spectrum_rows:
        if pattern:
            return [], f"No TLUSTY {spectrum_product_label} spectra matched pattern '{pattern}'."
        return [], f"No TLUSTY {spectrum_product_label} spectra were found in the local TLUSTY index."

    candidates: list[dict[str, object]] = []
    missing_continuum = 0
    for row in spectrum_rows:
        model_name = str(row["model_name"])
        grid = str(row["grid"])
        spectrum_relpath = str(row["spectrum_relpath"])
        spectrum_path = tlusty_root / spectrum_relpath
        products = _tlusty_row_products(row)
        available_arrays = {str(item).strip() for item in row.get("available_arrays", [])}
        continuum_row: dict[str, object] | None = None
        continuum_relpath = ""
        continuum_path = ""

        if mode != "both":
            if "normalized_flux_candidate" not in available_arrays:
                key = _tlusty_pair_key(grid, model_name)
                continuum_options = list(continuum_by_key.get(key, []))
                if not continuum_options and key[2]:
                    continuum_options = list(continuum_by_key.get((key[0], key[1], ""), []))
                paired_from_family = False
                continuum_row = _tlusty_select_continuum_row(row, continuum_options)
                if continuum_row is None:
                    family_key = _tlusty_family_key(grid, model_name)
                    continuum_row = _tlusty_select_paired_spectrum_continuum(row, family_rows.get(family_key, []))
                    paired_from_family = continuum_row is not None
                if continuum_row is None:
                    missing_continuum += 1
                    continue
                if paired_from_family:
                    spec_points_raw = row.get("points")
                    cont_points_raw = continuum_row.get("points")
                    if isinstance(spec_points_raw, int | float) and isinstance(cont_points_raw, int | float):
                        if int(spec_points_raw) <= int(cont_points_raw):
                            missing_continuum += 1
                            continue
                continuum_relpath = str(continuum_row.get("spectrum_relpath", "")).strip().strip("/")
                if not continuum_relpath:
                    missing_continuum += 1
                    continue
                continuum_file = tlusty_root / continuum_relpath
                if not continuum_file.is_file():
                    missing_continuum += 1
                    continue
                continuum_path = str(continuum_file.resolve())

        spectrum_label = _tlusty_segment_label(products)
        tlusty_params = _tlusty_fit_params_payload(row)
        candidates.append(
            {
                "fit_source": GRID_FIT_SOURCE_TLUSTY,
                "grid": grid,
                "model_name": model_name,
                "model_path": f"tlusty/{grid}/{model_name}",
                "model_relpath": f"tlusty/{grid}/{model_name}",
                "model_path_str": str(spectrum_path.resolve()),
                "spectrum_label": spectrum_label,
                "spectrum_relpath": spectrum_relpath,
                "spectrum_path_str": str(spectrum_path.resolve()),
                "continuum_relpath": continuum_relpath,
                "continuum_path_str": continuum_path,
                "tlusty_params": tlusty_params,
            }
        )

    candidates.sort(key=lambda item: (str(item.get("model_name", "")).lower(), str(item.get("spectrum_relpath", "")).lower()))
    if candidates:
        return candidates, None

    if mode != "both" and missing_continuum > 0:
        return [], (
            "No TLUSTY candidates had usable continuum counterparts for normalized fitting "
            f"({missing_continuum} spectrum entries lacked matching continuum files)."
        )
    if missing_files > 0:
        return [], f"No TLUSTY spectra with accessible files were found ({missing_files} entries missing on disk)."
    return [], "No TLUSTY models are available for grid search."


def _discover_grid_fit_candidates(
    config: dict[str, object],
    *,
    fit_source: str,
    mode: str,
    basepath: str,
    summary_cache_db: str,
    model_name_pattern: str,
) -> tuple[list[dict[str, object]], str | None]:
    normalized_source = _normalize_grid_fit_source(fit_source)
    if normalized_source == GRID_FIT_SOURCE_TLUSTY:
        return _discover_tlusty_grid_models(
            config,
            mode=mode,
            model_name_pattern=model_name_pattern,
        )

    model_dirs, discover_error = _discover_model_grid_from_cache(
        basepath,
        summary_cache_db=summary_cache_db,
        model_name_pattern=model_name_pattern,
    )
    if discover_error:
        return [], discover_error

    candidates = [
        {
            "fit_source": GRID_FIT_SOURCE_CMFGEN,
            "model_name": model_name,
            "model_path": relpath,
            "model_relpath": relpath,
            "model_path_str": str(path.resolve()),
            "cmfgen_params": cmfgen_params,
        }
        for model_name, relpath, path, cmfgen_params in model_dirs
    ]
    return candidates, None


