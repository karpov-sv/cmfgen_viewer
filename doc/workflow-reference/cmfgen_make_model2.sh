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
cp ../../lte2/HYDRO_PARAMS .



# cd lte
# cp ../../lte2/GRID_PARAMS .
# cp ../../lte2/HYDRO_PARAMS .
# ./clean.sh ; rm *OUT ; rm POP*
# cp ROSSELAND_LTE_TAB ../ ; cp RVSIG_COL_NEW ../ ; cp RVSIG_COL_NEW ../RVSIG_COL
# cd ..

