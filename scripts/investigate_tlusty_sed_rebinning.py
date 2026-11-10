#!/usr/bin/env python3
"""Read-only SED rebinning experiments; never modify the model cache.

Run from the repository root. Results describe the viewer's rectangular band
approximation, not synthetic photometry through measured throughput curves.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cmfgen_viewer.parsers.common import downsample_xy
from cmfgen_viewer.spectrum_fitting import _sample_model_on_observed_grid
from cmfgen_viewer.spectrum_transforms import _reddening_scale
from cmfgen_viewer.vizier_photometry import FILTER_LIBRARY
from scripts.download_tlusty_spectra import _conservative_sed_bins as conservative_bins, _reduce_resolution


def select_models(rows, per_grid):
    """Deterministic stratification across composition, temperature, and gravity."""
    selected = []
    for grid in sorted({row["grid"] for row in rows}):
        group = [row for row in rows if row["grid"] == grid]
        group.sort(key=lambda r: tuple(float(r[k]) for k in ("z_over_zsun", "vturb_km_s", "teff_k", "log_g")))
        if per_grid == 0:
            selected.extend(group)
            continue
        indices = set(np.linspace(0, len(group) - 1, min(per_grid, len(group))).astype(int))
        # Include parameter and file-size extrema, even if they fall between
        # the evenly spaced rows. Actual sample count can exceed per_grid.
        for key in ("z_over_zsun", "vturb_km_s", "teff_k", "log_g", "points"):
            for operation in (min, max):
                indices.add(operation(range(len(group)), key=lambda i: float(group[i][key])))
        selected.extend(group[i] for i in sorted(indices))
    return selected


def bands():
    broad = [(key, item.lambda_eff_a, item.band_width_a, "catalogue") for key, item in FILTER_LIBRARY.items()]
    broad += [("UV_1500", 1500, 400, "uv_u"), ("UV_2300", 2300, 800, "uv_u"), ("U_3531", 3531, 706, "uv_u")]
    narrow = [(f"narrow_{center}", center, center * .01, "narrow")
              for center in (912, 1216, 1500, 2175, 3646, 4861, 6563, 8204, 10000, 22000)]
    return broad + narrow


def summarize(values):
    values = np.asarray(values, dtype=float)
    return dict(median=float(np.median(values)), p95=float(np.percentile(values, 95)), maximum=float(np.max(values)))


def ranking_diagnostics(records, methods):
    """Limited grid ranking: fixed z/E(B-V), free normalization, 1% errors."""
    native = np.array([row["broadband_flux"] for row in records])
    truth = np.repeat(native, 4, axis=0)
    noise = np.random.default_rng(20261110).normal(0, .01, truth.shape)
    noise[::4] = 0
    observed, sigma = truth * (1 + noise), truth * .01

    def scores(prediction):
        weighted = prediction[None, :, :] / sigma[:, None, :]
        data = observed / sigma
        scale = np.sum(weighted * data[:, None, :], axis=2) / np.sum(weighted**2, axis=2)
        return np.sum((weighted * scale[:, :, None] - data[:, None, :])**2, axis=2)

    reference_scores = scores(native)
    native_best = np.argmin(reference_scores, axis=1)
    result = {}
    for method in methods:
        prediction = np.array([row["methods"][method]["broadband_flux"] for row in records])
        method_scores = scores(prediction)
        best = np.argmin(method_scores, axis=1)
        penalty = reference_scores[np.arange(len(truth)), best] - np.min(reference_scores, axis=1)
        details = {}
        for name, mask in (("noiseless", np.arange(len(truth)) % 4 == 0),
                           ("one_percent_noise", np.arange(len(truth)) % 4 != 0)):
            details[name] = dict(observations=int(mask.sum()), changed_best_model=int(np.sum(best[mask] != native_best[mask])),
                                 native_delta_chi2_of_changed_choice=summarize(penalty[mask]))
        result[method] = details
    return dict(description="Subset ranking only; fixed z=0 and E(B-V)=0; free normalization; 1% errors; 3 noise realizations/model; seed 20261110",
                methods=result)


def investigate(root, *, per_grid, powers, output, conservative_only=False, unreddened_only=False):
    root, output = root.resolve(), output.resolve()
    if output.is_relative_to(root):
        raise ValueError("Experiment output must be outside the input model cache")
    with (root / "models.csv").open(newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["model_name"].endswith(".flux")]
    selected = select_models(rows, per_grid)
    check_ranking = len(selected) <= 200
    filters = bands()
    centers = np.array([band[1] for band in filters])
    widths = np.array([band[2] for band in filters])
    groups = {name: np.array([band[3] == name for band in filters]) for name in ("catalogue", "uv_u", "narrow")}
    metrics = {}
    model_records = []
    transform_settings = [(0., 0.)] if unreddened_only else [(z, ebv) for z in (-.02, 0., .02) for ebv in (0., 1., 3.)]

    for index, row in enumerate(selected, 1):
        path = root / row["spectrum_relpath"]
        with np.load(path, allow_pickle=False) as source:
            native_x, native_y = source["wavelength_angstrom"], source["flux_lambda_cgs"]
            metadata = {key: source[key] for key in ("input_columns", "x_axis_kind", "x_unit_guess") if key in source}
        baseline = {}
        for z, ebv in transform_settings:
            shifted = native_x * (1 + z)
            baseline[z, ebv] = _sample_model_on_observed_grid(shifted, native_y * _reddening_scale(shifted, ebv), centers, widths)
        native_total = np.trapezoid(native_y, native_x)
        candidates = []
        if not conservative_only:
            old_x, old_y = downsample_xy(native_x, native_y, max_points=20000)
            candidates.append(("legacy_20000", np.asarray(old_x), np.asarray(old_y), None))
        for power in powers:
            proposed_count = int(np.ceil(np.log(native_x[-1] / native_x[0]) * power)) + 2
            if proposed_count >= len(native_x):
                # Avoid growing already-sparse SEDs, notably metal-free models.
                rebinned_x, rebinned_y, mass = native_x, native_y, np.array([native_total])
            else:
                rebinned_x, rebinned_y, mass = conservative_bins(native_x, native_y, power)
            candidates.append((f"conservative_{power:g}", rebinned_x, rebinned_y, float(mass.sum() / native_total - 1)))
            if not conservative_only:
                candidates.append((f"interpolation_{power:g}", rebinned_x, np.interp(rebinned_x, native_x, native_y), None))
        # Comparable output counts to binning powers ~900 and ~3000.
        for resolution in (() if conservative_only else (300, 1000)):
            reduced = _reduce_resolution({"arrays": {"wavelength_angstrom": native_x, "flux_lambda_cgs": native_y}},
                                         resolving_power=resolution, samples_per_resolution=3)
            arrays = reduced["arrays"]
            if len(arrays["wavelength_angstrom"]) >= len(native_x):
                x, y = native_x, native_y
            else:
                x, y = arrays["wavelength_angstrom"], arrays["flux_lambda_cgs"]
            candidates.append((f"gaussian_R{resolution}_s3", x, y, None))

        record = {key: row[key] for key in ("grid", "model_name", "teff_k", "log_g", "z_over_zsun", "vturb_km_s")}
        record.update(native_points=len(native_x), native_bytes=path.stat().st_size, methods={})
        broad_mask = groups["catalogue"] | groups["uv_u"]
        if check_ranking:
            record["broadband_flux"] = baseline[0., 0.][broad_mask].tolist()
        for method, x, y, integral_error in candidates:
            packed = io.BytesIO()
            np.savez_compressed(packed, wavelength_angstrom=x, flux_lambda_cgs=y, **metadata)
            size = len(packed.getvalue())
            if method not in metrics:
                metrics[method] = dict(native_bytes=0, output_bytes=0, native_points=0, output_points=0,
                                       conserved_integral_errors=[], interpolated_integral_errors=[], groups={}, worst={})
            aggregate = metrics[method]
            for key, amount in (("native_bytes", path.stat().st_size), ("output_bytes", size),
                                ("native_points", len(native_x)), ("output_points", len(x))):
                aggregate[key] += amount
            if integral_error is not None:
                aggregate["conserved_integral_errors"].append(abs(integral_error))
            aggregate["interpolated_integral_errors"].append(abs(np.trapezoid(y, x) / native_total - 1))
            record["methods"][method] = dict(points=len(x), bytes=size)
            for z, ebv in transform_settings:
                shifted = x * (1 + z)
                actual = _sample_model_on_observed_grid(shifted, y * _reddening_scale(shifted, ebv), centers, widths)
                reference = baseline[z, ebv]
                ratio = actual / reference
                if check_ranking and z == 0 and ebv == 0:
                    record["methods"][method]["broadband_flux"] = actual[broad_mask].tolist()
                if not np.all(np.isfinite(ratio)):
                    raise ValueError(f"Nonfinite band comparison: {row['model_name']} {method}")
                for group, mask in groups.items():
                    errors = abs(ratio[mask] - 1)
                    group_metrics = aggregate["groups"].setdefault(group, dict(errors=[], color_errors=[]))
                    group_metrics["errors"].extend(errors.tolist())
                    group_metrics["color_errors"].extend(abs(ratio[mask] / np.median(ratio[mask]) - 1).tolist())
                    worst_index = np.flatnonzero(mask)[int(np.argmax(errors))]
                    context = dict(relative_error=float(max(errors)), model=row["model_name"], grid=row["grid"],
                                   band=filters[worst_index][0], redshift=z, ebv=ebv)
                    if context["relative_error"] > aggregate["worst"].get(group, {}).get("relative_error", -1):
                        aggregate["worst"][group] = context
        model_records.append(record)
        if index % max(8, len(selected) // 20) == 0 or index == len(selected):
            print(f"{index}/{len(selected)} SEDs investigated", flush=True)

    for aggregate in metrics.values():
        aggregate["storage_reduction"] = 1 - aggregate["output_bytes"] / aggregate["native_bytes"]
        for group in aggregate["groups"].values():
            group["relative_flux_error"] = summarize(group.pop("errors"))
            group["relative_color_error"] = summarize(group.pop("color_errors"))
        for key in ("conserved_integral_errors", "interpolated_integral_errors"):
            if aggregate[key]:
                aggregate[key] = summarize(aggregate[key])
    report = dict(input_root=str(root), models=len(selected), total_indexed_seds=len(rows),
                  transform_settings=transform_settings, bands=filters, binning_powers=powers,
                  note="Viewer rectangular bands; no measured throughput curves. No cache files modified.",
                  methods=metrics, models_tested=model_records)
    if check_ranking:
        report["ranking_check"] = ranking_diagnostics(model_records, metrics)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {output}", flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/tlusty"))
    parser.add_argument("--models-per-grid", type=int, default=32, help="0 tests all indexed SEDs; extrema are also included")
    parser.add_argument("--binning-powers", nargs="+", type=float, default=[300, 1000, 3000, 10000])
    parser.add_argument("--output", type=Path, default=Path("tmp/tlusty-sed-rebinning/summary.json"))
    parser.add_argument("--conservative-only", action="store_true", help="Skip interpolation, Gaussian, and legacy controls")
    parser.add_argument("--unreddened-only", action="store_true", help="Survey all models at z=0, E(B-V)=0 only")
    args = parser.parse_args()
    if args.models_per_grid < 0 or any(not np.isfinite(value) or value <= 0 for value in args.binning_powers):
        parser.error("Sample counts must be nonnegative and binning powers finite and positive")
    investigate(args.root, per_grid=args.models_per_grid, powers=args.binning_powers, output=args.output,
                conservative_only=args.conservative_only, unreddened_only=args.unreddened_only)
