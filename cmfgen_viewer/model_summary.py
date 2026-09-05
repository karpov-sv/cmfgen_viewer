"""Named scientific model summaries, versioned storage, and table presentation."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone

from .parsers.common import format_number, parse_float_token

SUMMARY_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ModelSummary:
    name: str = ""
    luminosity: float | None = None
    mass_loss_rate: float | None = None
    stellar_temperature: float | None = None
    stellar_radius: float | None = None
    outer_radius: float | None = None
    effective_temperature: float | None = None
    photospheric_radius: float | None = None
    wind_efficiency: float | None = None
    filling_factor: float | None = None
    clumping_onset: float | None = None
    optical_depth: float | None = None
    terminal_velocity: float | None = None
    velocity_beta: float | None = None
    hydrogen_abundance: float | None = None
    nitrogen_abundance: float | None = None
    iron_abundance: float | None = None
    log_g: float | None = None
    oxygen_abundance: float | None = None
    carbon_abundance: float | None = None


# Frozen historical ordering: only the migration decoder uses these positions.
LEGACY_SUMMARY_FIELDS = (
    "name",
    "luminosity",
    "mass_loss_rate",
    "stellar_temperature",
    "stellar_radius",
    "outer_radius",
    "effective_temperature",
    "photospheric_radius",
    "wind_efficiency",
    "filling_factor",
    "clumping_onset",
    "optical_depth",
    "terminal_velocity",
    "velocity_beta",
    "hydrogen_abundance",
    "nitrogen_abundance",
    "iron_abundance",
    "log_g",
    "oxygen_abundance",
    "carbon_abundance",
)

# Presentation order is independent of both storage and scientific consumers.
SUMMARY_COLUMN_FIELDS = {
    "MODEL": "name",
    "LSTAR": "luminosity",
    "MDOT": "mass_loss_rate",
    "T_*": "stellar_temperature",
    "RSTAR": "stellar_radius",
    "RMAX": "outer_radius",
    "T_2/3": "effective_temperature",
    "R_2/3": "photospheric_radius",
    "Eta": "wind_efficiency",
    "f": "filling_factor",
    "f_beg": "clumping_onset",
    "TAU": "optical_depth",
    "Vinf": "terminal_velocity",
    "Beta": "velocity_beta",
    "HYD/X": "hydrogen_abundance",
    "NIT/X": "nitrogen_abundance",
    "IRON/X": "iron_abundance",
    "logg": "log_g",
    "OXY/X": "oxygen_abundance",
    "CAR/X": "carbon_abundance",
    "Last updated": None,
}
SUMMARY_COLUMNS = list(SUMMARY_COLUMN_FIELDS)
SUMMARY_COLUMN_INDEX = {name: index for index, name in enumerate(SUMMARY_COLUMNS)}


def summary_number(value: object) -> float | None:
    number = parse_float_token(str(value)) if value is not None else None
    return number if number is not None and math.isfinite(number) else None


def summary_from_model(model: dict[str, object]) -> ModelSummary:
    params = model.get("params") or {}
    vadat = model.get("vadat") or {}
    return ModelSummary(
        name=str(model.get("name", "")),
        luminosity=summary_number(vadat.get("LSTAR")),
        mass_loss_rate=summary_number(vadat.get("MDOT")),
        stellar_temperature=summary_number(params.get("T*(K)")),
        stellar_radius=summary_number(vadat.get("RSTAR")),
        outer_radius=summary_number(vadat.get("RMAX")),
        effective_temperature=summary_number(params.get("Teff(K)")),
        photospheric_radius=summary_number(params.get("R_/Rsun")),
        wind_efficiency=summary_number(params.get("Eta")),
        filling_factor=summary_number(params.get("CL_P_1")),
        clumping_onset=summary_number(params.get("CL_P_2")),
        optical_depth=summary_number(params.get("Tau")),
        terminal_velocity=summary_number(params.get("Vinf1")),
        velocity_beta=summary_number(params.get("Beta1")),
        hydrogen_abundance=summary_number(vadat.get("HYD/X")),
        nitrogen_abundance=summary_number(vadat.get("NIT/X")),
        iron_abundance=summary_number(vadat.get("IRON/X")),
        log_g=summary_number(params.get("Log_g")),
        oxygen_abundance=summary_number(vadat.get("OXY/X")),
        carbon_abundance=summary_number(vadat.get("CARB/X")),
    )


def summary_payload(summary: ModelSummary) -> dict[str, object]:
    return {"schema_version": SUMMARY_SCHEMA_VERSION, "fields": asdict(summary)}


def summary_from_payload(payload: object) -> ModelSummary:
    if isinstance(payload, list):
        values = dict(zip(LEGACY_SUMMARY_FIELDS, payload))
    elif (
        isinstance(payload, dict)
        and payload.get("schema_version") == SUMMARY_SCHEMA_VERSION
    ):
        values = payload.get("fields")
        if not isinstance(values, dict):
            raise ValueError("Invalid model summary fields.")
    else:
        raise ValueError("Unsupported model summary schema.")
    return ModelSummary(
        name=str(values.get("name", "")),
        **{
            field.name: summary_number(values.get(field.name))
            for field in fields(ModelSummary)
            if field.name != "name"
        },
    )


def format_summary_timestamp(timestamp: float | None) -> str:
    if timestamp is None or not math.isfinite(timestamp):
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def summary_table_row(
    summary: ModelSummary,
    *,
    mod_sum_mtime: float | None = None,
    columns: list[str] | None = None,
) -> list[str]:
    row = []
    for label in SUMMARY_COLUMNS if columns is None else columns:
        key = SUMMARY_COLUMN_FIELDS[label]
        if key is None:
            row.append(format_summary_timestamp(mod_sum_mtime))
        else:
            value = getattr(summary, key)
            row.append(
                format_number(value)
                if value is not None
                else "-"
                if key == "filling_factor"
                else ""
            )
    return row


def build_summary_row(
    model: dict[str, object], *, mod_sum_mtime: float | None = None
) -> list[str]:
    return summary_table_row(summary_from_model(model), mod_sum_mtime=mod_sum_mtime)


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
