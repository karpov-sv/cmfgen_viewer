#!/usr/bin/env python3
"""Compile the actual native limiter block and test its guarded fallback.

No opacity floor is invented here: ESEC_CHK's original 0.1*CHI_SCAT is tested
against the failing SRCE_CHK input and an ordinary positive source-floor case.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('cmfgen_root',type=Path)
    ap.add_argument('--compiler',default='gfortran')
    ap.add_argument('--optimization',choices=['O0','O2'],default='O0')
    args=ap.parse_args()
    text=(args.cmfgen_root/'new_main/cmfgen_sub.f').read_text()
    start=text.index("\t    IF(NEG_OPAC_OPTION .EQ. 'SRCE_CHK')THEN")
    end=text.index('\n\t    IF(LST_ITERATION .AND. AT_LEAST_ONE_NEG_OPAC)',start)
    block=text[start:end]
    assert 'SRCE_CHK nonpositive opacity floor' in block
    program='''      PROGRAM CHECK_LIMITER
      IMPLICIT NONE
      INTEGER,PARAMETER :: LDP=KIND(1.0D0),ND=1,LUER=6
      INTEGER I,MAIN_COUNTER
      REAL(KIND=LDP) CHI(ND),CHI_CONT(ND),CHI_NOSCAT(ND)
      REAL(KIND=LDP) ETA(ND),ETA_CONT(ND),CHI_SCAT(ND),T1
      REAL(KIND=LDP) NEG_OPAC_FAC(ND),FL
      LOGICAL NEG_OPACITY(ND),AT_LEAST_ONE_NEG_OPAC
      CHARACTER(LEN=10) NEG_OPAC_OPTION,CASE_NAME
      CALL GET_COMMAND_ARGUMENT(1,NEG_OPAC_OPTION)
      CALL GET_COMMAND_ARGUMENT(2,CASE_NAME)
      MAIN_COUNTER=1
      FL=0.415375D0
      CHI=-1.0D0
      CHI_CONT=-0.5D0
      CHI_NOSCAT=-2.0D0
      ETA=2.0D0
      ETA_CONT=1.0D0
      CHI_SCAT=2.0D0
      NEG_OPACITY=.FALSE.
      NEG_OPAC_FAC=1.0D0
      AT_LEAST_ONE_NEG_OPAC=.FALSE.
      IF(CASE_NAME.EQ.'positive')THEN
        CHI_CONT=1.0D0
        CHI_NOSCAT=0.5D0
      ELSE IF(CASE_NAME.EQ.'unchanged')THEN
        CHI=3.0D0
      ELSE IF(CASE_NAME.EQ.'zero')THEN
        ETA=0.0D0
      END IF
'''+block+'''
      IF(ANY(CHI.LE.0.0D0))STOP 7
      IF(CASE_NAME.EQ.'unchanged')THEN
        IF(ANY(CHI.NE.3.0D0))STOP 8
        IF(ANY(NEG_OPACITY))STOP 9
      ELSE
        IF(.NOT.ALL(NEG_OPACITY))STOP 10
        IF(ANY(NEG_OPAC_FAC.NE.0.0D0))STOP 11
        IF(.NOT.AT_LEAST_ONE_NEG_OPAC)STOP 12
        IF(NEG_OPAC_OPTION.EQ.'ESEC_CHK')THEN
          IF(ANY(ABS(CHI-0.2D0).GT.1.0D-14))STOP 13
        ELSE
          IF(ANY(ABS(CHI-0.1D0).GT.1.0D-14))STOP 14
        END IF
      END IF
      WRITE(6,*)'PASSED'
      END
'''
    with tempfile.TemporaryDirectory(prefix='source-opacity-') as folder:
        d=Path(folder);(d/'test.f').write_text(program)
        subprocess.run([args.compiler,'-'+args.optimization,'-ffixed-line-length-none',
                        '-ffpe-trap=invalid,zero,overflow',str(d/'test.f'),'-o',str(d/'test')],check=True)
        for option,case in [('SRCE_CHK','negative'),('SRCE_CHK','zero'),
                            ('ESEC_CHK','negative'),('ESEC_CHK','zero'),
                            ('SRCE_CHK','positive'),('SRCE_CHK','unchanged'),
                            ('ESEC_CHK','unchanged')]:
            r=subprocess.run([str(d/'test'),option,case],capture_output=True,text=True)
            if option=='SRCE_CHK' and case in {'negative','zero'}:
                assert r.returncode==1 and 'SRCE_CHK nonpositive opacity floor' in r.stdout,(option,case,r)
            else:
                assert r.returncode==0 and 'PASSED' in r.stdout,(option,case,r)
        print('7 native opacity-limiter cases passed at '+args.optimization)


if __name__=='__main__':
    main()
