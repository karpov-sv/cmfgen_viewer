program test_xray
 use set_kind_module
 use steq_data_mod
 implicit none
 real(ldp) :: a(1,1),b(1,1),da(1,1),w(1,1),one(1,1),z(1),edge(1),t(1),f(2),tp,eps,numerical
 real(ldp) :: chibf,chiff,hdkt,twohcsq
 integer :: k
 common /constants/ chibf,chiff,hdkt,twohcsq
 hdkt=4.7994145_ldp; chibf=1;chiff=1;twohcsq=1
 allocate(se(1)%steq(2,1),se(1)%qfv_r(2,1),se(1)%qfv_p(2,1),se(1)%ba_par(2,4,1),se(1)%lnk_to_iv(2))
 se(1)%n_iv=4;se(1)%xray_eq=2;se(1)%lnk_to_iv=[1,2]
 one=1;w=1;z=0;edge=1;t=2;eps=1e-5_ldp
 do k=1,2
 tp=t(1)+(2*k-3)*eps
 a=tp**(-1.5_ldp)*exp(hdkt*2/tp)
 b=tp**(-1.5_ldp)*exp(hdkt/tp)
 se(1)%steq=0;se(1)%qfv_r=0;se(1)%qfv_p=0
 call evalse_x_qwvj_v4(1,w,one,a,1,one,b,1,2,[1.0_ldp],z,1,1)
 f(k)=se(1)%steq(1,1)
 end do
 numerical=(f(2)-f(1))/(2*eps)
 a=t(1)**(-1.5_ldp)*exp(hdkt*2/t(1));b=t(1)**(-1.5_ldp)*exp(hdkt/t(1))
 da=-1.5_ldp-hdkt*2/t(1)
 se(1)%ba_par=0
 call vsebyj_x_v7(1,w,one,a,da,1,one,b,edge,1,[1.0_ldp],2,[1.0_ldp],t,[1.0_ldp],z,z,.false.,1,1,1,1)
 print *, 'X-ray temperature derivative: finite difference, source, ratio'
 print *, numerical,se(1)%ba_par(1,4,1),se(1)%ba_par(1,4,1)/numerical
 if(.not.(abs(se(1)%ba_par(1,4,1)/numerical-1)<1e-7_ldp))error stop 'X-ray temperature derivative'
end program
