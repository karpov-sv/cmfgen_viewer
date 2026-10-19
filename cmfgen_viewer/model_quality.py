"""Advisory scientific-quality checks, separate from execution success."""

from functools import lru_cache
import math
from pathlib import Path
import re

from .parsers.common import parse_float_token


@lru_cache(maxsize=16)
def _boundary_bands(path: str, mtime_ns: int, size: int) -> dict[str, tuple[float, float]]:
    """Stream the outer-boundary columns; cache only a few summary numbers."""
    if size > 64 * 1024 * 1024:
        return {}
    bands = {"All frequencies": (0, math.inf), "UV (0.09–0.3 μm)": (0.09, 0.3),
             "Optical (0.3–1 μm)": (0.3, 1), "Infrared (1–1000 μm)": (1, 1000)}
    result = {}
    try:
        with Path(path).open() as stream:
            header_seen = False
            for line in stream:
                if "Indx" in line and "J(mom)" in line and "%Diff" in line:
                    header_seen = True
                    continue
                tokens = line.split()
                if not header_seen or not tokens or not tokens[0].isdigit():
                    continue
                if len(tokens) != 9:
                    return {}
                nu, diff = parse_float_token(tokens[1]), parse_float_token(tokens[4])
                if nu is None or diff is None or not math.isfinite(nu + diff) or nu <= 0:
                    return {}
                wavelength = 0.299792458 / nu  # Nu in 10^15 Hz, wavelength in microns.
                for name, (low, high) in bands.items():
                    if low <= wavelength < high and abs(diff) > result.get(name, (-1, 0))[0]:
                        result[name] = (abs(diff), wavelength)
    except (OSError, UnicodeError):
        return {}
    return result


def inspect_quality(model_dir, records, run_text, started_epoch, requested, correction):
    # These helpers also govern the existing convergence overview's freshness rules.
    from .model_convergence import _current_for_run, _finite, _read_text

    checks = []

    def add(code, label, level, detail, action, path="OUTGEN"):
        checks.append(dict(code=code, label=label, level=level, detail=detail,
                           action=action, path=path))

    # Screening values are deliberately advisory, not native stopping criteria.
    for key, label, limit in (
        ("solver_maximum_change", "Solver corrections", 1.0),
        ("maximum_increase_percent", "Population increases", 1.0),
        ("maximum_decrease_percent", "Population decreases", 1.0),
        ("spectrum_latest_change_percent", "Spectrum stability", 1.0),
        ("luminosity_difference_percent", "Generated versus target luminosity", 2.0),
    ):
        record = next((r for r in reversed(records) if key in r), None)
        if record is None:
            add(key, label, "unknown", "No measurement recorded in this run.",
                "Inspect later full iterations before assessing convergence.")
            continue
        value = float(record[key])
        level = "warning" if abs(value) > limit else "info"
        add(key, label, level,
            f"{value:.4g}% at global iteration {record['global_iteration']}; "
            f"advisory screening threshold {limit:g}%.",
            "Continue from the saved model and look for several stable full iterations; "
            "choose tighter tolerances for the quantities you intend to use.")

    comparable = [r for r in records if not r.get("lambda_iteration")
                  and "solver_maximum_change" in r][-5:]
    if len(comparable) >= 3:
        values = [float(r["solver_maximum_change"]) for r in comparable]
        if values[-1] > 1.25 * values[0]:
            add("recent_trend", "Recent correction trend", "warning",
                f"Normal-iteration corrections rose overall from {values[0]:.4g}% "
                f"to {values[-1]:.4g}% across {len(values)} records.",
                "Review the history and intervening special iterations; this alone does not prove divergence.")
    lambdas = [i for i, r in enumerate(records) if r.get("lambda_iteration")]
    if lambdas and len(records) - 1 - lambdas[-1] < 3:
        add("late_lambda", "Recent lambda iteration", "warning",
            f"Only {len(records) - 1 - lambdas[-1]} iteration(s) recorded after the latest lambda iteration.",
            "Allow more full iterations to settle before accepting the final populations and spectrum.")
    if records and all(r.get("temperature_fixed") for r in records[-5:]):
        add("fixed_temperature", "Temperature convergence not demonstrated", "warning",
            "Temperature was held fixed in all recent recorded iterations.",
            "Review temperature iteration controls and energy balance before accepting a self-consistent atmosphere.")
    if requested is not None and len(records) >= requested:
        add("iteration_budget", "Requested iteration count reached", "info",
            f"{len(records)} iterations recorded; current IN_ITS requests {requested}.",
            "Reaching the iteration count is not a convergence criterion. Inputs may have changed since the run.")
    scaled = [r for r in records[-5:] if float(r.get("major_species_minimum_scale", 1)) < 1]
    if scaled:
        add("scaled_corrections", "Recent corrections were limited", "warning",
            f"Major-species correction scaling was below unity in {len(scaled)} recent iteration(s).",
            "Check whether small applied corrections reflect damping rather than a settled solution.")
    if correction.get("current"):
        threshold = next((t for t in correction.get("thresholds", [])
                          if t["threshold"] == "1.0%"), None)
        if threshold and threshold["maximum_count"]:
            add("correction_distribution", "Corrections across the depth grid", "warning",
                f"Up to {threshold['maximum_count']} variables exceed 1% correction at depth "
                f"{threshold['depth']}; {threshold['nonzero_depths']} depths are affected.",
                "Inspect the depth distribution, including populations important to your spectral lines.",
                "CORRECTION_SUM")

    link = model_dir / "CORRECTION_LINK"
    if link.is_file():
        from .parsers.correction_link import read_correction_link

        if not _current_for_run(link, started_epoch):
            add("correction_drivers", "Species driving solver corrections", "unknown",
                "CORRECTION_LINK predates the latest recorded run.",
                "Inspect a fresh correction snapshot.", "CORRECTION_LINK")
        else:
            snapshot = read_correction_link(link)
            entries = snapshot["entries"]
            if not entries or snapshot["warnings"]:
                add("correction_drivers", "Species driving solver corrections", "unknown",
                    " ".join(snapshot["warnings"]),
                    "Inspect CORRECTION_LINK directly; incomplete rows cannot establish the largest correction.",
                    "CORRECTION_LINK")
            else:
                ranked = sorted(entries, key=lambda e: abs(e["change_percent"]), reverse=True)
                detail = "; ".join(
                    f"{e['species']} SL {e['superlevel']} (equation {e['equation']}): "
                    f"{e['change_percent']:+.4g}% at depth {e['depth']}" for e in ranked[:3]
                )
                add("correction_drivers", "Species driving solver corrections",
                    "warning" if abs(ranked[0]["change_percent"]) > 1 else "info",
                    "Largest listed solver corrections: " + detail + ".",
                    "These are selected ranked entries, before damping/scaling, not an applied-change "
                    "or convergence verdict. Review the listed species, superlevels and depths alongside "
                    "CORRECTION_SUM and the iteration history. T/Ne denote temperature/electron density.",
                    "CORRECTION_LINK")

    hydro_blocks = re.findall(
        r"large error in photosphere(.*?)(?:\*{5,}|\Z)", run_text, re.I | re.S)
    if hydro_blocks:
        block = hydro_blocks[-1]
        values = []
        for label, pattern in (("mean", r"Mean error is\s*(\S+)"),
                               ("RMS", r"Root mean squared error is\s*(\S+)"),
                               ("maximum", r"Maximum error is\s*(\S+)")):
            match = re.search(pattern, block, re.I)
            value = _finite(match[1]) if match else None
            if value is not None:
                values.append(f"{label} {value:g}%")
        add("hydrostatic_balance", "Photospheric hydrostatic balance", "warning",
            "Native hydrostatic warning: " + (", ".join(values) or "large photospheric residual") + ".",
            "Review HYDRO and the structure after further convergence; reassess LTE/hydro preparation "
            "if the residual persists. Native warning limits include RMS >5% or maximum >20%.")

    boundary = model_dir / "J_COMP"
    if _current_for_run(boundary, started_epoch):
        try:
            stat = boundary.stat()
            bands = _boundary_bands(str(boundary.resolve()), stat.st_mtime_ns, stat.st_size)
        except OSError:
            bands = {}
        if bands:
            maximum = bands["All frequencies"][0]
            add("boundary_radiation", "Measured outer-boundary radiation agreement",
                "warning" if maximum > 10 else "info",
                "; ".join(f"{name}: {diff:g}% at {wave:.5g} μm"
                          for name, (diff, wave) in bands.items()) + ".",
                "Compare a finer outer radial grid, particularly in the affected wavelength range. "
                "These are differences between J(mom) and J(ray), not direct emergent-flux errors. "
                "The 10% screening threshold is advisory.", "J_COMP")
        else:
            add("boundary_radiation", "Measured outer-boundary radiation agreement", "unknown",
                "The current J_COMP could not be summarized within the supported format/size limit.",
                "Inspect J_COMP directly.", "J_COMP")

    obs = model_dir / "OBSFLUX"
    if _current_for_run(obs, started_epoch):
        text = _read_text(obs)
        match = re.search(r"Normalized luminosity check[^\n]*\n\s*\n((?:[^\n]*\S[^\n]*\n)+)", text)
        if match:
            tokens = match[1].split()
            values = [_finite(token) for token in tokens]
            nd_match = re.search(r"^\s*(\d+)\s+\[ND\]", _read_text(model_dir / "MODEL_SPEC"), re.M)
            complete = nd_match is None or len(values) == int(nd_match[1])
            if values and all(v is not None for v in values) and complete:
                deviation, depth = max((100 * abs(v - 1), i + 1) for i, v in enumerate(values))
                add("luminosity_depth", "Luminosity consistency through the model",
                    "warning" if deviation > 2 else "info",
                    f"Maximum deviation from unity {deviation:.4g}% at depth {depth} "
                    f"across {len(values)} depths; advisory screening threshold 2%.",
                    "Review the depth profile and energy balance; this normalized check is not the observed luminosity.",
                    "OBSFLUX")
            else:
                add("luminosity_depth", "Luminosity consistency through the model", "unknown",
                    "The normalized luminosity vector is incomplete or contains invalid/non-finite values.",
                    "Inspect OBSFLUX before accepting the model.", "OBSFLUX")

    meanopac = model_dir / "MEANOPAC"
    if _current_for_run(meanopac, started_epoch):
        text = _read_text(meanopac)
        if "Tau(Ross)" in text.split("\n")[0]:
            rows = [line.split() for line in text.splitlines()[1:]]
            rows = [row for row in rows if len(row) >= 3 and row[1].isdigit()]
            tau = _finite(rows[-1][2]) if rows else None
            if tau is not None:
                add("inner_optical_depth", "Inner Rosseland optical depth",
                    "warning" if tau < 50 else "info", f"Innermost depth: τRoss = {tau:g}.",
                    "CMFGEN checks for depth below 30 and recommends at least 50, preferably 100. "
                    "Review the inner structure if the model is too shallow.", "MEANOPAC")

    for code, label, path in (
        ("boundary_radiation", "Measured outer-boundary radiation agreement", "J_COMP"),
        ("luminosity_depth", "Luminosity consistency through the model", "OBSFLUX"),
        ("inner_optical_depth", "Inner Rosseland optical depth", "MEANOPAC"),
    ):
        if not any(c["code"] == code for c in checks):
            add(code, label, "unknown", "No usable measurement from a current auxiliary file.",
                "Inspect the source file; missing, stale, or unreadable data cannot establish quality.", path)

    return {"checks": checks, "needs_review": any(c["level"] == "warning" for c in checks),
            "incomplete": any(c["level"] == "unknown" for c in checks)}
