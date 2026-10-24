! Actual line kernel; prescribed radiation derivatives.
! Continuum BA_UPDATE/ADD_PAR and profiling are stubbed below.
program lambda_fixture
 use set_kind_module
 use mod_cmfgen,only:atm,pop_atom,num_ions,species_pres,t,ed
 use control_variable_mod,only:compute_ba,lambda_iteration,new_line_ba,n_par,xrays,scl_line_cool_rates,scl_line_density_limit,verbose_output,include_dsldt,znet_var_limit
 use steq_data_mod,only:se,ba_t
 use line_vec_mod,only:vec_id,vec_mnl_f,vec_mnup_f
 use line_mod,only:end_res_zone,weak_line,sim_nup,sim_nl,line_opac_con,gldgu,line_emis_con,sim_line_pointer,eina,jbar_sim,chil_mat,etal_mat,u_star_ratio,l_star_ratio,znet_sim,line_qw_sum,ave_energy,resonance_zone,line_qw_sim,low_pointer,up_pointer,var_in_use_cnt,var_lev_id,use_this_var_mat,imp_trans_vec,do_this_tx_matrix,du_rat_dt,dl_rat_dt
 use var_rad_mod,only:vj,dj_loc,dz,dz_pops
 use opac_mod,only:vchi,veta,vchi_all,veta_all,esec,eta_noscat,chi_noscat
 use radiation_mod,only:rj,ta
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
 integer,parameter::nd=4,nt=5
 real(ldp)::pops(nt,nd),jr(nd),dj(nd),jp(nd),ups(5),w(3),rad(3)
 integer::c,k,j,m,q,b,l,ix
 real(ldp)::fac,sh
 allocate(pop_atom(nd),atm(1)%xzv_f(2,nd),atm(1)%f_to_s_xzv(2),se(1)%ba(nt,nt,3,nd),ba_t(nt,3,nd))
 allocate(end_res_zone(1),weak_line(1),resonance_zone(1),sim_nup(1),sim_nl(1),line_opac_con(1),gldgu(1),line_emis_con(1),sim_line_pointer(1),eina(1),ave_energy(nt))
 allocate(vec_id(1),vec_mnl_f(1),vec_mnup_f(1))
 allocate(jbar_sim(nd,1),chil_mat(nd,1),etal_mat(nd,1),u_star_ratio(nd,1),l_star_ratio(nd,1),znet_sim(nd,1),line_qw_sum(nd,1))
 allocate(vj(nt,3,nd),dj_loc(8,3,nd),dz(8,3,nd,1),dz_pops(nt,3,nd))
 allocate(vchi(nt,nd),veta(nt,nd),vchi_all(nt,nd),veta_all(nt,nd),esec(nd),eta_noscat(nd),chi_noscat(nd))
 allocate(rj(nd),ta(nd),t(nd),ed(nd),line_qw_sim(nd,1),du_rat_dt(nd,1),dl_rat_dt(nd,1))
 allocate(low_pointer(1),up_pointer(1),var_in_use_cnt(8),var_lev_id(8),use_this_var_mat(8),imp_trans_vec(8),do_this_tx_matrix(8))
 allocate(se(1)%lnk_to_f(nt),se(1)%lnk_to_iv(nt))
 se(1)%n_iv=nt;se(1)%lnk_to_f=[1,2,3,4,5];se(1)%lnk_to_iv=[1,2,3,4,5]
 atm(1)%eqxzv=1;atm(1)%nxzv=2;num_ions=1;species_pres=.false.
 vchi=0;veta=0;vchi_all=0;veta_all=0;esec=0;eta_noscat=0;chi_noscat=1;t=1;ed=1;vj=0;dj_loc=0
 low_pointer=7;up_pointer=7;var_in_use_cnt=0;var_in_use_cnt(7)=2;var_lev_id=0;var_lev_id(7)=1
 imp_trans_vec=.false.;do_this_tx_matrix=.true.;du_rat_dt=0;dl_rat_dt=0
 include_dsldt=.false.;znet_var_limit=0
 compute_ba=.true.;lambda_iteration=.true.;new_line_ba=.false.;n_par=100;xrays=.false.
 scl_line_cool_rates=.false.;scl_line_density_limit=1.e99_ldp;verbose_output=.false.
 end_res_zone=.true.;resonance_zone=.true.;weak_line=.false.
 sim_nl=1;sim_nup=1;sim_line_pointer=1;vec_id=1;vec_mnl_f=1;vec_mnup_f=2
 atm(1)%f_to_s_xzv=[1,1];line_opac_con=2.4e-12_ldp;gldgu=.4_ldp;line_emis_con=3.7e-4_ldp;eina=1.234e8_ldp
 u_star_ratio=.7_ldp;l_star_ratio=1.2_ldp;ave_energy=1;pop_atom=1.e4_ldp
 ups=[1.e-4_ldp,1.e-20_ldp,1.e-60_ldp,1.e-128_ldp,10._ldp]
 w=[.13_ldp,.27_ldp,.51_ldp];rad=[.76_ldp,1.37_ldp,2.11_ldp]*1.e-6_ldp
 jr=0;dj=0;jp=0
 do q=1,4
 include_dsldt=q>=3;znet_var_limit=0
 if(q==4)znet_var_limit=1.e300_ldp
 dl_rat_dt=0;du_rat_dt=0
 if(q>=3)then
 dl_rat_dt=.02_ldp;du_rat_dt=.03_ldp
 endif
 do m=1,3
 lambda_iteration=m==1;weak_line=m==2
 do c=1,5
 pops=1;pops(1,:)=.8_ldp;pops(2,:)=ups(c);se(1)%ba=0;ba_t=0
 atm(1)%xzv_f(1,:)=l_star_ratio(:,1)*pops(1,:);atm(1)%xzv_f(2,:)=u_star_ratio(:,1)*pops(1,:)
 chil_mat(:,1)=line_opac_con(1)*(atm(1)%xzv_f(1,:)-gldgu(1)*atm(1)%xzv_f(2,:))
 etal_mat(:,1)=line_emis_con(1)*atm(1)%xzv_f(2,:)
 znet_sim=0;jbar_sim=0;line_qw_sum=0;dz=0;end_res_zone=.false.
 do j=1,3
 do k=1,nd
 rj(k)=rad(j)*(1._ldp-.17_ldp*(k-1));line_qw_sim(k,1)=w(j)
 znet_sim(k,1)=znet_sim(k,1)+w(j)*(1-rj(k)*chil_mat(k,1)/etal_mat(k,1))
 jbar_sim(k,1)=jbar_sim(k,1)+w(j)*rj(k)
 line_qw_sum(k,1)=line_qw_sum(k,1)+w(j)
 enddo
 dj_loc=0;vchi=0;veta=0;esec=0
 if(q>=2)then
 vchi(3,:)=.2_ldp;veta(3,:)=-.3_ldp;esec=1
 do k=1,nd
 sh=rad(j)/1.e-6_ldp*(1._ldp-.17_ldp*(k-1))
 do b=max(3-k,1),min(6-k,3)
 fac=.1_ldp
 if(b==2)fac=1
 dj_loc(3,b,k)=fac*sh*.25e7_ldp
 dj_loc(4,b,k)=fac*sh*.12e7_ldp
 dj_loc(5,b,k)=fac*sh*.4e7_ldp
 dj_loc(6,b,k)=fac*sh*.09e7_ldp
 dj_loc(7,b,k)=fac*sh*2.e7_ldp
 dj_loc(8,b,k)=fac*sh*(-1.3e7_ldp)
 enddo
 enddo
 endif
 end_res_zone=j==3
 call update_ba_for_line(2._ldp,1._ldp,j,pops,jr,dj,jp,nd,nt,3,1,2,5,1,8,3,1,6,.false.,.false.)
 enddo
 do k=1,nd
 do b=max(3-k,1),min(6-k,3)
 l=k+b-2
 do ix=1,nt
 write(*,'(6I4,3ES28.17E3)')q,m,c,k,l,ix,-se(1)%ba(2,ix,b,k),-ba_t(ix,b,k),sum(se(1)%ba(1:2,ix,b,k))
 enddo
 enddo
 enddo
 enddo
 enddo
 enddo
end program
subroutine tune(i,label)
 integer::i
 character(*)::label
end subroutine

! Prescribed fixed radiation and no continuum derivatives in this line-only limit.
subroutine ba_update_v7
end subroutine
subroutine add_par_to_full_v2
end subroutine
