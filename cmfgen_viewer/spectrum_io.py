"""Discovery and cached parsing of CMFGEN final/continuum spectra."""

from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .model_metadata import _safe_stat
from .parsers.common import parse_numeric_tokens
from .spectrum_constants import LIGHT_SPEED_ANGSTROM_PER_10P15_HZ

try:
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover - optional runtime dependency
    np = None

COUNT_RE = re.compile(r"\((\s*\d+)\)")
_NUMBER_PATTERN = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?"
_NUMERIC_LINE_RE = re.compile(rf"{_NUMBER_PATTERN}(?:\s+{_NUMBER_PATTERN})*", re.ASCII)


def discover_final_spectrum_files(model_dir: Path) -> dict[str, object] | None:
    obs_dir = model_dir / "obs"
    if not obs_dir.is_dir():
        return None
    obs_cont = obs_dir / "obs_cont"
    if not obs_cont.is_file():
        return None
    fin_files = [path for path in obs_dir.glob("obs_fin*") if path.is_file()]

    def sort_key(item: Path) -> tuple[int, int, str]:
        match = re.match(r"^obs_fin[_-]?(\d+)", item.name, re.IGNORECASE)
        if match:
            return (0, int(match.group(1)), item.name.lower())
        return (1, 0, item.name.lower())

    fin_files.sort(key=sort_key)
    if not fin_files:
        return None
    return {
        "obs_dir": obs_dir,
        "obs_cont": obs_cont,
        "fin_files": fin_files,
    }


def _series_heading(line: str) -> tuple[str | None, int | None]:
    text = " ".join(line.strip().split())
    if text.startswith("Continuum Frequencies"):
        match = COUNT_RE.search(text)
        return "continuum_frequencies", int(match.group(1)) if match else None
    if text.startswith("Observed intensity (Janskys)"):
        return "observed_intensity_janskys", None
    return None, None


def _trim_short_wavelength_floor(
    wavelengths: list[float], flux: list[float]
) -> tuple[list[float], list[float], int]:
    if len(wavelengths) < 3 or len(flux) < 3 or len(wavelengths) != len(flux):
        return wavelengths, flux, 0

    # Match the OBSFLUX view trimming rule: treat the intensity at the
    # longest wavelength as the run-specific floor and trim only the leading
    # short-wavelength segment that stays at or below that floor.
    longest_wavelength_floor = flux[-1]
    if not math.isfinite(longest_wavelength_floor):
        return wavelengths, flux, 0

    first_keep_index = 0
    max_trim = len(flux) - 2
    while (
        first_keep_index < max_trim
        and flux[first_keep_index] <= longest_wavelength_floor
    ):
        first_keep_index += 1

    if first_keep_index <= 0:
        return wavelengths, flux, 0
    return wavelengths[first_keep_index:], flux[first_keep_index:], first_keep_index


def _normalize_wavelength_bounds(
    lambda_min: float | None,
    lambda_max: float | None,
) -> tuple[float | None, float | None]:
    min_value = float(lambda_min) if isinstance(lambda_min, int | float) else None
    max_value = float(lambda_max) if isinstance(lambda_max, int | float) else None
    if min_value is not None and (not math.isfinite(min_value) or min_value <= 0):
        min_value = None
    if max_value is not None and (not math.isfinite(max_value) or max_value <= 0):
        max_value = None
    if min_value is not None and max_value is not None and min_value > max_value:
        min_value, max_value = max_value, min_value
    return min_value, max_value


def _read_obs_vectors(path: Path) -> tuple[dict[str, Any], int | None]:
    """Validate whole numeric lines before bulk conversion (never parse prefixes).

    The legacy parser handles missing-E Fortran notation and punctuation. An
    invalid line ends the active vector, just as in the original reader.
    """
    vectors: dict[str, Any] = {
        "continuum_frequencies": [],
        "observed_intensity_janskys": [],
    }
    blocks: dict[str, list[str]] = {key: [] for key in vectors}
    expected_count: int | None = None
    active_key: str | None = None

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue

            # Numeric lines need no heading normalization/tokenization.
            heading_key, count = (
                _series_heading(stripped) if stripped[0] in "CO" else (None, None)
            )
            if heading_key:
                active_key = heading_key
                if heading_key == "continuum_frequencies" and count is not None:
                    expected_count = count
                continue

            if active_key and np is not None and _NUMERIC_LINE_RE.fullmatch(stripped):
                blocks[active_key].append(stripped)
                continue
            values = parse_numeric_tokens(stripped) if active_key else []
            if active_key and values:
                if np is None:
                    vectors[active_key].extend(values)
                else:
                    blocks[active_key].append(" ".join(repr(value) for value in values))
                continue
            active_key = None

    if np is not None:
        vectors = {
            key: np.fromstring(" ".join(lines).replace("D", "E").replace("d", "e"), sep=" ")
            for key, lines in blocks.items()
        }
    return vectors, expected_count


@lru_cache(maxsize=16)
def _load_obs_spectrum_cached(
    path_str: str,
    mtime_ns: int,
    size: int,
    lambda_min: float | None,
    lambda_max: float | None,
    as_arrays: bool = False,
) -> dict[str, object]:
    del mtime_ns, size
    path = Path(path_str)
    vectors, expected_count = _read_obs_vectors(path)
    freq = vectors["continuum_frequencies"]
    intensity = vectors["observed_intensity_janskys"]
    size = min(len(freq), len(intensity))
    if np is not None:
        freq, intensity = freq[:size], intensity[:size]
        valid = (freq > 0) & np.isfinite(freq) & np.isfinite(intensity)
        skipped = int(size - np.count_nonzero(valid))
        with np.errstate(over="ignore", divide="ignore"):
            wavelengths = LIGHT_SPEED_ANGSTROM_PER_10P15_HZ / freq[valid]
        flux = intensity[valid]
        if wavelengths.size >= 2 and wavelengths[0] > wavelengths[-1]:
            if np.all(np.diff(wavelengths) < 0):
                wavelengths, flux = wavelengths[::-1], flux[::-1]
            else:
                # Match Python's stable sort, including duplicate wavelengths.
                order = np.argsort(wavelengths, kind="stable")
                wavelengths, flux = wavelengths[order], flux[order]
        in_range = np.ones(wavelengths.size, dtype=bool)
        if lambda_min is not None:
            in_range &= wavelengths >= lambda_min
        if lambda_max is not None:
            in_range &= wavelengths <= lambda_max
        range_skipped = int(wavelengths.size - np.count_nonzero(in_range))
        wavelengths, flux = wavelengths[in_range], flux[in_range]
        trimmed_points = 0
        if flux.size >= 3 and math.isfinite(flux[-1]):
            above_floor = np.flatnonzero(flux[:-2] > flux[-1])
            trimmed_points = int(above_floor[0]) if above_floor.size else flux.size - 2
            wavelengths, flux = wavelengths[trimmed_points:], flux[trimmed_points:]
        if as_arrays:
            # Cached arrays are shared by callers and must not be mutated.
            wavelengths.setflags(write=False)
            flux.setflags(write=False)
        else:
            wavelengths, flux = wavelengths.tolist(), flux.tolist()
        return {
            "name": path.name, "wavelength": wavelengths, "flux": flux,
            "lambda_min": lambda_min, "lambda_max": lambda_max,
            "expected_count": expected_count, "raw_points": size,
            "skipped_points": skipped, "range_skipped_points": range_skipped,
            "trimmed_points": trimmed_points,
        }

    # Dependency-free compatibility path for plotting installations.
    wavelengths: list[float] = []
    flux: list[float] = []
    skipped = 0
    for frequency, value in zip(freq[:size], intensity[:size]):
        if frequency <= 0 or not math.isfinite(frequency) or not math.isfinite(value):
            skipped += 1
            continue
        wavelengths.append(LIGHT_SPEED_ANGSTROM_PER_10P15_HZ / frequency)
        flux.append(value)

    if len(wavelengths) >= 2 and wavelengths[0] > wavelengths[-1]:
        paired = sorted(zip(wavelengths, flux), key=lambda item: item[0])
        wavelengths = [item[0] for item in paired]
        flux = [item[1] for item in paired]

    range_skipped = 0
    if lambda_min is not None or lambda_max is not None:
        filtered_wavelengths: list[float] = []
        filtered_flux: list[float] = []
        for wavelength, intensity in zip(wavelengths, flux):
            if lambda_min is not None and wavelength < lambda_min:
                continue
            if lambda_max is not None and wavelength > lambda_max:
                continue
            filtered_wavelengths.append(wavelength)
            filtered_flux.append(intensity)
        range_skipped = len(wavelengths) - len(filtered_wavelengths)
        wavelengths = filtered_wavelengths
        flux = filtered_flux

    wavelengths, flux, trimmed_points = _trim_short_wavelength_floor(wavelengths, flux)

    return {
        "name": path.name,
        "wavelength": wavelengths,
        "flux": flux,
        "lambda_min": lambda_min,
        "lambda_max": lambda_max,
        "expected_count": expected_count,
        "raw_points": size,
        "skipped_points": skipped,
        "range_skipped_points": range_skipped,
        "trimmed_points": trimmed_points,
    }


def load_obs_spectrum(
    path: Path,
    *,
    lambda_min: float | None = None,
    lambda_max: float | None = None,
    as_arrays: bool = False,
) -> dict[str, object]:
    """Load list-based viewer data, or read-only NumPy arrays for fitting."""
    bound_min, bound_max = _normalize_wavelength_bounds(lambda_min, lambda_max)
    mtime_ns, size = _safe_stat(path)
    return _load_obs_spectrum_cached(
        str(path.resolve()), mtime_ns, size, bound_min, bound_max, as_arrays
    )
