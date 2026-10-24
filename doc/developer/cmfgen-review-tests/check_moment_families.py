#!/usr/bin/env python3
"""Validate related native moment repairs in an isolated build directory.

Real forward/variation solvers, interpolation, history, and DO_VAR_CONT through
projection are executed. Formal-ray fields are frozen. Kernel time tests prescribe
old radiation; the separate cache test executes the real binary old-time reader
with only metadata discovery stubbed. No atmosphere-convergence claim is made.
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
import numpy as np

HERE=Path(__file__).resolve().parent
M=runpy.run_path(str(HERE/'check_moment_grid_jacobian.py'))
FIX=HERE/'fixtures'


def build(root, base, work, compiler, optimization, threads):
    native=M['build_workflow'](root,base,work,compiler,optimization,threads)
    record=json.loads((work/'workflow-build.json').read_text())
    link=record['commands'][-1]
    flags=record['commands'][0][:-4]
    def execute(cmd):
        p=subprocess.run(cmd,cwd=work,capture_output=True,text=True)
        with (work/'family-build.log').open('a') as f:f.write(p.stdout+p.stderr)
        record['commands'].append(cmd)
        if p.returncode:raise RuntimeError(p.stdout+p.stderr)
    old=(FIX/'moment_ddt_closure.f90.in').read_text()
    reader=old[old.index('! The previous-time reader'):]
    fixtures={'workflow':(FIX/'moment_family_driver.f90.in').read_text()+'\n'+(FIX/'moment_family_workflow.f90.in').read_text()+'\n'+reader,
              'rel':(FIX/'moment_rel_closure.f90.in').read_text(), 'ddt':old}
    for family,text in fixtures.items():
        path=work/(family+'-fixture.f90');path.write_text(text)
        cmd=[str(path) if v==str(work/'fixture.f90') else str(work/(family+'-test')) if v==str(work/'test') else v for v in link]
        execute(cmd)
        record[family+'_fixture_sha256']=hashlib.sha256(text.encode()).hexdigest()
    # Full production line-slot routine, including all neighboring storage.
    execute(flags+['-x','f95',str(FIX/'moment_slot_reuse.f90.in'),'-x','none',
                   str(work/'init_line_opac_var_v2.o'),str(work/'var_rad_mod.o'),str(work/'mom_j_cmf_v11.o'),
                   '-L'+str(base/'lib'),'-lsubs','-lmod','-o',str(work/'slots')])
    # Compile the actual cache reader; stub only file metadata discovery.
    path=M['source'](root,base,'plane','get_jh_at_prev_time_step.f')
    record['source_sha256'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    execute(flags+['-c',str(path),'-o',str(work/'time-reader.o')])
    execute(flags+['-x','f95',str(FIX/'moment_time_cache.f90.in'),'-x','none',str(work/'time-reader.o'),
                   '-L'+str(base/'lib'),'-lsubs','-lmod','-o',str(work/'cache')])
    execute(flags+['-finit-real=snan','-x','f95',str(FIX/'related_moment_bounds.f90.in'),'-x','none',
                   str(work/'get_moms_rel.o'),str(work/'mod_ray_mom_store.o'),
                   '-L'+str(base/'lib'),'-lsubs','-lmod','-o',str(work/'bounds')])
    for folder,name in [('subs','up_tx_tvx.f'),('plane','var_mom_jext_cmf_v3.f')]:
        path=M['source'](root,base,folder,name)
        record['source_sha256'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        execute(flags+['-c',str(path),'-o',str(work/(path.stem+'.o'))])
    execute(flags+['-finit-real=snan','-x','f95',str(FIX/'moment_private_history.f90.in'),'-x','none',
                   str(work/'up_tx_tvx.o'),str(work/'up_tx_tvx_v2.o'),
                   '-L'+str(base/'lib'),'-lsubs','-lmod','-o',str(work/'private-history')])
    record['fixture_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in FIX.glob('moment_*.f90.in')}
    record['fixture_sha256']['related_moment_bounds.f90.in']=hashlib.sha256((FIX/'related_moment_bounds.f90.in').read_bytes()).hexdigest()
    (work/'family-build.json').write_text(json.dumps(record,indent=2)+'\n')
    return native


def checks(work, threads):
    error=M['column_error'];records=[];calls=0
    def run_simple(name,*args):
        p=subprocess.run([str(work/name),*map(str,args)],cwd=work,env={**os.environ,'OMP_NUM_THREADS':str(threads)},capture_output=True,text=True)
        (work/(name+'-'+ '-'.join(map(str,args))+'.log')).write_text(p.stdout+p.stderr)
        assert p.returncode==0,p.stdout+p.stderr
    run_simple('slots');run_simple('cache');run_simple('private-history')
    for case in range(1,5):run_simple('bounds',case)
    for family in ['rel','ddt','workflow']:
        shutil.copyfile(work/(family+'-test'),work/'test')
        native=M['Native'](work,threads,8 if family=='workflow' else 3)
        if family=='workflow':
            cases=[(mode,dict(bc=bc,outer=outer,coherent=coh,method='LOGMON',profile=1,node=0,ns=13))
                   for mode in range(1,6) for coh in [0,1]
                   for bc,outer in ([(1,1),(2,2),(3,2),(4,1)] if mode in [1,4,5] else [(2,2),(3,2),(4,2)])]
            # Exercise no internal insertion and high relativistic velocity as well.
            cases += [(mode,dict(bc=3,outer=2,coherent=1,method='LOGMON',profile=2,fraction=20000)) for mode in range(1,6)]
            cases += [(2,dict(bc=3,outer=2,coherent=1,method='LOGMON',profile=4))]
        else:
            cases=[(0,dict(bc=bc,outer=outer,coherent=coh,method=meth,profile=profile,node=node,ntype=ntype,ns=ns,fraction=frac))
                   for bc,outer,coh,meth,profile,node,ntype,ns,frac in [
                       (3,2,1,'ZERO',0,1,'N_ON_J',7,.25),
                       (3,2,1,'LOGMON',1,0,'G_ONLY',13,.25),
                       (2,2,1,'ZERO',0,1,'N_ON_J',7,.25),
                       (4,2,1,'ZERO',0,1,'N_ON_J',7,.25),
                       (3,2,0,'ZERO',0,0,'N_ON_J',13,.25),
                       (3,1,1,'LOGMON',1,1,'N_ON_J',7,.25),
                       (3,2,1,'ZERO',0,1,'N_ON_J',7,20000),
                       *[(3,2,1,m,0,1,'N_ON_J',13,.25) for m in ['LINEAR','LINMON','LOGLIN','LOGLOG']],
                       *(([(3,2,1,'LOGMON',4,0,'N_ON_J',13,.25)]) if family=='rel' else [])]]
            if family=='ddt':cases += [(o,dict(bc=bc,outer=2,coherent=1,method='ZERO',profile=0)) for o,bc in [('HALF_MOM',3),('HALF_MOM',4),('HONJM',3)]]
        for tag,cfg in cases:
            native.env.pop('MOM_TEST_OUTER',None)
            if family=='workflow':native.env['MOM_TEST_FAMILY']=str(tag)
            elif isinstance(tag,str):native.env['MOM_TEST_OUTER']=tag
            nominal=native.run(**cfg)
            field=max(error(r[o],r[key]) for r in nominal for o,key in [('j','jvar'),('h','hvar')])
            assert field<1e-10,(family,tag,cfg,'field',field)
            assert all((r['j']>0).all() for r in nominal),(family,tag,cfg,'positive J required')
            variables=[(1,3),(2,4),(5,5),(6,7),(7,8),(8,6)] if family=='workflow' else [(1,1),(2,2),(5,0),(9,3)]
            for kind,slot in variables:
                actual=1 if kind==9 else kind;at=1 if kind==9 else 3;worst=0.
                for depth in range(1,8):
                    # Weak prior-frequency responses: Richardson steps reduce
                    # subtraction noise while canceling central truncation error.
                    # Peaked/high-velocity profiles need smaller steps to stay
                    # on the same interpolation-limiter branch (step sweeps
                    # checked separately; no acceptance-threshold relaxation).
                    step=(2**-12 if cfg.get('profile')==4 else 2**-10 if cfg.get('profile')==1 else 2**-8) if kind==9 else 2**-12
                    values=[]
                    for scale in ([1,.5] if kind==9 else [1]):
                        hi=native.run(**cfg,perturb=actual,depth=depth,atfreq=at,delta=step*scale,mode='field')[-1]
                        lo=native.run(**cfg,perturb=actual,depth=depth,atfreq=at,delta=-step*scale,mode='field')[-1]
                        if family=='workflow':
                            cf=.4+.03*depth
                            value=(M['model_value'](cfg,1,depth,3)-M['model_value'](cfg,5,depth,3))/cf if kind==1 else M['model_value'](cfg,kind,depth,3)/cf if kind in [2,5] else 1
                        else:value=M['model_value'](cfg,actual,depth,at)
                        values.append({o:(hi[o]-lo[o])/(2*step*scale*value) for o in ['j','h']})
                    for o,key in [('j','tx'),('h','tvx')]:
                        fd=(4*values[1][o]-values[0][o])/3 if kind==9 else values[0][o]
                        analytic=nominal[-1]['esc_'+o][:,depth-1] if family!='workflow' and kind==5 else nominal[-1][key][:,depth-1,slot-1]
                        worst=max(worst,error(fd,analytic))
                row=dict(family=family,tag=tag,config=cfg,variable=kind,field_error=field,maximum_column_relative_error=worst)
                records.append(row);assert worst<3e-5,row
            if cfg['bc']==3:
                for kind,jkey,hkey in [(3,'dt','ht'),(4,'dg','hg')]:
                    step=2**-12
                    hi=native.run(**cfg,perturb=kind,delta=step,mode='field')[-1];lo=native.run(**cfg,perturb=kind,delta=-step,mode='field')[-1]
                    worst=max(error((hi[o]-lo[o])/(2*step),nominal[-1][key]) for o,key in [('j',jkey),('h',hkey)])
                    row=dict(family=family,tag=tag,config=cfg,boundary_variable=kind,maximum_column_relative_error=worst)
                    records.append(row);assert worst<3e-5,row
            print(family,tag,cfg,'passed',flush=True)
        calls+=native.calls
    return dict(passed=True,threads=threads,native_invocations=calls,checks=records,
                maximum_column_relative_error=max(r['maximum_column_relative_error'] for r in records),
                maximum_field_relative_error=max(r.get('field_error',0) for r in records),
                scope=__doc__)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cmfgen-root',type=Path,default=Path('~/CMFGEN2023/cur_cmf'))
    p.add_argument('--source-root',type=Path)
    p.add_argument('--work-dir',type=Path)
    p.add_argument('--compiler',default=shutil.which('gfortran') or '/opt/local/bin/gfortran')
    p.add_argument('--optimization',choices=['O0','O2'],default='O0')
    p.add_argument('--threads',type=int,default=1)
    args=p.parse_args();base=args.cmfgen_root.expanduser().resolve();root=(args.source_root or base).expanduser().resolve()
    work=args.work_dir.resolve() if args.work_dir else Path(tempfile.mkdtemp(prefix='cmfgen-moment-family-'))
    work.mkdir(parents=True,exist_ok=True)
    build(root,base,work/'native',args.compiler,args.optimization,args.threads)
    report=checks(work/'native',args.threads)
    report['optimization']=args.optimization
    (work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='checks'},indent=2));print('Evidence:',work)

if __name__=='__main__':main()
