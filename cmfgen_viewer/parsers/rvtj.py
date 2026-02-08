from __future__ import annotations

from pathlib import Path

from .common import (
    build_svg_line_plot,
    format_number,
    maybe_number,
    normalize_space,
    parse_float_token,
    parse_numeric_tokens,
)

RVTJ_VECTOR_HEADINGS: list[tuple[str, str, str]] = [
    ("Radius", "radius", "10^10 cm"),
    ("Velocity", "velocity", "km/s"),
    ("dlnV/dlnr-1", "dlnv_dlnr_minus_1", ""),
    ("Electron density", "electron_density", "cm^-3"),
    ("Temperature", "temperature", "10^4 K"),
    ("Grey temperature", "grey_temperature", "10^4 K"),
    ("Heating: radioactive decay", "heating_radioactive_decay", "erg cm^-3 s^-1"),
    ("Rosseland Mean Opacity", "rosseland_mean_opacity", ""),
    ("Flux Mean Opacity", "flux_mean_opacity", ""),
    ("Atom Density", "atom_density", "cm^-3"),
    ("Ion Density", "ion_density", "cm^-3"),
    ("Mass Density", "mass_density", "g cm^-3"),
    ("Clumping Factor", "clumping_factor", ""),
    ("Hydrogen Density", "hydrogen_density", "cm^-3"),
    ("Helium Density", "helium_density", "cm^-3"),
]


def _detect_vector_heading(line: str) -> tuple[str, str, str] | None:
    normalized = normalize_space(line)
    for heading, key, unit in RVTJ_VECTOR_HEADINGS:
        if normalized.startswith(heading):
            return heading, key, unit
    return None


def parse_rvtj(path: Path) -> dict[str, object]:
    metadata: dict[str, object] = {}
    vector_map: dict[str, dict[str, object]] = {}
    vector_order: list[str] = []
    warnings: list[str] = []

    active_key: str | None = None
    stop_after_populations = False

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue

            if stop_after_populations:
                break

            lower = stripped.lower()
            if " populations" in lower and active_key is None:
                stop_after_populations = True
                continue

            vector_heading = _detect_vector_heading(stripped)
            if vector_heading is not None:
                title, key, unit = vector_heading
                if key not in vector_map:
                    vector_map[key] = {
                        "title": title,
                        "unit": unit,
                        "values": [],
                    }
                    vector_order.append(key)
                active_key = key
                continue

            numeric_values = parse_numeric_tokens(stripped)
            if active_key and numeric_values:
                values = vector_map[active_key]["values"]
                if isinstance(values, list):
                    values.extend(numeric_values)
                continue

            active_key = None

            if ":" in stripped:
                key, raw = stripped.split(":", 1)
                metadata[normalize_space(key)] = maybe_number(raw.strip())
                continue

    nd_value = metadata.get("ND")
    nd_expected = int(nd_value) if isinstance(nd_value, int | float) else None

    summary_rows: list[list[str]] = []
    for key in ["ND", "NC", "NP", "NCF", "Mdot(Msun/yr)", "L(Lsun)", "H/He abundance", "Was T fixed?"]:
        if key in metadata:
            summary_rows.append([key, format_number(metadata[key])])

    vectors_table_rows: list[list[str]] = []
    for key in vector_order:
        vector_info = vector_map[key]
        values = vector_info.get("values", [])
        if not isinstance(values, list):
            continue
        vectors_table_rows.append([str(vector_info["title"]), str(len(values)), str(vector_info["unit"])])
        if nd_expected and len(values) != nd_expected:
            warnings.append(
                f"{vector_info['title']} has {len(values)} values while ND={nd_expected}"
            )

    radius_values = vector_map.get("radius", {}).get("values", [])
    if isinstance(radius_values, list) and radius_values:
        x_label = "Radius (10^10 cm)"
        x_values = radius_values
    else:
        x_values = list(range(1, max((len(v.get("values", [])) for v in vector_map.values()), default=0) + 1))
        x_label = "Depth index"

    plot_specs = [
        ("velocity", "Velocity profile", "Velocity (km/s)"),
        ("temperature", "Temperature profile", "Temperature (10^4 K)"),
        ("electron_density", "Electron density", "n_e (cm^-3)"),
        ("mass_density", "Mass density", "rho (g cm^-3)"),
        ("clumping_factor", "Clumping factor", "f_cl"),
    ]
    plots: list[dict[str, object]] = []
    for key, title, y_label in plot_specs:
        values = vector_map.get(key, {}).get("values", [])
        if not isinstance(values, list) or len(values) < 2:
            continue
        x_for_plot = x_values
        if len(x_for_plot) != len(values):
            x_for_plot = list(range(1, len(values) + 1))
            x_label_local = "Depth index"
        else:
            x_label_local = x_label
        svg = build_svg_line_plot(x_for_plot, values, max_points=800)
        if svg:
            plots.append(
                {
                    "title": title,
                    "x_label": x_label_local,
                    "y_label": y_label,
                    "svg": svg,
                }
            )

    return {
        "parser": "RVTJ",
        "title": "RVTJ radial structure",
        "summary_table": {
            "title": "Model header",
            "columns": ["Field", "Value"],
            "rows": summary_rows,
        },
        "tables": [
            {
                "title": "Parsed vectors",
                "columns": ["Vector", "Count", "Unit"],
                "rows": vectors_table_rows,
            }
        ],
        "plots": plots,
        "warnings": warnings,
    }
