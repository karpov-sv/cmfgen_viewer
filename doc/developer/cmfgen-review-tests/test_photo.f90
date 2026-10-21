program check
use set_kind_module
use phot_data_mod
use mod_lev_dis_blk
implicit none
integer,parameter::nf=104,ns=44,ni=105,nsi=50
real(8)::edge(nf),g(nf),ei(ni),gi(ni),ed(1),t(1),pop(nsi,1),d(1),z,gion
real(8)::hf(nf,1),lhf(nf,1),w(nf,1),hs(ns,1),lhs(ns,1),dh(ns,1),fs(nf,1)
real(8)::hfi(ni,1),lhfi(ni,1),wi(ni,1),hsi(nsi,1),lhsi(nsi,1),dhi(nsi,1),fsi(ni,1)
real(8)::wse(ns,1),dw(ns,1),wcr(ns,1),dcr(ns,1),rr(ns,1),pr(ns,1),bf(ns,1),ff(1)
real(8)::nu,dnu,jrec(1),jp(1),jrcr(1),jpc(1),bpc(1),raw(4,ns),fixed(4,ns),q,ground
real(8)::chibf,chiff,hdkt,twohcsq
common /constants/chibf,chiff,hdkt,twohcsq
integer::map(nf),mi(ni),ids(100),nphot,i,k,l,which,steps,luin,luout
character(40)::names(nf),namesi(ni)
print *, 'start'
chibf=0;chiff=0;hdkt=4.799243073d0;twohcsq=0.01474499465d0
open(10,file='NI.dat');do i=1,nf;read(10,*)names(i),edge(i),g(i),map(i);enddo;close(10)
open(10,file='N2.dat');do i=1,ni;read(10,*)namesi(i),ei(i),gi(i),mi(i);enddo;close(10)
open(10,file='pops.dat');read(10,*)ed;read(10,*)t;do i=1,nsi;read(10,*)pop(i,1);enddo;close(10)
print *, 'loaded'
z=1;gion=1;luin=31;luout=32
call rdphot_gen_v2(edge,names,gion,7d0,z,nf,ids,nphot,100,.true.,ei,gi,mi,namesi,ni, &
 0d0,0.1d0,0.01d0,.true.,.false.,1,'NI',luin,luout)
call rd_hyd_bf_data(luin,luout,6)
print *, 'Returned IDs:',ids(1:nphot)
print *, 'Internal full-level IDs:',pd(1)%ion_lev_id(1:nphot)
if(nphot/=4)error stop 'Wrong number of photoionization routes'
if(any(ids(1:4)/=[1,2,3,4]))error stop 'Returned photoionization target mapping'
if(any(pd(1)%ion_lev_id(1:4)/=[1,4,5,6]))error stop 'Internal full-level indices changed'
call comp_lev_dis_blk(ed,ed,t,.false.,1)
d=1
call ltepop_wld_v2(hfi,lhfi,wi,ei,gi,2d0,1d0,ni,d,ed,t,1)
call lte_pop_sl_v2(hsi,lhsi,dhi,nsi,hfi,lhfi,fsi,ei,mi,ni,.true.,t,1)
ground=pop(1,1)*fsi(1,1);d=ground
call ltepop_wld_v2(hf,lhf,w,edge,g,1d0,1d0,nf,d,ed,t,1)
call lte_pop_sl_v2(hs,lhs,dh,ns,hf,lhf,fs,edge,map,nf,.true.,t,1)
steps=100000;dnu=10d0/steps
raw=0;fixed=0
! Both accumulators use the corrected returned superlevel target index.
do k=1,nphot
 do i=1,steps
  nu=(i-0.5d0)*dnu
  call quad_multi_v10(wse,dw,wcr,dcr,hs,dh,ns,fs,edge,nf,map,nu,t,1, &
    .false.,.true.,.true.,'NI',1d0,k,1)
  jrec=twohcsq*nu**2*exp(-hdkt*nu/t(1))*dnu*1d15
  jp=0;jrcr=jrec*nu;jpc=0;bpc=0
  do which=1,2
   l=ids(k)
   call prrr_sl_v6(pr,rr,bf,ff,wse,wcr,hf_dummy(),hs,ns,1d0,pop,lhsi,nsi, &
    1,l,ed,t,jrec,jp,jrcr,jpc,bpc,nu,nu,.true.,1)
   if(which==1)raw(k,:)=raw(k,:)+rr(:,1)
   if(which==2)fixed(k,:)=fixed(k,:)+rr(:,1)
  enddo
 enddo
enddo
print *, 'Outer Ne,T:',ed,t
print *, 'Native/raw and mapped rate by route for NI superlevels 2,3,6'
do k=1,nphot
 print '(I3,6ES16.7)',k,raw(k,2),fixed(k,2),raw(k,3),fixed(k,3),raw(k,6),fixed(k,6)
enddo
print *, 'Total recombination / (Ne*NII ground superlevel):',sum(raw)/(ed(1)*pop(1,1)),sum(fixed)/(ed(1)*pop(1,1))
if(abs(sum(raw)/(ed(1)*pop(1,1))/6.5797154d-13-1)>1d-6)error stop 'NI recombination regression'
open(11,file='rates.dat');do k=1,ns;write(11,'(I4,2ES24.14)')k,sum(raw(:,k)),sum(fixed(:,k));enddo;close(11)
contains
function hf_dummy() result(a)
real(8)::a(ns,1)
a=0
end function
end program
