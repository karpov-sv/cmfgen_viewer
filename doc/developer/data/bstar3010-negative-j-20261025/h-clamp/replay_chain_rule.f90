program replay_eta
use set_kind_module
use mod_ray_mom_store
use mod_var_mom_j_cmf, only: jnum1,rsq_hnum1,hu,hl,hs,eps_a,eps_b,eps_prev_a,eps_prev_b
implicit none
integer :: n,u,ios,outbc,k,i,rec,selected,source_depth
real(ldp) :: nu,dnu,dbb,ic,stab,delta,step,rawmin,err
real(ldp),allocatable :: rr(:),v(:),sigma(:),eta(:),chi(:),es(:),prevj(:),prevh(:),a(:),b(:),c(:),rhs(:),dq(:),native_raw(:),native_fixed(:)
real(ldp),allocatable :: hp(:),hm(:),hc(:),bound(:),jcor(:),hcor(:)
integer :: ii,win
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
 allocate(hp(n-1),hm(n-1),hc(n-1),bound(n-1),jcor(n),hcor(n-1))
 tx=0;tvx=0;dt=0;dg=0;ht=0;hg=0;chosen=.true.;theta=0
 if(coherent)theta=es/chi
 call mod_var_mom_alloc(n)
 jnum1=prevj/(rr*rr);rsq_hnum1=prevh
 call var_mom_j_cmf_v12(eta,chi,es,theta,v,sigma,rr,tx,tvx,dt,dg,ht,hg,ki,wm,dh,.false.,dnu,'DIFFUSION',1._ldp,dbb,0._ldp,ic,stab,nu,'MAX_VAL',outbc,chosen,method,n,2,2)
 ! The forward recorder stores r^2 J; variation returns J.
 print *, 'RECORD',rec,'NU',nu,'RAW_J33',native_raw(33)/rr(33)**2,'USED_J33',native_fixed(33)/rr(33)**2
 k=source_depth
 print *, 'FORWARD_RECONSTRUCT_ROW33',jnum1(33),'NATIVE_RAW_ROW33',native_raw(33)/rr(33)**2
 do i=1,n-1
 hc(i)=hu(i)*(native_fixed(i+1)/rr(i+1)**2)-hl(i)*(native_fixed(i)/rr(i)**2)+hs(i)*prevh(i) &
 +eps_prev_a(i)*(prevj(i)/rr(i)**2)-eps_a(i)*(native_fixed(i)/rr(i)**2) &
 +eps_prev_b(i)*(prevj(i+1)/rr(i+1)**2)-eps_b(i)*(native_fixed(i+1)/rr(i+1)**2)
 bound(i)=max(native_fixed(i),native_fixed(i+1))
 enddo
 print *, 'FORWARD_H_CLIPPED_ROWS',count(abs(hc)>bound)
 print *, 'FORWARD_H_BEFORE',hc(31:35),'BOUND',bound(31:35)
 where(hc>bound)hc=.99999_ldp*bound
 where(hc< -bound)hc=-.99999_ldp*bound
 print *, 'FORWARD_H_USED',hc(31:35),'VAR_H_USED',rsq_hnum1(31:35)
 analytic=tx(:,k,2)
 jcor=analytic
 where(native_raw<0)jcor=-.1_ldp*jcor
 do ii=1,n-1
 hcor(ii)=(hu(ii)-eps_b(ii))*jcor(ii+1)-(hl(ii)+eps_a(ii))*jcor(ii)
 if(abs(hc(ii)-.99999_ldp*bound(ii))<=1.e-15_ldp*bound(ii) .or. &
 abs(hc(ii)+.99999_ldp*bound(ii))<=1.e-15_ldp*bound(ii))then
 win=ii
 if(native_fixed(ii+1)>native_fixed(ii))win=ii+1
 hcor(ii)=sign(.99999_ldp,hc(ii))*rr(win)**2*jcor(win)
 endif
 enddo

 do i=1,4
  delta=10._ldp**(-i-1);step=eta(k)*delta
  bb=b;cc=c;xp=rhs;xp(k)=xp(k)+dq(k)*rr(k)**2/chi(k)*step
  call thomas(a,bb,cc,xp,n,1)
  bb=b;cc=c;xm=rhs;xm(k)=xm(k)-dq(k)*rr(k)**2/chi(k)*step
  call thomas(a,bb,cc,xm,n,1)
  where(xp<0)xp=abs(xp)/10._ldp
  where(xm<0)xm=abs(xm)/10._ldp
  do k=1,n-1
  hp(k)=hu(k)*(xp(k+1)/rr(k+1)**2)-hl(k)*(xp(k)/rr(k)**2)+hs(k)*prevh(k) &
  +eps_prev_a(k)*(prevj(k)/rr(k)**2)-eps_a(k)*(xp(k)/rr(k)**2) &
  +eps_prev_b(k)*(prevj(k+1)/rr(k+1)**2)-eps_b(k)*(xp(k+1)/rr(k+1)**2)
  hm(k)=hu(k)*(xm(k+1)/rr(k+1)**2)-hl(k)*(xm(k)/rr(k)**2)+hs(k)*prevh(k) &
  +eps_prev_a(k)*(prevj(k)/rr(k)**2)-eps_a(k)*(xm(k)/rr(k)**2) &
  +eps_prev_b(k)*(prevj(k+1)/rr(k+1)**2)-eps_b(k)*(xm(k+1)/rr(k+1)**2)
  if(hp(k)>max(xp(k),xp(k+1)))hp(k)=.99999_ldp*max(xp(k),xp(k+1))
  if(hp(k)<-max(xp(k),xp(k+1)))hp(k)=-.99999_ldp*max(xp(k),xp(k+1))
  if(hm(k)>max(xm(k),xm(k+1)))hm(k)=.99999_ldp*max(xm(k),xm(k+1))
  if(hm(k)<-max(xm(k),xm(k+1)))hm(k)=-.99999_ldp*max(xm(k),xm(k+1))
  enddo
  k=source_depth
  print *, 'H_ROW32_FD', (hp(32)-hm(32))/(2*step),'ANALYTIC',tvx(32,k,2)
  print *, 'H_ROW33_FD', (hp(33)-hm(33))/(2*step),'ANALYTIC',tvx(33,k,2)
  fd=(xp-xm)/(2*step)/(rr*rr)
  print *, 'CHAIN_J_COL_ERR',maxval(abs(fd-jcor))/max(maxval(abs(fd)),maxval(abs(jcor)),1.e-200_ldp)
  print *, 'CHAIN_H_COL_ERR',maxval(abs((hp-hm)/(2*step)-hcor))/max(maxval(abs((hp-hm)/(2*step))),maxval(abs(hcor)),1.e-200_ldp)
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
