program test_profile
 use set_kind_module
 implicit none
 integer::np,nf,npv,nfv,ms
 call get_profile_storage_limits_v2(np,nf,npv,nfv,ms,[3],[5],['STARK'],['CMF'],1,10)
 if(np/=1.or.nf/=3.or.ms/=1)error stop 'Single Stark line storage V2'
 call get_profile_storage_limits(np,nf,[3],[5],['STARK'],1,10)
 if(np/=1.or.nf/=3)error stop 'Single Stark line storage'
 call get_profile_storage_limits_v2(np,nf,npv,nfv,ms,[1,3],[2,5],['DOP  ','STARK'],['CMF','CMF'],2,10)
 if(np/=1.or.ms/=1)error stop 'Final Stark line storage V2'
 call get_profile_storage_limits(np,nf,[1,3],[2,5],['DOP  ','STARK'],2,10)
 if(np/=1)error stop 'Final Stark line storage'
 call get_profile_storage_limits_v2(np,nf,npv,nfv,ms,[3,4],[5,6],['STARK','STARK'],['CMF','CMF'],2,10)
 if(np/=2.or.ms/=2)error stop 'Overlapping Stark lines'
 call get_profile_storage_limits_v2(np,nf,npv,nfv,ms,[3],[5],['VOIGT'],['CMF'],1,10)
 if(np/=0.or.npv/=1.or.nfv/=3.or.ms/=1)error stop 'Voigt storage'
 call get_profile_storage_limits_v2(np,nf,npv,nfv,ms,[3],[5],['STARK'],['SOB'],1,10)
 if(np/=0.or.ms/=0)error stop 'Sobolev storage'
 print *, 'PASS single, final, overlapping, Voigt and Sobolev profiles'
end program
