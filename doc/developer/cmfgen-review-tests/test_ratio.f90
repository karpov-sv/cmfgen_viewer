program test_ratio
 use set_kind_module
 use steq_data_mod
 use, intrinsic :: ieee_arithmetic
 implicit none
 real(ldp)::w(1,1),hn(1,1),hnst(1,1),di(2,1),logdist(2,1),zero(1),expected,derivative
 integer::i,target
 allocate(se(1)%steq(2,1),se(1)%qfv_r(2,1),se(1)%qfv_p(2,1),se(1)%t_ehb(1), &
 se(1)%qfv_r_ehb(2,1),se(1)%qfv_p_ehb(2,1),se(1)%ion_lev_to_eq_pnt(2),se(1)%ba_par(2,4,1))
 se(1)%ion_lev_to_eq_pnt=[2,2];se(1)%n_iv=4
 w=1;hn=0;zero=0
 do i=1,7
 target=2;hnst=1;di=1;logdist=0;expected=1
 select case(i)
 case(1)
 di(1,1)=1e200_ldp;di(2,1)=exp(-720.0_ldp)*di(1,1);logdist(2,1)=-720
 case(2)
 di(1,1)=1e200_ldp;di(2,1)=1e-200_ldp;logdist(2,1)=-400*log(10.0_ldp)
 case(3)
 di(1,1)=1e-200_ldp;di(2,1)=1e200_ldp;logdist(2,1)=400*log(10.0_ldp)
 case(4)
 hnst=1e-300_ldp;logdist(2,1)=-800;expected=exp(log(hnst(1,1))+800)
 case(5)
 hnst=1e300_ldp;logdist(2,1)=800;expected=exp(log(hnst(1,1))-800)
 case(6)
 hnst=0;logdist(2,1)=-800;expected=0
 case(7)
 target=1;hnst=2;expected=2
 end select
 se(1)%steq=0;se(1)%qfv_r=0;se(1)%qfv_p=0;se(1)%t_ehb=0
 se(1)%qfv_r_ehb=0;se(1)%qfv_p_ehb=0;se(1)%ba_par=0
 call evalse_qwvj_v8(1,w,w,hn,hnst,1,target,di,logdist,2,[1.0_ldp],zero,zero,zero,4,1)
 call vsebyj_multi_v8(1,w,reshape([0.0_ldp],[1,1]),hn,hnst,reshape([0.0_ldp],[1,1]),1, &
 di,logdist,reshape([0.0_ldp,0.0_ldp],[2,1]),2,target,[1.0_ldp],[1.0_ldp], &
 [1.0_ldp],zero,zero,.false.,1,1,1,1)
 if(.not.ieee_is_finite(se(1)%steq(1,1)))error stop 'Non-finite recombination'
 if(abs(se(1)%steq(1,1)-expected)>1e-10_ldp*abs(expected))error stop 'Incorrect recombination'
 derivative=expected/di(target,1)
 if(.not.all(ieee_is_finite(se(1)%ba_par)))error stop 'Non-finite Jacobian'
 if(abs(se(1)%ba_par(1,2,1)-derivative)>1e-10_ldp*abs(derivative))error stop 'Incorrect ion derivative'
 if(abs(se(1)%ba_par(1,3,1)-expected)>1e-10_ldp*abs(expected))error stop 'Incorrect electron derivative'
 if(abs(sum(se(1)%steq(:,1)))>0)error stop 'Rate conservation'
 print *, 'PASS departure-ratio rate and Jacobian case',i
 end do
end program
function plancks_constant() result(x)
 use set_kind_module
 real(ldp)::x
 x=6.62607015e-27_ldp
end function
