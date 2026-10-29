program check
use set_kind_module
implicit none
real(kind=LDP)::r(5),y(5,3),q(17),z(17,3),lo,hi,tmp
integer i,j,k,rev
do rev=1,2
 r=[5.0_LDP,4.0_LDP,3.0_LDP,2.0_LDP,1.0_LDP]
 y(:,1)=[1.e-20_LDP,1.e-80_LDP,1.e-140_LDP,1.e-200_LDP,1.e-260_LDP]
 y(:,2)=[-1.0_LDP,0.0_LDP,3.0_LDP,1.0_LDP,-2.0_LDP]
 y(:,3)=1.0e-280_LDP
 do i=1,17
  q(i)=5.0_LDP-(i-1)*0.25_LDP
 enddo
 if(rev==2)then
  r=r(5:1:-1);y=y(5:1:-1,:);q=q(17:1:-1)
 endif
 call mon_interp(z,17,3,q,17,y,5,r,5)
 do i=1,17
  do j=1,5
   if(q(i)==r(j))then
    if(any(z(i,:)/=y(j,:)))stop 51
   endif
  enddo
  do j=1,4
   if(q(i)>=min(r(j),r(j+1)).and.q(i)<=max(r(j),r(j+1)))then
    do k=1,3
     lo=min(y(j,k),y(j+1,k));hi=max(y(j,k),y(j+1,k))
     if(z(i,k)<lo.or.z(i,k)>hi)stop 52
    enddo
   endif
  enddo
 enddo
 if(any(z(:,1)<=0.0_LDP).or.any(z(:,3)/=1.e-280_LDP))stop 53
enddo
print *, 'PASS: exact nodes, positive dynamic range, signed bounds, constant data, both grid orders'
end program
