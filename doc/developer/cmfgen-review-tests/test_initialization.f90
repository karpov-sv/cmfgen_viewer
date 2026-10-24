! Synthetic hydrogen atom with an occupation-sensitive high level.
program test_initialization
  use set_kind_module
  use mod_cmfgen
  use mod_lev_dis_blk
  use init_population_estimates_mod
  use control_variable_mod, only: dc_interp_method
  implicit none
  real(ldp) :: chibf,chiff,hdkt,twohcsq
  common /constants/ chibf,chiff,hdkt,twohcsq
  real(ldp) :: source_r(2),source_ne(2),source_t(2),source_density(2),expected(2,2),dc(2,2)
  real(ldp) :: lte(2,2),loglte(2,2),occupation(2,2),fraction(3,2),middle(3),norm
  integer :: format_number,i,k,lu
  logical :: dissolve
  character(20) :: argument
  hdkt=4.7994145_ldp; chibf=0;chiff=0;twohcsq=0
  dc_interp_method='R'
  num_ions=2; species_pres=.false.;species_pres(1)=.true.
  species_beg_id=0;species_end_id=0;species_beg_id(1)=1;species_end_id(1)=2
  atm%xzv_pres=.false.;atm(1)%xzv_pres=.true.
  atm(1)%nxzv=2;atm(1)%nxzv_f=2;atm(1)%zxzv=1;atm(1)%gionxzv_f=1
  ion_id(1)='HX'
  allocate(atm(1)%edgexzv_f(2),atm(1)%gxzv_f(2),atm(1)%f_to_s_xzv(2))
  atm(1)%edgexzv_f=[3.289395_ldp,3.289395_ldp/900]
  atm(1)%gxzv_f=[2.0_ldp,1800.0_ldp];atm(1)%f_to_s_xzv=[1,2]
  allocate(r(2),t(2),ed(2),popion(2),pop_atom(2),pop_species(2,num_species))
  allocate(atm(1)%xzv_f(2,2),atm(1)%xzv(2,2),atm(1)%dxzv_f(2),atm(1)%dxzv(2))
  source_r=[4.0_ldp,1.0_ldp];source_t=[0.2_ldp,1.0_ldp]
  source_ne=[1e10_ldp,1e12_ldp];source_density=[1e14_ldp,1e13_ldp]
  expected(2,:)=(source_density-source_ne)*0.01_ldp
  expected(1,:)=source_density-source_ne-expected(2,:)
  r=source_r;t=source_t;ed=source_ne;pop_atom=source_density;pop_species=0;pop_species(:,1)=source_density
  call comp_lev_dis_blk(ed,ed,t,.true.,2)
  call ltepop_wld_v2(lte,loglte,occupation,atm(1)%edgexzv_f,atm(1)%gxzv_f, &
       1.0_ldp,1.0_ldp,2,ed,ed,t,2)
  dc=log(expected)-loglte
  atm(1)%xzv_f=dc;atm(1)%dxzv_f=ed
  call reconstruct_dc_estimates(2,.true.,.true.,6)
  if(maxval(abs(atm(1)%xzv_f/expected-1))>1e-8_ldp) error stop 'Occupation round trip'
  if(maxval(abs(popion/source_ne-1))>1e-8_ldp) error stop 'Charged-ion source_density'
  print *, 'PASS self-consistent occupation round trip'
  do k=1,2
    fraction(1:2,k)=expected(:,k)/source_density(k)
    fraction(3,k)=source_ne(k)/source_density(k)
  end do
  middle=sqrt(fraction(:,1)*fraction(:,2));middle=middle/sum(middle)
  ! LTE must solve Ne from the reconstructed charged populations, rather than
  ! retaining DET_LTE_ED's approximate (possibly TMIN-clamped) starting Ne.
  dc_interp_method='LTE'
  atm(1)%xzv_f=0.0_ldp;atm(1)%dxzv_f=pop_atom
  ed=10.0_ldp*source_ne
  call reconstruct_dc_estimates(2,.true.,.false.,6)
  if(maxval(abs(ed/atm(1)%dxzv_f-1))>1e-8_ldp) error stop 'LTE charge consistency'
  if(maxval(abs((sum(atm(1)%xzv_f,dim=1)+atm(1)%dxzv_f)/pop_atom-1))>1e-8_ldp) &
      error stop 'LTE elemental normalization'
  print *, 'PASS LTE charge and element consistency with inconsistent initial Ne'
  dc_interp_method='R'
  deallocate(r,t,ed,popion,pop_atom,pop_species)
  deallocate(atm(1)%xzv_f,atm(1)%xzv,atm(1)%dxzv_f,atm(1)%dxzv)
  allocate(r(3),t(3),ed(3),popion(3),pop_atom(3),pop_species(3,num_species))
  allocate(atm(1)%xzv_f(2,3),atm(1)%xzv(2,3),atm(1)%dxzv_f(3),atm(1)%dxzv(3))
  r=[4.0_ldp,2.0_ldp,1.0_ldp];t=[source_t(1),sqrt(product(source_t)),source_t(2)]
  pop_atom=[source_density(1),2e13_ldp,source_density(2)];pop_species=0;pop_species(:,1)=pop_atom
  argument=' ';call get_command_argument(1,argument)
  do format_number=1,5
    dissolve=format_number/=5
    if(format_number==4)then
      expected(2,1)=0
      expected(1,1)=source_density(1)-source_ne(1)
    end if
    call comp_lev_dis_blk(source_ne,source_ne,source_t,dissolve,2)
    call ltepop_wld_v2(lte,loglte,occupation,atm(1)%edgexzv_f,atm(1)%gxzv_f, &
         1.0_ldp,1.0_ldp,2,source_ne,source_ne,source_t,2)
    dc=log(max(expected,tiny(1.0_ldp)))-loglte
    where(expected==0)dc=-huge(1.0_ldp)
    do k=1,2
      fraction(1:2,k)=expected(:,k)/source_density(k)
      fraction(3,k)=source_ne(k)/source_density(k)
    end do
    middle=sqrt(fraction(:,1)*fraction(:,2))
    if(format_number>=4)middle(2)=0.5_ldp*sum(fraction(2,:))
    middle=middle/sum(middle)
    do i=1,2
      if(i==1)then
        open(newunit=lu,file='T_IN',status='replace')
      else
        open(newunit=lu,file='HX_IN',status='replace')
      end if
      select case(format_number)
      case(1,4,5)
        write(lu,'(A)')'24-FEB-2004 !Format date'
      case(2)
        write(lu,'(A)')'10-Dec-2010 !Format date'
      case(3)
        write(lu,'(A)')'18-Nov-2010 !Format date'
      end select
      write(lu,*)1.0_ldp,1.0_ldp,2,2
      do k=1,2
        norm=1
        if(trim(argument)=='mismatch'.and.i==2)norm=1.01_ldp
        write(lu,*)source_r(k)*norm,source_ne(k),source_ne(k),source_t(k),0.0_ldp,1.0_ldp,1.0_ldp
        select case(format_number)
        case(1,4,5)
          write(lu,*)exp(dc(:,k))
        case(2)
          write(lu,*)dc(:,k)/log(10.0_ldp)
        case(3)
          write(lu,*)dc(:,k)
        end select
      end do
      close(lu)
    end do
    call read_population_estimates(3,dissolve,10,6)
    if(maxval(abs(atm(1)%xzv_f(:,1)-expected(:,1))/max(expected(:,1),tiny(1.0_ldp)))>1e-8_ldp)error stop 'POP original outer node'
    if(maxval(abs(atm(1)%xzv_f(:,3)/expected(:,2)-1))>1e-8_ldp)error stop 'POP original inner node'
    if(maxval(abs(atm(1)%xzv(:,2)/pop_atom(2)/middle(1:2)-1))>1e-8_ldp)error stop 'POP midpoint'
    if(maxval(abs(ed/atm(1)%dxzv-1))>1e-10_ldp)error stop 'Charge conservation'
    if(maxval(abs((sum(atm(1)%xzv,dim=1)+atm(1)%dxzv)/pop_atom-1))>1e-12_ldp) &
         error stop 'Element conservation'
    if(size(b_lev_dis)/=3)error stop 'Occupation storage on new grid'
    print *, 'PASS POP nodes, midpoint, charge and element conservation; format',format_number
  end do
end program
integer function error_lu()
 error_lu=6
end function
