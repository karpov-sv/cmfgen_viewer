"""Read-only, declarative review hints for explicit solver controls.

These settings can be intentional. Their presence does not establish that a
recovery changed them, that the model has converged, or that resetting is safe.
Conditions are shared with the quick editor's live checks through JSON.
"""
import math

from .control_files import control_occurrences
from .parsers.common import parse_float_token


SOLVER_NOTICES = (
    dict(id='manual_lambda', file='IN_ITS', key='DO_LAM_AUTO', tone='info',
         badge='Manual handoff', title='Automatic Lambda handoff disabled',
         conditions=[dict(key='DO_LAM_AUTO', op='eq', value='F')],
         detail='Requested Lambda iterations will not automatically hand off to full iterations. '
                'F can be intentional for controlled tests. Consider T for routine continuations '
                'or derived models; changing this switch does not itself speed up healthy full iterations.'),
    dict(id='lambda_start', file='IN_ITS', key='DO_LAM_IT', tone='info',
         badge='Lambda mode', title='Lambda starting mode selected',
         conditions=[dict(key='DO_LAM_IT', op='eq', value='T')],
         detail='Useful for population recovery, but convergence assessment requires full, variable-temperature '
                'solves. DO_LAM_AUTO=T permits the native handoff when its switching criteria are met; '
                'otherwise review DO_LAM_IT before normal continuation.'),
    dict(id='large_lambda_limit', file='VADAT', key='MAX_LAM', tone='warning',
         badge='Large Lambda limit', title='Unusually permissive Lambda correction limit',
         conditions=[dict(key='MAX_LAM', op='gt', value=1e4)],
         detail='Large limits such as 1e12 may have been chosen for a population bootstrap. '
                'Review whether the usual limit for this model should be restored '
                '(1e4 in the Bstar templates). This affects Lambda steps, not ordinary full iterations.'),
    dict(id='fixed_temperature', file='VADAT', key='FIX_T', tone='warning',
         badge='Fixed T', title='Fixed temperature requested',
         conditions=[dict(key='FIX_T', op='eq', value='T')],
         detail='This can be intentional for recovery or a fixed-temperature calculation. '
                'Full convergence verification requires variable-temperature solves. '
                'DO_T_AUTO=T may release fixed temperature when native criteria are met; '
                'review both controls before using the model for normal continuation.'),
    dict(id='ng_disabled', file='VADAT', key='DO_NG', tone='info',
         badge='Ng disabled', title='Ng acceleration disabled',
         conditions=[dict(key='DO_NG', op='eq', value='F')],
         detail='Disabling Ng can help during unstable recovery. Stable continuations may benefit '
                'from re-enabling it, subject to native scheduling and validity checks. '
                'Keep it disabled if the model still needs that stabilization.'),
    dict(id='reduced_relaxation', file='ADJUST_CORRECTIONS', key='RELAX', tone='info',
         badge='Damped corrections', title='Correction under-relaxation selected',
         conditions=[dict(key='RELAX', op='gt', value=0), dict(key='RELAX', op='lt', value=1)],
         detail='Reduced corrections can suppress oscillations but may slow progress. '
                'This damping may still be essential. Test any increase toward 1 on a copy '
                'before removing a successful stabilization.'),
)


def solver_settings_notices(contents, filename):
    rows = control_occurrences(contents)

    def matches(condition):
        values = rows.get(condition['key'], [])
        if len(values) != 1:
            return False
        value = values[0]['value']
        if condition['op'] == 'eq':
            return value.upper() == condition['value']
        number = parse_float_token(value)
        if number is None or not math.isfinite(number):
            return False
        if condition['op'] == 'gt':
            return number > condition['value']
        if condition['op'] == 'lt':
            return number < condition['value']
        return False

    return [{**notice, 'active': all(matches(c) for c in notice['conditions'])}
            for notice in SOLVER_NOTICES if notice['file'] == filename]
