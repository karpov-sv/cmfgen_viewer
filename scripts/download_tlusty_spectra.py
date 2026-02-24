#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import fnmatch
import gzip
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import tarfile
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import numpy as np


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "tlusly"
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
    for index in range(y_values.shape[1]):
        arrays[f"y_col_{index + 1}"] = y_values[:, index].astype(np.float64)

    primary = y_values[:, 0].astype(np.float64)
    arrays["flux_lambda_cgs"] = primary

    if x_axis_kind == "frequency_hz":
        arrays["frequency_hz"] = x_values.astype(np.float64)
        arrays["hnu_cgs"] = primary
        arrays["flux_lambda_cgs"] = (primary * (LIGHT_SPEED_ANGSTROM_PER_SECOND / np.square(wavelength))).astype(
            np.float64
        )

    if "continuum" in product_tags:
        arrays["continuum_lambda_cgs"] = arrays["flux_lambda_cgs"].astype(np.float64)

    if y_values.shape[1] >= 2:
        normalized = _try_build_normalized_flux(y_values[:, 0], y_values[:, 1])
        if normalized is not None:
            arrays["continuum_candidate_col2"] = y_values[:, 1].astype(np.float64)
            arrays["normalized_flux_candidate"] = normalized

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

    x_axis_kind = "frequency_hz" if "frequency_hz" in available_arrays else "wavelength_input"
    x_unit_guess = "hz" if x_axis_kind == "frequency_hz" else "angstrom"

    return {
        "points": int(wavelength.size),
        "wavelength_min_angstrom": float(wavelength[0]),
        "wavelength_max_angstrom": float(wavelength[-1]),
        "x_axis_kind": x_axis_kind,
        "x_unit_guess": x_unit_guess,
        "input_columns": _infer_input_columns_from_arrays(available_arrays),
        "available_arrays": available_arrays,
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
            relpath = _model_output_relpath(grid, archive_name, member_basename)
            destination = output_dir / relpath
            model_stem = _model_name_from_member(member_basename)
            metadata = _parse_model_metadata(model_stem, grid=grid)

            destination_exists = destination.exists()
            if destination_exists and not force_process:
                cached = _existing_npz_spectrum_metadata(destination)
                if cached is not None:
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

            arrays = parsed.get("arrays")
            if not isinstance(arrays, dict):
                archive_stats.skipped_invalid += 1
                continue
            wavelength = arrays.get("wavelength_angstrom")
            if not isinstance(wavelength, np.ndarray) or wavelength.size < 2:
                archive_stats.skipped_invalid += 1
                continue

            archive_stats.spectra_indexed += 1
            should_write = force_process or (not destination_exists)
            if destination_exists and not force_process:
                # Existing file is unreadable/missing required arrays; repair it.
                should_write = True
            if should_write:
                if not dry_run:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    np.savez_compressed(destination, **arrays)
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
            "preprocessed per-model spectra under data/tlusly/ for reuse in fitting."
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
    return parser.parse_args(list(argv) if argv is not None else None)


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

    discovered_archives: list[ArchiveSource] = []
    for grid, page_url in pages.items():
        print(f"[info] discovering archives for grid={grid} from {page_url}")
        archives = _discover_archive_urls(
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
            print(
                f"[warn] no remote archives discovered for grid={grid}; "
                f"using {len(local_archives)} local archive(s) from {output_dir / 'raw' / grid}"
            )
            continue

        print(f"[warn] no archive links discovered for grid={grid}")

    if not discovered_archives:
        print("[error] no TLUSTY archive links were discovered.")
        return 1

    stats = RunStats()
    model_rows: list[dict[str, object]] = []
    archives_summary: list[dict[str, object]] = []

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

        try:
            archive_stats, entries = _extract_archive(
                archive_path,
                grid=grid,
                archive_url=archive_url,
                archive_products=archive_products,
                output_dir=output_dir,
                force_process=bool(args.force_process),
                dry_run=bool(args.dry_run),
            )
        except Exception as exc:  # pragma: no cover - tar/data corruption is runtime-dependent
            stats.failed_archives += 1
            print(f"[error] Failed to process archive {archive_path}: {exc}")
            continue

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
            )
        )

    if not args.dry_run:
        now = datetime.now(timezone.utc).isoformat()
        model_rows.sort(key=lambda row: (str(row.get("grid", "")), str(row.get("model_name", ""))))
        manifest = {
            "generated_at_utc": now,
            "source_pages": pages,
            "products": sorted(selected_products),
            "archive_patterns": archive_patterns,
            "archives": archives_summary,
            "total_models": len(model_rows),
            "models": model_rows,
            "format": {
                "spectrum_file_type": "npz",
                "required_arrays": ["wavelength_angstrom", "flux_lambda_cgs"],
                "optional_arrays": [
                    "hnu_cgs",
                    "frequency_hz",
                    "continuum_lambda_cgs",
                    "normalized_flux_candidate",
                    "continuum_candidate_col2",
                    "y_col_*",
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
    if stats.failed_archives > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
