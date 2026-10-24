#!/usr/bin/env python3
"""Test native Lambda line derivatives against high-precision net-rate differences.

Reads a built CMFGEN tree without changing it. The unpatched expression fails
for vanishing upper populations; pass --source to test an isolated candidate.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, localcontext
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def net_rate(upper: Decimal, lower: Decimal, depth: int) -> Decimal:
    """Original physical net downward rate, including its source-function form."""
    d = Decimal
    weights = (d(".13"), d(".27"), d(".51"))
    intensities = (d(".76e-6"), d("1.37e-6"), d("2.11e-6"))
    scale = d(1) - d(".17") * (depth - 1)
    chi = d("2.4e-12") * (d("1.2") * lower - d(".4") * d(".7") * upper)
    eta = d("3.7e-4") * d(".7") * upper
    znet = sum(w * (1 - j * scale * chi / eta) for w, j in zip(weights, intensities))
    return d("1.234e8") * d(".7") * upper * znet


def derivative_oracle(case: int, depth: int) -> tuple[float, float]:
    """Central differences at 350 decimal digits resolve even the 1e-128 case."""
    with localcontext() as ctx:
        ctx.prec = 350
        up = tuple(map(Decimal, ("1e-4", "1e-20", "1e-60", "1e-128", "10")))[case - 1]
        low = Decimal(".8")
        hu, hl = up / 2**20, low / 2**20
        dup = (net_rate(up + hu, low, depth) - net_rate(up - hu, low, depth)) / (2 * hu)
        dlow = -(net_rate(up, low + hl, depth) - net_rate(up, low - hl, depth)) / (2 * hl)
        return float(dup), float(dlow)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cmfgen-root", type=Path, default=Path("~/CMFGEN2023/cur_cmf").expanduser())
    ap.add_argument("--source", type=Path)
    ap.add_argument("--compiler", default="gfortran")
    ap.add_argument("--work-dir", type=Path)
    args = ap.parse_args()
    root = args.cmfgen_root.expanduser().resolve()
    source = (args.source or root / "new_main/subs/update_ba_for_line.f").resolve()
    fixture = Path(__file__).with_name("fixtures") / "lambda_line_jacobian.f90"
    work = args.work_dir.resolve() if args.work_dir else Path(tempfile.mkdtemp(prefix="cmfgen-lambda-line-"))
    if args.work_dir:
        work.mkdir(parents=True, exist_ok=False)
    (work / "mod").mkdir()
    env = os.environ.copy()
    env["OPENBLAS_NUM_THREADS"] = "1"
    commands = [
        [args.compiler, "-fopenmp", "-fallow-argument-mismatch", "-O",
         "-ffixed-line-length-0", "-fd-lines-as-comments",
         "-I" + str(root / "mod"), "-J" + str(work / "mod"),
         "-c", str(source), "-o", str(work / "update_ba_for_line.o")],
        [args.compiler, "-fopenmp", "-fallow-argument-mismatch", "-ffree-line-length-none",
         "-fcheck=bounds", "-I" + str(root / "mod"), str(fixture),
         str(work / "update_ba_for_line.o"), "-L" + str(root / "lib"), "-lsubs", "-lmod",
         "-L/opt/local/lib", "-lopenblas", "-o", str(work / "fixture")],
        [str(work / "fixture")],
    ]
    for i, cmd in enumerate(commands):
        result = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True)
        (work / f"command-{i}-stdout.txt").write_text(result.stdout)
        (work / f"command-{i}-stderr.txt").write_text(result.stderr)
        if result.returncode:
            raise RuntimeError(f"Native command failed ({result.returncode}); see {work}")
    rows = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 7:
            raise ValueError(f"Unexpected native fixture row: {line!r}")
        case, depth = map(int, fields[:2])
        population, upper, lower, balance_up, balance_low = map(float, fields[2:])
        oracle_up, oracle_low = derivative_oracle(case, depth)
        error_up, error_low = abs(upper / oracle_up - 1), abs(lower / oracle_low - 1)
        rows.append({"case": case, "depth": depth, "upper_population": population,
                     "native_upper_derivative": upper, "oracle_upper_derivative": oracle_up,
                     "upper_relative_error": error_up, "lower_relative_error": error_low,
                     "number_conservation_exact": balance_up == balance_low == 0,
                     "passed": upper > 0 and error_up < 1e-12 and error_low < 1e-12
                     and balance_up == balance_low == 0})
    if {(r["case"], r["depth"]) for r in rows} != {(c, k) for c in range(1, 6) for k in (1, 2)}:
        raise ValueError("Incomplete native fixture cases")
    report = {"passed": all(r["passed"] for r in rows), "native_cases": len(rows),
              "maximum_upper_relative_error": max(r["upper_relative_error"] for r in rows),
              "oracle": "350-digit central differences of the original source-function net rate",
              "source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
              "scope": "Actual UPDATE_BA_FOR_LINE; only TUNE profiling stubbed. Lambda branch shared by weak-line treatment. No installed files changed.",
              "commands": commands, "cases": rows}
    (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("passed", "native_cases", "maximum_upper_relative_error", "oracle")}))
    print(f"Evidence: {work / 'report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
