program test_xray
use set_kind_module
use, intrinsic :: ieee_arithmetic
implicit none
real(kind=LDP) f,m,qnan
logical changed,valid,ba,edd
integer n,i
real(kind=LDP) :: obs(8)=[17.2138_LDP,0.25_LDP,1.0_LDP,1.05_LDP,0.0_LDP, &
                        1.0e10_LDP,1.0e-10_LDP,1.11_LDP]
real(kind=LDP) :: expect(8)=[sqrt(1.0_LDP/17.2138_LDP),2.0_LDP,1.0_LDP,1.0_LDP, &
                           10.0_LDP,0.1_LDP,10.0_LDP,sqrt(1.0_LDP/1.11_LDP)]
do i=1,8
 call cmfgen_xray_scale(obs(i),1.0_LDP,0.1_LDP,f,changed,valid)
 if(.not.valid.or.abs(f-expect(i))>1.e-14_LDP)stop 11
 if(changed.neqv.(i/=3.and.i/=4))stop 12
enddo
call cmfgen_xray_scale(huge(f),tiny(f),0.1_LDP,f,changed,valid)
if(.not.valid.or.f/=0.1_LDP)stop 13
call cmfgen_xray_scale(tiny(f),huge(f),0.1_LDP,f,changed,valid)
if(.not.valid.or.f/=10.0_LDP)stop 14
call cmfgen_xray_scale(0.0_LDP,huge(f),huge(f),f,changed,valid)
if(.not.valid.or.changed)stop 15
qnan=ieee_value(1.0_LDP,ieee_quiet_nan)
call cmfgen_xray_scale(qnan,1.0_LDP,0.1_LDP,f,changed,valid)
if(valid.or.changed)stop 16
call cmfgen_xray_scale(1.0_LDP,0.0_LDP,0.1_LDP,f,changed,valid)
if(valid.or.changed)stop 17
call cmfgen_xray_scale(-1.0_LDP,1.0_LDP,0.1_LDP,f,changed,valid)
if(valid.or.changed)stop 18
call cmfgen_xray_scale(1.0_LDP,1.0_LDP,-0.1_LDP,f,changed,valid)
if(valid.or.changed)stop 19
! Cycle override has just requested held BA and terminal formal-only pass.
n=1; m=0.001_LDP; ba=.false.; edd=.false.
call cmfgen_xray_continue(.true.,m,ba,edd,n)
if(n/=2.or.m<100.or..not.ba.or..not.edd)stop 21
! Native loop decrements before deciding whether it is a solved iteration.
n=n-1
if(n==0)stop 22
n=7; m=0.001_LDP; ba=.false.; edd=.false.
call cmfgen_xray_continue(.false.,m,ba,edd,n)
if(n/=7.or.m/=0.001_LDP.or.ba.or.edd)stop 23
print *, 'PASS: bidirectional scaling, bounds, invalid inputs, fresh solved continuation'
end program
