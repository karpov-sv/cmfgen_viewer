from __future__ import annotations

from bisect import bisect_right
from functools import lru_cache
import math
from pathlib import Path
import re

from .parsers.common import downsample_xy, format_number, parse_float_token, parse_numeric_tokens

VADAT_ENTRY_RE = re.compile(r"^\s*(\S+)\s+\[(\S*)\]")
COUNT_RE = re.compile(r"\((\s*\d+)\)")

# OBSFLUX/OBS_CONT frequencies are in units of 10^15 Hz.
LIGHT_SPEED_ANGSTROM_PER_10P15_HZ = 2997.92458

MAX_MODEL_TIME_LINES = 4
MAX_SPECIES_ROWS = 12
MAX_SERIES_POINTS = 5000


def _safe_stat(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def _parse_float_legacy(value: str):
    stripped = value.strip().replace("D", "E").replace("d", "e")
    parsed = parse_float_token(stripped)
    if parsed is not None:
        return parsed

    match = re.match(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))([+-]\d+)$", stripped)
    if match:
        try:
            return float(f"{match.group(1)}E{match.group(2)}")
        except ValueError:
            return stripped
    return stripped


def _as_text(value: object) -> str:
    if isinstance(value, float | int):
        return format_number(value)
    return str(value)


def _parse_vadat(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip() or line.lstrip().startswith("!"):
                continue
            match = VADAT_ENTRY_RE.match(line)
            if not match:
                continue
            values[match.group(2)] = match.group(1)
    return values


def _parse_mod_sum(path: Path, do_cl_flag: str = "F") -> dict[str, object]:
    model: dict[str, object] = {"params": {}, "ions": [], "species": {}, "time": "", "maxcorr": ""}
    if not path.is_file():
        return model

    params = model["params"]
    ions = model["ions"]
    species = model["species"]
    if not isinstance(params, dict) or not isinstance(ions, list) or not isinstance(species, dict):
        return model

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()

    state = 0
    just_skipped = False
    do_cl = str(do_cl_flag).upper()
    for line in lines:
        tokens = line.split()
        if not tokens:
            if not just_skipped:
                state += 1
            just_skipped = True
            continue
        just_skipped = False

        if state == 1:
            model["time"] = f"{model.get('time', '')}{line}"
            continue

        if state == 2:
            for token in tokens:
                if "[" not in token or not token.endswith("]"):
                    continue
                left, right = token.split("[", 1)
                value = right[:-1]
                try:
                    model[left] = int(value)
                except ValueError:
                    continue
            continue

        if state == 3:
            for token in tokens:
                if "[" not in token:
                    continue
                ions.append(token.split("[", 1)[0])
            continue

        if state in (4, 5):
            normalized_line = line.replace("R ", "R_").replace("Log g", "Log_g")
            for token in normalized_line.split():
                if "=" not in token:
                    continue
                key, raw = token.split("=", 1)
                params[key] = _parse_float_legacy(raw)
            continue

        if state == 7:
            if tokens[0] == "SPECIES" or len(tokens) < 5:
                continue
            species[tokens[0]] = {
                "rel_frac": _parse_float_legacy(tokens[1]),
                "mass_frac": _parse_float_legacy(tokens[2]),
                "z_z_sun": _parse_float_legacy(tokens[3]),
                "z_sun": _parse_float_legacy(tokens[4]),
            }
            continue

        if state == 8 and do_cl == "T":
            for token in tokens:
                if "=" not in token:
                    continue
                key, raw = token.split("=", 1)
                params[key] = _parse_float_legacy(raw)
            continue

        if state == 9 or (state == 8 and do_cl != "T"):
            if ":" in line:
                model["maxcorr"] = _parse_float_legacy(line.split(":", 1)[1])

    return model


@lru_cache(maxsize=64)
def _read_model_cached(path_str: str, vadat_mtime: int, vadat_size: int, mod_sum_mtime: int, mod_sum_size: int) -> dict[str, object]:
    del vadat_mtime, vadat_size, mod_sum_mtime, mod_sum_size
    model_dir = Path(path_str)
    model: dict[str, object] = {"params": {}, "ions": [], "species": {}, "vadat": {}}
    model["path"] = str(model_dir)
    model["name"] = model_dir.name
    vadat = _parse_vadat(model_dir / "VADAT")
    model["vadat"] = vadat

    mod_sum = _parse_mod_sum(model_dir / "MOD_SUM", do_cl_flag=str(vadat.get("DO_CL", "F")))
    if isinstance(mod_sum.get("params"), dict):
        model["params"] = mod_sum["params"]
    if isinstance(mod_sum.get("ions"), list):
        model["ions"] = mod_sum["ions"]
    if isinstance(mod_sum.get("species"), dict):
        model["species"] = mod_sum["species"]
    if "time" in mod_sum:
        model["time"] = mod_sum["time"]
    if "maxcorr" in mod_sum:
        model["maxcorr"] = mod_sum["maxcorr"]
    for key, value in mod_sum.items():
        if key in {"params", "ions", "species", "time", "maxcorr", "vadat"}:
            continue
        model[key] = value
    return model


def read_model(model_dir: Path) -> dict[str, object]:
    vadat = model_dir / "VADAT"
    mod_sum = model_dir / "MOD_SUM"
    vadat_mtime, vadat_size = _safe_stat(vadat) if vadat.is_file() else (0, 0)
    mod_sum_mtime, mod_sum_size = _safe_stat(mod_sum) if mod_sum.is_file() else (0, 0)
    return _read_model_cached(
        str(model_dir.resolve()),
        vadat_mtime,
        vadat_size,
        mod_sum_mtime,
        mod_sum_size,
    )


def build_model_summary_sections(model: dict[str, object]) -> list[dict[str, object]]:
    params = model.get("params")
    vadat = model.get("vadat")
    species = model.get("species")
    if not isinstance(params, dict):
        params = {}
    if not isinstance(vadat, dict):
        vadat = {}
    if not isinstance(species, dict):
        species = {}

    time_raw = str(model.get("time", "")).strip()
    time_lines = [line.strip() for line in time_raw.splitlines() if line.strip()][:MAX_MODEL_TIME_LINES]
    time_text = " | ".join(time_lines)

    metadata_rows = [
        ("Model name", _as_text(model.get("name", ""))),
        ("Model path", _as_text(model.get("path", ""))),
        ("Run time block", time_text),
    ]
    metadata_rows = [(label, value) for label, value in metadata_rows if value]

    key_param_rows = [
        ("Luminosity (L*)", params.get("L*")),
        ("Mass-loss rate (Mdot)", params.get("Mdot")),
        ("T* temperature (K)", params.get("T*(K)")),
        ("Effective temperature (K)", params.get("Teff(K)")),
        ("Log g", params.get("Log_g")),
        ("Vinf1", params.get("Vinf1")),
        ("Velocity law", vadat.get("VEL_LAW")),
        ("CL_PAR_1", vadat.get("CL_PAR_1")),
        ("CL_PAR_2", vadat.get("CL_PAR_2")),
    ]
    parameter_rows = [(label, _as_text(value)) for label, value in key_param_rows if value not in (None, "")]

    composition_rows: list[tuple[str, str]] = []
    hyd = species.get("HYD")
    if isinstance(hyd, dict) and "mass_frac" in hyd:
        composition_rows.append(("Hydrogen mass fraction", _as_text(hyd.get("mass_frac", ""))))
    for key, label in [
        ("HYD", "Hydrogen number fraction"),
        ("CARB", "Carbon number fraction"),
        ("NIT", "Nitrogen number fraction"),
        ("OXY", "Oxygen number fraction"),
        ("IRON", "Iron number fraction"),
    ]:
        data = species.get(key)
        if not isinstance(data, dict):
            continue
        rel = data.get("rel_frac")
        if rel in (None, ""):
            continue
        composition_rows.append((label, _as_text(rel)))

    species_rows: list[list[str]] = []
    for name in sorted(species.keys()):
        data = species[name]
        if not isinstance(data, dict):
            continue
        rel = _as_text(data.get("rel_frac", ""))
        mass = _as_text(data.get("mass_frac", ""))
        if not rel and not mass:
            continue
        species_rows.append([str(name), rel, mass])
    species_rows = species_rows[:MAX_SPECIES_ROWS]

    dimensions_rows = []
    for key in ("ND", "NC", "NP", "NCF"):
        value = model.get(key)
        if value in (None, ""):
            continue
        dimensions_rows.append((key, _as_text(value)))

    return [
        {"title": "Metadata", "rows": metadata_rows},
        {"title": "Key Parameters", "rows": parameter_rows},
        {"title": "Composition Highlights", "rows": composition_rows},
        {"title": "Dimensions", "rows": dimensions_rows},
        {"title": "Species Table", "rows": species_rows, "columns": ["Species", "Rel. # Fraction", "Mass Fraction"]},
    ]


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


def _trim_short_wavelength_floor(wavelengths: list[float], flux: list[float]) -> tuple[list[float], list[float], int]:
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
    while first_keep_index < max_trim and flux[first_keep_index] <= longest_wavelength_floor:
        first_keep_index += 1

    if first_keep_index <= 0:
        return wavelengths, flux, 0
    return wavelengths[first_keep_index:], flux[first_keep_index:], first_keep_index


@lru_cache(maxsize=16)
def _load_obs_spectrum_cached(path_str: str, mtime_ns: int, size: int) -> dict[str, object]:
    del mtime_ns, size
    path = Path(path_str)
    vectors: dict[str, list[float]] = {
        "continuum_frequencies": [],
        "observed_intensity_janskys": [],
    }
    expected_count: int | None = None
    active_key: str | None = None

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue

            heading_key, count = _series_heading(stripped)
            if heading_key:
                active_key = heading_key
                if heading_key == "continuum_frequencies" and count is not None:
                    expected_count = count
                continue

            values = parse_numeric_tokens(stripped)
            if active_key and values:
                vectors[active_key].extend(values)
                continue
            active_key = None

    freq = vectors["continuum_frequencies"]
    intensity = vectors["observed_intensity_janskys"]
    size = min(len(freq), len(intensity))
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

    wavelengths, flux, trimmed_points = _trim_short_wavelength_floor(wavelengths, flux)

    return {
        "name": path.name,
        "wavelength": wavelengths,
        "flux": flux,
        "expected_count": expected_count,
        "raw_points": size,
        "skipped_points": skipped,
        "trimmed_points": trimmed_points,
    }


def load_obs_spectrum(path: Path) -> dict[str, object]:
    mtime_ns, size = _safe_stat(path)
    return _load_obs_spectrum_cached(str(path.resolve()), mtime_ns, size)


def _interp_linear(x_src: list[float], y_src: list[float], x: float) -> float | None:
    if len(x_src) < 2:
        return None
    if x < x_src[0] or x > x_src[-1]:
        return None

    right = bisect_right(x_src, x)
    if right <= 0:
        return None
    if right >= len(x_src):
        return y_src[-1]

    left = right - 1
    x0 = x_src[left]
    x1 = x_src[right]
    y0 = y_src[left]
    y1 = y_src[right]
    if x1 == x0:
        return y0
    weight = (x - x0) / (x1 - x0)
    return y0 + (y1 - y0) * weight


def _plot_layout(*, y_label: str, y_scale: str) -> dict[str, object]:
    return {
        "template": "plotly_white",
        "margin": {"l": 62, "r": 24, "t": 14, "b": 52},
        "height": 420,
        "xaxis": {
            "title": {"text": "Wavelength (Å)"},
            "showgrid": True,
            "zeroline": False,
            "type": "log",
        },
        "yaxis": {
            "title": {"text": y_label},
            "showgrid": True,
            "zeroline": False,
            "type": y_scale,
        },
        "showlegend": True,
        "legend": {"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
        "hovermode": "closest",
    }


def _plot_config() -> dict[str, object]:
    return {
        "responsive": True,
        "displaylogo": False,
        "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
    }


def build_both_plot(continuum: dict[str, object], final: dict[str, object]) -> dict[str, object] | None:
    cont_x = continuum.get("wavelength")
    cont_y = continuum.get("flux")
    fin_x = final.get("wavelength")
    fin_y = final.get("flux")
    if not isinstance(cont_x, list) or not isinstance(cont_y, list) or not isinstance(fin_x, list) or not isinstance(fin_y, list):
        return None
    if len(cont_x) < 2 or len(fin_x) < 2:
        return None

    cont_x_ds, cont_y_ds = downsample_xy(cont_x, cont_y, max_points=MAX_SERIES_POINTS)
    fin_x_ds, fin_y_ds = downsample_xy(fin_x, fin_y, max_points=MAX_SERIES_POINTS)
    if len(cont_x_ds) < 2 or len(fin_x_ds) < 2:
        return None

    return {
        "data": [
            {
                "type": "scatter",
                "mode": "lines",
                "name": f"Final ({final.get('name', 'obs_fin')})",
                "x": fin_x_ds,
                "y": fin_y_ds,
                "line": {"color": "#1f77b4", "width": 1.6},
                "hovertemplate": "Wavelength=%{x:.6g} Å<br>Flux=%{y:.6g}<extra></extra>",
            },
            {
                "type": "scatter",
                "mode": "lines",
                "name": "Continuum (obs_cont)",
                "x": cont_x_ds,
                "y": cont_y_ds,
                "line": {"color": "#d62728", "width": 1.3},
                "hovertemplate": "Wavelength=%{x:.6g} Å<br>Flux=%{y:.6g}<extra></extra>",
            },
        ],
        "layout": _plot_layout(y_label="Flux (Janskys)", y_scale="log"),
        "config": _plot_config(),
        "default_x_scale": "log",
        "default_y_scale": "log",
    }


def build_normalized_plot(continuum: dict[str, object], final: dict[str, object]) -> dict[str, object] | None:
    cont_x = continuum.get("wavelength")
    cont_y = continuum.get("flux")
    fin_x = final.get("wavelength")
    fin_y = final.get("flux")
    if not isinstance(cont_x, list) or not isinstance(cont_y, list) or not isinstance(fin_x, list) or not isinstance(fin_y, list):
        return None
    if len(cont_x) < 2 or len(fin_x) < 2:
        return None

    ratio_x: list[float] = []
    ratio_y: list[float] = []
    for wavelength, flux in zip(fin_x, fin_y):
        interp = _interp_linear(cont_x, cont_y, wavelength)
        if interp is None or interp == 0 or not math.isfinite(interp) or not math.isfinite(flux):
            continue
        value = flux / interp
        if not math.isfinite(value):
            continue
        ratio_x.append(wavelength)
        ratio_y.append(value)

    ratio_x_ds, ratio_y_ds = downsample_xy(ratio_x, ratio_y, max_points=MAX_SERIES_POINTS)
    if len(ratio_x_ds) < 2:
        return None

    return {
        "data": [
            {
                "type": "scatter",
                "mode": "lines",
                "name": f"{final.get('name', 'obs_fin')} / obs_cont",
                "x": ratio_x_ds,
                "y": ratio_y_ds,
                "line": {"color": "#198754", "width": 1.5},
                "hovertemplate": "Wavelength=%{x:.6g} Å<br>Normalized=%{y:.6g}<extra></extra>",
            }
        ],
        "layout": _plot_layout(y_label="Normalized flux", y_scale="linear"),
        "config": _plot_config(),
        "default_x_scale": "log",
        "default_y_scale": "linear",
    }


def spectrum_data_rows(continuum: dict[str, object], final: dict[str, object]) -> list[list[str]]:
    rows = [
        ["Selected final spectrum", _as_text(final.get("name", ""))],
        ["Final points", _as_text(len(final.get("wavelength", [])))],
        ["Continuum points", _as_text(len(continuum.get("wavelength", [])))],
    ]
    final_skipped = final.get("skipped_points")
    cont_skipped = continuum.get("skipped_points")
    if isinstance(final_skipped, int) and final_skipped > 0:
        rows.append(["Final skipped points", str(final_skipped)])
    if isinstance(cont_skipped, int) and cont_skipped > 0:
        rows.append(["Continuum skipped points", str(cont_skipped)])
    final_trimmed = final.get("trimmed_points")
    cont_trimmed = continuum.get("trimmed_points")
    if isinstance(final_trimmed, int) and final_trimmed > 0:
        rows.append(["Final trimmed short-wavelength points", str(final_trimmed)])
    if isinstance(cont_trimmed, int) and cont_trimmed > 0:
        rows.append(["Continuum trimmed short-wavelength points", str(cont_trimmed)])
    return rows


def fin_file_label(filename: str) -> str:
    match = re.match(r"^obs_fin[_-]?(.+)$", filename, re.IGNORECASE)
    if not match:
        return filename
    suffix = match.group(1).strip("_-")
    if not suffix:
        return filename
    if suffix.isdigit():
        return f"{filename} (vturb={suffix})"
    return filename
