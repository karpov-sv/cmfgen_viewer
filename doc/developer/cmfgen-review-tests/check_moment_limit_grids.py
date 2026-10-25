#!/usr/bin/env python3
"""Active J/H-limit regression on inserted grids and the production wrapper.

Reuses the native grid fixtures with a sharply changing source profile.
Formal-ray moments stay frozen; native interpolation, transport, variation and
DO_VAR_CONT projection are compiled. No model or installed source is edited.
"""
from pathlib import Path
import argparse,hashlib,itertools,json,os,shutil,subprocess,tempfile
import numpy as np
from check_moment_grid_jacobian import build, build_workflow, column_error, model_value

PROFILE_CODE=''' if(profile==10.and.k==1)eta(7)=eta(7)*1.e7_ldp
'''


def active_fixture(text,workflow=False):
    text=text.replace('only: jvar=>jnu,hvar=>rsq_hnu','only: jvar=>jnu,hvar=>rsq_hnu,raw_solution=>xm')
    text=text.replace('integer::ns,i,k,u,perturb','integer::ns,i,k,u,ipos,ineg,perturb')
    text=text.replace('real(ldp)::factor_view','real(ldp)::bound\ncharacter(16)::hcheck\nreal(ldp)::factor_view')
    anchor='outer=1;call get_command_argument(14,arg);if(len_trim(arg)>0)read(arg,*)outer'
    assert text.count(anchor)==1
    text=text.replace(anchor,anchor+"\nhcheck='MAX_VAL';call get_environment_variable('MOM_H_CHECK',arg);if(len_trim(arg)>0)hcheck=trim(arg)")
    # Perturb inputs after prescribing the stress profiles, as in the baseline.
    anchor=' if(.true.)then' if workflow else ' if(k==atfreq)then'
    assert text.count(anchor)==1;text=text.replace(anchor,PROFILE_CODE+anchor)
    text=text.replace(",ntype,'NONE',method",",ntype,trim(hcheck),method").replace(",nu,'NONE',outer",",nu,trim(hcheck),outer")
    # Ordinary coherent forcing uses the RAW matrix-solve intensity.
    text=text.replace('x=jvar(i)','x=raw_solution(i)')
    if workflow:
        # Adapter knobs must match the prescribed native forward calculation.
        text=text.replace("h_chk_option='NONE'", "call get_environment_variable('MOM_H_CHECK',arg)\nh_chk_option=trim(arg)")
        text=text.replace('integer n,nm,outer,i','integer n,nm,outer,i\ncharacter(64) arg')
    else:
        start=text.index('  if(k==1)then\n   tx(:,:,3)')
        end=text.index(' endif\nenddo',start)
        text=text[:start]+'''  if(k==atfreq.and.k<3)then
   if(perturb==1.or.perturb==2)then
    tx(:,:,3)=tx(:,:,perturb);tvx(:,:,3)=tvx(:,:,perturb)
    if(nfine>n)then
     grid_tx(:,:,3)=grid_tx(:,:,perturb);grid_tvx(:,:,3)=grid_tvx(:,:,perturb)
    endif
   else if(perturb==5)then
    tx(:,:,3)=esc_j;tvx(:,:,3)=esc_h
    if(nfine>n)then
     if(coherent)then
      grid_tx(:,:,3)=grid_tx(:,:,1)+grid_esc
      grid_tvx(:,:,3)=grid_tvx(:,:,1)+grid_esc_h
     else
      do i=1,n
       grid_tx(:,i,3)=grid_tx(:,i,1)+grid_tx(:,i,2)*external_j(i)
       grid_tvx(:,i,3)=grid_tvx(:,i,1)+grid_tvx(:,i,2)*external_j(i)
      enddo
     endif
    endif
   endif
  endif
'''+text[end:]
    # Emit branch counts from the reconstructed native field, before FD runs.
    anchor='  if(any(fine_saved'
    pos=text.index(anchor)
    metric='''  ipos=0;ineg=0
  do i=1,nfine-1
   if(trim(hcheck)=='AV_VAL')then
    bound=(jvar(i)*rf(i)**2+jvar(i+1)*rf(i+1)**2)/2
   else
    bound=max(jvar(i)*rf(i)**2,jvar(i+1)*rf(i+1)**2)
   endif
   if(trim(hcheck)/='NONE'.and.bound>0)then
    if(abs(hvar(i)/bound-.99999_ldp)<1.e-12_ldp)ipos=ipos+1
    if(abs(hvar(i)/bound+.99999_ldp)<1.e-12_ldp)ineg=ineg+1
   endif
  enddo
  if(k==1)open(unit=91,file='branches.txt',status='replace')
  write(91,*)k,count(raw_solution<0),ipos,ineg
  if(k==3)close(91)
'''
    return text[:pos]+metric+text[pos:]


def rebuild(native,workflow=False):
    work=native.work;p=work/'fixture.f90';p.write_text(active_fixture(p.read_text(),workflow))
    record_path=work/('workflow-build.json' if workflow else 'build.json')
    record=json.loads(record_path.read_text());cmd=record['commands'][-1]
    v=subprocess.run(cmd,cwd=work,capture_output=True,text=True)
    (work/'active-build.log').write_text(v.stdout+v.stderr)
    if v.returncode:raise RuntimeError(v.stderr)
    record['active_fixture_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    record['active_profiles']='Strong inner emissivity at first frequency (10)'
    record_path.write_text(json.dumps(record,indent=2)+'\n')


def value(config,kind,depth,k):
    x=model_value(config,kind,depth,k)
    if config['profile']==10 and k==1 and kind==2 and depth==7:x*=1e7
    return x


def check_kernel(native):
    checks=[];max_error=0;field_error=0;negative=0;capped=0;branches=[]
    for profile,hcheck,ntype,coh in itertools.product([10],['NONE','MAX_VAL','AV_VAL'],['N_ON_J','G_ONLY'],[0,1]):
        config=dict(profile=profile,ntype=ntype,coherent=coh,method='LOGMON',bc=3,fraction=.1,ns=13,node=0)
        native.env['MOM_H_CHECK']=hcheck
        nominal=native.run(**config)
        counts=np.loadtxt(native.work/'branches.txt',dtype=int)
        negative+=int(counts[:,1].sum());capped+=int(counts[:,2:].sum())
        branches.append(dict(config=config,hcheck=hcheck,counts=counts.tolist()))
        for row in nominal:
            field_error=max(field_error,column_error(row['j'],row['jvar']),column_error(row['h'],row['hvar']))
        assert field_error<1e-10,field_error
        # Frequency2 is the negative-J solve in the sharp-source case; its
        # corrected response must persist through frequency3.
        for kind,at in [(1,1),(2,1),(5,1),(1,2),(2,2),(5,2),(1,3),(2,3),(5,3)]:
            base=native.run(**config,perturb=kind,atfreq=at)
            for depth in range(1,8):
                step=2**-11
                hi=native.run(**config,perturb=kind,depth=depth,atfreq=at,delta=step,mode='field')[-1]
                lo=native.run(**config,perturb=kind,depth=depth,atfreq=at,delta=-step,mode='field')[-1]
                worst=0
                for obs,key in [('j','tx'),('h','tvx')]:
                    fd=(hi[obs]-lo[obs])/(2*step*value(config,kind,depth,at))
                    if at<3:an=base[-1][key][:,depth-1,2]
                    elif kind==5:an=base[-1]['esc_'+obs][:,depth-1]
                    else:an=base[-1][key][:,depth-1,kind-1]
                    worst=max(worst,column_error(fd,an))
                row=dict(config=config,hcheck=hcheck,kind=kind,atfreq=at,depth=depth,error=worst)
                checks.append(row);max_error=max(max_error,worst);assert worst<3e-5,row
        for kind,key,hkey in [(3,'dt','ht'),(4,'dg','hg')]:
            step=2**-11
            hi=native.run(**config,perturb=kind,delta=step,mode='field')[-1]
            lo=native.run(**config,perturb=kind,delta=-step,mode='field')[-1]
            worst=max(column_error((hi['j']-lo['j'])/(2*step),nominal[-1][key]),column_error((hi['h']-lo['h'])/(2*step),nominal[-1][hkey]))
            row=dict(config=config,hcheck=hcheck,boundary=kind,error=worst)
            checks.append(row);max_error=max(max_error,worst);assert worst<3e-5,row
    assert negative and capped,(negative,capped)
    return dict(passed=True,maximum_field_error=field_error,maximum_column_error=max_error,checks=checks,branches=branches,native_calls=native.calls)


def check_workflow(native):
    checks=[];maximum=0;field_error=0
    for profile,hcheck,coh in itertools.product([10],['NONE','MAX_VAL','AV_VAL'],[0,1]):
        config=dict(profile=profile,ntype='N_ON_J',coherent=coh,method='LOGMON',bc=3,fraction=.1,ns=13,node=0)
        native.env['MOM_H_CHECK']=hcheck
        base=native.run(**config)[-1]
        field_error=max(field_error,column_error(base['j'],base['jvar']),column_error(base['h'],base['hvar']))
        assert field_error<1e-10,field_error
        for kind,slot in [(1,3),(2,4),(5,5),(6,7),(7,8),(8,6)]:
            for depth in range(1,8):
                step=2**-12
                hi=native.run(**config,perturb=kind,depth=depth,delta=step,mode='field')[-1]
                lo=native.run(**config,perturb=kind,depth=depth,delta=-step,mode='field')[-1]
                filling=.4+.03*depth
                if kind==1:scale=(value(config,1,depth,3)-value(config,5,depth,3))/filling
                elif kind in [2,5]:scale=value(config,kind,depth,3)/filling
                else:scale=1.
                worst=max(column_error((hi[obs]-lo[obs])/(2*step*scale),base[key][:,depth-1,slot-1]) for obs,key in [('j','tx'),('h','tvx')])
                row=dict(config=config,hcheck=hcheck,kind=kind,depth=depth,error=worst)
                checks.append(row);maximum=max(maximum,worst);assert worst<3e-5,row
    return dict(passed=True,maximum_column_error=maximum,maximum_field_error=field_error,checks=checks,native_calls=native.calls)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cmfgen-root',type=Path,default=Path('~/CMFGEN2023/cur_cmf.25'))
    ap.add_argument('--source-root',type=Path);ap.add_argument('--work-dir',type=Path)
    ap.add_argument('--compiler',default=shutil.which('gfortran'))
    ap.add_argument('--optimization',choices=['O0','O2'],default='O0');ap.add_argument('--threads',type=int,default=1)
    a=ap.parse_args();base=a.cmfgen_root.expanduser().resolve();src=(a.source_root or base).expanduser().resolve()
    work=a.work_dir.resolve() if a.work_dir else Path(tempfile.mkdtemp(prefix='cmfgen-moment-limit-grids-'))
    work.mkdir(parents=True,exist_ok=True)
    native,_=build(src,base,work/'kernel',a.compiler,a.optimization,a.threads);rebuild(native)
    result=dict(kernel=check_kernel(native))
    workflow=build_workflow(src,base,work/'workflow',a.compiler,a.optimization,a.threads);rebuild(workflow,True)
    result['workflow']=check_workflow(workflow)
    (work/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({name:{k:v for k,v in entry.items() if k not in ['checks','branches']} for name,entry in result.items()},indent=2));print('Evidence:',work)

if __name__=='__main__':main()
