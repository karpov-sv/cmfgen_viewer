module mod_cmfgen
 use set_kind_module
 implicit none
 type atom_type
 integer::nxzv_f
 real(ldp)::gxzv_f(1)
 end type
 integer::num_species=1
 integer::species_beg_id(1)=[1],species_end_id(1)=[4]
 type(atom_type)::atm(4)
 character(6)::ion_id(4)=['CI    ','CII   ','CIII  ','CIV   ']
 character(6)::species(1)=['C     ']
end module
module control_variable_mod
 logical::auto_add_ion_stages=.true.
end module
