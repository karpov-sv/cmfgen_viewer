"""Complete subprocess lifecycle for the provisional checkpoint mutation."""
import json
import shutil
import sys

import pytest

from test_runner_auto import auto_workspace
from test_population_projection import projection_model
from cmfgen_viewer import auto_policies as policies
from cmfgen_viewer.checkpoint_physics import checkpoint_physics
from cmfgen_viewer.population_projection import localized_population_projection, propose_projection
from cmfgen_viewer.runner import run_plan


NATIVE = r'''
from pathlib import Path
import re,struct,sys,time
if sys.argv[1:]==['--version']:
 print('CMFGEN_VIEWER_PATCH 2026-10-31.1');raise SystemExit(0)
p=Path('.')
def get(name,key,default):
 m=re.search(r'^\s*(\S+)\s+\['+re.escape(key)+r'\]',(p/name).read_text(),re.M)
 return m[1] if m else default
mode=(p/'scenario').read_text()
count=int(get('IN_ITS','NUM_ITS','3'))
point=(p/'POINT1').read_text().splitlines()[1].split()
record,iteration=int(point[0]),int(point[1])
data=(p/'SCRTEMP').read_bytes();size=16376
geometry=data[:size]
values=list(struct.unpack_from('<30d',data,(3+2*(record-1))*size))
spike=values[12]/sum(values[12:14])>.5
if not spike:
 (p/'projection-observed').write_text(str(values[12]/sum(values[12:14])))
 if mode=='projection_fail':print('Unrelated native failure');raise SystemExit(1)
 if mode=='projection_ineffective':
  values[12:14]=[9e9,1e9];values[16]=values[13]+values[15]
def pack(items):
 b=struct.pack('<'+str(len(items))+'d',*items)
 return b+bytes(size-len(b))
out='Model started on: now\n'
with (p/'STEQ_VALS').open('a') as sol:
 for n in range(count):
  iteration+=1;record+=1
  decrease=1e7 if spike else (110 if mode=='projection_bad_target' else .1)
  increase=10 if spike else .1
  out+=f'Current great iteration count is {iteration}\nBA matrix computed\n'
  out+=f'Luminosity of star (d=1,ND)(iteration {iteration}) is: 1 1\n'
  out+=f'Maximum % increase at depth 3 is {increase} (BA computed) --- iteration {iteration}\n'
  out+=f'Maximum % decrease at depth 3 is {decrease} (BA computed) --- iteration {iteration}\n'
  out+=f'Maximm changes as returned by SOLVEBA_V13 is {max(increase,decrease)}\n'
  out+=f'The minimum value of scale for Major species is: {1e-4 if spike else 1}\n'
  sol.write(' STEQ SOLUTION ARRAY\n')
  for variable in range(1,7):
   raw=[.001]*5
   if variable==1:raw[2]=decrease/100
   sol.write(f'{variable}( 1)# '+' '.join(map(str,raw))+'\n')
  data=data[:(2+2*(record-1))*size]+geometry+pack(values)
(p/'SCRTEMP').write_bytes(data)
for name in ['POINT1','POINT2']:
 (p/name).write_text(f'28-Feb-2004 !Format date\n{record} {iteration} 1 -1000 T\n')
(p/'OUTGEN').write_text(out)
(p/'MODEL').write_text((p/'MODEL').read_text()+'\nNative update '+str(time.time_ns())+'\n')
(p/'MOD_SUM').write_text('Model Finalized on: '+str(time.time_ns())+'\n')
(p/'RVTJ').write_text('ND: 5\nRadius\n6 5 4 3 2\nVelocity\n20 20 20 20 20\nTemperature\n1 1 1 1 1\nElectron density\n'+' '.join(str(values[i*6+4]) for i in range(5))+'\n')
(p/'CORRECTION_SUM').write_text('NT=6\nDepth 100.0% 10.0% 1.0% 0.1% 0.01% 0.001% 0.0001%\n'+''.join(f'{d} 0 0 0 0 1 1 6\n' for d in range(1,6)))
(p/'OBSFLUX').write_text('Normalized luminosity check (normalized by L[ND])\n1 1 1 1 1\n')
(p/'MEANOPAC').write_text('Depth Tau(Ross)\n'+''.join(f'a {d} {50*d} '+' '.join(['1']*12)+'\n' for d in range(1,6)))
'''


@pytest.fixture
def projection_workspace(auto_workspace, projection_model):
    model, plan = auto_workspace
    for name in ['MODEL', 'POINT1', 'POINT2', 'SCRTEMP']:
        shutil.copy2(projection_model/name, model/name)
    (model/'MODEL_SPEC').write_text('5 [ND]\n1 [NC]\n6 [NP]\n1,1,1 [HI_ISF]\n1,1,1 [HeI_ISF]\n')
    (model/'VADAT').write_text(
        '1 [RSTAR]\n.02 [EPS_TERM]\nF [FIX_T]\nT [INCL_dSLdT]\nMAJOR [SCALE_OPT]\n'
        '0 [N_FIX_BA]\n0.0 [FIX_BA]\nT [COMP_BA]\nF [DO_HYDRO]\n')
    exe = model.parent/'cmf/exe/cmfgen_dev.exe'
    exe.write_text(f'#!{sys.executable}\n'+NATIVE);exe.chmod(0o755)
    assert any(p.id=='localized_population_projection' and p.max_applications==1 for p in policies.POLICIES)
    return model, plan


def test_projection_is_provisional_and_hands_back_without_claiming_convergence(projection_workspace):
    model, plan = projection_workspace
    result = run_plan(plan('projection', max_attempts=2))
    assert result['status']=='limit_reached',result
    assert result['attempts'][-1]['recovery_verified']=='localized_population_projection'
    assert result['actions'][0]['checkpoint_projection']['restart_counter_unchanged']
    check = result['attempts'][-1]['population_projection_check']
    assert len(check['full_solve_requests']) == 2
    assert check['remaining_contrast'] < 10
    assert 'numerical_convergence' not in result
    assert propose_projection(model,3) is None
    assert checkpoint_physics(model)['charge_relative_error'] < 1e-14


@pytest.mark.parametrize('mode', ['projection_fail','projection_ineffective','projection_bad_target'])
def test_failed_or_ineffective_native_followup_restores_whole_preconditioner(projection_workspace, mode):
    model, plan = projection_workspace
    original = (model/'VADAT').read_bytes()
    result = run_plan(plan(mode,max_attempts=2))
    assert result['status']=='needs_review',result
    assert result['provisional_recovery_rolled_back']=='localized_population_projection'
    assert propose_projection(model,3) is not None
    assert (model/'VADAT').read_bytes()==original
    assert len(result['actions'])==1


def test_insufficient_budget_does_not_mutate_checkpoint_guess(projection_workspace):
    model, plan = projection_workspace
    result = run_plan(plan('projection',max_attempts=2,max_iterations=4))
    assert result['status']=='limit_reached',result
    assert not result['actions']
    assert propose_projection(model,3) is not None


def test_cancel_after_projection_rolls_back_the_entire_provisional_action(projection_workspace):
    model, plan = projection_workspace
    stopped = False
    def emit(event):
        nonlocal stopped
        if event['event']=='auto_action' and event['action']['policy_id']=='localized_population_projection':
            stopped = True
    result = run_plan(plan('projection',max_attempts=2),emit,stop_requested=lambda:stopped)
    assert result['status'] in {'stopped','cancelled'},result
    assert result['provisional_recovery_rolled_back']=='localized_population_projection'
    assert propose_projection(model,3) is not None


def test_ordinary_run_reports_projection_without_applying_it(projection_workspace):
    model, plan = projection_workspace
    native = plan('projection')
    native.pop('kind');native.pop('auto')
    result = run_plan(native)
    assert result['status']=='succeeded',result
    item = next(f for f in result['main_diagnostics']['findings']
                if f['policy_id']=='localized_population_projection')
    assert item['automatic_eligible']
    assert item['proposal']['steps'][0]['name']=='population_projection_full'
    assert propose_projection(model,3) is not None
    assert not (model/'projection-observed').exists()
