#!/usr/bin/env python3
"""Run asserting regression tests against CMFGEN source without editing its checkout.

Usage: python3 run_review.py /path/to/cur_cmf [--compiler gfortran]
--atomic-data additionally enables the NI reader/rate regression fixture.
The fixtures mock file readers, initialization interfaces, and the matrix
solver where noted in the accompanying review. Numerical routines under
review are always compiled from the supplied checkout.
"""
import argparse
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source", type=Path)
parser.add_argument("--compiler", default="gfortran")
parser.add_argument("--threads", type=int, default=1)
parser.add_argument("--optimization", choices=["O0", "O2"], default="O0")
parser.add_argument("--atomic-data", type=Path,
                    help="Also test the actual photo reader and NI rates using atomic data and source/lib archives")
args = parser.parse_args()
root = args.source.expanduser().resolve()
fixtures = Path(__file__).resolve().parent
work = Path(tempfile.mkdtemp(prefix="cmfgen-review-"))
flags = [args.compiler, "-" + args.optimization, "-g", "-fcheck=all", "-fopenmp",
         "-ffixed-line-length-none", "-ffree-line-length-none"]
cases = {
    "xray": [root / "new_main/mod_subs/steq_data_mod.f",
             root / "new_main/subs/evalse_x_qwvj_v4.f",
             root / "new_main/subs/vsebyj_x_v7.f", fixtures / "test_xray.f90"],
    "ratio": [root / "new_main/mod_subs/steq_data_mod.f",
              root / "new_main/subs/evalse_qwvj_v8.f",
              root / "new_main/subs/vsebyj_multi_v8.f", fixtures / "test_ratio.f90"],
    "omega": [root / "newsubs/omega_gen_v3.f", root / "subs/ex_e1x_fun.f",
              fixtures / "test_omega.f90"],
    "profile": [root / "stark/get_prof_storage_limits_v2.f",
                root / "stark/get_prof_storage_limits.f", fixtures / "test_profile.f90"],
    "auto": [fixtures / "auto_modules.f90", root / "new_main/subs/auto_add_ion.f",
             fixtures / "test_auto.f90"],
    "global": [fixtures / "test_global.f90", root / "new_main/subs/solveba_v13.f"],
}
if (root / "new_main/mod_subs/init_population_estimates.f90").exists():
    cases["initialization"] = [root / "new_main/mod_subs/mod_cmfgen.f",
        root / "new_main/mod_subs/mod_lev_dis_blk.f", root / "subs/occupation_prob.f",
        root / "subs/ltepop_wld_v2.f", root / "new_main/mod_subs/init_population_estimates.f90",
        fixtures / "test_initialization.f90"]
    cases["endpoint"] = [root / "subs/regrid_t_ed_v3.f", root / "subs/lin_interp.f",
                         fixtures / "test_endpoint.f90"]
env = dict(os.environ, OMP_NUM_THREADS=str(args.threads))
for name, sources in cases.items():
    case_dir = work / name
    case_dir.mkdir()
    # Compile the checkout's actual precision selection; no installed .mod files needed.
    command = flags + [str(root / "tools/set_kind_module.f")]
    command += [str(p) for p in sources] + ["-o", str(case_dir / "test")]
    subprocess.run(command, cwd=case_dir, check=True, env=env)
    result = subprocess.run([str(case_dir / "test")], cwd=case_dir,
                            capture_output=True, text=True, env=env)
    output = result.stdout + result.stderr
    (case_dir / "results.txt").write_text(output)
    result.check_returncode()
    print(f"\n{name}:\n{output}")
    if name in {"initialization", "endpoint"}:
        argument = "mismatch" if name == "initialization" else "no-overlap"
        negative = subprocess.run([str(case_dir / "test"), argument], cwd=case_dir,
                                  capture_output=True, text=True, env=env)
        (case_dir / "negative-results.txt").write_text(negative.stdout + negative.stderr)
        expected = "one common source model" if name == "initialization" else "No overlapping radius grid"
        if negative.returncode == 0 or expected not in negative.stdout + negative.stderr:
            raise RuntimeError(f"{name}: invalid input was not rejected as expected")
        print(f"PASS {name}: rejected {argument}")
    if name == "auto":
        empty_dir = work / "auto-empty"
        empty_dir.mkdir()
        result = subprocess.run([str(case_dir / "test"), "empty"], cwd=empty_dir,
                                capture_output=True, text=True, env=env)
        output = result.stdout + result.stderr
        (empty_dir / "results.txt").write_text(output)
        print(f"auto-empty (exit {result.returncode}):\n{output}")
        result.check_returncode()
if args.atomic_data:
    case_dir = work / "photo"
    case_dir.mkdir()
    atomic = args.atomic_data.expanduser().resolve()
    for source in (fixtures / "data").iterdir():
        shutil.copyfile(source, case_dir / source.name)
    for suffix in "ABCD":
        (case_dir / ("PHOTNI_" + suffix)).symlink_to(atomic / "NIT/I/19apr23" / ("phot_data_" + suffix))
    for name, relative in [("HYD_L_DATA", "HYD/I/5dec96/hyd_l_data.dat"),
                           ("GBF_N_DATA", "HYD/I/5dec96/gbf_n_data.dat")]:
        (case_dir / name).symlink_to(atomic / relative)
    command = flags + ["-I" + str(root / "mod")]
    if sys.platform == "darwin":
        command.append("-Wl,-stack_size,0x4000000")
    command += [str(root / "newsubs/rdphot_gen_v2.f"), str(fixtures / "test_photo.f90"),
                "-o", str(case_dir / "test"), str(root / "lib/libsubs.a"), str(root / "lib/libmod.a")]
    subprocess.run(command, cwd=case_dir, check=True, env=env)
    # Avoid repeated multithreaded startup inside the one-depth rate quadrature fixture.
    result = subprocess.run([str(case_dir / "test")], cwd=case_dir, capture_output=True,
                            text=True, env=dict(env, OMP_NUM_THREADS="1"))
    output = result.stdout + result.stderr
    (case_dir / "results.txt").write_text(output)
    print(f"photo:\n{output}")
    result.check_returncode()
print(f"Artifacts: {work}")
