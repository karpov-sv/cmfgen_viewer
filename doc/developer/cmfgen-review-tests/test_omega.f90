program test_omega
 use set_kind_module
 implicit none
 real(ldp)::om(2,2),der(2,2),edge(2),ein(2,2),g(2),hdk,t0,eps,f(2)
 real(ldp)::chibf,chiff,hdkt,twohcsq
 character(6)::names(2)
 integer::k
 common /constants/ chibf,chiff,hdkt,twohcsq
 hdkt=4.7994145_ldp;edge=[5.0_ldp,1.0_ldp];ein=0;ein(1,2)=1;g=1;names=['lev1  ','lev2  ']
 t0=hdkt*4/20;eps=1e-5_ldp
 do k=1,2
 call omega_gen_v3(om,der,edge,ein,g,names,1.0_ldp,2,t0*exp((2*k-3)*eps),1,'fixture')
 f(k)=log(om(1,2))
 end do
 call omega_gen_v3(om,der,edge,ein,g,names,1.0_ldp,2,t0,1,'fixture')
 print *, 'Neutral collision at X=20: finite difference dlnOmega/dlnT, source'
 print *, (f(2)-f(1))/(2*eps),der(1,2)
 if(.not.(abs((f(2)-f(1))/(2*eps)-der(1,2))<1e-7_ldp))error stop 'Neutral collision derivative'
end program
subroutine tune(i,s)
 integer::i
 character(*)::s
end subroutine
integer function error_lu()
 error_lu=6
end function
logical function same_n(a,b)
 character(*)::a,b
 same_n=.false.
end function
subroutine sub_phot_gen(id,cross,nu,edge,n,phot_id,ret)
 use set_kind_module
 integer::id,n,phot_id
 real(ldp)::cross(n),nu,edge(n)
 logical::ret
 cross=1
end subroutine
subroutine gen_omega_rd_v2(om,tt,lo,up,ix,scale,set,names,g,n,file,nt,nv,mt,mv,ms)
 use set_kind_module
 integer::n,nt,nv,mt,mv,ms,lo(mt),up(mt),ix(mt)
 real(ldp)::om(ms),tt(mv),scale,set,g(n)
 character(*)::names(n),file
 nt=0;nv=0;scale=1;set=0.1_ldp
end subroutine
