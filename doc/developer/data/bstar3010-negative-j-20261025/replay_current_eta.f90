program replay_eta
use set_kind_module
use mod_ray_mom_store
use mod_var_mom_j_cmf, only: jnum1,rsq_hnum1
implicit none
integer :: n,u,ios,outbc,k,i,rec,selected,source_depth
real(ldp) :: nu,dnu,dbb,ic,stab,delta,step,rawmin,err
real(ldp),allocatable :: rr(:),v(:),sigma(:),eta(:),chi(:),es(:),prevj(:),prevh(:),a(:),b(:),c(:),rhs(:),dq(:),native_raw(:),native_fixed(:)
real(ldp),allocatable :: tx(:,:,:),tvx(:,:,:),dt(:),dg(:),ht(:),hg(:),ki(:,:,:),wm(:,:),dh(:,:),theta(:),bb(:),cc(:),xp(:),xm(:),analytic(:),fd(:)
character(6) :: method,ntype
logical :: coherent,chosen(2)
character(256):: arg
call get_command_argument(1,arg);read(arg,*)selected
source_depth=33
call get_command_argument(2,arg);if(len_trim(arg)>0)read(arg,*)source_depth
open(newunit=u,file='B3010_RADIATION.bin',access='stream',form='unformatted',status='old')
rec=0
 do
 read(u,iostat=ios)n
 if(ios/=0)exit
 if(.not.allocated(rr))then
  allocate(rr(n),v(n),sigma(n),eta(n),chi(n),es(n),prevj(n),prevh(n),a(n),b(n),c(n),rhs(n),dq(n),native_raw(n),native_fixed(n))
  allocate(k_on_j(n),nmid_on_j(n),nmid_on_hmid(n),k_on_j_prev(n),nmid_on_j_prev(n),nmid_on_hmid_prev(n))
 endif
 read(u)nu,dnu,dbb,ic,stab,hbc,nbc,in_hbc,hbc_prev,nbc_prev,in_hbc_prev,coherent,outbc,method,ntype
 read(u)rr,v,sigma,eta,chi,es,k_on_j,nmid_on_j,nmid_on_hmid,k_on_j_prev,nmid_on_j_prev,nmid_on_hmid_prev,prevj,prevh,a,b,c,rhs,dq
 read(u)native_raw,native_fixed
 rec=rec+1
 if(rec/=selected)cycle
 allocate(tx(n,n,2),tvx(n-1,n,2),dt(n),dg(n),ht(n-1),hg(n-1),ki(n,n,2),wm(n,n),dh(n-1,n),theta(n),bb(n),cc(n),xp(n),xm(n),analytic(n),fd(n))
 tx=0;tvx=0;dt=0;dg=0;ht=0;hg=0;chosen=.true.;theta=0
 if(coherent)theta=es/chi
 call mod_var_mom_alloc(n)
 jnum1=prevj/(rr*rr);rsq_hnum1=prevh
 call var_mom_j_cmf_v12(eta,chi,es,theta,v,sigma,rr,tx,tvx,dt,dg,ht,hg,ki,wm,dh,.false.,dnu,'DIFFUSION',1._ldp,dbb,0._ldp,ic,stab,nu,'MAX_VAL',outbc,chosen,method,n,2,2)
 ! The forward recorder stores r^2 J; variation returns J.
 print *, 'RECORD',rec,'NU',nu,'RAW_J33',native_raw(33)/rr(33)**2,'USED_J33',native_fixed(33)/rr(33)**2
 k=source_depth
 print *, 'FORWARD_RECONSTRUCT_ROW33',jnum1(33),'NATIVE_RAW_ROW33',native_raw(33)/rr(33)**2
 analytic=tx(:,k,2)
 do i=1,4
  delta=10._ldp**(-i-1);step=eta(k)*delta
  bb=b;cc=c;xp=rhs;xp(k)=xp(k)+dq(k)*rr(k)**2/chi(k)*step
  call thomas(a,bb,cc,xp,n,1)
  bb=b;cc=c;xm=rhs;xm(k)=xm(k)-dq(k)*rr(k)**2/chi(k)*step
  call thomas(a,bb,cc,xm,n,1)
  where(xp<0)xp=abs(xp)/10._ldp
  where(xm<0)xm=abs(xm)/10._ldp
  fd=(xp-xm)/(2*step)/(rr*rr)
  err=maxval(abs(fd-analytic))/max(maxval(abs(fd)),maxval(abs(analytic)),1.e-200_ldp)
  print *, 'DELTA',delta,'SOURCE_DEPTH',k,'FD',fd(k),'ANALYTIC',analytic(k),'RATIO',fd(k)/analytic(k),'COLUMN_ERROR',err
 enddo
 exit
 enddo
close(u)
contains
end program
subroutine tune(i,name)
integer i
character(*) name
end subroutine
