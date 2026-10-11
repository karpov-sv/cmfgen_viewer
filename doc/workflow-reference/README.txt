Dear Bhawna,

to change log g in model is the most difficult change in CMFGEN. To change \dot M or velocity is easier.  Here are the main steps. I write name directories the same as I use.

1) create directory lte2. I have  ~/CMFGEN2023/models/ostar/lte2
In lte2 there are files:  GRID_PARAMS  ltebat.sh

My lte2 directory in the attachment

2) for example -- I create new model model_poems1025 from old model_poems1005
---------------------
mkdir model_poems1025
mkdir model_poems1025/obs
cp obs2/* model_poems1025/obs
cp clean.sh model_poems1025/obs
cp clean.sh model_poems1025/
./cpmod.sh model_poems1005 model_poems1025
cp IN_ITS model_poems1025/
cd model_poems1025
chmod 755 *
chmod 755 */*
cp RVSIG_COL RVSIG_COL_OLD
cp ../HYDRO_DEFAULTS HYDRO_DEFAULTS
mkdir lte ; cp VADAT ./lte ; cp batch.sh ./lte/ ; cp MODEL_SPEC ./lte ;  cp ../clean.sh ./lte
cd lte
cp ../../lte2/GRID_PARAMS .
cp ../../lte2/ltebat.sh

----------------
all these command are in the attached file cmfgen_make_model2.sh

3) put in model_poems1025/lte/ file HYDRO_PARAMS (file attached)

4) change VADAT (in model_poems1025/lte/)
in VADAT put 
3.900D0      [TEFF]
3.5500       [LOGG]

5) change MODEL_SPEC (in model_poems1025/lte/)
925             [ND]                !Number of depth points
15             [NC]                !Number of core rays
940             [NP]                !Number of impact parameters [ND+NC]

6) start  ltebat.sh (calculation will take ~50 min)
./ltebat.sh

7) Now HYDRO_PARAMS already reduced -- and you may use my file (attached). But usually reduce file HYDRO_PARAMS -- put log g as you need.Also compare/check other parameters in the HYDRO_PARAMS file (such as Teff, L*) they should match the values from  file MOD_SUM of the old model (in my case model_poems1005). 

8) after thatwind_hyd.exe ($cmfdist = /home/maryeva/CMFGEN2023/cur_cmf/exe)
/home/maryeva/CMFGEN2023/cur_cmf/exe/wind_hyd.exe

> $cmfdist/exe/wind_hyd.exe
> /null
> e
> 70 (number of grid points)
> enter      (or put 100 (tau max for model))

8) open file RVSIG_COL_NEW and check luminosity -- if luminosity is different from value in HYDRO_PARAMS -- go to HYDRO_PARAMS file and change [REF_R]. -- repet wind_hyd.exe
if value of  luminosity is correct then:

-- take from HYDRO_PARAMS   value Ratio of inner to outer radius is:  109.79561244 and put this value in VADAT as [RMAX] (please take a look to VADAT in the attachment)

 ./clean.sh ; rm *OUT ; rm POP*
 cp ROSSELAND_LTE_TAB ../ ; cp RVSIG_COL_NEW ../ ; cp RVSIG_COL_NEW ../RVSIG_COL ; cp VADAT ../
cd ..

9) now in model_poems1025 start calculations:
./batch.sh

I hope it should work!
Let me know about your results.
