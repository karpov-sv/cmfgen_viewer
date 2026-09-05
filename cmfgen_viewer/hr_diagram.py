"""Hr diagram definitions independent of Flask."""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

from .parsers.common import parse_float_token

HR_AUX_DIR = Path(__file__).resolve().parent.parent / "data"


MAMAJEK_TABLE_PATH = HR_AUX_DIR / "EEM_dwarf_UBVIJHK_colors_Teff.txt"


@lru_cache(maxsize=1)
def _load_mamajek_hr_overlay() -> dict[str, object] | None:
    """
    Load Mamajek dwarf sequence points as Teff-L pairs for HR overlay plotting.

    Source file is kept verbatim under data/ and parsed here on demand.
    """
    if not MAMAJEK_TABLE_PATH.is_file():
        return None

    try:
        lines = MAMAJEK_TABLE_PATH.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
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

        luminosity = 10.0**log_l
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
