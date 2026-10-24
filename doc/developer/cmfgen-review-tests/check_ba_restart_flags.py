"""Native BA producer/reader regression, without running or editing a model.

Use --reader-source and --caller-source for isolated proposed source copies.
The configured CMFGEN module files and libraries must already be built.
"""
from pathlib import Path
import argparse,json,os,re,shutil,subprocess,tempfile
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--cmfgen-root',type=Path,default=Path('~/CMFGEN2023/cur_cmf'))
parser.add_argument('--reader-source',type=Path)
parser.add_argument('--caller-source',type=Path)
parser.add_argument('--compiler',default=shutil.which('gfortran') or '/opt/local/bin/gfortran')
parser.add_argument('--work-dir',type=Path)
args=parser.parse_args();root=args.cmfgen_root.expanduser().resolve()
reader=(args.reader_source or root/'new_main/subs/read_ba_data_v3.f').resolve()
caller=(args.caller_source or root/'new_main/cmfgen_sub.f').resolve()
if args.work_dir:
 work=args.work_dir.resolve();work.mkdir(parents=True,exist_ok=False)
else:work=Path(tempfile.mkdtemp(prefix='cmfgen-ba-restart-'))

DRIVER = r"""
program test_ba_restart
use set_kind_module
use steq_data_mod
implicit none
integer::i,j,u,badflags
logical::saved_fixed,saved_compute,fixed,compute,ok
logical::missing_mutates,dim_mutates,truncated_accepted,truncated_mutates,bypass_ok
allocate(SE(1)%BA(2,2,3,3),BA_ED(2,3,3),BA_T(2,3,3),BA_T_EHB(2,3,3))
badflags=0
do i=0,1
do j=0,1
saved_fixed=i==1;saved_compute=j==1
call fill_values()
call store_ba_data_v3(51,1,3,3,saved_compute,saved_fixed,'CACHE')
SE(1)%BA=-7;BA_ED=-7;BA_T=-7;BA_T_EHB=-7
fixed=.not.saved_fixed;compute=.false.
call read_ba_data_v3(51,1,3,3,compute,fixed,ok,'CACHE')
if(.not.ok)error stop 'valid writer output rejected'
if(compute)error stop 'reader changed requested compute flag'
if(any(SE(1)%BA/=1.25_LDP).or.any(BA_ED/=2.5_LDP).or.any(BA_T/=3.75_LDP).or.any(BA_T_EHB/=5._LDP))error stop 'matrix round trip changed values'
if(fixed.neqv.saved_fixed)badflags=badflags+1
enddo
enddo
saved_fixed=.true.;saved_compute=.true.
call fill_values();call store_ba_data_v3(51,1,3,3,saved_compute,saved_fixed,'CACHE')
open(newunit=u,file='CACHE',status='old');close(u,status='delete')
fixed=.false.;compute=.false.;call read_ba_data_v3(51,1,3,3,compute,fixed,ok,'CACHE')
if(ok)error stop 'missing binary accepted'
missing_mutates=fixed
call fill_values();call store_ba_data_v3(51,1,3,3,saved_compute,saved_fixed,'CACHE')
fixed=.false.;compute=.false.;call read_ba_data_v3(51,1,3,4,compute,fixed,ok,'CACHE')
if(ok)error stop 'wrong dimensions accepted'
dim_mutates=fixed
! Recreate a native sequential-unformatted cache missing only its final record.
call fill_values();call store_ba_data_v3(51,1,3,3,saved_compute,saved_fixed,'CACHE')
open(newunit=u,file='CACHE',form='unformatted',access='sequential',status='replace')
write(u)SE(1)%BA;write(u)BA_ED;write(u)BA_T;close(u)
fixed=.false.;compute=.false.;call read_ba_data_v3(51,1,3,3,compute,fixed,ok,'CACHE')
truncated_accepted=ok;truncated_mutates=fixed
! Requesting fresh matrices must bypass even a valid fixed-temperature cache.
call fill_values();call store_ba_data_v3(51,1,3,3,saved_compute,saved_fixed,'CACHE')
SE(1)%BA=-7;fixed=.false.;compute=.true.
call read_ba_data_v3(51,1,3,3,compute,fixed,ok,'CACHE')
bypass_ok=compute.and..not.ok.and..not.fixed.and.all(SE(1)%BA==-7)
write(*,*)'FLAG_ROUNDTRIP_FAILURES',badflags
write(*,*)'MISSING_BINARY_MUTATED_FIXED_T',missing_mutates
write(*,*)'DIMENSION_MISMATCH_MUTATED_FIXED_T',dim_mutates
write(*,*)'TRUNCATED_LAST_RECORD_ACCEPTED',truncated_accepted
write(*,*)'TRUNCATED_LAST_RECORD_MUTATED_FIXED_T',truncated_mutates
write(*,*)'FRESH_COMPUTE_BYPASSES_CACHE',bypass_ok
contains
subroutine fill_values()
SE(1)%BA=1.25_LDP;BA_ED=2.5_LDP;BA_T=3.75_LDP;BA_T_EHB=5._LDP
end subroutine
end program
"""

(work/'test_ba_restart.f90').write_text(DRIVER)
commands=[
 [args.compiler,'-fopenmp','-fcheck=bounds','-ffixed-line-length-0','-I'+str(root/'mod'),'-c',str(reader),'-o',str(work/'reader.o')],
 [args.compiler,'-fopenmp','-fcheck=bounds','-ffree-line-length-none','-I'+str(root/'mod'),str(work/'test_ba_restart.f90'),str(work/'reader.o'),'-L'+str(root/'lib'),'-lsubs','-lmod','-o',str(work/'test')],
]
for command in commands:subprocess.run(command,cwd=work,check=True)
env=dict(os.environ);env.pop('SCRATCH_DIR',None)
run=subprocess.run([str(work/'test')],cwd=work,env=env,check=True,capture_output=True,text=True)
(work/'stdout.txt').write_text(run.stdout+run.stderr)
keys=['FLAG_ROUNDTRIP_FAILURES','MISSING_BINARY_MUTATED_FIXED_T','DIMENSION_MISMATCH_MUTATED_FIXED_T','TRUNCATED_LAST_RECORD_ACCEPTED','TRUNCATED_LAST_RECORD_MUTATED_FIXED_T','FRESH_COMPUTE_BYPASSES_CACHE'];results={}
for line in run.stdout.splitlines():
 words=line.split()
 if words and words[0] in keys:results[words[0]]=int(words[1]) if words[0]=='FLAG_ROUNDTRIP_FAILURES' else words[1]=='T'
text=caller.read_text();call=re.search(r'CALL READ_BA_DATA_V3\([^\n]*,CHK,FIXED_T',text)
assignments=re.findall(r'^\s*CHK\s*=([^!\n]*)',text[:call.start()] if call else '',re.M)
results['CALLER_FORWARDS_FRESH_COMPUTE_REQUEST']=bool(assignments and assignments[-1].strip()=='COMPUTE_BARDIN')
passed=(set(results)==set(keys)|{'CALLER_FORWARDS_FRESH_COMPUTE_REQUEST'} and results['FLAG_ROUNDTRIP_FAILURES']==0 and results['FRESH_COMPUTE_BYPASSES_CACHE'] and results['CALLER_FORWARDS_FRESH_COMPUTE_REQUEST'] and not any(results[k] for k in keys[1:-1]))
report={'passed':passed,'reader_source':str(reader),'caller_source':str(caller),'work_dir':str(work),'cases':results,'commands':commands}
(work/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(0 if passed else 1)
