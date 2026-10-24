#!/usr/bin/env python3
"""Test actual shared-superlevel line heating against independent physical differences.

An internal transition cancels in its one superlevel population equation, but
still heats/cools the gas. Both levels depend on P=.8; the upper level ratio
ranges from 1e-4 down to 1e-128 and includes an inverted-opacity case. Actual
UPDATE_BA_FOR_LINE is compiled; continuum/profiling routines are stubbed.
"""
from pathlib import Path
from decimal import Decimal as D, localcontext
import argparse,hashlib,json,math,os,subprocess,tempfile
from check_line_jacobian_branches import read_rows


def heat(q,mode,case,k,l,ix,delta,separate=False):
    p=D('.8');temperature=D(1)
    if l==k:
        if ix==1:p+=delta
        if ix==5:temperature+=delta
    lr=D('1.2');ur=list(map(D,['1e-4','1e-20','1e-60','1e-128','10']))[case-1]
    if mode==3 and q>=3:
        lr+=D('.02')*(temperature-1);ur+=D('.03')*(temperature-1)
    chi=D('2.4e-12')*(lr-D('.4')*ur)*p;eta=D('3.7e-4')*ur*p
    znet=D(0)
    for weight,rad in zip(map(D,['.13','.27','.51']),map(D,['.76e-6','1.37e-6','2.11e-6'])):
        shape=rad/D('1e-6')*(1-D('.17')*(k-1));intensity=rad*(1-D('.17')*(k-1))
        if mode==3 and q>=2:
            slopes=list(map(D,['.7e7' if separate else '2e7','0','.014e7','.4e7','.09e7']))
            intensity+=shape*(D(1) if l==k else D('.1'))*slopes[ix-1]*delta
        znet+=weight*(1-intensity*chi/eta)
    return eta*znet


def oracle(*key,separate=False):
    with localcontext() as ctx:
        ctx.prec=350
        ix=key[-1];h=(D('.8') if ix==1 else D(1))/2**20
        return float((heat(*key,h,separate=separate)-heat(*key,-h,separate=separate))/(2*h))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cmfgen-root',type=Path,default=Path('~/CMFGEN2023/cur_cmf').expanduser())
    ap.add_argument('--source',type=Path)
    ap.add_argument('--baseline-source',type=Path)
    ap.add_argument('--compiler',default='gfortran')
    ap.add_argument('--work-dir',type=Path)
    ap.add_argument('--pointer-layout',choices=['shared','separate'],default='shared',
        help='Separate pointers represent native NEW_VST_METH=T while both map to the same population.')
    ap.add_argument('--cooling-reset',action='store_true',
        help='Use model-like SCL_LN=T/SCL_LN_FAC=.5, which resets the shared-level cooling multiplier to one.')
    args=ap.parse_args();root=args.cmfgen_root.expanduser().resolve()
    source=(args.source or root/'new_main/subs/update_ba_for_line.f').resolve()
    baseline=(args.baseline_source or root/'new_main/subs/update_ba_for_line.f').resolve()
    if args.work_dir:work=args.work_dir.resolve();work.mkdir(parents=True,exist_ok=False)
    else:work=Path(tempfile.mkdtemp(prefix='cmfgen-shared-line-'))
    fixture=work/'line_jacobian_shared_heat.f90'
    text=(Path(__file__).with_name('fixtures')/fixture.name).read_text()
    if args.pointer_layout=='separate':
        old='low_pointer=7;up_pointer=7;var_in_use_cnt=0;var_in_use_cnt(7)=2;var_lev_id=0;var_lev_id(7)=1'
        new='low_pointer=7;up_pointer=8;var_in_use_cnt=0;var_in_use_cnt(7:8)=1;var_lev_id=0;var_lev_id(7:8)=1'
        assert text.count(old)==1;text=text.replace(old,new)
    if args.cooling_reset:
        replacements={
            'use line_mod,only:end_res_zone':'use line_mod,only:fl_sim,end_res_zone',
            'include_dsldt,znet_var_limit':'include_dsldt,znet_var_limit,scl_line_ht_fac',
            'scl_line_cool_rates=.false.;scl_line_density_limit=1.e99_ldp':
                'scl_line_cool_rates=.true.;scl_line_density_limit=1.e30_ldp;scl_line_ht_fac=.5_ldp',
            'u_star_ratio=.7_ldp;l_star_ratio=1.2_ldp;ave_energy=1;pop_atom=1.e4_ldp':
                'allocate(fl_sim(1));fl_sim=2\n u_star_ratio=.7_ldp;l_star_ratio=1.2_ldp;ave_energy=1;pop_atom=1.e4_ldp'}
        for old,new in replacements.items():
            assert text.count(old)==1;text=text.replace(old,new)
    fixture.write_text(text)
    commands=[];results={};env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    for name,src in [('candidate',source),('baseline',baseline)]:
        obj=work/(name+'.o');exe=work/name
        cmds=[[args.compiler,'-fopenmp','-fcheck=bounds','-O','-ffixed-line-length-0',
               '-fd-lines-as-comments','-I'+str(root/'mod'),'-c',str(src),'-o',str(obj)],
              [args.compiler,'-fopenmp','-fcheck=all','-ffree-line-length-none','-I'+str(root/'mod'),
               str(fixture),str(obj),'-L'+str(root/'lib'),'-lsubs','-lmod',
               '-L/opt/local/lib','-lopenblas','-o',str(exe)],[str(exe)]]
        for i,cmd in enumerate(cmds):
            commands.append(cmd);result=subprocess.run(cmd,cwd=work,env=env,capture_output=True,text=True)
            (work/f'{name}-{i}-stdout.txt').write_text(result.stdout)
            (work/f'{name}-{i}-stderr.txt').write_text(result.stderr)
            if result.returncode:raise RuntimeError(f'Native command failed; see {work}/{name}-{i}-stderr.txt')
        results[name]=read_rows(work/f'{name}-2-stdout.txt')
    checks=[]
    for key,(internal,actual,balance) in results['candidate'].items():
        if key[0]==4 and key[1]==3:continue
        expected=oracle(*key,separate=args.pointer_layout=='separate');scale=abs(expected) if expected else 1e-300
        heat_error=abs(actual-expected)/scale
        # Convert the population-equation residual to heating units. The line
        # itself must cancel when both levels share the same superlevel.
        internal_error=abs(internal)*3.7e-4/1.234e8/scale
        balance_error=abs(balance)*3.7e-4/1.234e8/scale
        checks.append({'key':key,'actual_heat_derivative':actual,'oracle_heat_derivative':expected,
            'heat_relative_error':heat_error,'internal_line_equation_error':internal_error,
            'number_balance_error':balance_error,'passed':math.isfinite(heat_error) and
            heat_error<1e-12 and internal_error<1e-12 and balance_error<1e-12})
    skipped=[k for k in results['candidate'] if k[0]==4 and k[1]==3]
    identical=all(results['candidate'][k]==results['baseline'][k] for k in skipped)
    report={'passed':all(c['passed'] for c in checks) and identical,'oracle_entries':len(checks),
        'pointer_layout':args.pointer_layout,
        'model_cooling_reset':args.cooling_reset,
        'maximum_heat_error':max(c['heat_relative_error'] for c in checks),
        'maximum_internal_line_equation_error':max(c['internal_line_equation_error'] for c in checks),
        'skipped_linearization_entries':len(skipped),'skipped_linearization_bitwise_identical':identical,
        'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'baseline_source':str(baseline),'baseline_sha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),
        'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),
        'scope':'Actual line routine, shared population/full-level ratios, prescribed local/neighbor radiation responses, continuum/profiling stubs. 350-digit differences of original eta*ZNET. Ratio-temperature stress cases are algebraic tests, not bounds on physical thermal derivatives. No whole-model attribution or convergence claim.',
        'groups':{f'q{q}-mode{m}':{'checks':sum(c['key'][:2]==(q,m) for c in checks),
            'max_heat_error':max(c['heat_relative_error'] for c in checks if c['key'][:2]==(q,m))}
            for q in range(1,5) for m in range(1,4) if (q,m)!=(4,3)},
        'commands':commands,'checks':checks}
    (work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['passed','oracle_entries','maximum_heat_error',
        'maximum_internal_line_equation_error','skipped_linearization_bitwise_identical']}))
    print(f'Evidence: {work / "report.json"}')
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
