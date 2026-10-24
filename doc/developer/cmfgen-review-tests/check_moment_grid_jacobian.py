#!/usr/bin/env python3
"""Native regression for inserted moment grids and their model-grid Jacobian.

Compiles actual MOM, VAR, interpolation and rectangular update routines.
Only TUNE profiling is stubbed. Finite differences rerun the native refined
transport with frozen formal-ray moments. No installed/model files are edited.
"""
from pathlib import Path
import argparse,hashlib,itertools,json,os,shutil,subprocess,tempfile
import numpy as np


def source(root, base, folder, name):
    for p in [root/folder/name,root/name,base/folder/name]:
        if p.is_file():return p
    raise FileNotFoundError(name)


def build(root,base,work,compiler,optimization,threads):
    work.mkdir();(work/'mod').mkdir()
    flags=[compiler,'-fopenmp','-'+optimization,'-g','-fcheck=all','-ffpe-trap=invalid,zero,overflow',
           '-ffixed-line-length-0','-ffree-line-length-none','-fd-lines-as-comments',
           '-I'+str(work/'mod'),'-I'+str(base/'mod'),'-J'+str(work/'mod')]
    files=[('plane','mod_ray_mom_store.f'),('plane','mod_var_mom_j_cmf.f'),
           ('plane','get_moms_non_rel.f'),('plane','mom_j_cmf_v11.f'),
           ('subs','up_tx_tvx_v2.f'),('subs','edd_j_var_v6.f'),('plane','var_mom_j_cmf_v12.f')]
    commands=[];hashes={}
    for folder,name in files:
        p=source(root,base,folder,name);hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
        cmd=flags+['-c',str(p),'-o',str(work/(p.stem+'.o'))];commands.append(cmd)
        result=subprocess.run(cmd,cwd=work,capture_output=True,text=True)
        (work/'build.log').open('a').write(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError(result.stderr)
    fixed='SUBROUTINE VAR_MOM_J_GRID_V1' in source(root,base,'plane','var_mom_j_cmf_v12.f').read_text()
    fixture=Path(__file__).with_name('fixtures')/'moment_grid_closure.f90.in'
    (work/'fixture.f90').write_text(fixture.read_text())
    cmd=flags+['-cpp']+(['-DMOM_GRID_FIX'] if fixed else [])+[str(work/'fixture.f90')]
    cmd += [str(work/(Path(name).stem+'.o')) for _,name in files]
    cmd += ['-L'+str(base/'lib'),'-lsubs','-lmod','-o',str(work/'test')]
    commands.append(cmd);result=subprocess.run(cmd,cwd=work,capture_output=True,text=True)
    (work/'build.log').open('a').write(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(result.stderr)
    (work/'build.json').write_text(json.dumps({'commands':commands,'source_sha256':hashes,'fixed':fixed,
        'fixture_sha256':hashlib.sha256((work/'fixture.f90').read_bytes()).hexdigest()},indent=2)+'\n')
    return Native(work,threads),fixed


class Native:
    def __init__(self,work,threads,nm=3):self.work=work;self.nm=nm;self.calls=0;self.env={**os.environ,'OMP_NUM_THREADS':str(threads),'OPENBLAS_NUM_THREADS':'1'}
    def run(self,*,fraction=.25,ntype='N_ON_J',ns=7,node=1,bc=1,perturb=0,depth=1,atfreq=3,delta=0,mode='all',method='ZERO',profile=0,coherent=1,outer=1):
        args=[fraction,ntype,ns,node,bc,perturb,depth,atfreq,delta,mode,method,profile,coherent,outer]
        result=subprocess.run([str(self.work/'test'),*map(str,args)],cwd=self.work,env=self.env,capture_output=True,text=True)
        self.calls+=1
        if result.returncode:raise RuntimeError(str(args)+'\n'+result.stdout+result.stderr)
        rows=[]
        with (self.work/'output.bin').open('rb') as stream:
            while header:=stream.read(16):
                n,nf,ns,k=map(int,np.frombuffer(header,'<i4'));r={'n':n,'nf':nf,'frequency':k}
                shapes=[('j',(n,)),('h',(n-1,)),('angular',(n,6)),('fine',(nf,6)),('prevfine',(nf,3))]
                if mode!='field':shapes += [('jvar',(n,)),('hvar',(n-1,)),('tx',(n,n,self.nm)),('tvx',(n-1,n,self.nm)),('dt',(n,)),('dg',(n,)),('ht',(n-1,)),('hg',(n-1,)),('esc_j',(n,n)),('esc_h',(n-1,n))]
                for name,shape in shapes:
                    count=int(np.prod(shape));values=np.fromfile(stream,'<f8',count=count)
                    if len(values)!=count:raise RuntimeError('Truncated native fixture output')
                    r[name]=values.reshape(shape,order='F')
                    if not np.isfinite(r[name]).all():raise RuntimeError('Nonfinite '+name)
                rows.append(r)
        if len(rows)!=3:raise RuntimeError('Missing native frequency output: '+result.stdout+result.stderr)
        return rows


def column_error(fd,analytic):
    scale=max(float(np.max(np.abs(fd))),float(np.max(np.abs(analytic))),1e-25)
    return float(np.max(np.abs(fd-analytic))/scale)


def model_value(config,kind,depth,k):
    r=np.array([10,8.5,7,5.5,4,2.5,1.]);chi=.2+.05*r;eta=(.05+.01*r)*(1+.03*k);es=.03+.001*r
    if config.get('profile') in [2,3]:chi*=10
    if config.get('profile') in [1,3]:chi[2]*=2.3;eta[4]*=.12;es[3]*=1.6
    return {1:chi,2:eta,5:es}[kind][depth-1]


def check(candidate,baseline=None):
    forward=0;noinsert=0;variation_error=0.;records=[]
    # Cartesian structural coverage; expensive finite differences are sampled below.
    for ntype,node,bc,outer,coherent in itertools.product(['G_ONLY','N_ON_J'],[0,1],[1,2,3,4],[1,2],[0,1]):
        config=dict(ntype=ntype,node=node,bc=bc,outer=outer,coherent=coherent)
        new=candidate.run(**config)
        if baseline:
            old=baseline.run(**config)
            assert all(np.array_equal(a[key],b[key]) for a,b in zip(new,old) for key in ['j','h','fine','prevfine'])
            forward+=1
            a=candidate.run(**config,fraction=20000);b=baseline.run(**config,fraction=20000)
            assert all(np.array_equal(x[key],y[key]) for x,y in zip(a,b) for key in ['j','h'])
            noinsert+=1
        for row in new:
            variation_error=max(variation_error,column_error(row['j'],row['jvar']),column_error(row['h'],row['hvar']))
    assert variation_error<1e-10,variation_error
    configs=[dict(ntype='N_ON_J',ns=7,node=1,bc=1,outer=1,coherent=1,method='ZERO',profile=0),
             dict(ntype='G_ONLY',ns=13,node=0,bc=2,outer=2,coherent=1,method='LOGMON',profile=1),
             dict(ntype='N_ON_J',ns=61,node=0,bc=3,outer=1,coherent=1,method='LOGMON',profile=1,fraction=.02),
             dict(ntype='G_ONLY',ns=13,node=1,bc=4,outer=2,coherent=0,method='ZERO',profile=1),
             *[dict(ntype='N_ON_J',ns=13,node=0,bc=3,outer=2,coherent=1,method=method,profile=1)
               for method in ['LINMON','LINEAR','LOGLIN','LOGLOG']],
             *[dict(ntype=ntype,ns=7,node=1,bc=bc,outer=outer,coherent=1,method=method,profile=profile,fraction=20000)
               for ntype,bc,outer,method,profile in [('N_ON_J',3,1,'LOGMON',1),('G_ONLY',2,1,'ZERO',1),('G_ONLY',3,2,'ZERO',2),('N_ON_J',3,2,'LOGMON',2)]]]
    maximum=0.;h=2**-12
    for config in configs:
        nominal=candidate.run(**config)
        for kind,at in [(1,3),(2,3),(1,1),(5,3)]:
            worst=0.
            for depth in range(1,8):
                # On opaque coarse grids the two-frequency-old response is very
                # small. Richardson differences resolve it above floating-point
                # subtraction noise without weakening the comparison threshold.
                step=2**-8 if at==1 and config.get('fraction')==20000 else h
                hi=candidate.run(**config,perturb=kind,depth=depth,atfreq=at,delta=step,mode='field')[-1]
                lo=candidate.run(**config,perturb=kind,depth=depth,atfreq=at,delta=-step,mode='field')[-1]
                if step!=h:
                    hi2=candidate.run(**config,perturb=kind,depth=depth,atfreq=at,delta=step/2,mode='field')[-1]
                    lo2=candidate.run(**config,perturb=kind,depth=depth,atfreq=at,delta=-step/2,mode='field')[-1]
                value=model_value(config,kind,depth,at)
                for observable,key in [('j','tx'),('h','tvx')]:
                    fd=(hi[observable]-lo[observable])/(2*step*value)
                    if step!=h:fd=(4*(hi2[observable]-lo2[observable])/(step*value)-fd)/3
                    if kind==5:an=nominal[-1]['esc_'+observable][:,depth-1]
                    else:an=nominal[-1][key][:,depth-1,2 if at==1 else kind-1]
                    worst=max(worst,column_error(fd,an))
            records.append({'config':config,'variable':kind,'input_frequency':at,'maximum_column_relative_error':worst})
            maximum=max(maximum,worst)
            assert worst<3e-5,records[-1]
        if config['bc']==3:
            for kind,key,hkey in [(3,'dt','ht'),(4,'dg','hg')]:
                hi=candidate.run(**config,perturb=kind,delta=h,mode='field')[-1]
                lo=candidate.run(**config,perturb=kind,delta=-h,mode='field')[-1]
                worst=max(column_error((hi['j']-lo['j'])/(2*h),nominal[-1][key]),column_error((hi['h']-lo['h'])/(2*h),nominal[-1][hkey]))
                records.append({'config':config,'boundary_variable':kind,'maximum_column_relative_error':worst});maximum=max(maximum,worst);assert worst<3e-5,records[-1]
    # Same-frequency radiation subiterations, changed refinement and slot reuse.
    for mode in ['repeat','rebuild','clear']:
        data=candidate.run(mode=mode,bc=3)
        assert all(column_error(x['j'],x['jvar'])<1e-10 for x in data)
    return {'passed':True,'forward_transport_bitwise_cases':forward,'no_insertion_forward_bitwise_cases':noinsert,
            'maximum_refined_variation_field_relative_error':variation_error,
            'maximum_finite_difference_column_relative_error':maximum,'finite_difference_checks':records,
            'native_invocations':candidate.calls,'scope':'Frozen formal-ray moments; actual native refined transport and interpolation. Includes current opacity/emissivity/scattering, prior-frequency history, diffusion boundary derivatives, both midpoint storage modes and outer boundary types. No scientific model convergence claim.'}



def workflow_fixture():
    """Reuse forward transport; perturb a parameter consistently at all frequencies."""
    fixture_dir = Path(__file__).with_name('fixtures')
    text = (fixture_dir/'moment_grid_closure.f90.in').read_text()
    text = text.replace('n=7,nm=3', 'n=7,nm=8')
    text = text.replace('if(k==atfreq)then', 'if(.true.)then')
    text = text.replace('chi(depth)=chi(depth)*(1+delta)',
                        'chi(depth)=chi(depth)+(chi(depth)-es(depth))*delta')
    text = text.replace('if(.not.coherent)eta=eta+es*external_j', """
 if(perturb==6)chi(depth)=chi(depth)+(.4_ldp+.03_ldp*depth)*.06_ldp*delta
 if(perturb==7)then
  chi(depth)=chi(depth)-(.4_ldp+.03_ldp*depth)*.03_ldp*delta
  eta(depth)=eta(depth)+(.4_ldp+.03_ldp*depth)*.04_ldp*delta
 endif
 if(perturb==8)then
  chi(depth)=chi(depth)+(.4_ldp+.03_ldp*depth)*.0003_ldp*delta
  eta(depth)=eta(depth)+(.4_ldp+.03_ldp*depth)*.0012_ldp*delta
 endif
 if(.not.coherent)eta=eta+es*external_j""")
    start = text.index(' if(.not.field_only)then')
    end = text.index('  if(any(fine_saved', start)
    text = text[:start]+""" if(.not.field_only)then
 call workflow_adapter(chi,eta,es,r,v,sigma,j,external_j,nu,dbb,init,coherent,inner,method,outer,n,nm,tx,tvx,dt,dg,ht,hg)
"""+text[end:]
    start = text.index(' write(u)n,nfine')
    end = text.index('close(u)', start)
    text = text[:start]+""" write(u)n,nfine,ns,k
 write(u)j,h(1:n-1),factor_view,fine_saved,prev_saved
 if(.not.field_only)then
  esc_j=tx(:,:,5);esc_h=tvx(:,:,5)
  write(u)jvar(j_indx(:)),hvar(h_indx(1:n-1)),tx,tvx,dt,dg,ht,hg,esc_j,esc_h
 endif
enddo
"""+text[end:]
    return text+'\n'+(fixture_dir/'moment_grid_workflow.f90.in').read_text()


def build_workflow(root, base, work, compiler, optimization, threads):
    """Compile production DO_VAR_CONT through projection, before atomic-rate assembly.

    This explicit truncation avoids requiring a whole atomic model in a unit fixture.
    None of the transport, clumping, frequency, line or temperature transforms are
    replaced. The complete production routine is compiled separately as well.
    """
    native, fixed = build(root, base, work, compiler, optimization, threads)
    assert fixed
    native.nm = 8
    record = json.loads((work/'build.json').read_text())
    flags = record['commands'][0][:-4]
    objects = [Path(cmd[-1]) for cmd in record['commands'][:-1]]
    for folder,name in [('plane','mod_var_jrel_v2.f'),('plane','get_moms_rel.f'),('plane','mom_jrel_v9.f'),('plane','edd_jrel_var_v3.f'),('plane','var_jrel_v5.f'),('plane','mom_j_ddt_v6.f'),('plane','edd_j_hub_var_v3.f'),('plane','var_mom_j_ddt_v6.f'),
                        *[('new_main/mod_subs',n) for n in ['var_rad_mod.f','do_var_cont.f','init_line_opac_var_v2.f']]]:
        path = source(root, base, folder, name)
        record['source_sha256'][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        cmd = flags+['-c', str(path), '-o', str(work/(path.stem+'.o'))]
        subprocess.run(cmd, cwd=work, check=True, capture_output=True)
        record['commands'].append(cmd)
        if folder=='plane' or name == 'var_rad_mod.f':
            objects.append(work/(path.stem+'.o'))
        elif name == 'do_var_cont.f':
            code = path.read_text()
            end = code.index('\t  ELSE IF(EDDINGTON)THEN') if '\t  ELSE IF(CONT_VEL)THEN' in code else code.index('\t  ELSE IF(CONT_VEL .AND. ACCURATE)THEN')
            prefix = work/'do_var_cont_prefix.f'
            prefix.write_text(code[:end]+'\t  END IF\n\t  RETURN\n\t  END\n')
            cmd = flags+['-c', str(prefix), '-o', str(work/'do_var_cont_prefix.o')]
            subprocess.run(cmd, cwd=work, check=True, capture_output=True)
            record['commands'].append(cmd)
            objects.append(work/'do_var_cont_prefix.o')
    (work/'fixture.f90').write_text(workflow_fixture())
    cmd = flags+['-cpp', '-DMOM_GRID_FIX', str(work/'fixture.f90'), *map(str, objects),
                 '-L'+str(base/'lib'), '-lsubs', '-lmod', '-o', str(work/'test')]
    subprocess.run(cmd, cwd=work, check=True, capture_output=True)
    record['commands'].append(cmd)
    record['workflow_fixture_sha256'] = hashlib.sha256((work/'fixture.f90').read_bytes()).hexdigest()
    record['instrumentation'] = 'DO_VAR_CONT truncated after projection; subsequent atomic-rate assembly excluded'
    (work/'workflow-build.json').write_text(json.dumps(record, indent=2)+'\n')
    return native


def check_workflow(native):
    records = []
    for coherent in [0, 1]:
        for bc, outer in [(1, 1), (2, 2), (3, 2), (4, 1)]:
            config = dict(ntype='N_ON_J', ns=13, node=0, bc=bc, outer=outer,
                          coherent=coherent, method='LOGMON', profile=1)
            nominal = native.run(**config)[-1]
            # Continuum opacity/emissivity, electron scattering, two line levels,
            # and super-level temperature response; nonuniform volume filling factors.
            for kind, slot in [(1, 3), (2, 4), (5, 5), (6, 7), (7, 8), (8, 6)]:
                worst = 0.
                for depth in range(1, 8):
                    step = 2**-13
                    hi = native.run(**config, perturb=kind, depth=depth, delta=step, mode='field')[-1]
                    lo = native.run(**config, perturb=kind, depth=depth, delta=-step, mode='field')[-1]
                    filling = .4+.03*depth
                    if kind == 1:
                        value = (model_value(config, 1, depth, 3)-model_value(config, 5, depth, 3))/filling
                    elif kind in [2, 5]:
                        value = model_value(config, kind, depth, 3)/filling
                    else:
                        value = 1.
                    for observable, key in [('j', 'tx'), ('h', 'tvx')]:
                        fd = (hi[observable]-lo[observable])/(2*step*value)
                        worst = max(worst, column_error(fd, nominal[key][:, depth-1, slot-1]))
                records.append(dict(config=config, variable=kind, maximum_column_relative_error=worst))
                assert worst < 3e-5, records[-1]
    return dict(passed=True, maximum_finite_difference_column_relative_error=max(
        row['maximum_column_relative_error'] for row in records),
        finite_difference_checks=records, native_invocations=native.calls,
        scope='Actual DO_VAR_CONT prefix; three-frequency continuum, scattering, line-level and super-level temperature responses with nonuniform clumping. Atomic-rate assembly excluded.')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cmfgen-root',type=Path,default=Path('~/CMFGEN2023/cur_cmf'))
    ap.add_argument('--source-root',type=Path)
    ap.add_argument('--baseline-root',type=Path)
    ap.add_argument('--compiler',default=shutil.which('gfortran') or '/opt/local/bin/gfortran')
    ap.add_argument('--optimization',choices=['O0','O2'],default='O0')
    ap.add_argument('--threads',type=int,default=1)
    ap.add_argument('--work-dir',type=Path)
    args=ap.parse_args();base=args.cmfgen_root.expanduser().resolve();src=(args.source_root or base).expanduser().resolve()
    work=args.work_dir.resolve() if args.work_dir else Path(tempfile.mkdtemp(prefix='cmfgen-moment-grid-'))
    work.mkdir(parents=True,exist_ok=True)
    candidate,fixed=build(src,base,work/'candidate',args.compiler,args.optimization,args.threads)
    if not fixed:raise RuntimeError('Source has no refined-grid variation repair; use a patched --source-root')
    baseline=None
    if args.baseline_root:baseline,_=build(args.baseline_root.expanduser().resolve(),base,work/'baseline',args.compiler,args.optimization,args.threads)
    result=check(candidate,baseline)
    workflow=build_workflow(src,base,work/'workflow',args.compiler,args.optimization,args.threads)
    result['workflow']=check_workflow(workflow)
    (work/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    summary={k:v for k,v in result.items() if k not in {'finite_difference_checks','workflow'}}
    summary['workflow']={k:v for k,v in result['workflow'].items() if k!='finite_difference_checks'}
    print(json.dumps(summary,indent=2));print('Evidence:',work)


if __name__=='__main__':main()
