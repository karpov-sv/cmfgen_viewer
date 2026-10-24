program lambda_fixture
 use set_kind_module
 use mod_cmfgen,only:atm,pop_atom
 use control_variable_mod,only:compute_ba,lambda_iteration,new_line_ba,n_par,xrays,scl_line_cool_rates,scl_line_density_limit,verbose_output
 use steq_data_mod,only:se,ba_t
 use line_vec_mod,only:vec_id,vec_mnl_f,vec_mnup_f
 use line_mod,only:end_res_zone,weak_line,sim_nup,sim_nl,line_opac_con,gldgu,line_emis_con,sim_line_pointer,eina,jbar_sim,chil_mat,etal_mat,u_star_ratio,l_star_ratio,znet_sim,line_qw_sum,ave_energy,resonance_zone
 implicit none
 interface
  subroutine update_ba_for_line(fl,fqw,freq_indx,pops,jrec,djrecdt,jphot, &
      nd,nt,num_bnds,nion,diag_indx,tx_offset,max_sim,nm,ncf,nlf,luer, &
      final_constant_cross,lst_iteration)
   use set_kind_module,only:ldp
   implicit none
   integer::freq_indx,nd,nt,num_bnds,nion,diag_indx,tx_offset,max_sim,nm,ncf,nlf,luer
   real(ldp)::fl,fqw,pops(nt,nd),jrec(nd),djrecdt(nd),jphot(nd)
   logical::final_constant_cross,lst_iteration
  end subroutine
 end interface
 integer,parameter::nd=2,nt=5
 real(ldp)::pops(nt,nd),jr(nd),dj(nd),jp(nd),ups(5),w(3),rad(3)
 integer::c,k,j
 allocate(pop_atom(nd),atm(1)%xzv_f(2,nd),atm(1)%f_to_s_xzv(2),se(1)%ba(nt,nt,1,nd),ba_t(nt,1,nd))
 allocate(end_res_zone(1),weak_line(1),resonance_zone(1),sim_nup(1),sim_nl(1),line_opac_con(1),gldgu(1),line_emis_con(1),sim_line_pointer(1),eina(1),ave_energy(nt))
 allocate(vec_id(1),vec_mnl_f(1),vec_mnup_f(1))
 allocate(jbar_sim(nd,1),chil_mat(nd,1),etal_mat(nd,1),u_star_ratio(nd,1),l_star_ratio(nd,1),znet_sim(nd,1),line_qw_sum(nd,1))
 compute_ba=.true.;lambda_iteration=.true.;new_line_ba=.false.;n_par=100;xrays=.false.
 scl_line_cool_rates=.false.;scl_line_density_limit=1.e99_ldp;verbose_output=.false.
 end_res_zone=.true.;resonance_zone=.true.;weak_line=.false.
 sim_nl=1;sim_nup=2;sim_line_pointer=1;vec_id=1;vec_mnl_f=1;vec_mnup_f=2
 atm(1)%f_to_s_xzv=[1,2];line_opac_con=2.4e-12_ldp;gldgu=.4_ldp;line_emis_con=3.7e-4_ldp;eina=1.234e8_ldp
 u_star_ratio=.7_ldp;l_star_ratio=1.2_ldp;ave_energy=1;pop_atom=1.e4_ldp
 ups=[1.e-4_ldp,1.e-20_ldp,1.e-60_ldp,1.e-128_ldp,10._ldp]
 w=[.13_ldp,.27_ldp,.51_ldp];rad=[.76_ldp,1.37_ldp,2.11_ldp]*1.e-6_ldp
 jr=0;dj=0;jp=0
 do c=1,5
 pops=1;pops(1,:)=.8_ldp;pops(2,:)=ups(c);se(1)%ba=0;ba_t=0
 atm(1)%xzv_f(1,:)=l_star_ratio(:,1)*pops(1,:);atm(1)%xzv_f(2,:)=u_star_ratio(:,1)*pops(2,:)
 chil_mat(:,1)=line_opac_con(1)*(atm(1)%xzv_f(1,:)-gldgu(1)*atm(1)%xzv_f(2,:))
 etal_mat(:,1)=line_emis_con(1)*atm(1)%xzv_f(2,:)
 znet_sim=0;jbar_sim=0;line_qw_sum=0
 do k=1,nd
 do j=1,3
 znet_sim(k,1)=znet_sim(k,1)+w(j)*(1-rad(j)*(1._ldp-.17_ldp*(k-1))*chil_mat(k,1)/etal_mat(k,1))
 jbar_sim(k,1)=jbar_sim(k,1)+w(j)*rad(j)*(1._ldp-.17_ldp*(k-1))
 line_qw_sum(k,1)=line_qw_sum(k,1)+w(j)
 enddo
 enddo
 call update_ba_for_line(2._ldp,1._ldp,1,pops,jr,dj,jp,nd,nt,1,1,1,5,1,8,2,1,6,.false.,.false.)
 do k=1,nd
 write(*,'(2I4,5ES28.17E3)')c,k,ups(c),-se(1)%ba(2,2,1,k),se(1)%ba(2,1,1,k),sum(se(1)%ba(1:2,2,1,k)),sum(se(1)%ba(1:2,1,1,k))
 enddo
 enddo
end program
subroutine tune(i,label)
 integer::i
 character(*)::label
end subroutine
