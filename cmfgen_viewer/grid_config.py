"""Grid config definitions independent of Flask."""

from __future__ import annotations

import re
from pathlib import Path

GRID_FIT_SOURCE_CMFGEN = "cmfgen"


GRID_FIT_SOURCE_TLUSTY = "tlusty"


GRID_FIT_SOURCE_VALUES = {GRID_FIT_SOURCE_CMFGEN, GRID_FIT_SOURCE_TLUSTY}


TLUSTY_DEFAULT_ROOT = (
    Path(__file__).resolve().parent.parent / "data" / "tlusly"
).resolve()


TLUSTY_FIT_MAX_MODEL_POINTS = 20000


TLUSTY_CONFIDENCE_PARAM_SPECS = (
    {"key": "teff_k", "label": "Teff", "unit": "K", "integer": True},
    {"key": "log_g", "label": "log g", "unit": "", "integer": False},
    {"key": "z_over_zsun", "label": "Z/Zsun", "unit": "", "integer": False},
    {"key": "vturb_km_s", "label": "vturb", "unit": "km/s", "integer": True},
)


TLUSTY_CHI2_CONFIDENCE_LEVELS = (
    {"label": "68%", "delta_chi2": 1.0},
    {"label": "90%", "delta_chi2": 2.705543454095404},
    {"label": "95%", "delta_chi2": 3.841458820694124},
)


TLUSTY_CONFIDENCE_PHOTOMETRY_STRICT_REDUCED_CHI2_MAX = 2.0


TLUSTY_OSTAR_METALLICITY_MAP = {
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


TLUSTY_BSTAR_METALLICITY_MAP = {
    "BC": 2.0,
    "BG": 1.0,
    "BL": 0.5,
    "BS": 0.2,
    "BT": 0.1,
    "BZ": 0.0,
}


TLUSTY_MODEL_NAME_RE = re.compile(
    r"^(?P<code>[A-Za-z]+)"
    r"(?P<teff>\d{4,5})"
    r"g(?P<logg>\d{3})"
    r"(?:v(?P<vturb>\d+))?"
    r"(?P<tag>[A-Za-z0-9_]*)$"
)


TLUSTY_MODEL_SUFFIXES = (
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


def _normalize_grid_fit_source(raw_source: object) -> str:
    source = str(raw_source or GRID_FIT_SOURCE_CMFGEN).strip().lower()
    if source not in GRID_FIT_SOURCE_VALUES:
        return GRID_FIT_SOURCE_CMFGEN
    return source


def _grid_fit_source_label(source: str) -> str:
    normalized = _normalize_grid_fit_source(source)
    if normalized == GRID_FIT_SOURCE_TLUSTY:
        return "TLUSTY Grid"
    return "Cached CMFGEN Models"


def _tlusty_root(config: dict[str, object]) -> Path:
    raw = str(config.get("tlusty_root", str(TLUSTY_DEFAULT_ROOT)))
    return Path(raw).expanduser().resolve()
