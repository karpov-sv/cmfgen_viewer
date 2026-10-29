program check
use set_kind_module
implicit none
integer,parameter::n=3,nd=1
real(ldp)::omega(n,n),domega(n,n),col(n,n,nd),dc(n,n,nd),hn(n,nd),lte(n,nd),dl(n,nd)
real(ldp)::ratio(n,nd),w(n,nd),edge(n),aa(n,n),gg(n),cool(nd),t(nd),ed(nd),chi_bf,chi_ff,hdkt,twoh
real(ldp)::values(3),analytic,h
integer::i,k,map(n)
character(20)::names(n)
external omega_fixed
common /constants/chi_bf,chi_ff,hdkt,twoh
hdkt=4.79924307_ldp;chi_bf=0;chi_ff=0;twoh=0
edge=[2._ldp,1._ldp,.2_ldp];gg=[1._ldp,3._ldp,5._ldp];aa=0;ed=1.e8_ldp
hn(:,1)=[1.e6_ldp,1.e4_ldp,1.e2_ldp];ratio=1;w(:,1)=[1._ldp,.7_ldp,.2_ldp];map=[1,2,3]
names=['ground              ','upper1              ','upper2              '];h=1.e-5_ldp
do k=1,3
 t=1._ldp+(k-2)*h;cool=0
 do i=1,n
  lte(i,1)=t(1)**(-1.5_ldp)*exp(hdkt*edge(i)/t(1))
  dl(i,1)=-1.5_ldp-hdkt*edge(i)/t(1)
 enddo
 call subcol_multi_v6(omega,domega,col,dc,hn,lte,dl,n,hn,ratio,w,edge,aa,gg,names,n, &
  1._ldp,1,'synthetic',omega_fixed,map,cool,t,ed,nd,.true.,.false.,.false.)
 values(k)=col(1,1,1)
 if(k==2)analytic=dc(1,1,1)
enddo
write(*,'(a,es24.16)')'RATE ',values(2)
write(*,'(a,es24.16)')'ANALYTIC ',analytic
write(*,'(a,es24.16)')'FINITE_DIFFERENCE ',(values(3)-values(1))/(2*h)
end program
subroutine omega_fixed(omega,domega,edge,aa,gg,names,z,n,t,id,file)
use set_kind_module
implicit none
integer n,id,i,j
real(ldp)::omega(n,n),domega(n,n),edge(n),aa(n,n),gg(n),z,t
character(*) names(n),file
omega=1;domega=0
do i=1,n
 omega(i,i)=0
enddo
end subroutine
subroutine tune(i,s)
integer i
character(*)s
end subroutine
