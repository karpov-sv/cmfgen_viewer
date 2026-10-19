"""Ranked solver corrections emitted by SUM_STEQ_SOL."""
from __future__ import annotations

import math
from pathlib import Path
import re

from .common import format_number, parse_float_token

SECTION_RE = re.compile(
    r"^\s*(\d+)\s+largest\s+(reductions|increases)\s+at depth:\s*(\d+)\s*$", re.I
)
MAX_FILE_BYTES = 4 * 1024 * 1024


def read_correction_link(path: Path) -> dict[str, object]:
    """Read a snapshot, preserving section labels independently of correction signs."""
    entries = []
    warnings = []
    try:
        with path.open('rb') as stream:
            payload = stream.read(MAX_FILE_BYTES + 1)
    except OSError:
        return {"entries": [], "warnings": ["CORRECTION_LINK could not be read."]}
    if len(payload) > MAX_FILE_BYTES:
        return {"entries": [], "warnings": ["CORRECTION_LINK exceeds the 4 MiB parsing limit."]}
    section = None
    section_rows = 0
    invalid = 0
    for line in payload.decode('utf-8', errors='replace').splitlines():
        match = SECTION_RE.match(line)
        if match:
            section = (int(match[1]), match[2].lower(), int(match[3]))
            section_rows = 0
            continue
        tokens = line.split()
        if not tokens or 'SOL(J,L)' in line:
            continue
        if section is None:
            invalid += 1
            continue
        count, label, depth = section
        value = parse_float_token(tokens[0]) if len(tokens) == 4 else None
        if (value is None or not math.isfinite(value) or not math.isfinite(100 * value)
                or not tokens[2].isdigit() or not tokens[3].isdigit()
                or depth < 1 or int(tokens[3]) < 1 or section_rows >= count):
            invalid += 1
            continue
        section_rows += 1
        entries.append({
            "depth": depth, "section": label, "rank": section_rows,
            "solution": value, "change_percent": -100 * value,
            "species": tokens[1], "superlevel": int(tokens[2]), "equation": int(tokens[3]),
        })
    if invalid:
        warnings.append(f"Skipped {invalid} unrecognized or invalid row(s).")
    if not entries:
        warnings.append("No supported ranked correction rows were found.")
    return {"entries": entries, "warnings": warnings}



def _correction_plots(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    """Plot individual listed entries without interpolating across missing depths."""
    palette = ("#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
               "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf")
    species = sorted({e["species"] for e in entries})
    plots = []
    for magnitude in (True, False):
        traces = []
        for index, name in enumerate(species):
            rows = sorted((e for e in entries if e["species"] == name
                           and (not magnitude or e["change_percent"] != 0)),
                          key=lambda e: (e["depth"], e["equation"]))
            if not rows:
                continue
            traces.append({
                "type": "scatter", "mode": "markers", "name": name,
                "x": [e["depth"] for e in rows],
                "y": [abs(e["change_percent"]) if magnitude else e["change_percent"] for e in rows],
                "customdata": [[e["species"], e["superlevel"], e["equation"],
                                e["change_percent"], e["section"], e["rank"]] for e in rows],
                "marker": {"size": 8, "opacity": 0.8, "color": palette[index % len(palette)],
                           "symbol": ["triangle-up" if e["change_percent"] > 0 else
                                      "triangle-down" if e["change_percent"] < 0 else "circle"
                                      for e in rows]},
                "hovertemplate": (
                    "%{customdata[0]} · SL %{customdata[1]} · equation %{customdata[2]}"
                    "<br>Depth %{x}<br>Solver change %{customdata[3]:+.6g}%"
                    "<br>%{customdata[4]}, rank %{customdata[5]}<extra></extra>"
                ),
            })
        if not traces:
            continue
        scale = "log" if magnitude else "linear"
        plots.append({
            "title": "Listed correction magnitudes vs depth" if magnitude else "Signed listed corrections vs depth",
            "data": traces,
            "layout": {
                "template": "plotly_white", "height": 420,
                "margin": {"l": 75, "r": 24, "t": 65, "b": 55},
                "annotations": [{"text": "Selected entries only · ▲ increase · ▼ reduction"
                                 + (" · zeros omitted on log scale" if magnitude else ""),
                                 "xref": "paper", "yref": "paper", "x": 0, "y": 1.14,
                                 "showarrow": False, "xanchor": "left"}],
                "xaxis": {"title": {"text": "Depth index (1 = outer boundary)"},
                          "type": "linear", "zeroline": False},
                "yaxis": {"title": {"text": "Absolute solver change (%)" if magnitude else "Solver change (%)"},
                          "type": scale, "zeroline": not magnitude},
                "showlegend": True, "hovermode": "closest",
            },
            "config": {"responsive": True, "displaylogo": False},
            "default_x_scale": "linear", "default_y_scale": scale,
            "point_count": sum(len(t["x"]) for t in traces),
        })
    return plots


def parse_correction_link(path: Path) -> dict[str, object]:
    data = read_correction_link(path)
    entries = data['entries']
    ranked = sorted(entries, key=lambda e: abs(e['change_percent']), reverse=True)
    species = sorted({e['species'] for e in entries})
    overview = []
    for name in species:
        rows = [e for e in entries if e['species'] == name]
        worst = max(rows, key=lambda e: abs(e['change_percent']))
        overview.append([name, str(len(rows)), str(len({e['depth'] for e in rows})),
                         format_number(worst['change_percent']), str(worst['depth']),
                         str(worst['superlevel']), str(worst['equation'])])
    warnings = list(data["warnings"])
    if len(ranked) > 500:
        warnings.append("Ranked table limited to the 500 largest listed corrections.")
    return {
        "parser": "CORRECTION_LINK",
        "title": "CORRECTION_LINK species and superlevel corrections",
        "summary_table": {
            "title": "Ranked correction snapshot", "columns": ["Field", "Value"],
            "rows": [["Listed entries", str(len(entries))],
                     ["Listed depths", str(len({e['depth'] for e in entries}))],
                     ["Convention", "Solver change (%) = -100 × SOL(J,L); positive means increase."],
                     ["Scope", "Selected ranked entries only; not all variables or depths. "
                      "Solver corrections precede any damping or scaling. T and Ne denote "
                      "temperature and electron density; SL=0 is not a population superlevel."]],
        },
        "tables": [
            {"title": "Largest listed corrections by magnitude",
             "columns": ["Depth", "Section", "Rank", "Species / variable", "SL", "I(STEQ)",
                         "SOL(J,L)", "Solver change (%)"],
             "rows": [[str(e['depth']), e['section'], str(e['rank']), e['species'],
                       str(e['superlevel']), str(e['equation']), format_number(e['solution']),
                       format_number(e['change_percent'])] for e in ranked[:500]]},
            {"title": "Species / variable overview (listed entries only)",
             "columns": ["Species / variable", "Entries", "Depths", "Largest solver change (%)",
                         "Depth", "SL", "I(STEQ)"], "rows": overview},
        ],
        "plots": _correction_plots(entries), "default_plot_mode": "separate", "warnings": warnings,
    }
