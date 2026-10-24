#!/usr/bin/env python3
"""Reproduce line-Jacobian cancellation with native source and independent differences.

Tests Lambda, weak-line and strong-line branches at four depths and three bands.
Continuum BA_UPDATE/ADD_PAR and profiling are stubbed; prescribed nonzero radiation
responses exercise line coupling, not the full transport solver. No installed edits.
The old source is expected to fail. Pass --source for an isolated candidate.
"""
from pathlib import Path
from decimal import Decimal as D, localcontext
import argparse, hashlib, json, math, os, subprocess, tempfile, sys

def rate(q,mode,case,k,l,ix,delta,radiation_response=True):
    upper=list(map(D,['1e-4','1e-20','1e-60','1e-128','10']))[case-1]
    lower=D('.8');temperature=D(1)
    if l==k:
        if ix==1:lower+=delta
        if ix==2:upper+=delta
        if ix==5:temperature+=delta
    lr,ur=D('1.2'),D('.7')
    if mode==3 and q>=3:lr+=D('.02')*(temperature-1);ur+=D('.03')*(temperature-1)
    chi=D('2.4e-12')*(lr*lower-D('.4')*ur*upper);eta=D('3.7e-4')*ur*upper
    znet=D(0)
    for w,rad in zip(map(D,['.13','.27','.51']),map(D,['.76e-6','1.37e-6','2.11e-6'])):
        shape=rad/D('1e-6')*(1-D('.17')*(k-1));intensity=rad*(1-D('.17')*(k-1))
        if radiation_response and mode==3 and q>=2:
            slopes=list(map(D,['2e7','-1.3e7','.014e7','.4e7','.09e7']))
            intensity+=shape*(D(1) if l==k else D('.1'))*slopes[ix-1]*delta
        znet+=w*(1-intensity*chi/eta)
    return D('1.234e8')*ur*upper*znet

def oracle(q,mode,case,k,l,ix,radiation_response=True):
    with localcontext() as ctx:
        ctx.prec=350
        h=([D('.8'),list(map(D,['1e-4','1e-20','1e-60','1e-128','10']))[case-1],D(1),D(1),D(1)][ix-1])/2**20
        value=(rate(q,mode,case,k,l,ix,h,radiation_response)-rate(q,mode,case,k,l,ix,-h,radiation_response))/(2*h)
        return float(value),float(value*D('3.7e-4')/D('1.234e8'))


def read_rows(path):
    rows={}
    for line in path.read_text().splitlines():
        f=line.split()
        if len(f)!=9:raise ValueError(f"Unexpected native row: {line!r}")
        key=tuple(map(int,f[:6]));rows[key]=tuple(map(float,f[6:]))
    expected={(q,m,c,k,l,i) for q in range(1,5) for m in range(1,4)
              for c in range(1,6) for k in range(1,5)
              for l in range(max(1,k-1),min(4,k+1)+1) for i in range(1,6)}
    if set(rows)!=expected:raise ValueError("Incomplete native matrix coverage")
    return rows


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cmfgen-root',type=Path,default=Path('~/CMFGEN2023/cur_cmf').expanduser())
    ap.add_argument('--source',type=Path)
    ap.add_argument('--baseline-source',type=Path)
    ap.add_argument('--compiler',default='gfortran')
    ap.add_argument('--work-dir',type=Path)
    ap.add_argument('--variant',choices=['baseline','cooling','mixed-new-line'],default='baseline')
    ap.add_argument('--shared-check',choices=['legacy','physical'],default='legacy',
        help='Physical uses independent shared-level oracles for both native pointer layouts; baseline variant only.')
    args=ap.parse_args();root=args.cmfgen_root.expanduser().resolve()
    if args.shared_check=='physical' and args.variant!='baseline':
        ap.error('--shared-check physical currently covers the baseline shared-level fixtures only')
    source=(args.source or root/'new_main/subs/update_ba_for_line.f').resolve()
    baseline=(args.baseline_source or root/'new_main/subs/update_ba_for_line.f').resolve()
    if args.work_dir:work=args.work_dir.resolve();work.mkdir(parents=True,exist_ok=False)
    else:work=Path(tempfile.mkdtemp(prefix='cmfgen-line-branches-'))
    fixture_sources=Path(__file__).with_name('fixtures')
    fixtures=work/'fixtures';fixtures.mkdir()
    for name in ['line_jacobian_branches.f90','line_jacobian_shared_superlevel.f90']:
        text=(fixture_sources/name).read_text()
        if args.variant=='cooling':
            text=text.replace('ave_energy,resonance_zone,','fl_sim,ave_energy,resonance_zone,')
            text=text.replace('include_dsldt,znet_var_limit','include_dsldt,znet_var_limit,scl_line_ht_fac')
            text=text.replace('scl_line_cool_rates=.false.;scl_line_density_limit=1.e99_ldp',
                'scl_line_cool_rates=.true.;scl_line_density_limit=1.e4_ldp;scl_line_ht_fac=2')
            text=text.replace('ave_energy=1;pop_atom=1.e4_ldp',
                'ave_energy=1;ave_energy(1)=2;allocate(fl_sim(1));fl_sim=.5_ldp;pop_atom=[1.e3_ldp,1.e3_ldp,1.e5_ldp,1.e5_ldp]')
        if args.variant=='mixed-new-line':
            text=text.replace('include_dsldt,znet_var_limit','include_dsldt,znet_var_limit,indx_ba_meth_rd')
            text=text.replace('esec,eta_noscat,chi_noscat','esec,eta_noscat,chi_noscat,eta,chi,chi_scat')
            text=text.replace('only:rj,ta','only:rj,ta,tb,tc')
            text=text.replace('new_line_ba=.false.;','new_line_ba=.true.;indx_ba_meth_rd=3;')
            text=text.replace('allocate(rj(nd),ta(nd),t(nd)',
                'allocate(eta(nd),chi(nd),chi_scat(nd),tb(nd),tc(nd))\n allocate(rj(nd),ta(nd),t(nd)')
            text=text.replace('include_dsldt=.false.;znet_var_limit=0',
                'eta=1;chi=1;chi_scat=0;tb=0;tc=0\n include_dsldt=.false.;znet_var_limit=0')
        (fixtures/name).write_text(text)
    env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    commands=[]
    def run(cmd,name):
        commands.append(cmd)
        result=subprocess.run(cmd,cwd=work,env=env,capture_output=True,text=True)
        (work/(name+'-stdout.txt')).write_text(result.stdout)
        (work/(name+'-stderr.txt')).write_text(result.stderr)
        if result.returncode:raise RuntimeError(f'Native command failed; see {work}/{name}-stderr.txt')
        return result
    results={}
    for label,src in [('candidate',source),('baseline',baseline)]:
        obj=work/(label+'.o')
        run([args.compiler,'-fopenmp','-fcheck=bounds','-O','-ffixed-line-length-0',
             '-fd-lines-as-comments','-I'+str(root/'mod'),'-c',str(src),'-o',str(obj)],label+'-compile')
        for kind,fixture in [('coupled','line_jacobian_branches.f90'),('shared','line_jacobian_shared_superlevel.f90')]:
            name=label+'-'+kind;exe=work/name
            run([args.compiler,'-fopenmp','-fcheck=all','-ffree-line-length-none','-I'+str(root/'mod'),
                 str(fixtures/fixture),str(obj),'-L'+str(root/'lib'),'-lsubs','-lmod',
                 '-L/opt/local/lib','-lopenblas','-o',str(exe)],name+'-link')
            run([str(exe)],name)
            results[name]=read_rows(work/(name+'-stdout.txt'))
    errors=[];groups={}
    for key,(value,heat,balance) in results['candidate-coupled'].items():
        q,mode,case,k,l,ix=key
        if q==4 and mode==3:continue  # Existing deliberate no-linearization approximation.
        expected,expected_heat=oracle(*key)
        if args.variant=='cooling' and k<=2:expected_heat*=2
        if args.variant=='mixed-new-line' and mode==3 and k>=3:
            # Continuum BA_UPDATE is stubbed; these depths contain only the
            # direct line heat derivative, while full SE radiation coupling remains.
            _,expected_heat=oracle(*key,radiation_response=False)
        def error(actual,wanted):return abs(actual/wanted-1) if wanted else abs(actual)
        err,he=error(value,expected),error(heat,expected_heat)
        passed=(math.isfinite(err) and math.isfinite(he) and err<1e-12 and he<1e-12 and balance==0)
        row={'key':key,'rate_error':err,'heat_error':he,'number_conservation_exact':balance==0,'passed':passed}
        errors.append(row);groups.setdefault(f'scenario{q}-mode{mode}',[]).append(row)
    skipped=[k for k in results['candidate-coupled'] if k[0]==4 and k[1]==3]
    shared=[k for k in results['candidate-shared'] if k[1]==3]
    skip_ok=all(results['candidate-coupled'][k]==results['baseline-coupled'][k] for k in skipped)
    shared_ok=all(results['candidate-shared'][k]==results['baseline-shared'][k] for k in shared)
    physical_reports={}
    if args.shared_check=='physical':
        for layout in ['shared','separate']:
            child=work/('shared-physical-'+layout)
            cmd=[sys.executable,str(Path(__file__).with_name('check_shared_line_jacobian.py')),
                 '--cmfgen-root',str(root),'--source',str(source),'--baseline-source',str(baseline),
                 '--compiler',args.compiler,'--pointer-layout',layout,'--work-dir',str(child)]
            commands.append(cmd)
            result=subprocess.run(cmd,cwd=work,env=env,capture_output=True,text=True)
            (work/('shared-physical-'+layout+'-stdout.txt')).write_text(result.stdout)
            (work/('shared-physical-'+layout+'-stderr.txt')).write_text(result.stderr)
            if not (child/'report.json').exists():
                raise RuntimeError(f'Shared native test failed to produce evidence; see {work}')
            physical_reports[layout]=json.loads((child/'report.json').read_text())
            assert physical_reports[layout]['source_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
            assert result.returncode==(0 if physical_reports[layout]['passed'] else 1)
    required_shared_ok=all(r['passed'] for r in physical_reports.values()) if args.shared_check=='physical' else shared_ok
    report={'variant':args.variant,'passed':all(r['passed'] for r in errors) and skip_ok and required_shared_ok,
        'shared_superlevel_requirement':args.shared_check,
        'shared_physical_checks':{layout:{k:r[k] for k in ['passed','oracle_entries','maximum_heat_error',
            'maximum_internal_line_equation_error','skipped_linearization_bitwise_identical']} for layout,r in physical_reports.items()},
        'oracle_entries':len(errors),'maximum_rate_error':max(r['rate_error'] for r in errors),
        'maximum_heat_error':max(r['heat_error'] for r in errors),
        'skipped_linearization_entries':len(skipped),'skipped_linearization_bitwise_identical':skip_ok,
        'shared_superlevel_strong_entries':len(shared),'shared_superlevel_strong_bitwise_identical':shared_ok,
        'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'baseline_source':str(baseline),'baseline_sha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),
        'fixture_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [fixtures/'line_jacobian_branches.f90',fixtures/'line_jacobian_shared_superlevel.f90']},
        'oracle':'350-digit central differences of original source-function rate; heat is original eta*ZNET derivative',
        'scope':'Mixed-new-line heat oracle excludes the deliberately stubbed continuum radiation response at new-method depths. Actual UPDATE_BA_FOR_LINE. Four depths / three bands. Prescribed radiation responses, line-only continuum/profiling stubs. Not full transport or model convergence. Shared-superlevel path and skipped linearization are compatibility checks, not correctness certification.',
        'groups':{g:{'entries':len(rr),'max_rate_error':max(r['rate_error'] for r in rr),'max_heat_error':max(r['heat_error'] for r in rr)} for g,rr in groups.items()},
        'commands':commands,'checks':errors}
    (work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['passed','oracle_entries','maximum_rate_error','maximum_heat_error','skipped_linearization_bitwise_identical','shared_superlevel_strong_bitwise_identical','shared_superlevel_requirement','shared_physical_checks']}))
    print(f'Evidence: {work / "report.json"}')
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
