#!/usr/bin/env python3
"""Check the actual V4 Ng temperature guard through its scratch-reader interface.

The fixture returns four positive population/temperature states without file I/O.
Test wrong-sign warming/cooling, correct-sign warming/cooling and fixed T over
five band widths. The corrected routine must reject the first two and preserve
the last three. --expect-original-defect instead certifies reproduction of the
original geometry-index error; that mode does not certify a correction.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import tempfile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cmfgen-root', type=Path,
                    default=Path('~/CMFGEN2023/cur_cmf').expanduser())
    ap.add_argument('--source', type=Path)
    ap.add_argument('--compiler', default='/opt/local/bin/gfortran')
    ap.add_argument('--work-dir', type=Path)
    ap.add_argument('--expect-original-defect', action='store_true')
    args = ap.parse_args()
    root = args.cmfgen_root.expanduser().resolve()
    source = (args.source or root/'new_main/subs/do_ng_accel_band_v4.f').resolve()
    if args.work_dir:
        work = args.work_dir.resolve()
        work.mkdir(parents=True, exist_ok=False)
    else:
        work = Path(tempfile.mkdtemp(prefix='cmfgen-ng-temperature-guard-'))
    template = Path(__file__).with_name('fixtures')/'ng_temperature_guard.f90.in'
    text = template.read_text()
    assert text.count('BASELINE_EXPECTATION') == 1
    expectation = '''if(scenario==1)then
    expected_done=.true.;expected_t=.96_ldp;expected_p=1.92_ldp
   else if(scenario==2)then
    expected_done=.true.;expected_t=1.04_ldp;expected_p=2.08_ldp
   end if''' if args.expect_original_defect else ''
    fixture = work/'fixture.f90'
    fixture.write_text(text.replace('BASELINE_EXPECTATION', expectation))
    env = os.environ.copy()
    env.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    # The original routine reads an undefined comparison temporary when its
    # mistaken geometry difference is zero. Do not conflate that with the
    # deterministic indexing defect being reproduced. Corrected code is also
    # checked with signaling-NaN initialization and floating-point traps.
    flags = [] if args.expect_original_defect else [
        '-fcheck=all', '-ffpe-trap=invalid,zero,overflow', '-finit-real=snan']
    obj, exe = work/'ng.o', work/'fixture'
    commands = [
        [args.compiler, '-O', '-ffixed-line-length-0', *flags,
         '-I'+str(root/'mod'), '-c', str(source), '-o', str(obj)],
        [args.compiler, '-fopenmp', '-ffree-line-length-none', *flags,
         '-I'+str(root/'mod'), str(fixture), str(obj), '-L'+str(root/'lib'),
         '-lsubs', '-lmod', '-L/opt/local/lib', '-lopenblas', '-o', str(exe)],
        [str(exe)],
    ]
    results = []
    for i, cmd in enumerate(commands):
        run = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True)
        (work/f'command-{i}.stdout.txt').write_text(run.stdout)
        (work/f'command-{i}.stderr.txt').write_text(run.stderr)
        results.append({'command': cmd, 'returncode': run.returncode})
        if run.returncode:
            raise RuntimeError(f'Native check failed; see {work}/command-{i}.*.txt')
    rows = [line for line in run.stdout.splitlines() if line.startswith('CASE')]
    assert len(rows) == 25
    report = {
        'passed': True,
        'mode': 'original_defect_reproduced' if args.expect_original_defect
                else 'corrected_guard_verified',
        'native_cases': 25,
        'scenarios': ['wrong-sign warming', 'wrong-sign cooling',
                      'correct-sign warming', 'correct-sign cooling', 'fixed T'],
        'bands': [0, 1, 2, 3, 4],
        'geometry_bitwise_preserved': True,
        'whole_V4_wrapper_exercised': True,
        'source': str(source),
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'fixture_sha256': hashlib.sha256(fixture.read_bytes()).hexdigest(),
        'commands': results,
        'native_rows': rows,
        'scope': 'Actual full V4 Ng source and native NGACCEL; deterministic '
                 'scratch-reader stub, no checkpoint I/O or model job. CHK_NG '
                 'is false, as in Bstar3502. No whole-model attribution or '
                 'convergence claim. Original-defect mode is not fix validation.',
    }
    (work/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ['passed', 'mode', 'native_cases']}))
    print(f'Evidence: {work / "report.json"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
