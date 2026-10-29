program normal
use set_kind_module
implicit none
real(kind=LDP)::r(5),y(5,2),q(200),z(200,2)
integer i,rev
character(len=500)path
call get_command_argument(1,path)
open(18,file=trim(path),access='stream',form='unformatted',status='replace')
do rev=1,2
 r=[10.0_LDP,7.0_LDP,4.0_LDP,2.0_LDP,1.0_LDP]
 y(:,1)=[3.0_LDP,1.0_LDP,5.0_LDP,2.0_LDP,4.0_LDP]
 y(:,2)=-y(:,1)
 do i=1,200
  q(i)=10.0_LDP-(i-0.37_LDP)*9.0_LDP/200.0_LDP
 enddo
 if(rev==2)then
  r=r(5:1:-1);y=y(5:1:-1,:);q=q(200:1:-1)
 endif
 call mon_interp(z,200,2,q,200,y,5,r,5)
 write(18)z
enddo
close(18)
end program
