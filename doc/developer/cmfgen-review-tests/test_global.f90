module control_variable_mod
 logical::lte_model=.false.
end module
program test_global
 use set_kind_module
 implicit none
 real(ldp)::s(3,2),p(3,2),popatom(2),maxch
 integer::i,j
 real(ldp)::limit
 logical::success
 character(8)::scale
 popatom=1
 do i=1,2
 limit=0.2_ldp/i
 do j=1,2
 s=0;s(3,j)=0.8_ldp;p=1;p(3,:)=2;scale='GLOBAL'
 call solveba_v13(s,p,popatom,1,3,1,1,2,maxch,'DIAG',success,scale,'NONE    ', &
 2.0_ldp,limit,0.01_ldp,.true.,.false.,.false.,.false.,1,.false.)
 if(.not.(abs(p(3,j)-2*(1-limit))<1e-12_ldp))error stop 'GLOBAL temperature limit'
 print *, 'PASS GLOBAL limit and depth',limit,j
 end do
 end do
end program
subroutine cmf_blkband_v3(s,p,method,success,diag,nt,nion,nb,nd,ba,wr,prt)
 use set_kind_module
 integer::diag,nt,nion,nb,nd
 real(ldp)::s(nt,nd),p(nt,nd)
 character(*)::method
 integer::i,j
 real(ldp)::limit
 logical::success,ba,wr,prt
 success=.true.
end subroutine
subroutine tune(i,s)
 integer::i
 character(*)::s
end subroutine
integer function error_lu()
 error_lu=6
end function
subroutine set_case_up(s,i,j)
 character(*)::s
 integer::i,j
end subroutine
subroutine gen_asci_open(lu,a,b,c,d,i,ios)
 integer::lu,i,ios
 character(*)::a,b,c,d
 open(lu,status='scratch',iostat=ios)
end subroutine
subroutine fiddle_pop_corrections_v2()
 stop 'unexpected MAJOR branch'
end subroutine
subroutine set_pops_to_pure_lte()
 stop 'unexpected LTE branch'
end subroutine
