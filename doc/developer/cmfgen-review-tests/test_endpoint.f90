program test_endpoint
 use set_kind_module
 implicit none
 real(ldp)::r(4),ne(4),temp(4),atoms(4),eps
 integer::i,lu
 character(20)::argument
 open(newunit=lu,file='estimates',status='replace')
 write(lu,'(A)')'24-FEB-2004 !Format date'
 write(lu,*)1.0_ldp,1.0_ldp,1,3
 do i=1,3
  write(lu,*)real(4-i,ldp),1.0_ldp,real(i,ldp)*1e5_ldp,real(i,ldp)
  write(lu,*)1.0_ldp
 end do
 close(lu)
 atoms=[1.0_ldp,2.0_ldp,3.0_ldp,4.0_ldp]
 eps=2.36e-11_ldp
 r=[3*(1+eps),2.0_ldp,1.5_ldp,1.0_ldp];ne=-1;temp=-1
 call regrid_t_ed_v3(r,ne,temp,atoms,4,'R','estimates')
 if(abs(temp(1)-1)>1e-10_ldp)error stop 'Rounded outer endpoint'
 r=[3.0_ldp,2.0_ldp,1.5_ldp,1-eps];ne=-1;temp=-1
 call regrid_t_ed_v3(r,ne,temp,atoms,4,'RNS','estimates')
 if(abs(temp(4)-3)>1e-10_ldp)error stop 'Rounded inner endpoint'
 r=[4.0_ldp,3.0_ldp,1.0_ldp,0.5_ldp];ne=-1;temp=-1
 call regrid_t_ed_v3(r,ne,temp,atoms,4,'RNS','estimates')
 if(abs(temp(1)-1)>1e-10_ldp.or.abs(temp(4)-3)>1e-10_ldp)error stop 'True grid extension T'
 if(abs(ne(1)/5e4_ldp-1)>1e-10_ldp.or.abs(ne(4)/4e5_ldp-1)>1e-10_ldp)error stop 'Grid extension Ne'
 r=[5.0_ldp,4.0_ldp,3.0_ldp,0.5_ldp];ne=-1;temp=-1
 call regrid_t_ed_v3(r,ne,temp,atoms,4,'RNS','estimates')
 if(maxval(abs(temp-1))>1e-10_ldp)error stop 'Single overlapping point'
 print *, 'PASS rounded endpoints and genuine inner/outer extrapolation'
 call get_command_argument(1,argument)
 if(trim(argument)=='no-overlap')then
  r=[8.0_ldp,7.0_ldp,6.0_ldp,5.0_ldp]
  call regrid_t_ed_v3(r,ne,temp,atoms,4,'RNS','estimates')
  error stop 'No overlap accepted'
 end if
end program
integer function error_lu()
 error_lu=6
end function
