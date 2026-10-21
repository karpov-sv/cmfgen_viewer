program test_auto
 use mod_cmfgen
 implicit none
 integer::j
 atm%nxzv_f=[10,20,30,1]
 do j=1,4
 atm(j)%gxzv_f=1
 end do
 if(command_argument_count()==0)then
 open(71,file='CI_IN',status='replace');close(71)
 end if
 call auto_add_ion()
end program
subroutine sub_guess_dc_v2(n,ion,ref,g1,g2)
 use set_kind_module
 use mod_cmfgen, only: ion_id,atm
 integer::n,j
 character(*)::ion,ref
 real(ldp)::g1,g2
 do j=1,size(ion_id)
 if(ion==ion_id(j))then
 if(n/=atm(j)%nxzv_f)error stop 'Wrong atom level count'
 end if
 end do
 print *, 'SUB_GUESS_DC_V2: ',ion,' supplied NLEV=',n
end subroutine
subroutine deallocate_mod_guess_dc()
end subroutine
