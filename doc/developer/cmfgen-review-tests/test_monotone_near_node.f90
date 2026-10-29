program near
use set_kind_module
implicit none
real(kind=LDP)::r(5),y(5,2),q(3),z(3,2),expected(3)
r=[5.0_LDP,4.0_LDP,3.0_LDP,2.0_LDP,1.0_LDP]
y(:,1)=[1.0_LDP,1.e-5_LDP,1.e-20_LDP,1.e-100_LDP,1.e-200_LDP]
y(:,2)=-y(:,1)
q=[2.0_LDP+1.e-6_LDP,2.0_LDP+1.e-10_LDP,2.0_LDP+1.e-12_LDP]
expected=1.e-20_LDP*(q-2.0_LDP)**2
call mon_interp(z,3,2,q,3,y,5,r,5)
if(any(abs(z(:,1)/expected-1)>1.e-12_LDP).or.any(abs(z(:,2)/expected+1)>1.e-12_LDP))then
 print *, 'Expected:',expected
 print *, 'Actual:',z(:,1)
 stop 71
endif
print *, 'PASS: near-node values retain relative accuracy, both signs, 100+ orders of range'
end program
