#!/usr/bin/env python3
"""Compile production interpolation/collision code and extracted X-ray branches.

No model or checkout files are modified. The optional baseline interpolation
comparison checks that ordinary interior arithmetic is byte-identical.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def check(root, build, baseline=None, optimization='O2', baseline_main=None):
    drivers = Path(__file__).resolve().parent
    build.mkdir(parents=True, exist_ok=False)
    flags = ['gfortran', '-'+optimization, '-fopenmp', '-ffixed-line-length-0',
             '-fallow-argument-mismatch', '-fno-backslash', '-fd-lines-as-comments',
             '-I'+str(root/'mod'), '-I'+str(build), '-J'+str(build),
             '-ffpe-trap=invalid,zero,overflow']
    commands = []

    def run(command, *, expected=0):
        if command[0] == 'gfortran':
            command = [*command, '-L'+str(root/'lib'), '-lsubs', '-lmod']
        commands.append([str(x) for x in command])
        p = subprocess.run(command, cwd=build, text=True, capture_output=True,
                           env={**os.environ, 'OMP_NUM_THREADS': '1'})
        if p.returncode != expected:
            raise AssertionError((command, p.returncode, p.stdout, p.stderr))
        return p.stdout

    results = {}
    for name in ('range', 'near_node', 'ordinary'):
        exe = build/('interp_'+name)
        run([*flags, drivers/('test_monotone_'+name+'.f90'), root/'subs/mon_interp.f', '-o', exe])
        args = [str(build/'ordinary.bin')] if name == 'ordinary' else []
        results['interpolation_'+name] = run([exe, *args]).strip() or 'passed'
    if baseline:
        exe = build/'interp_baseline'
        run([*flags, drivers/'test_monotone_ordinary.f90', baseline, '-o', exe])
        run([exe, build/'baseline.bin'])
        assert (build/'ordinary.bin').read_bytes() == (build/'baseline.bin').read_bytes()
        results['ordinary_800_values_byte_identical'] = True
    exe = build/'collision'
    run([*flags, drivers/'test_collision_temperature.f90', root/'newsubs/subcol_multi_v6.f', '-o', exe])
    fields = dict(line.split() for line in run([exe]).splitlines())
    analytic, fd = float(fields['ANALYTIC']), float(fields['FINITE_DIFFERENCE'])
    assert abs(analytic/fd-1) < 1e-7, fields
    results['collision_temperature'] = {**fields, 'relative_error': abs(analytic/fd-1)}
    main = (root/'new_main/cmfgen_sub.f').read_text()
    helpers = main[main.index('      SUBROUTINE CMFGEN_XRAY_SCALE('):]
    (build/'xray_helpers.f').write_text(helpers)
    # Compile the production eligibility assignments, on both sides of the solve.
    # SOLVE_FOR_POPS changes flags for the next iteration; testing only its final
    # flags would miss the automatic-Lambda normalization bug.
    start = main.index('      XRAY_NORMALIZATION_READY=RD_LAMBDA .OR.')
    end = main.index("\n\tCALL TUNE(IONE,'SOLVE_FOR_POPS')", start)
    (build/'actual_xray_before_solve.inc').write_text(main[start:end]+'\n')
    start = main.index('      XRAY_NORMALIZATION_READY=XRAY_NORMALIZATION_READY .AND.')
    end = main.index('\n\tIF(LAST_NG .EQ. MAIN_COUNTER)', start)
    (build/'actual_xray_after_solve.inc').write_text(main[start:end]+'\n')

    for name, driver in [('helpers', 'test_xray_normalization.f90'),
                         ('block', 'test_xray_normalization_block.f')]:
        if name == 'block':
            start = main.index('\t  ELSE IF(XRAYS .AND. MAXCH .LT. 100.0_LDP .AND. .NOT. ADD_XRAYS_SLOWLY)THEN')
            end = main.index('\n\t  IF(INCL_ADVECTION', start)
            (build/'actual_xray_block.inc').write_text(main[start:end].replace('ELSE IF(', 'IF(', 1)+'\n')
        exe = build/('xray_'+name)
        run([*flags, drivers/driver, build/'xray_helpers.f', '-o', exe])
        results['xray_'+name] = run([exe]).strip()
        if name == 'block':
            for case in (11, 12):
                run([exe, str(case)], expected=1)
            if baseline_main:
                # The recorded small Lambda step must mutate the old source,
                # while the production test above requires no mutation now.
                native = baseline_main.read_text()
                start = native.index('\t  ELSE IF(XRAYS .AND. MAXCH .LT. 100.0_LDP .AND. .NOT. ADD_XRAYS_SLOWLY)THEN')
                end = native.index('\n\t  IF(INCL_ADVECTION', start)
                (build/'actual_xray_block.inc').write_text(native[start:end].replace('ELSE IF(', 'IF(', 1)+'\n')
                old_exe = build/'xray_block_baseline'
                run([*flags, drivers/driver, build/'xray_helpers.f', '-o', old_exe])
                output = run([old_exe, '13'], expected=31)
                factor = re.search(r'XRAY_NORMALIZATION_FACTOR:\s*(\S+)', output)
                assert factor and abs(float(factor[1])-1.4762399868465603) < 1e-14
                results['baseline_automatic_lambda_reproduced'] = True
    paths = ['subs/mon_interp.f', 'newsubs/subcol_multi_v6.f', 'new_main/cmfgen_sub.f']
    report = {'passed': True, 'optimization': optimization, 'results': results, 'commands': commands,
              'compiler': run(['gfortran', '--version']).splitlines()[0],
              'sources': {p: hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}}
    (build/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('--build', type=Path)
    p.add_argument('--baseline-interpolation', type=Path)
    p.add_argument('--baseline-main', type=Path,
                   help='Reproduce the Bstar3514 Lambda-triggered source change in the previous main source')
    p.add_argument('--optimization', choices=['O0', 'O2'], default='O2')
    a = p.parse_args()
    build = a.build or Path(tempfile.mkdtemp(prefix='cmfgen-repairs-'))/'build'
    report = check(a.root.expanduser().resolve(), build.resolve(),
                   a.baseline_interpolation.resolve() if a.baseline_interpolation else None, a.optimization,
                   a.baseline_main.resolve() if a.baseline_main else None)
    print(json.dumps({'passed': report['passed'], 'results': report['results'], 'report': str(build/'report.json')}, indent=2))
