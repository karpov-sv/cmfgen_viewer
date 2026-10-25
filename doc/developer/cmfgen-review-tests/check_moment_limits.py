#!/usr/bin/env python3
"""Check active ordinary moment limits against native forward finite differences.

Replay actual Bstar3010 coefficients with frozen recorded angular factors;
rerun native MOM and VAR for current/prior-frequency opacity, emissivity,
scattering and diffusion changes. A separate synthetic refined-grid suite
exercises native angular-factor interpolation and the production wrapper.
"""
from pathlib import Path
import argparse,hashlib,itertools,json,os,shutil,subprocess,tempfile
import numpy as np
from check_moment_grid_jacobian import column_error, source


def build(src,base,work,compiler,optimization,assembly=False):
    work.mkdir(parents=True);(work/'mod').mkdir()
    flags=[compiler,'-fopenmp','-'+optimization,'-g','-fcheck=all','-ffpe-trap=invalid,zero,overflow',
           '-ffixed-line-length-0','-ffree-line-length-none','-fd-lines-as-comments',
           '-I'+str(work/'mod'),'-I'+str(base/'mod'),'-J'+str(work/'mod')]
    files=[('plane','mod_ray_mom_store.f'),('plane','mod_var_mom_j_cmf.f'),
           ('plane','mom_j_cmf_v11.f'),('plane','var_mom_j_cmf_v12.f')]
    commands=[];hashes={}
    for folder,name in files:
        p=source(src,base,folder,name);hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
        cmd=flags+['-c',str(p),'-o',str(work/(p.stem+'.o'))];commands.append(cmd)
        result=subprocess.run(cmd,cwd=work,capture_output=True,text=True)
        (work/'build.log').open('a').write(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError(result.stderr)
    fixture=Path(__file__).with_name('fixtures')/'moment_limit_replay.f90.in'
    text=fixture.read_text()
    extra=[]
    if assembly:
        text=text.replace('selected(3)','selected(5)').replace('tx(n,n,3),tvx(n-1,n,3)','tx(n,n,5),tvx(n-1,n,5)')
        text=text.replace('selected,method,n,3,2)','selected,method,n,5,2)')
        text=text.replace('  nnegative=count(raw_j<0)', '  if(k==3)call production_es_assembly(tx,tvx,j,jused_record/(r*r),coherent,n)\n  nnegative=count(raw_j<0)')
        production=source(src,base,'new_main/mod_subs','do_var_cont.f').read_text()
        start=production.index('! We use TB as a temporary vector for J')
        start=production.index('\t    IF(COHERENT_ES)THEN',start)
        end=production.index('! Update line variation matrices.',start)
        use=next(x for x in production.splitlines() if 'USE MOD_VAR_MOM_J_CMF,' in x)
        code='''        SUBROUTINE PRODUCTION_ES_ASSEMBLY(TXW,TVXW,RJ,RJ_ES,COHERENT_ES,ND)
        USE SET_KIND_MODULE
'''+use+'''
        IMPLICIT NONE
        INTEGER ND,NROW,J,K
        REAL(KIND=LDP) TXW(ND,ND,5),TVXW(ND-1,ND,5),RJ(ND),RJ_ES(ND),TB(ND)
        REAL(KIND=LDP) GRID_ESC(ND,ND),GRID_ESC_H(ND-1,ND)
        LOGICAL COHERENT_ES,GRID_ACTIVE,ACCURATE,USE_J_REL,USE_DJDT_RTE,ORDINARY_MOM_VAR
        NROW=ND; GRID_ACTIVE=.FALSE.; ACCURATE=.FALSE.
        USE_J_REL=.FALSE.; USE_DJDT_RTE=.FALSE.; ORDINARY_MOM_VAR=.TRUE.
'''+production[start:end]+'''        END
'''
        p=work/'production_es_assembly.f';p.write_text(code)
        cmd=flags+['-c',str(p),'-o',str(work/'production_es_assembly.o')]
        commands.append(cmd);v=subprocess.run(cmd,cwd=work,capture_output=True,text=True)
        if v.returncode:raise RuntimeError(v.stderr)
        extra=[str(work/'production_es_assembly.o')]
        hashes[str(source(src,base,'new_main/mod_subs','do_var_cont.f'))]=hashlib.sha256(production.encode()).hexdigest()
    (work/'fixture.f90').write_text(text)
    cmd=flags+[str(work/'fixture.f90'),*extra,*[str(work/(Path(name).stem+'.o')) for _,name in files],
               '-L'+str(base/'lib'),'-lsubs','-lmod','-o',str(work/'test')]
    commands.append(cmd);result=subprocess.run(cmd,cwd=work,capture_output=True,text=True)
    (work/'build.log').open('a').write(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(result.stderr)
    (work/'build.json').write_text(json.dumps(dict(commands=commands,source_sha256=hashes,
        fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest()),indent=2)+'\n')


class Replay:
    def __init__(self,work,threads,nm=3):
        self.work=work;self.calls=0;self.nm=nm
        self.env={**os.environ,'OMP_NUM_THREADS':str(threads),'OPENBLAS_NUM_THREADS':'1'}
    def run(self,record,kind=2,depth=33,atfreq=3,delta=0,hcheck='MAX_VAL',coherent=1,field=False,history_sign=1):
        args=[record,kind,depth,atfreq,delta,hcheck,'field' if field else 'all',coherent,history_sign]
        p=subprocess.run([str(self.work/'test'),*map(str,args)],cwd=self.work,env=self.env,capture_output=True,text=True)
        self.calls+=1
        if p.returncode:raise RuntimeError(str(args)+'\n'+p.stdout+p.stderr)
        rows=[]
        with (self.work/'output.bin').open('rb') as f:
            while header:=f.read(20):
                n,k,neg,poscap,negcap=map(int,np.frombuffer(header,'<i4'))
                row=dict(n=n,frequency=k,negative_j=neg,positive_h_caps=poscap,negative_h_caps=negcap)
                shapes=[('j',(n,)),('h',(n-1,))]
                if not field:shapes += [('jvar',(n,)),('hvar',(n-1,)),('tx',(n,n,self.nm)),('tvx',(n-1,n,self.nm)),('dt',(n,)),('dg',(n,)),('ht',(n-1,)),('hg',(n-1,)),('raw_j',(n,))]
                for key,shape in shapes:
                    a=np.fromfile(f,'<f8',int(np.prod(shape)))
                    row[key]=a.reshape(shape,order='F')
                    if not np.isfinite(a).all():raise RuntimeError('Nonfinite '+key)
                rows.append(row)
        if len(rows)!=3:raise RuntimeError('Expected three native frequency steps')
        return rows


def run_checks(native,records):
    checks=[];maximum=0;field_error=0;branches={};step=2**-13
    for record in records:
        import struct
        with record.open('rb') as f:
            header=f.read(112);n=struct.unpack_from('<i',header)[0]
            data=np.fromfile(f,'<f8',21*n).reshape(21,n)
        for hcheck in ['NONE','MAX_VAL','AV_VAL']:
            for coherent,history_sign in itertools.product([0,1],[1,-1]):
                config=dict(record=record,hcheck=hcheck,coherent=coherent,history_sign=history_sign)
                base=native.run(**config)
                branches[f'{record.parent.name}/{hcheck}/{coherent}/{history_sign}']=[{key:row[key] for key in ['negative_j','positive_h_caps','negative_h_caps']} for row in base]
                for row in base:
                    field_error=max(field_error,column_error(row['j'],row['jvar']),column_error(row['h'],row['hvar']))
                assert field_error<1e-10,field_error
                if coherent and hcheck=='MAX_VAL' and history_sign==1:
                    assert np.allclose(base[0]['j'],data[20]/data[0]**2,rtol=1e-10,atol=0)
                for kind,atfreq in [(1,3),(2,3),(5,3),(1,1),(2,1),(5,1)]:
                    # Include the affected layers and positive remote controls.
                    for depth in [29,31,32,33,34,35,40]:
                        nominal=native.run(**config,kind=kind,atfreq=atfreq)
                        local_step=2**-8 if atfreq==1 and kind==5 else step
                        hi=native.run(**config,kind=kind,depth=depth,atfreq=atfreq,delta=local_step,field=True)[-1]
                        lo=native.run(**config,kind=kind,depth=depth,atfreq=atfreq,delta=-local_step,field=True)[-1]
                        if local_step!=step:
                            hi2=native.run(**config,kind=kind,depth=depth,atfreq=atfreq,delta=local_step/2,field=True)[-1]
                            lo2=native.run(**config,kind=kind,depth=depth,atfreq=atfreq,delta=-local_step/2,field=True)[-1]
                        value={1:data[4],2:data[3],5:data[5]}[kind][depth-1]
                        worst=0.
                        for observable,key in [('j','tx'),('h','tvx')]:
                            fd=(hi[observable]-lo[observable])/(2*local_step*value)
                            if local_step!=step:fd=(4*(hi2[observable]-lo2[observable])/(local_step*value)-fd)/3
                            if atfreq==1:an=nominal[-1][key][:,depth-1,2]
                            elif kind==5:
                                x=nominal[-1]['raw_j'][depth-1] if coherent else data[20,depth-1]/data[0,depth-1]**2
                                an=nominal[-1][key][:,depth-1,0]+nominal[-1][key][:,depth-1,1]*x
                            else:an=nominal[-1][key][:,depth-1,kind-1]
                            worst=max(worst,column_error(fd,an))
                        check=dict(record=str(record),hcheck=hcheck,coherent=coherent,kind=kind,frequency=atfreq,depth=depth,error=worst)
                        checks.append(check);maximum=max(maximum,worst)
                        assert worst<3e-5,check
                for kind,key,hkey in [(3,'dt','ht'),(4,'dg','hg')]:
                    hi=native.run(**config,kind=kind,delta=step,field=True)[-1]
                    lo=native.run(**config,kind=kind,delta=-step,field=True)[-1]
                    worst=max(column_error((hi['j']-lo['j'])/(2*step),base[-1][key]),column_error((hi['h']-lo['h'])/(2*step),base[-1][hkey]))
                    check=dict(record=str(record),hcheck=hcheck,coherent=coherent,boundary_variable=kind,error=worst)
                    checks.append(check);maximum=max(maximum,worst);assert worst<3e-5,check
    assert any(x['negative_j'] for rows in branches.values() for x in rows),'No negative-J branch exercised'
    assert any(x['positive_h_caps'] for rows in branches.values() for x in rows),'No positive H cap exercised'
    assert any(x['negative_h_caps'] for rows in branches.values() for x in rows),'No negative H cap exercised'
    return dict(passed=True,maximum_field_error=field_error,maximum_column_error=maximum,checks=checks,branches=branches,native_calls=native.calls)


def check_assembly(native,records):
    checks=[];maximum=0;step=2**-13
    for record,hcheck,coherent,history_sign in itertools.product(records,['NONE','MAX_VAL','AV_VAL'],[0,1],[1,-1]):
        config=dict(record=record,hcheck=hcheck,coherent=coherent,history_sign=history_sign,kind=5,atfreq=3)
        with record.open('rb') as f:
            n=int(np.frombuffer(f.read(4),'<i4')[0]);f.seek(112)
            data=np.fromfile(f,'<f8',21*n).reshape(21,n)
        nominal=native.run(**config)[-1]
        for depth in [29,31,32,33,34,35,40]:
            hi=native.run(**config,depth=depth,delta=step,field=True)[-1]
            lo=native.run(**config,depth=depth,delta=-step,field=True)[-1]
            worst=max(column_error((hi[obs]-lo[obs])/(2*step*data[5,depth-1]),nominal[key][:,depth-1,4]) for obs,key in [('j','tx'),('h','tvx')])
            row=dict(record=str(record),hcheck=hcheck,coherent=coherent,history_sign=history_sign,depth=depth,error=worst)
            checks.append(row);maximum=max(maximum,worst);assert worst<3e-5,row
    return dict(passed=True,maximum_column_error=maximum,checks=checks,native_calls=native.calls,
                scope='Actual DO_VAR_CONT coherent-scattering/current-continuum assembly block; ordinary grid, native recorded clipping cases. Other wrapper operations tested separately.')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cmfgen-root',type=Path,default=Path('~/CMFGEN2023/cur_cmf.25'))
    ap.add_argument('--source-root',type=Path);ap.add_argument('--work-dir',type=Path)
    ap.add_argument('--compiler',default=shutil.which('gfortran'))
    ap.add_argument('--optimization',choices=['O0','O2'],default='O0');ap.add_argument('--threads',type=int,default=1)
    a=ap.parse_args();base=a.cmfgen_root.expanduser().resolve();src=(a.source_root or base).expanduser().resolve()
    work=a.work_dir.resolve() if a.work_dir else Path(tempfile.mkdtemp(prefix='cmfgen-moment-limits-'))
    work.mkdir(parents=True,exist_ok=True)
    build(src,base,work/'native',a.compiler,a.optimization)
    record_root=Path(__file__).resolve().parents[1]/'data/bstar3010-negative-j-20261025'
    records=[record_root/'B3010_RADIATION.bin',record_root/'h-clamp/B3010_RADIATION.bin']
    result=run_checks(Replay(work/'native',a.threads),records)
    build(src,base,work/'assembly',a.compiler,a.optimization,assembly=True)
    result['assembly']=check_assembly(Replay(work/'assembly',a.threads,nm=5),records)
    (work/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['checks','branches','assembly']},indent=2));print('Assembly maximum error:',result['assembly']['maximum_column_error']);print('Evidence:',work)

if __name__=='__main__':main()
