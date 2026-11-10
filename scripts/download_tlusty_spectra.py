#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
import fnmatch
import gzip
from html.parser import HTMLParser
import json
import math
import multiprocessing
import os
from pathlib import Path
import re
import tarfile
import tempfile
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import numpy as np
from scipy.ndimage import gaussian_filter1d


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "tlusty"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_CRAWL_DEPTH = 2
DEFAULT_ARCHIVE_PATTERN = "*"
USER_AGENT = "cmfgen-viewer-tlusty-fetcher/1.0"

SPECTRAL_GRID_PAGES = {
    "ostar": "https://tlusty.oca.eu/tlusty/Tlusty2002/tlusty-OS02.html",
    "bstar": "https://tlusty.oca.eu/tlusty/Tlusty2002/tlusty-BS06.html",
}

PRODUCT_KEYWORDS = {
    "flux": ("flux", "sed"),
    "uv": ("uv", "uvb", "uvby"),
    "optical": ("opt", "optical", "vis"),
    "continuum": ("cont", "continuum"),
}
DEFAULT_PRODUCTS = ("flux", "uv", "optical", "continuum")

# Solar-metallicity multipliers described by the TLUSTY OSTAR2002/BSTAR2006 docs.
OSTAR_METALLICITY_MAP = {
    "C": 2.0,
    "G": 1.0,
    "L": 0.5,
    "S": 0.2,
    "T": 0.1,
    "V": 0.03,
    "W": 0.01,
    "X": 0.003,
    "Y": 0.001,
    "Z": 0.0001,
}
BSTAR_METALLICITY_MAP = {
    "BC": 2.0,
    "BG": 1.0,
    "BL": 0.5,
    "BS": 0.2,
    "BT": 0.1,
    "BZ": 0.0,
}

LIGHT_SPEED_ANGSTROM_PER_SECOND = 2.99792458e18
SED_BINNING_METHOD = "flux_conserving_log_bins_v1"
FORTRAN_FLOAT_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$")
FORTRAN_MISSING_E_RE = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))([+-]\d+)$")
MODEL_NAME_RE = re.compile(
    r"^(?P<code>[A-Za-z]+)"
    r"(?P<teff>\d{4,5})"
    r"g(?P<logg>\d{3})"
    r"(?:v(?P<vturb>\d+))?"
    r"(?P<tag>[A-Za-z0-9_]*)$"
)
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
Y_COL_ARRAY_RE = re.compile(r"^y_col_(\d+)$")

ARCHIVE_SUFFIXES = (".tar", ".tar.gz", ".tgz")


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.append(value.strip())
                break


@dataclass
class ArchiveStats:
    grid: str
    archive_url: str
    archive_path: str
    archive_products: list[str]
    spectra_indexed: int = 0
    spectra_saved: int = 0
    skipped_non_spectrum: int = 0
    skipped_invalid: int = 0


@dataclass
class RunStats:
    downloaded_archives: int = 0
    skipped_existing_archives: int = 0
    reused_local_archives: int = 0
    processed_archives: int = 0
    indexed_spectra: int = 0
    saved_spectra: int = 0
    skipped_non_spectrum_files: int = 0
    skipped_invalid_spectra: int = 0
    failed_archives: int = 0


@dataclass
class ArchiveSource:
    grid: str
    archive_url: str
    archive_products: list[str]
    local_path: Path | None = None


def _parse_float_token(token: str) -> float | None:
    value = token.strip().rstrip(",;")
    if not value:
        return None

    value = value.replace("D", "E").replace("d", "e")
    if FORTRAN_FLOAT_RE.match(value):
        try:
            return float(value)
        except ValueError:
            return None

    match = FORTRAN_MISSING_E_RE.match(value)
    if match:
        try:
            return float(f"{match.group(1)}E{match.group(2)}")
        except ValueError:
            return None
    return None


def _decode_text(payload: bytes) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def _fetch_bytes(url: str, timeout: float) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def _fetch_links(url: str, timeout: float) -> list[str]:
    parser = _LinkCollector()
    parser.feed(_decode_text(_fetch_bytes(url, timeout)))
    return parser.links


def _normalize_url(url: str) -> str:
    normalized = url.split("#", 1)[0].strip()
    return normalized


def _is_archive_url(url: str) -> bool:
    lowered = url.lower()
    return any(lowered.endswith(suffix) for suffix in ARCHIVE_SUFFIXES)


def _looks_like_html_page(url: str) -> bool:
    path = urlparse(url).path.lower()
    if path.endswith(".html") or path.endswith(".htm"):
        return True
    last = Path(path).name
    return "." not in last


def _classify_archive_products(name: str) -> list[str]:
    lowered = name.lower()
    categories: list[str] = []
    for product, keywords in PRODUCT_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            categories.append(product)
    return categories


def _archive_passes_filters(
    file_name: str,
    *,
    selected_products: set[str],
    archive_patterns: list[str],
) -> tuple[bool, list[str]]:
    lowered = file_name.lower()
    categories = _classify_archive_products(lowered)

    cleaned_patterns = [pattern.lower() for pattern in archive_patterns if pattern.strip()]
    has_specific_pattern = any(pattern not in {"*", "*.*"} for pattern in cleaned_patterns)

    if categories:
        if selected_products and not selected_products.intersection(categories):
            return False, categories
    elif not has_specific_pattern:
        return False, categories

    if cleaned_patterns and not any(fnmatch.fnmatch(lowered, pattern) for pattern in cleaned_patterns):
        return False, categories
    return True, categories


def _discover_archive_urls(
    page_url: str,
    *,
    timeout: float,
    max_depth: int,
    selected_products: set[str],
    archive_patterns: list[str],
) -> list[tuple[str, list[str]]]:
    base_prefix = page_url.rsplit("/", 1)[0] + "/"

    pending: list[tuple[str, int]] = [(page_url, 0)]
    visited_pages: set[str] = set()
    discovered: dict[str, set[str]] = {}

    while pending:
        current_url, depth = pending.pop(0)
        if current_url in visited_pages:
            continue
        visited_pages.add(current_url)
        print(f"[scan] page={current_url} depth={depth}")

        try:
            links = _fetch_links(current_url, timeout)
        except Exception as exc:  # pragma: no cover - runtime network variability
            print(f"[error] Failed to read page {current_url}: {exc}")
            continue

        for href in links:
            absolute = _normalize_url(urljoin(current_url, href))
            if not absolute:
                continue

            parsed = urlparse(absolute)
            if parsed.scheme not in {"http", "https"}:
                continue
            if parsed.netloc.lower() != "tlusty.oca.eu":
                continue
            if not absolute.startswith(base_prefix):
                continue

            if _is_archive_url(absolute):
                filename = Path(parsed.path).name.lower()
                include, categories = _archive_passes_filters(
                    filename,
                    selected_products=selected_products,
                    archive_patterns=archive_patterns,
                )
                if not include:
                    continue
                discovered.setdefault(absolute, set()).update(categories)
                continue

            if depth >= max_depth:
                continue
            if _looks_like_html_page(absolute):
                pending.append((absolute, depth + 1))

    return [
        (url, sorted(tags))
        for url, tags in sorted(discovered.items(), key=lambda item: item[0])
    ]


def _download_file(
    url: str,
    destination: Path,
    *,
    timeout: float,
    force_download: bool,
    dry_run: bool,
) -> bool:
    if destination.exists() and not force_download:
        return False
    if dry_run:
        return True

    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        with destination.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 128)
                if not chunk:
                    break
                handle.write(chunk)
    return True


def _sanitize_name(value: str) -> str:
    sanitized = SAFE_NAME_RE.sub("_", value).strip("._")
    return sanitized or "unnamed"


def _metadata_stem_from_model_name(model_name: str) -> str:
    stem = str(model_name or "").strip()
    known_suffixes = (
        ".flux",
        ".cont",
        ".continuum",
        ".hhe",
        ".uv",
        ".uvb",
        ".uvby",
        ".opt",
        ".optical",
        ".vis",
        ".spec",
        ".sp",
    )
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
        for suffix in known_suffixes:
            if lowered.endswith(suffix):
                stem = stem[: -len(suffix)]
                changed = True
                break
        stem = stem.strip(". ")
    return stem


def _parse_model_metadata(model_name: str, grid: str) -> dict[str, object]:
    stem = str(model_name or "").strip()
    payload: dict[str, object] = {
        "model_name": stem,
        "grid": grid,
        "composition_code": "",
        "teff_k": None,
        "log_g": None,
        "vturb_km_s": None,
        "tag": "",
        "z_over_zsun": None,
    }
    metadata_stem = _metadata_stem_from_model_name(stem)
    match = MODEL_NAME_RE.match(metadata_stem)
    if not match:
        return payload

    code = match.group("code").upper()
    teff = int(match.group("teff"))
    log_g_raw = int(match.group("logg"))
    vturb_raw = match.group("vturb")
    tag = match.group("tag")

    z_map = OSTAR_METALLICITY_MAP if grid == "ostar" else BSTAR_METALLICITY_MAP
    payload["composition_code"] = code
    payload["teff_k"] = teff
    payload["log_g"] = log_g_raw / 100.0
    payload["vturb_km_s"] = int(vturb_raw) if vturb_raw else None
    payload["tag"] = tag
    if code in z_map:
        payload["z_over_zsun"] = float(z_map[code])
    return payload


def _model_name_from_member(member_basename: str) -> str:
    stem = Path(member_basename).stem
    return stem.strip() or Path(member_basename).stem


def _parse_numeric_matrix(payload: bytes) -> np.ndarray | None:
    rows_by_width: dict[int, list[list[float]]] = {}
    text = _decode_text(payload)
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].split("!", 1)[0].strip()
        if not line:
            continue
        tokens = line.split()
        if len(tokens) < 2:
            continue
        parsed_row: list[float] = []
        for token in tokens:
            parsed = _parse_float_token(token)
            if parsed is None:
                parsed_row = []
                break
            parsed_row.append(float(parsed))
        if len(parsed_row) < 2:
            continue
        width = len(parsed_row)
        rows_by_width.setdefault(width, []).append(parsed_row)

    if not rows_by_width:
        return None

    best_width, rows = max(
        rows_by_width.items(),
        key=lambda item: (len(item[1]), item[0]),
    )
    if best_width < 2 or len(rows) < 2:
        return None
    return np.asarray(rows, dtype=np.float64)


def _normalize_wavelength_axis(x_values: np.ndarray) -> tuple[np.ndarray, str, str]:
    p90 = float(np.percentile(x_values, 90.0))
    if p90 > 1.0e12:
        wavelength = LIGHT_SPEED_ANGSTROM_PER_SECOND / x_values
        return wavelength, "frequency_hz", "hz"
    if p90 < 50.0:
        return x_values * 1.0e4, "wavelength_input", "micron"
    if p90 < 1000.0:
        return x_values * 10.0, "wavelength_input", "nm"
    return x_values, "wavelength_input", "angstrom"


def _try_build_normalized_flux(flux: np.ndarray, continuum: np.ndarray) -> np.ndarray | None:
    finite = np.isfinite(flux) & np.isfinite(continuum) & (continuum > 0.0)
    if int(finite.sum()) < 32:
        return None
    ratio = np.full(flux.shape, np.nan, dtype=np.float64)
    ratio[finite] = flux[finite] / continuum[finite]
    valid = np.isfinite(ratio)
    if int(valid.sum()) < 32:
        return None
    p5 = float(np.nanpercentile(ratio[valid], 5.0))
    p95 = float(np.nanpercentile(ratio[valid], 95.0))
    if not math.isfinite(p5) or not math.isfinite(p95):
        return None
    if p5 <= -0.1 or p95 > 20.0:
        return None
    return ratio


def _parse_spectrum_payload(
    payload: bytes,
    *,
    product_tags: list[str],
) -> dict[str, object] | None:
    matrix = _parse_numeric_matrix(payload)
    if matrix is None:
        return None

    x_values = matrix[:, 0]
    y_values = matrix[:, 1:]
    finite_mask = np.isfinite(x_values) & (x_values > 0.0)
    if int(finite_mask.sum()) < 2:
        return None
    x_values = x_values[finite_mask]
    y_values = y_values[finite_mask, :]
    if y_values.shape[0] < 2 or y_values.shape[1] < 1:
        return None

    wavelength, x_axis_kind, x_unit_guess = _normalize_wavelength_axis(x_values)
    finite_rows = np.isfinite(wavelength) & (wavelength > 0.0) & np.any(np.isfinite(y_values), axis=1)
    if int(finite_rows.sum()) < 2:
        return None
    wavelength = wavelength[finite_rows]
    x_values = x_values[finite_rows]
    y_values = y_values[finite_rows, :]

    order = np.argsort(wavelength)
    wavelength = wavelength[order]
    x_values = x_values[order]
    y_values = y_values[order, :]

    unique_mask = np.concatenate(([True], np.diff(wavelength) > 0.0))
    if int(unique_mask.sum()) < 2:
        return None
    wavelength = wavelength[unique_mask]
    x_values = x_values[unique_mask]
    y_values = y_values[unique_mask, :]

    arrays: dict[str, np.ndarray] = {
        "wavelength_angstrom": wavelength.astype(np.float64),
    }
    primary = y_values[:, 0].astype(np.float64)
    arrays["flux_lambda_cgs"] = primary

    if x_axis_kind == "frequency_hz":
        arrays["flux_lambda_cgs"] = (primary * (LIGHT_SPEED_ANGSTROM_PER_SECOND / np.square(wavelength))).astype(
            np.float64
        )

    if "continuum" in product_tags:
        arrays["continuum_lambda_cgs"] = arrays["flux_lambda_cgs"].astype(np.float64)

    if y_values.shape[1] >= 2:
        normalized = _try_build_normalized_flux(y_values[:, 0], y_values[:, 1])
        if normalized is not None:
            arrays["normalized_flux_candidate"] = normalized

    arrays["input_columns"] = np.asarray(matrix.shape[1])
    arrays["x_axis_kind"] = np.asarray(x_axis_kind)
    arrays["x_unit_guess"] = np.asarray(x_unit_guess)

    return {
        "arrays": arrays,
        "points": int(wavelength.size),
        "wavelength_min_angstrom": float(np.min(wavelength)),
        "wavelength_max_angstrom": float(np.max(wavelength)),
        "input_columns": int(matrix.shape[1]),
        "x_axis_kind": x_axis_kind,
        "x_unit_guess": x_unit_guess,
    }


def _decode_member_payload(member_name: str, payload: bytes) -> bytes | None:
    name = member_name.lower()
    if name.endswith(".gz"):
        try:
            return gzip.decompress(payload)
        except OSError:
            return None
    return payload


def _reduce_resolution(
    parsed: dict[str, object], *, resolving_power: float, samples_per_resolution: float,
) -> dict[str, object]:
    """Add a Gaussian LSF in log wavelength, then sample at constant velocity.

    R specifies the added instrumental FWHM (lambda / R), not the width of
    intrinsically broadened stellar lines. Work at >=12 samples/FWHM before
    resampling, and never on fewer points than the native spectrum.
    """
    arrays = parsed["arrays"]
    wavelength = arrays["wavelength_angstrom"]
    log_wave = np.log(wavelength)
    span = log_wave[-1] - log_wave[0]
    output_count = max(2, int(np.ceil(span * resolving_power * samples_per_resolution)) + 1)
    work_count = max(len(wavelength), 4 * output_count, int(np.ceil(span * resolving_power * 12)) + 1)
    if work_count > 10_000_000:
        raise ValueError("Requested resolution requires more than 10 million working samples; lower R or sampling")
    work_log = np.linspace(log_wave[0], log_wave[-1], work_count)
    output_log = np.linspace(log_wave[0], log_wave[-1], output_count)
    sigma = 1.0 / (resolving_power * np.sqrt(8 * np.log(2))) / (work_log[1] - work_log[0])
    reduced = dict(arrays)
    for key in ("flux_lambda_cgs", "continuum_lambda_cgs", "normalized_flux_candidate"):
        if key not in arrays:
            continue
        values = arrays[key]
        if not np.all(np.isfinite(values)):
            raise ValueError(f"Cannot reduce resolution of nonfinite {key}")
        fine = np.interp(work_log, log_wave, values)
        smoothed = gaussian_filter1d(fine, sigma, mode="nearest", truncate=5.0)
        reduced[key] = np.interp(output_log, work_log, smoothed)
    reduced_wave = np.exp(output_log)
    reduced_wave[[0, -1]] = wavelength[[0, -1]]
    reduced["wavelength_angstrom"] = reduced_wave
    reduced["resolving_power"] = np.asarray(resolving_power)
    reduced["samples_per_resolution"] = np.asarray(samples_per_resolution)
    return {**parsed, "arrays": reduced, "points": output_count}


def _write_spectrum(destination: Path, arrays: dict) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.stem}-", suffix=".npz", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            np.savez_compressed(handle, **arrays)
        if destination.exists():
            os.chmod(temporary, destination.stat().st_mode & 0o777)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _conservative_sed_bins(wavelength, flux, binning_power):
    """Integrate native linear segments into bins of constant delta-lambda/lambda.

    Bin means become center samples, plus original endpoints, for the viewer's
    linear-interpolation representation. Sum local areas rather than subtracting
    cumulative integrals, which loses faint IR flux to cancellation.
    """
    if not math.isfinite(binning_power) or binning_power <= 0:
        raise ValueError("SED binning power must be finite and positive")
    span = np.log(wavelength[-1] / wavelength[0])
    if binning_power > 10_000_000 / span:
        raise ValueError("Requested SED grid exceeds 10 million bins")
    count = max(1, int(np.ceil(span * binning_power)))
    edges = np.geomspace(wavelength[0], wavelength[-1], count + 1)
    nodes = np.union1d(wavelength, edges)
    values = np.interp(nodes, wavelength, flux)
    mass = np.diff(nodes) * (values[:-1] + values[1:]) / 2
    bins = np.clip(np.searchsorted(edges, (nodes[1:] + nodes[:-1]) / 2) - 1, 0, count - 1)
    integrals = np.bincount(bins, weights=mass, minlength=count)
    means = integrals / np.diff(edges)
    centers = np.sqrt(edges[:-1] * edges[1:])
    return np.r_[wavelength[0], centers, wavelength[-1]], np.r_[flux[0], means, flux[-1]], integrals


def _rebin_sed(parsed: dict[str, object], *, binning_power: float) -> dict[str, object]:
    if not math.isfinite(binning_power) or binning_power <= 0:
        raise ValueError("SED binning power must be finite and positive")
    arrays = parsed["arrays"]
    wavelength = arrays["wavelength_angstrom"]
    span = np.log(wavelength[-1] / wavelength[0])
    # Record the request even if this atmosphere is already sparsely sampled,
    # so subsequent runs reuse it rather than rebuilding it every time.
    apply_rebin = binning_power < (len(wavelength) - 2) / span
    if apply_rebin:
        apply_rebin = int(np.ceil(span * binning_power)) + 2 < len(wavelength)
    reduced = dict(arrays)
    if apply_rebin:
        for key in ("flux_lambda_cgs", "continuum_lambda_cgs", "normalized_flux_candidate"):
            if key not in arrays:
                continue
            if not np.all(np.isfinite(arrays[key])):
                raise ValueError(f"Cannot rebin nonfinite SED {key}")
            new_wave, reduced[key], _ = _conservative_sed_bins(wavelength, arrays[key], binning_power)
        reduced["wavelength_angstrom"] = new_wave
    reduced["sed_binning_power"] = np.asarray(binning_power)
    reduced["sed_binning_method"] = np.asarray(SED_BINNING_METHOD)
    reduced["sed_rebin_applied"] = np.asarray(apply_rebin)
    return {**parsed, "arrays": reduced, "points": len(reduced["wavelength_angstrom"])}


def _archive_relpath(grid: str, archive_url: str) -> Path:
    archive_name = Path(urlparse(archive_url).path).name
    return Path("raw") / grid / archive_name


def _discover_local_archive_paths(
    output_dir: Path,
    *,
    grid: str,
    selected_products: set[str],
    archive_patterns: list[str],
) -> list[tuple[Path, list[str]]]:
    raw_dir = output_dir / "raw" / grid
    if not raw_dir.is_dir():
        return []
    matches: list[tuple[Path, list[str]]] = []
    for path in sorted(raw_dir.iterdir()):
        if not path.is_file():
            continue
        if not _is_archive_url(path.name):
            continue
        include, categories = _archive_passes_filters(
            path.name.lower(),
            selected_products=selected_products,
            archive_patterns=archive_patterns,
        )
        if not include:
            continue
        matches.append((path, categories))
    return matches


def _model_output_relpath(grid: str, archive_name: str, member_name: str) -> Path:
    safe_archive = _sanitize_name(Path(archive_name).stem)
    member_stem = _sanitize_name(Path(member_name).stem)
    return Path("spectra") / grid / safe_archive / f"{member_stem}.npz"


def _infer_input_columns_from_arrays(available_arrays: list[str]) -> int:
    max_y_col = 0
    for name in available_arrays:
        match = Y_COL_ARRAY_RE.match(str(name).strip())
        if not match:
            continue
        index = int(match.group(1))
        if index > max_y_col:
            max_y_col = index
    if max_y_col > 0:
        return max_y_col + 1
    if "flux_lambda_cgs" in available_arrays or "hnu_cgs" in available_arrays:
        return 2
    return 0


def _existing_npz_spectrum_metadata(npz_path: Path) -> dict[str, object] | None:
    try:
        with np.load(npz_path, allow_pickle=False) as arrays:
            available_arrays = sorted(str(name).strip() for name in arrays.files if str(name).strip())
            if "wavelength_angstrom" not in arrays:
                return None
            wavelength_raw = arrays["wavelength_angstrom"]
            input_columns = (
                int(arrays["input_columns"]) if "input_columns" in arrays
                else _infer_input_columns_from_arrays(available_arrays)
            )
            x_axis_kind = (
                str(arrays["x_axis_kind"]) if "x_axis_kind" in arrays
                else ("frequency_hz" if "frequency_hz" in arrays else "wavelength_input")
            )
            x_unit_guess = (
                str(arrays["x_unit_guess"]) if "x_unit_guess" in arrays
                else ("hz" if x_axis_kind == "frequency_hz" else "angstrom")
            )
            resolving_power = float(arrays["resolving_power"]) if "resolving_power" in arrays else None
            sampling = float(arrays["samples_per_resolution"]) if "samples_per_resolution" in arrays else None
            sed_power = float(arrays["sed_binning_power"]) if "sed_binning_power" in arrays else None
            sed_method = str(arrays["sed_binning_method"]) if "sed_binning_method" in arrays else ""
            sed_applied = bool(arrays["sed_rebin_applied"]) if "sed_rebin_applied" in arrays else False
    except Exception:
        return None

    if not isinstance(wavelength_raw, np.ndarray):
        return None

    wavelength = np.asarray(wavelength_raw, dtype=np.float64).reshape(-1)
    valid = np.isfinite(wavelength) & (wavelength > 0.0)
    wavelength = wavelength[valid]
    if wavelength.size < 2:
        return None

    wavelength.sort()
    unique = np.concatenate(([True], np.diff(wavelength) > 0.0))
    wavelength = wavelength[unique]
    if wavelength.size < 2:
        return None

    return {
        "points": int(wavelength.size),
        "wavelength_min_angstrom": float(wavelength[0]),
        "wavelength_max_angstrom": float(wavelength[-1]),
        "x_axis_kind": x_axis_kind,
        "x_unit_guess": x_unit_guess,
        "input_columns": input_columns,
        "available_arrays": available_arrays,
        "resolving_power": resolving_power,
        "samples_per_resolution": sampling,
        "sed_binning_power": sed_power,
        "sed_binning_method": sed_method,
        "sed_rebin_applied": sed_applied,
    }


def _build_manifest_row(
    *,
    grid: str,
    metadata: dict[str, object],
    archive_products: list[str],
    member_products: list[str],
    archive_url: str,
    archive_name: str,
    archive_member: str,
    relpath: Path,
    points: object,
    wavelength_min_angstrom: object,
    wavelength_max_angstrom: object,
    x_axis_kind: object,
    x_unit_guess: object,
    input_columns: object,
    available_arrays: object,
    resolving_power: float | None = None,
    samples_per_resolution: float | None = None,
    sed_binning_power: float | None = None,
    sed_binning_method: str = "",
    sed_rebin_applied: bool = False,
) -> dict[str, object]:
    arrays_list = [str(item).strip() for item in (available_arrays or []) if str(item).strip()]
    return {
        "grid": grid,
        "model_name": str(metadata["model_name"]),
        "composition_code": str(metadata["composition_code"]),
        "teff_k": metadata["teff_k"],
        "log_g": metadata["log_g"],
        "vturb_km_s": metadata["vturb_km_s"],
        "tag": str(metadata["tag"]),
        "z_over_zsun": metadata["z_over_zsun"],
        "archive_products": archive_products,
        "member_products": member_products,
        "archive_url": archive_url,
        "archive_name": archive_name,
        "archive_member": archive_member,
        "spectrum_relpath": str(relpath.as_posix()),
        "points": int(points or 0),
        "wavelength_min_angstrom": float(wavelength_min_angstrom or 0.0),
        "wavelength_max_angstrom": float(wavelength_max_angstrom or 0.0),
        "x_axis_kind": str(x_axis_kind or ""),
        "x_unit_guess": str(x_unit_guess or ""),
        "input_columns": int(input_columns or 0),
        "available_arrays": sorted(arrays_list),
        "resolving_power": resolving_power,
        "samples_per_resolution": samples_per_resolution,
        "sed_binning_power": sed_binning_power,
        "sed_binning_method": sed_binning_method,
        "sed_rebin_applied": sed_rebin_applied,
    }


def _extract_archive(
    archive_path: Path,
    *,
    grid: str,
    archive_url: str,
    archive_products: list[str],
    output_dir: Path,
    force_process: bool,
    dry_run: bool,
    resolving_power: float | None = None,
    samples_per_resolution: float = 3.0,
    sed_binning_power: float | None = None,
) -> tuple[ArchiveStats, list[dict[str, object]]]:
    archive_name = archive_path.name
    archive_stats = ArchiveStats(
        grid=grid,
        archive_url=archive_url,
        archive_path=str(archive_path),
        archive_products=list(archive_products),
    )
    manifest_entries: list[dict[str, object]] = []

    with tarfile.open(archive_path, mode="r:*") as handle:
        for member in handle.getmembers():
            if not member.isfile():
                continue

            member_basename = Path(member.name).name
            if not member_basename or member_basename.startswith("."):
                continue

            member_products = sorted(set(archive_products).union(_classify_archive_products(member_basename)))
            if member_basename.lower().removesuffix(".gz").endswith(".17"):
                member_products = sorted(set(member_products) | {"continuum"})
            relpath = _model_output_relpath(grid, archive_name, member_basename)
            destination = output_dir / relpath
            model_stem = _model_name_from_member(member_basename)
            metadata = _parse_model_metadata(model_stem, grid=grid)
            detailed = member_basename.lower().removesuffix(".gz").endswith(".7")
            target_resolution = resolving_power if detailed else None
            sed = member_basename.lower().removesuffix(".gz").endswith(".flux")
            target_sed_power = sed_binning_power if sed else None
            target_sed_method = SED_BINNING_METHOD if target_sed_power is not None else ""

            destination_exists = destination.exists()
            if destination_exists and not force_process:
                cached = _existing_npz_spectrum_metadata(destination)
                if cached is not None and (
                    cached.get("resolving_power") == target_resolution
                    and (target_resolution is None or cached.get("samples_per_resolution") == samples_per_resolution)
                    and cached.get("sed_binning_power") == target_sed_power
                    and cached.get("sed_binning_method", "") == target_sed_method
                ):
                    archive_stats.spectra_indexed += 1
                    manifest_entries.append(
                        _build_manifest_row(
                            grid=grid,
                            metadata=metadata,
                            archive_products=archive_products,
                            member_products=member_products,
                            archive_url=archive_url,
                            archive_name=archive_name,
                            archive_member=member.name,
                            relpath=relpath,
                            points=cached.get("points"),
                            wavelength_min_angstrom=cached.get("wavelength_min_angstrom"),
                            wavelength_max_angstrom=cached.get("wavelength_max_angstrom"),
                            x_axis_kind=cached.get("x_axis_kind"),
                            x_unit_guess=cached.get("x_unit_guess"),
                            input_columns=cached.get("input_columns"),
                            available_arrays=cached.get("available_arrays"),
                            resolving_power=cached.get("resolving_power"),
                            samples_per_resolution=cached.get("samples_per_resolution"),
                            sed_binning_power=cached.get("sed_binning_power"),
                            sed_binning_method=cached.get("sed_binning_method", ""),
                            sed_rebin_applied=cached.get("sed_rebin_applied", False),
                        )
                    )
                    continue

            stream = handle.extractfile(member)
            if stream is None:
                archive_stats.skipped_non_spectrum += 1
                continue

            payload_raw = stream.read()
            payload = _decode_member_payload(member.name, payload_raw)
            if payload is None:
                archive_stats.skipped_invalid += 1
                continue

            parsed = _parse_spectrum_payload(
                payload,
                product_tags=member_products,
            )
            if parsed is None:
                archive_stats.skipped_non_spectrum += 1
                continue

            if target_resolution is not None:
                parsed = _reduce_resolution(
                    parsed, resolving_power=target_resolution,
                    samples_per_resolution=samples_per_resolution,
                )
            if target_sed_power is not None:
                parsed = _rebin_sed(parsed, binning_power=target_sed_power)

            arrays = parsed.get("arrays")
            if not isinstance(arrays, dict):
                archive_stats.skipped_invalid += 1
                continue
            wavelength = arrays.get("wavelength_angstrom")
            if not isinstance(wavelength, np.ndarray) or wavelength.size < 2:
                archive_stats.skipped_invalid += 1
                continue

            archive_stats.spectra_indexed += 1
            # Cached files with matching conversion settings already continued
            # above; reaching here also covers a requested change in resolution.
            if not dry_run:
                _write_spectrum(destination, arrays)
            archive_stats.spectra_saved += 1

            manifest_entries.append(
                _build_manifest_row(
                    grid=grid,
                    metadata=metadata,
                    archive_products=archive_products,
                    member_products=member_products,
                    archive_url=archive_url,
                    archive_name=archive_name,
                    archive_member=member.name,
                    relpath=relpath,
                    points=parsed.get("points", 0),
                    wavelength_min_angstrom=parsed.get("wavelength_min_angstrom", 0.0),
                    wavelength_max_angstrom=parsed.get("wavelength_max_angstrom", 0.0),
                    x_axis_kind=parsed.get("x_axis_kind", ""),
                    x_unit_guess=parsed.get("x_unit_guess", ""),
                    input_columns=parsed.get("input_columns", 0),
                    available_arrays=arrays.keys(),
                    resolving_power=target_resolution,
                    samples_per_resolution=samples_per_resolution if target_resolution is not None else None,
                    sed_binning_power=target_sed_power,
                    sed_binning_method=target_sed_method,
                    sed_rebin_applied=bool(arrays.get("sed_rebin_applied", False)),
                )
            )

    return archive_stats, manifest_entries


def _write_manifest(output_dir: Path, manifest: dict[str, object], rows: list[dict[str, object]]) -> None:
    manifest_path = output_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=False)
        handle.write("\n")

    csv_path = output_dir / "models.csv"
    fieldnames = [
        "grid",
        "model_name",
        "composition_code",
        "teff_k",
        "log_g",
        "vturb_km_s",
        "tag",
        "z_over_zsun",
        "archive_products",
        "member_products",
        "archive_name",
        "archive_member",
        "spectrum_relpath",
        "points",
        "wavelength_min_angstrom",
        "wavelength_max_angstrom",
        "x_axis_kind",
        "x_unit_guess",
        "input_columns",
        "available_arrays",
        "resolving_power",
        "samples_per_resolution",
        "sed_binning_power",
        "sed_binning_method",
        "sed_rebin_applied",
        "archive_url",
    ]

    def _csv_value(value: object) -> object:
        if value is None:
            return ""
        if isinstance(value, list | dict):
            return json.dumps(value, separators=(",", ":"), ensure_ascii=True)
        return value

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: _csv_value(row.get(name, "")) for name in fieldnames})


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download TLUSTY OSTAR2002/BSTAR2006 spectral-grid archives and build "
            "preprocessed per-model spectra under data/tlusty/ for reuse in fitting."
        )
    )
    parser.add_argument(
        "--grid",
        action="append",
        choices=sorted(SPECTRAL_GRID_PAGES),
        default=[],
        help="Grid(s) to process. Can be passed multiple times. Defaults to both ostar and bstar.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Destination root directory (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS}).",
    )
    parser.add_argument(
        "--crawl-depth",
        type=int,
        default=DEFAULT_CRAWL_DEPTH,
        help=f"Maximum HTML link-crawl depth below each grid page (default: {DEFAULT_CRAWL_DEPTH}).",
    )
    parser.add_argument(
        "--product",
        action="append",
        choices=sorted(PRODUCT_KEYWORDS),
        default=[],
        help=(
            "Archive product category to include. Can be passed multiple times. "
            f"Defaults to: {', '.join(DEFAULT_PRODUCTS)}."
        ),
    )
    parser.add_argument(
        "--archive-pattern",
        action="append",
        default=[],
        help=(
            "Optional shell-style filename filter for archive links discovered on TLUSTY pages. "
            f"Can be passed multiple times. Default pattern: {DEFAULT_ARCHIVE_PATTERN}."
        ),
    )
    parser.add_argument(
        "--resolving-power", type=float,
        help="Add Gaussian instrumental broadening at R=lambda/FWHM and resample detailed .7 spectra. Default: native sampling. SEDs and continua are unchanged.",
    )
    parser.add_argument(
        "--sed-binning-power", type=float,
        help="Flux-conserving log-wavelength bins for broad .flux SEDs (lambda/bin width, e.g. 3000). Full coverage retained; rebinned SEDs are photometry-only fit products. Default: native sampling.",
    )
    parser.add_argument(
        "--samples-per-resolution", type=float, default=3.0,
        help="Samples per instrumental FWHM on the output log-wavelength grid (minimum 2; default 3).",
    )
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Archive conversion processes (1-32; default 1). Separate processes accelerate Python parsing; try 4 on a multicore machine.",
    )
    parser.add_argument(
        "--local-only", action="store_true",
        help="Rebuild using archives under output-dir/raw without any network requests.",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download archives even if already present under raw/.",
    )
    parser.add_argument(
        "--force-process",
        action="store_true",
        help="Rewrite model .npz files even if already present.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover archives and parse metadata without writing files.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not 1 <= args.workers <= 32:
        parser.error("--workers must be between 1 and 32")
    if args.resolving_power is not None and (not math.isfinite(args.resolving_power) or args.resolving_power <= 0):
        parser.error("--resolving-power must be finite and positive")
    if not math.isfinite(args.samples_per_resolution) or args.samples_per_resolution < 2:
        parser.error("--samples-per-resolution must be finite and at least 2")
    if args.sed_binning_power is not None and (not math.isfinite(args.sed_binning_power) or args.sed_binning_power <= 0):
        parser.error("--sed-binning-power must be finite and positive")
    if args.local_only and args.force_download:
        parser.error("--local-only cannot be combined with --force-download")
    return args


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir.expanduser().resolve()
    timeout = max(1.0, float(args.timeout))
    max_depth = max(0, int(args.crawl_depth))
    selected_products = {product.strip() for product in args.product if product.strip()} if args.product else set(DEFAULT_PRODUCTS)
    archive_patterns = [str(pattern).strip() for pattern in args.archive_pattern if str(pattern).strip()]
    if not archive_patterns:
        archive_patterns = [DEFAULT_ARCHIVE_PATTERN]

    grids = args.grid if args.grid else sorted(SPECTRAL_GRID_PAGES)
    pages = {grid: SPECTRAL_GRID_PAGES[grid] for grid in grids}

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[info] output_dir={output_dir}")
    print(f"[info] grids={', '.join(grids)}")
    print(f"[info] crawl_depth={max_depth}")
    print(f"[info] products={', '.join(sorted(selected_products))}")
    print(f"[info] archive_patterns={archive_patterns}")
    print(f"[info] detailed_spectra_resolution={args.resolving_power or 'native'} samples_per_resolution={args.samples_per_resolution}")
    print(f"[info] sed_binning_power={args.sed_binning_power or 'native'}")

    discovered_archives: list[ArchiveSource] = []
    for grid, page_url in pages.items():
        print(f"[info] discovering archives for grid={grid}" + (" locally" if args.local_only else f" from {page_url}"))
        archives = [] if args.local_only else _discover_archive_urls(
            page_url,
            timeout=timeout,
            max_depth=max_depth,
            selected_products=selected_products,
            archive_patterns=archive_patterns,
        )
        if archives:
            for archive_url, archive_products in archives:
                discovered_archives.append(
                    ArchiveSource(
                        grid=grid,
                        archive_url=archive_url,
                        archive_products=archive_products,
                    )
                )
            print(f"[info] discovered {len(archives)} archive(s) for grid={grid}")
            continue

        local_archives = _discover_local_archive_paths(
            output_dir,
            grid=grid,
            selected_products=selected_products,
            archive_patterns=archive_patterns,
        )
        if local_archives:
            for local_path, archive_products in local_archives:
                discovered_archives.append(
                    ArchiveSource(
                        grid=grid,
                        archive_url=f"file://{local_path}",
                        archive_products=archive_products,
                        local_path=local_path,
                    )
                )
            print(f"[info] using {len(local_archives)} local archive(s) from {output_dir / 'raw' / grid}")
            continue

        print(f"[warn] no archive links discovered for grid={grid}")

    if not discovered_archives:
        print("[error] no TLUSTY archive links were discovered.")
        return 1

    stats = RunStats()
    model_rows: list[dict[str, object]] = []
    archives_summary: list[dict[str, object]] = []

    def record_result(archive_path, relpath, result):
        archive_stats, entries = result
        stats.processed_archives += 1
        stats.indexed_spectra += archive_stats.spectra_indexed
        stats.saved_spectra += archive_stats.spectra_saved
        stats.skipped_non_spectrum_files += archive_stats.skipped_non_spectrum
        stats.skipped_invalid_spectra += archive_stats.skipped_invalid
        model_rows.extend(entries)
        archives_summary.append(
            {
                "grid": archive_stats.grid,
                "archive_url": archive_stats.archive_url,
                "archive_products": archive_stats.archive_products,
                "archive_relpath": str(relpath.as_posix()),
                "spectra_indexed": archive_stats.spectra_indexed,
                "spectra_saved": archive_stats.spectra_saved,
                "skipped_non_spectrum": archive_stats.skipped_non_spectrum,
                "skipped_invalid": archive_stats.skipped_invalid,
            }
        )
        print(
            "[ok] processed archive={0} indexed={1} saved={2} skipped_non_spectrum={3} skipped_invalid={4}".format(
                archive_path.name,
                archive_stats.spectra_indexed,
                archive_stats.spectra_saved,
                archive_stats.skipped_non_spectrum,
                archive_stats.skipped_invalid,
            ), flush=True,
        )

    workers = args.workers
    if workers > 1:
        output_folders = set()
        for source in discovered_archives:
            archive_name = source.local_path.name if source.local_path is not None else Path(urlparse(source.archive_url).path).name
            folder = (source.grid, _sanitize_name(Path(archive_name).stem))
            if folder in output_folders:
                print("[warn] Archives share an output directory; using one worker to avoid overlapping writes.")
                workers = 1
                break
            output_folders.add(folder)
    print(f"[info] conversion_workers={workers}", flush=True)

    # Each archive has its own output subdirectory. Only small model metadata
    # crosses process boundaries; spectrum arrays stay within each worker.
    executor = (
        ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"))
        if workers > 1 and not args.dry_run else nullcontext(None)
    )
    with executor as pool:
        pending = {}
        try:
            for source in discovered_archives:
                grid = source.grid
                archive_url = source.archive_url
                archive_products = source.archive_products
                local_path = source.local_path

                if local_path is not None:
                    archive_path = local_path
                    if not archive_path.is_file():
                        stats.failed_archives += 1
                        print(f"[error] Local archive is missing: {archive_path}")
                        continue
                    relpath = archive_path.relative_to(output_dir) if archive_path.is_relative_to(output_dir) else archive_path
                    stats.reused_local_archives += 1
                    print(f"[ok] using local archive: {archive_path}")
                else:
                    relpath = _archive_relpath(grid, archive_url)
                    archive_path = output_dir / relpath
                    try:
                        changed = _download_file(
                            archive_url,
                            archive_path,
                            timeout=timeout,
                            force_download=bool(args.force_download),
                            dry_run=bool(args.dry_run),
                        )
                        if changed:
                            stats.downloaded_archives += 1
                            action = "would download" if args.dry_run else "downloaded"
                            print(f"[ok] {action}: {archive_path}")
                        else:
                            stats.skipped_existing_archives += 1
                            print(f"[skip] exists: {archive_path}")
                    except Exception as exc:  # pragma: no cover - runtime network variability
                        stats.failed_archives += 1
                        print(f"[error] Failed to download {archive_url}: {exc}")
                        continue

                if args.dry_run:
                    archives_summary.append(
                        {
                            "grid": grid,
                            "archive_url": archive_url,
                            "archive_products": archive_products,
                            "archive_relpath": str(relpath.as_posix()),
                            "spectra_indexed": 0,
                            "spectra_saved": 0,
                            "skipped_non_spectrum": 0,
                            "skipped_invalid": 0,
                        }
                    )
                    continue

                options = dict(
                    grid=grid, archive_url=archive_url, archive_products=archive_products,
                    output_dir=output_dir, force_process=bool(args.force_process),
                    dry_run=bool(args.dry_run), resolving_power=args.resolving_power,
                    samples_per_resolution=args.samples_per_resolution,
                    sed_binning_power=args.sed_binning_power,
                )
                if pool is not None:
                    try:
                        future = pool.submit(_extract_archive, archive_path, **options)
                    except Exception as exc:
                        stats.failed_archives += 1
                        print(f"[error] Failed to queue archive {archive_path}: {exc}", flush=True)
                        continue
                    pending[future] = (archive_path, relpath)
                    print(f"[info] queued conversion: {archive_path.name}", flush=True)
                    continue
                try:
                    result = _extract_archive(archive_path, **options)
                except Exception as exc:  # pragma: no cover - tar/data corruption is runtime-dependent
                    stats.failed_archives += 1
                    print(f"[error] Failed to process archive {archive_path}: {exc}")
                    continue
                record_result(archive_path, relpath, result)

            for future in as_completed(pending):
                archive_path, relpath = pending[future]
                try:
                    result = future.result()
                except Exception as exc:
                    stats.failed_archives += 1
                    print(f"[error] Failed to process archive {archive_path}: {exc}", flush=True)
                    continue
                record_result(archive_path, relpath, result)
        finally:
            # Cancel queued work before pool shutdown if the parent is interrupted.
            for future in pending:
                future.cancel()

    if stats.failed_archives:
        print("[error] Conversion incomplete; existing indexes were not replaced. Fix the errors and rerun the same command.")
        return 2

    if not args.dry_run:
        now = datetime.now(timezone.utc).isoformat()
        model_rows.sort(key=lambda row: (str(row.get("grid", "")), str(row.get("model_name", "")), str(row.get("spectrum_relpath", ""))))
        archives_summary.sort(key=lambda row: (str(row.get("grid", "")), str(row.get("archive_relpath", ""))))
        manifest = {
            "generated_at_utc": now,
            "source_pages": pages,
            "products": sorted(selected_products),
            "archive_patterns": archive_patterns,
            "archives": archives_summary,
            "total_models": len(model_rows),
            "models": model_rows,
            "conversion": {
                "detailed_resolving_power": args.resolving_power,
                "samples_per_resolution": args.samples_per_resolution,
                "broadening": "Gaussian in log wavelength; native stellar profiles retained",
                "sed_binning_power": args.sed_binning_power,
                "sed_binning_method": SED_BINNING_METHOD if args.sed_binning_power is not None else "native",
                "continuum": "native",
            },
            "format": {
                "spectrum_file_type": "npz",
                "required_arrays": ["wavelength_angstrom", "flux_lambda_cgs"],
                "optional_arrays": [
                    "continuum_lambda_cgs",
                    "normalized_flux_candidate",
                    "input_columns",
                    "x_axis_kind",
                    "x_unit_guess",
                    "resolving_power",
                    "samples_per_resolution",
                    "sed_binning_power",
                    "sed_binning_method",
                    "sed_rebin_applied",
                ],
            },
        }
        _write_manifest(output_dir, manifest, model_rows)
        print(f"[ok] wrote manifest: {output_dir / 'manifest.json'}")
        print(f"[ok] wrote model table: {output_dir / 'models.csv'}")

    print(
        "[done] downloaded_archives={0} skipped_existing_archives={1} processed_archives={2} "
        "reused_local_archives={3} indexed_spectra={4} saved_spectra={5} skipped_non_spectrum_files={6} "
        "skipped_invalid_spectra={7} failed_archives={8}".format(
            stats.downloaded_archives,
            stats.skipped_existing_archives,
            stats.processed_archives,
            stats.reused_local_archives,
            stats.indexed_spectra,
            stats.saved_spectra,
            stats.skipped_non_spectrum_files,
            stats.skipped_invalid_spectra,
            stats.failed_archives,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
