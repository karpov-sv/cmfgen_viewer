#!/usr/bin/env python3
"""Audit related moment paths without modifying CMFGEN or model directories.

Reports observations, including known defects; this is not a pass/fail repair
certificate. Bounds cases call GET_MOMS_REL directly, so production reachability
must be assessed separately. Requires the installed moment-grid repair, NumPy,
and compiler-compatible native modules/libraries for the derivative checks.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile


def run(root, work, compiler):
    fixture_dir = Path(__file__).with_name('fixtures')
    helper = runpy.run_path(str(Path(__file__).with_name('check_moment_grid_jacobian.py')))
    env = {**os.environ, 'OMP_NUM_THREADS':'1', 'OPENBLAS_NUM_THREADS':'1'}
    flags = [compiler, '-fopenmp', '-O0', '-g', '-fcheck=all',
             '-finit-real=snan', '-ffpe-trap=invalid,zero,overflow',
             '-ffixed-line-length-0', '-ffree-line-length-none', '-I'+str(root/'mod')]
    commands = []

    def compile_native(args):
        commands.append(args)
        result = subprocess.run(args, cwd=work, capture_output=True, text=True)
        with (work/'build.log').open('a') as stream:
            stream.write(result.stdout+result.stderr)
        result.check_returncode()

    compile_native(flags+['-c', str(root/'plane/get_moms_rel.f'), '-o', str(work/'get_moms_rel.o')])
    # Explicit language selection because tracked fixtures have a .in suffix.
    compile_native(flags+['-x', 'f95', str(fixture_dir/'related_moment_bounds.f90.in'),
                          '-x', 'none', str(work/'get_moms_rel.o'), '-L'+str(root/'lib'),
                          '-lsubs', '-lmod', '-o', str(work/'bounds')])
    bounds = []
    names = ['stored ray grid larger than requested grid', 'requested grid grows after first call',
             'midpoint storage with requested grid larger than stored rays',
             'midpoint storage reads uninitialized local moments']
    for case, name in enumerate(names, 1):
        result = subprocess.run([str(work/'bounds'), str(case)], cwd=work, env=env,
                                capture_output=True, text=True)
        output = result.stdout+result.stderr
        (work/f'bounds-{case}.log').write_text(output)
        bounds.append(dict(case=case, description=name, returncode=result.returncode, output=output))

    compile_native(flags+['-cpp', '-DMOM_GRID_FIX', '-x', 'f95-cpp-input',
                          str(fixture_dir/'moment_grid_closure.f90.in'), '-x', 'none',
                          '-L'+str(root/'lib'), '-lsubs', '-lmod', '-o', str(work/'test')])
    native = helper['Native'](work, 1)
    derivatives = []
    for boundary, outer, method in [(1, 1, 'ZERO'), (1, 2, 'ZERO'), (2, 1, 'ZERO'),
                                     (3, 1, 'ZERO'), (3, 1, 'LOGMON')]:
        config = dict(fraction=20000, ntype='G_ONLY', ns=7, node=1, bc=boundary,
                      outer=outer, coherent=1, method=method, profile=1)
        nominal = native.run(**config)[-1]
        worst, location = 0., None
        for kind, frequency in [(1, 3), (1, 1), (2, 3)]:
            for depth in range(1, 8):
                step = 2**-14
                hi = native.run(**config, perturb=kind, depth=depth, atfreq=frequency,
                                delta=step, mode='field')[-1]
                lo = native.run(**config, perturb=kind, depth=depth, atfreq=frequency,
                                delta=-step, mode='field')[-1]
                value = helper['model_value'](config, kind, depth, frequency)
                for observable, key in [('j', 'tx'), ('h', 'tvx')]:
                    fd = (hi[observable]-lo[observable])/(2*step*value)
                    analytic = nominal[key][:, depth-1, 2 if frequency == 1 else kind-1]
                    error = helper['column_error'](fd, analytic)
                    if error > worst:
                        worst = error
                        location = dict(variable=kind, frequency=frequency, depth=depth, observable=observable)
        derivatives.append(dict(config=config, maximum_column_relative_error=worst, location=location))
    paths = ['plane/get_moms_rel.f', 'plane/mom_jrel_v9.f', 'plane/var_jrel_v5.f',
             'plane/var_mom_jext_cmf_v3.f', 'subs/edd_j_var_v6.f', 'subs/up_tx_tvx_v2.f',
             'subs/nordtau.f', 'lib/libsubs.a']
    return dict(meaning='Audit observations, not a repaired-source certificate or atmosphere error estimate',
                bounds_cases=bounds, unrefined_derivatives=derivatives, build_commands=commands,
                source_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in paths})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cmfgen-root', type=Path, default=Path('~/CMFGEN2023/cur_cmf'))
    parser.add_argument('--work-dir', type=Path)
    parser.add_argument('--compiler', default=shutil.which('gfortran') or '/opt/local/bin/gfortran')
    args = parser.parse_args()
    if args.work_dir:
        work = args.work_dir.resolve()
        work.mkdir(parents=True)  # Refuse existing directories, including model folders.
    else:
        work = Path(tempfile.mkdtemp(prefix='cmfgen-related-moments-'))
    result = run(args.cmfgen_root.expanduser().resolve(), work, args.compiler)
    (work/'report.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(bounds_exit_codes=[row['returncode'] for row in result['bounds_cases']],
                          unrefined_derivatives=result['unrefined_derivatives']), indent=2))
    print('Evidence:', work)


if __name__ == '__main__':
    main()
