# CMFGEN Comprehensive File Inventory

Derived from `CMFGEN_comprehensive_file_inventory_2026-02-09.txt` (technical content only).

## Conventions
- READ: file consumed by code/script.
- WRITE: file created/overwritten by code/script.
- UPDATE: in-place keyword update, rename, move, or copy to canonical alias.
- Names are opened as working-directory paths unless explicit prefix is used.
- Format tags:
    - KEYWORD_ASCII: line-oriented config, usually "value [KEY]".
    - VECTOR_ASCII: labeled vector blocks.
    - TABLE_ASCII: row/column table text.
    - LOG_ASCII: free-text log/trace.
    - BIN_DIRECT: direct-access unformatted binary (often with *_INFO sidecar).
    - BIN_SEQ: sequential unformatted binary.

## Core Model Configuration and Run-Control Files

### CMFGEN main controls
1. MODEL_SPEC
    - Role: READ by CMFGEN startup; READ by CMF_FLUX and LTE for model dimensions/options.
    - Producer/consumer:
        - READ: new_main/cmfgen.f:291
        - READ: obs/cmf_flux_v5.f:413-420
        - READ: lte_hydro/lte.f:285
    - Purpose: ND/NC/NP/NUM_BNDS limits and per-ion stage descriptors (*_ISF, *_NSF).
    - Format: KEYWORD_ASCII.
    - Example fields: [ND], [NC], [NP], [NUM_BNDS], [NCF_MAX], ion [*_ISF].

2. VADAT
    - Role: READ and sometimes UPDATE.
    - Producer/consumer:
        - READ: new_main/mod_subs/rd_control_variables.f:46
        - UPDATE: new_main/cmfgen_sub.f:1030-1031, 4555-4623, 4682
        - UPDATE: new_main/subs/do_cmf_hydro_v2.f:361-362, 385, 407-408, 1107-1110
    - Purpose: top-level physics/control switches (velocity law, hydro, clumping, X-rays, etc.).
    - Format: KEYWORD_ASCII.

3. IN_ITS
    - Role: READ and UPDATE.
    - Producer/consumer:
        - READ: new_main/cmfgen_sub.f:545, 4695
        - UPDATE: new_main/cmfgen_sub.f:4563, 4682 (e.g., [DO_LAM_IT])
    - Purpose: iteration-cycle controls ([NUM_ITS], lambda iteration toggles).
    - Format: KEYWORD_ASCII.

4. HYDRO_DEFAULTS
    - Role: READ and UPDATE when hydro iterations are enabled.
    - Producer/consumer:
        - READ check: new_main/subs/check_hydro_def.f:17
        - READ: new_main/subs/do_cmf_hydro_v2.f:258
        - UPDATE: new_main/cmfgen_sub.f:931; new_main/subs/do_cmf_hydro_v2.f:1097-1098, 362, 408-409
    - Purpose: hydro-iteration counters/options ([N_ITS], [ITS_DONE], [HYDRO_OPT], etc.).
    - Format: KEYWORD_ASCII.

5. ADJUST_R_DEFAULTS
    - Role: READ conditionally.
    - Producer/consumer: new_main/mod_subs/adjust_r_grid_v4.f:105.
    - Purpose: radial-grid adjustment controls.
    - Format: KEYWORD_ASCII.

6. RDINR / RVSIG_COL / deKOTER / input_hydro.dat
    - Role: READ conditionally by velocity-law branches.
    - Producer/consumer:
        - RDINR: subs/starpcyg_v3.f:119 and related velocity readers.
        - RVSIG_COL/deKOTER: newsubs/rd_rv_file_v2.f:62, 127.
        - input_hydro.dat: new_main/mod_subs/set_abund_clump.f:310.
    - Purpose: supplied velocity/radius structures.
    - Format: TABLE_ASCII or VECTOR_ASCII (profile-like text tables).

7. GRID_PARAMS
    - Role: READ in LTE.
    - Producer/consumer: lte_hydro/lte.f:272.
    - Purpose: temperature/electron-density grid controls.
    - Format: KEYWORD_ASCII-like numeric block.

8. HYDRO_PARAMS
    - Role: READ by wind_hyd executable.
    - Producer/consumer: lte_hydro/wind_hyd.f:227.
    - Purpose: hydro model setup (logg, mass, mdot, v_inf, beta, etc.).
    - Format: KEYWORD_ASCII.

9. IT_SPECIFIER
    - Role: READ optionally.
    - Producer/consumer: subs/specify_it_cycle_v3.f:59.
    - Purpose: per-iteration override behavior.
    - Format: KEYWORD_ASCII/TABLE_ASCII (control list).

### CMF_FLUX controls
1. IN_FILE
    - Role: READ by cmf_flux executable stdin redirection.
    - Producer/consumer: model obs scripts pass it to cmf_flux (`$PROG_CMF_OBS < IN_FILE`).
    - Purpose: RVTJ filename, mass, line-selection toggle.
    - Format: KEYWORD_ASCII.

2. CMF_FLUX_PARAM_INIT
    - Role: READ by scripts, transformed to CMF_FLUX_PARAM.
    - Producer/consumer:
        - script edit source: obs/bat_ins.sh, obs/batobs.sh
        - generator: misc/create_batobs_ins.f
    - Purpose: baseline cmf_flux options.
    - Format: KEYWORD_ASCII.

3. CMF_FLUX_PARAM
    - Role: READ by cmf_flux; WRITE/UPDATE by scripts.
    - Producer/consumer:
        - READ: obs/cmf_flux_v5.f:551
        - parsed by: obs/rd_cmf_flux_controls.f
        - UPDATE/WRITE via sed in model scripts.
    - Purpose: observer-frame run controls (frequency grid, ES handling, Sobolev options).
    - Format: KEYWORD_ASCII.

## Atomic and Microphysics Data Inputs

### Shared atomic/microphysics files
1. HYD_L_DATA, GBF_N_DATA
    - Role: READ required by CMFGEN and CMF_FLUX.
    - Producer/consumer:
        - reader call: new_main/cmfgen_sub.f:532; obs/cmf_flux_v5.f:265
        - file opens: newsubs/rd_hyd_bf_data.f:36, 103
    - Purpose: hydrogenic bound-free gaunt/cross-section data.
    - Format: TABLE_ASCII.

2. TWO_PHOT_DATA
    - Role: READ conditionally (if INCL_TWO_PHOT).
    - Producer/consumer: new_main/mod_subs/two_phot_mod.f:125.
    - Purpose: two-photon transitions metadata/rates.
    - Format: TABLE_ASCII.

3. CHG_EXCH_DATA
    - Role: READ conditionally (if charge exchange enabled).
    - Producer/consumer: new_main/subs/chg/rd_chg_exch_v3.f:51.
    - Purpose: charge-exchange reaction rates.
    - Format: TABLE_ASCII.

4. XRAY_PHOT_FITS
    - Role: READ (CMFGEN path).
    - Producer/consumer: newsubs/xray_data_mod.f:59, called from cmfgen_sub.
    - Purpose: X-ray photoionization fit tables.
    - Format: TABLE_ASCII.

5. RS_XRAY_FLUXES
    - Role: READ when XRAYS=.TRUE. and not FF_XRAYS path.
    - Producer/consumer: newsubs/rd_xray_spec.f:77.
    - Purpose: adopted X-ray emission spectrum bins.
    - Format: TABLE_ASCII.

6. FULL_STRK_LIST, LEMKE_HI, HeI_IR_STRK, DS_STRK, BS_HHE, REVISED_LAMBDAS
    - Role: READ by observer/spectral broadening paths.
    - Producer/consumer: linked by obs/batobs.sh and consumed in line-profile code.
    - Purpose: Stark and wavelength correction datasets.
    - Format: TABLE_ASCII.

### Per-ion atomic families (required/conditional by ion presence)
1. <ION>_F_OSCDAT
    - Role: READ.
    - Producer/consumer: GENOSC_V9 called in CMFGEN and CMF_FLUX.
    - Purpose: oscillator strengths, level definitions, radiative rates.
    - Format: TABLE_ASCII with headers.

2. <ION>_F_TO_S
    - Role: READ when super-level mapping is needed.
    - Producer/consumer: RD_F_TO_S_IDS* routines.
    - Purpose: full-level to super-level mapping.
    - Format: TABLE_ASCII index mapping.

3. PHOT<ION>_A / PHOT<ION>_B / ...
    - Role: READ.
    - Producer/consumer: RDPHOT_GEN_V2.
    - Purpose: photoionization cross sections by route blocks.
    - Format: TABLE_ASCII.

4. <ION>_COL_DATA
    - Role: READ.
    - Producer/consumer: GET_COL_REF + GEN_OMEGA_RD_V2.
    - Purpose: collisional transitions/rates.
    - Format: TABLE_ASCII.

5. DIE<ION>
    - Role: READ conditionally (dielectronic data).
    - Producer/consumer: RDGENDIE_V4 or RD_PHOT_DIE_V1 branches.
    - Purpose: dielectronic recombination channels.
    - Format: TABLE_ASCII.

6. <ION>_AUTO_DATA
    - Role: READ optionally.
    - Producer/consumer: STEQ_AUTO_V2 branch.
    - Purpose: autoionization/associated rates.
    - Format: TABLE_ASCII.

### Optional/auxiliary CMFGEN input families
1. CFDAT
    - Role: READ conditionally.
    - Producer/consumer: new_main/mod_subs/set_frequency_grid_v2.f:344.
    - Purpose: external continuum frequency list input when RD_CONT_FREQ/RD_CF_FILE mode is on.
    - Format: TABLE_ASCII.

2. GRID_PARAMS or PROF_T_ED
    - Role: READ conditionally in profile-grid setup.
    - Producer/consumer:
        - GRID_PARAMS path in set_frequency_grid_v2 logic
        - PROF_T_ED via subs/rd_t_ed.f
    - Purpose: temperature/electron-density profile grids for frequency/profile setup.
    - Format: TABLE_ASCII.

3. FIN_CAL_GRID
    - Role: READ optionally for initialization in LTE-estimate paths.
    - Producer/consumer: new_main/mod_subs/set_new_model_estimates.f:219.
    - Purpose: seed structure for new-model estimate generation.
    - Format: TABLE_ASCII.

4. GREY_SCL_FAC_IN / GREY_SCL_FAC
    - Role: READ optionally.
    - Producer/consumer: subs/scale_grey.f (primary + fallback open).
    - Purpose: scaling factors for grey/J initialization.
    - Format: TABLE_ASCII.

5. SN_HYDRO_DATA
    - Role: READ in SN hydro/abundance setup paths.
    - Producer/consumer: new_main/subs/rd_sn_data.f:91; set_rv_hydro_model_v3.f:117.
    - Purpose: supernova hydro structure input for SN mode.
    - Format: TABLE_ASCII.

6. NUC_DECAY_DATA
    - Role: READ conditionally when radioactive decay is enabled.
    - Producer/consumer: new_main/subs/rd_nuc_decay_data_v2.f:42.
    - Purpose: decay-chain and deposition controls for time-dependent/SN models.
    - Format: TABLE_ASCII.

7. arnaud_rothenflug.dat
    - Role: READ conditionally by non-thermal modules.
    - Producer/consumer: new_main/subs/non_therm/read_arnaud_ion_data.f90:38.
    - Purpose: non-thermal ionization/recombination coefficients.
    - Format: TABLE_ASCII.

8. NT_CROSEC_SCLFAC and NT_ION_CROSEC_SCLFAC
    - Role: READ conditionally.
    - Producer/consumer: new_main/subs/non_therm/rd_nt_crosec_sclfac_v2.f90.
    - Purpose: scaling factors for non-thermal cross sections.
    - Format: TABLE_ASCII/KEYWORD_ASCII.

9. NON_THERM_DEGRADATION_SPEC
    - Role: READ conditionally.
    - Producer/consumer: rd_non_therm_elec_spec_v1.f90.
    - Purpose: non-thermal degradation spectrum input.
    - Format: TABLE_ASCII.

10. SOL_ABUNDANCE
    - Role: READ optionally (fallback defaults exist).
    - Producer/consumer: subs/rd_sol_abund_scale.f:50.
    - Purpose: solar abundance scale reference for reporting/normalization.
    - Format: TABLE_ASCII.

11. INCIDENT_INTENSITY
    - Role: READ only in specific plane-parallel boundary paths.
    - Producer/consumer: plane/get_ibound.f:41.
    - Purpose: external incident boundary radiation.
    - Format: TABLE_ASCII/VECTOR_ASCII.

## CMFGEN Input/State Bootstrap Files for New or Continued Runs

1. <ION>_IN, T_IN, GAMMAS_IN
    - Role: READ for new-model initialization.
    - Producer/consumer:
        - <ION>_IN: regrid_log_dc_v1.f
        - T_IN: regrid_t_ed_v3.f / init_temp_v2.f
        - GAMMAS_IN: getelec_v2.f
    - Purpose: initial populations, thermal structure, electron density seed.
    - Format: VECTOR_ASCII / TABLE_ASCII.

2. POINT1, POINT2, SCRTEMP
    - Role: READ/WRITE continuation state.
    - Producer/consumer: subs/scr_read_v2.f:87,106,136 (read) and 449,460 (write pointers).
    - Purpose:
        - POINT1/POINT2: pointer metadata to restart record.
        - SCRTEMP: restart binary state.
    - Format:
        - POINT1/POINT2: KEYWORD_ASCII-like compact pointer record.
        - SCRTEMP: BIN_DIRECT/BIN_SEQ internal unformatted state (`file` reports "data").

3. NEW_POINT1, NEW_POINT2, NEW_SCRTEMP
    - Role: WRITE temporary continuation outputs before promotion.
    - Producer/consumer: subs/scr_read_v2.f:690,701,583+.
    - Purpose: staging restart state before script promotion to POINT*/SCRTEMP.
    - Format: POINT*: KEYWORD_ASCII; NEW_SCRTEMP: binary.

4. EDDFACTOR and EDDFACTOR_INFO (and similar *_INFO sidecars)
    - Role: READ/WRITE internal radiation state when relevant paths are enabled.
    - Producer/consumer:
        - open_rw_eddfactor.f + write_direct_info_v3.f
        - called from cmfgen_sub and cmf_flux_sub paths.
    - Purpose: direct-access continuum/J storage plus portable metadata.
    - Format:
        - EDDFACTOR: BIN_DIRECT
        - EDDFACTOR_INFO: KEYWORD_ASCII sidecar (record length/word size/date metadata)

## Core CMFGEN Science Outputs and Diagnostics

### Canonical primary outputs
1. MODEL
    - WRITE: new_main/cmfgen_sub.f:803
    - Purpose: run summary, species/equation descriptors, appended input headers.
    - Format: TABLE_ASCII + LOG_ASCII sections.

2. MOD_SUM
    - WRITE: new_main/cmfgen_sub.f:4091
    - Purpose: compact final model summary for quick inspection.
    - Format: KEYWORD_ASCII/TABLE_ASCII summary text.

3. RVTJ
    - WRITE: new_main/cmfgen_sub.f:4312
    - Purpose: primary radial structure profile bundle (R, V, sigma, ED, T, means, densities, selected populations).
    - Format: VECTOR_ASCII with labeled sections.

4. OBSFLUX
    - WRITE: new_main/cmfgen_sub.f:3027, 3715
    - Purpose: continuum frequencies + observed intensity vector + luminosity vector.
    - Format: VECTOR_ASCII.

5. MEANOPAC
    - WRITE: new_main/cmfgen_sub.f:3081
    - Purpose: Rosseland/flux/electron-scattering mean opacity diagnostics and tau scales.
    - Format: TABLE_ASCII with header row.

6. HYDRO
    - WRITE via HYDRO_TERMS:
        - call in cmfgen_sub
        - file open: subs/hydro_terms_v5.f:118
    - Purpose: momentum-balance terms, radiative acceleration diagnostics.
    - Format: TABLE_ASCII.

7. GAMMAS
    - WRITE: new_main/cmfgen_sub.f:4496-4499
    - Purpose: species-electron contribution vectors used as restart/analysis seed.
    - Format: VECTOR_ASCII multi-section.

8. <ION>OUT family
    - WRITE: WRITEDC_V2 call in new_main/cmfgen_sub.f:1485-1490
    - Purpose: per-ion departure coefficient/population outputs.
    - Format: VECTOR_ASCII/TABLE_ASCII (header + depth-resolved blocks).

9. POP<species> family (POPHYD, POPHE, POPNIT, etc.)
    - WRITE: new_main/cmfgen_sub.f:1446-1463 (TMP_STRING='POP'//species)
    - Purpose: per-species density/population bundle with embedded ion blocks.
    - Format: VECTOR_ASCII.

10. OUTGEN, WARNINGS, STEQ_VALS
    - WRITE:
        - OUTGEN: new_main/cmfgen.f:101
        - WARNINGS: new_main/cmfgen.f:108
        - STEQ_VALS: new_main/cmfgen_sub.f:528
    - Purpose: run logs, warnings, iterative correction traces.
    - Format: LOG_ASCII.

### Optional/conditional science diagnostics
1. NETRATE, TOTRATE, EWDATA, LINEHEAT, NEG_OPAC
    - WRITE: new_main/cmfgen_sub.f:1303-1308
    - Purpose: detailed cooling/heating/rate diagnostics.
    - Format: TABLE_ASCII or VECTOR_ASCII.

2. <ION>PRRR family (e.g., He2PRRR, NIVPRRR)
    - WRITE: new_main/cmfgen_sub.f:2969 + WRRECOMCHK_V4
    - Purpose: recombination/photoionization/cooling checks per ion.
    - Format: TABLE_ASCII with sectioned blocks.

3. CORRECTION_SUM, CORRECTION_LINK
    - WRITE:
        - CORRECTION_SUM via solveba_v*.f family (e.g., solveba_v13.f:145)
        - CORRECTION_LINK via new_main/subs/sum_steq_sol.f:44
    - Purpose: nonlinear solver correction statistics and largest links.
    - Format: TABLE_ASCII / LOG_ASCII.

4. COLLISION_SUMMARY
    - WRITE: subs/gen_omega_rd_v2.f:554
    - Purpose: collisional data ingestion summary and missing-transition diagnostics.
    - Format: LOG_ASCII + TABLE_ASCII.

5. AUTO_CHK_<ion>
    - WRITE: new_main/subs/auto/rd_auto_v1.f:182
    - Purpose: utilized autoionization-rate audit.
    - Format: TABLE_ASCII.

6. ADIABAT_CHK
    - WRITE: new_main/subs/eval_temp_ddt_v1.f:253 and related versions
    - Purpose: adiabatic/heating-term diagnostic decomposition.
    - Format: TABLE_ASCII.

7. TWO_PHOT_SUM
    - WRITE: subs/two/steq_ba_two_phot.f:62; ..._v3.f:70
    - Purpose: two-photon transition rates summary when enabled.
    - Format: VECTOR_ASCII / LOG_ASCII.

8. MOM_J_ERRORS
    - WRITE by MOM_J routines (e.g., subs/mom_j_cmf_v6.f:220, v7.f:220)
    - Purpose: moment-equation frequency error report.
    - Format: LOG_ASCII (may be empty file if no errors).

### Hydro/regridding side outputs
1. HYDRO_ITERATION_INFO, HYDRO_OLD_MODEL
    - WRITE: new_main/subs/do_cmf_hydro_v2.f:331, 472
    - Purpose: hydro iteration trace and pre-update model snapshot.
    - Format: LOG_ASCII/TABLE_ASCII.

2. NEW_CALC_GRID, FIN_CAL_GRID, RVSIG_COL, RVSIG_COL_IT_<iter>, RVSIG_COL_NEW
    - WRITE:
        - do_cmf_hydro_v2.f:840,1079,1019/1032
        - wind_hyd.f:754,933,898
    - Purpose: updated/regridded structure profiles.
    - Format: TABLE_ASCII.

3. GREY_SCL_FACOUT (and GREY_SCL_FAC_IN use/update)
    - WRITE: cmfgen_sub.f:3145
    - Purpose: grey scaling factors for subsequent initializations.
    - Format: TABLE_ASCII.

### Time-dependent/SN and matrix-state outputs
1. SN_HYDRO_FOR_NEXT_MODEL
    - WRITE: new_main/cmfgen_sub.f:4442 via OUT_SN_POPS_V3.
    - Purpose: SN hydro + composition state for subsequent time-step model.
    - Format: TABLE_ASCII/VECTOR_ASCII (profile + isotope/species content).

2. CUR_MODEL_DATA
    - WRITE: new_main/subs/write_seq_time_file_v1.f:21
    - Called in CMFGEN SN/time-sequence paths: cmfgen_sub.f:4509, 4628.
    - Purpose: unformatted time-sequence model state handoff.
    - Format: BIN_SEQ (unformatted sequential).

3. JH_AT_CURRENT_TIME (and JH_AT_CURRENT_TIME_INFO sidecar in some workflows)
    - WRITE: enabled by WRITE_JH control (rd_control_variables.f:663), via OUT_JH path.
    - Purpose: radiation-moment handoff between SN time steps.
    - Format: direct-access/binary + optional *_INFO metadata sidecar.
    - Note: exact writer subroutine name is outside the inspected text subset; presence and use
  are confirmed by staging scripts and control flags.

4. BAMAT and BAMATPNT
    - WRITE/READ conditional near-convergence BA matrix caching:
        - write/read calls: cmfgen_sub.f:2943, 3624, 3912, 4062
        - implementation: new_main/subs/store_ba_data_v3.f and read_ba_data_v3.f
    - Purpose: persist linearization matrix blocks between iterations/runs.
    - Format:
        - BAMAT: BIN_SEQ (unformatted sequential)
        - BAMATPNT: KEYWORD_ASCII pointer/metadata

5. Legacy/optional matrix files seen in cleanup scripts
    - Names: BAION, BAIONPNT, BA_STEQ
    - Purpose: legacy BA/ion-equation matrix artifacts from older/alternate flows.
    - Format: binary for matrix bodies, ASCII for pointer files.
    - Note: still removed by clean scripts even if not emitted in every modern run path.

## CMF_FLUX File Inventory

### cmf_flux inputs
1. RVTJ (or selected alternate path)
    - READ: obs/cmf_flux_v5.f:290, 297, 332, 355
    - Purpose: radial model and continuum vectors.
    - Format: VECTOR_ASCII.

2. MODEL
    - READ: obs/cmf_flux_v5.f:382-396 via RD_MODEL_FILE
    - Purpose: species/atomic option metadata (e.g., DIE_AS_LINE, MASS fallback).
    - Format: TABLE_ASCII.

3. MODEL_SPEC
    - READ: obs/cmf_flux_v5.f:413-420
    - Purpose: options store seed (e.g., SL_OPT).
    - Format: KEYWORD_ASCII.

4. CMF_FLUX_PARAM
    - READ: obs/cmf_flux_v5.f:551-558
    - Purpose: synthesis controls.
    - Format: KEYWORD_ASCII.

5. POP<species> files
    - READ default pattern: DIR_NAME + POP + species + extension (obs/cmf_flux_v5.f:450).
    - Purpose: level populations for transfer/spectrum.
    - Format: VECTOR_ASCII.

6. HYD_L_DATA, GBF_N_DATA
    - READ via RD_HYD_BF_DATA call (obs/cmf_flux_v5.f:265).
    - Purpose: hydrogen bound-free data.
    - Format: TABLE_ASCII.

### cmf_flux outputs
1. OUT_FLUX
    - WRITE: obs/cmf_flux_v5.f:89
    - Purpose: execution log/messages for cmf_flux run.
    - Format: LOG_ASCII.

2. OUT_PARAMS
    - WRITE: obs/cmf_flux_v5.f:556
    - Purpose: resolved CMF_FLUX_PARAM values with descriptions.
    - Format: KEYWORD_ASCII report.

3. OBS_FREQ
    - WRITE in cmf_flux flow.
    - Purpose: observer frequency grid (frequency + spacing).
    - Format: TABLE_ASCII (2-column style).

4. OBSFLUX
    - WRITE: obs/cmf_flux_sub_v5.f:1889-1898
    - Purpose: comoving/observer intensity vector package.
    - Format: VECTOR_ASCII.

5. OBSFRAME
    - WRITE: obs/cmf_flux_sub_v5.f:2120-2128
    - Purpose: final observer-frame spectrum used by plotting workflows.
    - Format: VECTOR_ASCII.

6. MEANOPAC
    - WRITE: obs/cmf_flux_sub_v5.f:1964-1992
    - Purpose: mean opacity diagnostics.
    - Format: TABLE_ASCII.

7. HYDRO
    - WRITE via HYDRO_TERMS call in cmf_flux_sub (subs/hydro_terms.f:65).
    - Purpose: momentum-term diagnostics for spectrum post-processing state.
    - Format: TABLE_ASCII.

8. EWDATA
    - WRITE: obs/cmf_flux_sub_v5.f:2158
    - Purpose: Sobolev equivalent width diagnostics (if DO_SOBOLEV_LINES).
    - Format: TABLE_ASCII/VECTOR_ASCII.

9. CFDAT_OUT
    - WRITE: subs/set_cont_freq_v4.f:298-303
    - Purpose: computed continuum frequency table with velocity spacing diagnostics.
    - Format: TABLE_ASCII.

10. CONT_FREQ
    - WRITE: subs/det_main_cont_freq.f:149-183
    - Purpose: continuum evaluation mapping and edge proximity checks.
    - Format: TABLE_ASCII with metadata headers.

11. TIMING
    - WRITE/APPEND: unix/tune.f:86, 177
    - Purpose: elapsed and CPU timing by identifier.
    - Format: LOG_ASCII/table-like report.

12. TRANS_INFO
    - WRITE conditionally: obs/cmf_flux_sub_v5.f:836
    - Purpose: transition information dump.
    - Format: LOG_ASCII/TABLE_ASCII.

13. EDDFACTOR, EDDFACTOR_INFO, ES_J_CONV, ES_J_CONV_INFO
    - WRITE/READ conditional branches in cmf_flux_sub (e.g., around 1185+, 1657+, 2150).
    - Purpose: direct-access radiation redistribution stores.
    - Format: BIN_DIRECT + KEYWORD_ASCII *_INFO sidecars.

14. Optional diagnostic files
    - PLANCK_KAPPA_MEAN (obs/cmf_flux_sub_v5.f:1860)
    - SOB_FORCE_MULT (obs/cmf_flux_sub_v5.f:2447)
    - RTAU_DATA/ZTAU_DATA/dFR_DATA with *_INFO from obs_frame_sub_v9.
    - Purpose: test or specialized observer diagnostics.
    - Format:
        - PLANCK_KAPPA_MEAN: TABLE_ASCII
        - SOB_FORCE_MULT: TABLE_ASCII
        - RTAU/ZTAU/dFR: BIN_DIRECT + *_INFO

## Script-Managed Aliases, Snapshots, and Cleanup Artifacts

These names are critical for workflow discovery but are not native core writer names.

### Observed in model_Bstar1060 scripts
Source scripts:
- /home/karpov/CMFGEN2023/models/ostar/model_Bstar1060/obs/bat_ins.sh
- /home/karpov/CMFGEN2023/models/ostar/model_Bstar1060/obs/batobs.sh

1. obs_fin_15 / obs_fin_10 / obs_fin_20
    - UPDATE from OBSFRAME via mv
    - bat_ins.sh:21,52,83
    - Purpose: VTURB sweep spectral snapshots.
    - Format: VECTOR_ASCII (same as OBSFRAME).

2. CMF_FLUX_PARAM_15 / _10 / _20
    - UPDATE from CMF_FLUX_PARAM via mv
    - bat_ins.sh:22,53,84
    - Purpose: frozen control snapshots matching each obs_fin_* output.
    - Format: KEYWORD_ASCII.

3. obs_cont
    - UPDATE from OBSFRAME via mv
    - batobs.sh:85
    - Purpose: continuum-only/reference observer-frame spectrum.
    - Format: VECTOR_ASCII.

4. hydro_cont
    - UPDATE from HYDRO via mv
    - batobs.sh:88
    - Purpose: hydro diagnostic paired with continuum run.
    - Format: TABLE_ASCII.

5. cont_timing
    - UPDATE from TIMING via mv
    - batobs.sh:86
    - Purpose: timing report for continuum pass.
    - Format: LOG_ASCII.

6. ewdata_fin
    - UPDATE from EWDATA via mv
    - batobs.sh:87
    - Purpose: retained EW diagnostics from final pass.
    - Format: TABLE_ASCII.

### Additional aliases generated by helper generator
Source:
- misc/create_batobs_ins.f:216-223

Potential generated rename targets include:
- OBSFRAME -> obs_fin<id>
- OBSFLUX -> obs_cmf<id>
- HYDRO -> hydro_fin<id>
- MEANOPAC -> meanopac<id>
- TIMING -> full_timing<id>
- J_COMP -> J_COMP<id>
- EDDFACTOR -> EDDFACTOR_STORE
- EDDFACTOR_INFO -> EDDFACTOR_STORE_INFO

All retain source formats (renamed aliases only).

### Cleanup deletions (model clean.sh / obs clean scripts)
Typical deletions:
- BAION, BAMAT, BAIONPNT, BAMATPNT, BA_STEQ, BA_ASCI_N_D*
- EDDFACTOR*, ES_J_CONV*, J_COMP, JEW
- EWDATA, STEQ_VALS, LINEHEAT, NETRATE, TOTRATE, TRANS_INFO
- CFDAT_OUT, CONT_FREQ, *SCRATCH*, fort.*
- symlink cleanup via rmlinks/find

Implication for viewer/indexing:
- Some files are intentionally transient and may be missing after standard cleanup.

## LTE Subfolder and wind_hyd File Inventory

Important path note
-------------------
No internal CMFGEN code path in this snapshot creates a directory literally named "lte/".
Files appear under run_dir/lte when executables are launched from that subfolder by scripts
(e.g., lte/ltebat.sh calls main_lte.exe in that CWD).

### LTE executable outputs (main_lte.exe path)
1. OUTLTE
    - WRITE: lte_hydro/lte.f:89
    - Purpose: main LTE log.
    - Format: LOG_ASCII.

2. MODEL, RVTJ, POP<species>, <ION>OUT, GAMMAS
    - WRITE in lte_sub flow:
        - MODEL: lte_sub.f:634
        - RVTJ: lte_sub.f:1347
        - POP* and ion OUT-like files: lte_sub.f:1450 and downstream writer calls
    - Purpose: LTE analogues of main CMFGEN structure/population outputs.
    - Format: TABLE_ASCII/VECTOR_ASCII.

3. MOD_SUM
    - WRITE: lte_sub.f:1161
    - Purpose: compact LTE model summary.
    - Format: KEYWORD_ASCII/TABLE_ASCII.

4. NEG_OPAC, ML_COUNTER, ROSSELAND_LTE_TAB
    - WRITE:
        - NEG_OPAC: lte_sub.f:890
        - ML_COUNTER: lte_sub.f:983
        - ROSSELAND_LTE_TAB: lte_sub.f:1103
    - Purpose: LTE opacity and loop diagnostics.
    - Format: LOG_ASCII/TABLE_ASCII.

5. TIMING
    - WRITE by TUNE utility if used in LTE flow.
    - Purpose: timing.
    - Format: LOG_ASCII.

### wind_hyd outputs (wind_hyd.exe path)
Inputs:
- HYDRO_PARAMS (READ, wind_hyd.f:227)
- Optional old model RVTJ path when OLD_MODEL is enabled.

Outputs:
- OLD_GRID (wind_hyd.f:363) -> TABLE_ASCII
- DIAGNOSTIC_EST_1 (wind_hyd.f:616) -> TABLE_ASCII
- DIAGNOSTIC_EST_2 (wind_hyd.f:620) -> TABLE_ASCII
- NEW_CALC_GRID (wind_hyd.f:754) -> TABLE_ASCII
- RVSIG_COL_NEW (wind_hyd.f:898) -> TABLE_ASCII
- FIN_CAL_GRID (wind_hyd.f:933) -> TABLE_ASCII

## Staging and Model-to-Model Transfer Scripts (file movement contracts)

### cpmod/out2in style setup
Source:
- /home/karpov/CMFGEN2023/models/ostar/cpmod.sh
- /home/karpov/CMFGEN2023/models/ostar/out2in.sh
- /home/karpov/CMFGEN2023/cur_cmf/com/*.sh related helpers

Common actions:
1. Copy control/bootstrap files:
    - batch.sh, IN_ITS, VADAT, MODEL_SPEC, *OUT, GAMMAS->GAMMAS_IN.

2. Optional hydro support copies:
    - batch_ins.sh, RVSIG_COL, HYDRO_DEFAULTS, ROSSELAND_LTE_TAB, RDINR, ADJUST_R_DEFAULTS.

3. Rename outputs into next-run inputs:
    - *OUT -> *_IN (out2in.sh perl rename).

4. SN-specific staging aliases (conditional):
    - SN_HYDRO_FOR_NEXT_MODEL -> SN_HYDRO_DATA
    - JH_AT_CURRENT_TIME -> JH_AT_OLD_TIME
    - CUR_MODEL_DATA -> OLD_MODEL_DATA

5. Restart promotion helper:
    - NEW_POINT1 -> POINT1
    - NEW_POINT2 -> POINT2
    - NEW_SCRTEMP -> SCRTEMP

### Practical implication
Many files in a run directory are a mix of:
- native code outputs,
- script-renamed aliases,
- copied/staged bootstrap inputs for next model.
Any Python reimplementation should preserve this distinction explicitly.

## File Format Summary for Parser/Viewer Implementation

### Stable text formats
1. KEYWORD_ASCII
    - Pattern: "value [KEY]" with comments.
    - Examples: VADAT, IN_ITS, MODEL_SPEC, HYDRO_PARAMS, CMF_FLUX_PARAM*.
    - Parsing strategy: regex for [KEY], preserve numeric/string/raw tokens.

2. VECTOR_ASCII
    - Pattern: labeled section headers followed by wrapped numeric vectors.
    - Examples: RVTJ, OBSFLUX, OBSFRAME aliases (obs_fin_*, obs_cont), GAMMAS, POP*.
    - Parsing strategy: header-driven block scanner; tolerate variable wrap width.

3. TABLE_ASCII
    - Pattern: header row(s), fixed-width/space-separated columns.
    - Examples: HYDRO, MEANOPAC, CONT_FREQ, CFDAT_OUT, FIN_CAL_GRID, NEW_CALC_GRID.
    - Parsing strategy: skip comment/meta lines, infer column count per section.

4. LOG_ASCII
    - Pattern: free-form text and diagnostics.
    - Examples: OUTGEN, OUT_FLUX, OUTLTE, WARNINGS, TIMING, batch logs.
    - Parsing strategy: line-based indexing/search; not strict schema.

### Binary/internal formats
1. BIN_DIRECT with *_INFO sidecar
    - Examples: EDDFACTOR, ES_J_CONV, RTAU_DATA, ZTAU_DATA, dFR_DATA.
    - *_INFO carries record-size metadata (critical for portability).

2. Restart binary
    - SCRTEMP (and NEW_SCRTEMP) are unformatted internal state stores.
    - Treat as opaque for viewer MVP unless implementing restart/state tools.

## High-Priority Viewer-Relevant Files (recommended ingest order)

1. RVTJ (radial structure backbone)
2. OBSFLUX and/or OBSFRAME aliases (obs_fin_*, obs_cont)
3. MOD_SUM and MODEL (metadata)
4. MEANOPAC and HYDRO (diagnostic profiles)
5. Optional: POP* and <ION>OUT for level-population diagnostics

Lower priority / internal:
- SCRTEMP, POINT1/2, EDDFACTOR*, ES_J_CONV*, BAMAT*, fort.*

## Notes on Ambiguous Names (obs_fin/obs_cont/hydro_cont)

1. obs_fin_* and obs_cont
    - Not core writer names in cmf_flux code; they are script renames of OBSFRAME.
    - Confirmed in model_Bstar1060/obs scripts.

2. hydro_cont
    - Also script rename (HYDRO -> hydro_cont) in this model’s batobs.sh.
    - Therefore it exists when that script path is used, not as a hardcoded code writer name.

3. Additional "files like that"
    - Yes; generator scripts can produce many alias names (obs_cmf*, hydro_fin*, meanopac*, full_timing*, J_COMP*).
