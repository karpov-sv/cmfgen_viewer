"""Command-line access to the same maintenance operations as the model UI."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .model_activity import inspect_model_activity
from .model_editor import ModelEditorError, _resolve_model, load_model_parameter_file
from .control_files import control_occurrences
from .model_quick_editor import (QUICK_PARAMETER_FILES, load_quick_model_parameter_cards,
    review_quick_model_parameter_edit, save_quick_model_parameter_edit)
from .model_staging import ModelStagingError, plan_model_from_solution, create_model_from_solution
from .model_workflow import ModelWorkflowError, cleanup_lte_workspace
from .lte_cleanup import inspect_lte_cleanup
from .model_full_cleanup import build_full_cleanup_plan, run_full_cleanup
from .model_reseed import build_reseed_plan, run_reseed_plan
from .runner import run_plan
from .runner_cleanup import build_cleanup_plan
from .runner_config import resolve_viewer_defaults
from .structure_update import OPERATIONS, inspect_structure_update, build_structure_plan, apply_structure_plan


class MaintenanceExecutionError(RuntimeError):
    """The operation failed after its initial validation."""


def _execute(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except (ValueError, OSError) as exc:
        raise MaintenanceExecutionError(str(exc)) from exc


def _model(raw):
    model = Path(raw).expanduser().resolve()
    _resolve_model(str(model.parent), model.name)
    return model


def _activity(plan, model):
    activity = inspect_model_activity(model)
    errors = list(plan.get('errors', []))
    if not activity['safe_to_modify']:
        errors.append(activity['reason'] or 'Model activity is uncertain.')
    return {**plan, 'activity': activity, 'errors': errors, 'ready': not errors}


def _card(model, filename):
    cards = load_quick_model_parameter_cards(str(model.parent), model_relpath=model.name)
    card = next((card for card in cards if card['file_relpath'] == filename), None)
    if card is None:
        raise ModelEditorError(f'No readable quick parameters in {filename}.')
    return card


def _assignments(assignments):
    values = {}
    for assignment in assignments:
        key, separator, value = assignment.partition('=')
        key = key.strip().upper()
        if not separator or not key or not value.strip():
            raise ModelEditorError('Parameters must use KEY=VALUE, for example LSTAR=2.8e5.')
        if key in values:
            raise ModelEditorError(f'Duplicate parameter: {key}.')
        values[key] = value.strip()
    return values


def plan_parameter_edit(model, filename, assignments, *, keep_teff_logg=False):
    card = _card(model, filename)
    requested = _assignments(assignments)
    values = {field['key']: field['value'] for field in card['fields']}
    unknown = set(requested) - set(values)
    if unknown:
        raise ModelEditorError('Parameters unavailable in this quick editor: ' + ', '.join(sorted(unknown)) + '. Use show to list editable keys.')
    if keep_teff_logg:
        if filename != 'VADAT' or 'LSTAR' not in requested:
            raise ModelEditorError('--keep-teff-logg requires an explicit LSTAR change in VADAT.')
        conflicts = set(requested) & {'RSTAR', 'MASS', 'LOGG'}
        if conflicts:
            raise ModelEditorError('--keep-teff-logg controls RSTAR/MASS and preserves LOGG; do not also set ' + ', '.join(sorted(conflicts)) + '.')
    values.update(requested)
    review = review_quick_model_parameter_edit(str(model.parent), model_relpath=model.name,
        file_relpath=filename, expected_digest=card['digest'], values=values,
        keep_temperature_logg=keep_teff_logg)
    return _activity({'command': 'set', 'model': str(model), 'file': filename,
        'requested': requested, 'values': values, 'expected_digest': card['digest'],
        'proposed_digest': review['proposed_digest'], 'changed': review['changed'],
        'keep_teff_logg': keep_teff_logg, 'warnings': review['warnings'],
        'diff_lines': review['diff_lines'], 'resulting_values': review['values']}, model)


def _copy(args):
    source = _model(args.source)
    # Resolve the parent, preserving the destination leaf so dangling symlinks and
    # existing destinations are still rejected by the shared staging code.
    requested = Path(args.destination).expanduser().absolute()
    destination = requested.parent.resolve() / requested.name
    base = Path(os.path.commonpath([source.parent, destination.parent]))
    defaults, _ = resolve_viewer_defaults()
    template = args.template_root or defaults.get('template_root')
    options = {'source_relpath': source.relative_to(base).as_posix(),
               'destination_relpath': destination.relative_to(base).as_posix(),
               'template_root': str(Path(template).expanduser().resolve()) if template else None}
    plan = plan_model_from_solution(str(base), **options)
    plan = _activity({**plan, 'command': 'copy',
        'errors': ['Missing required source files: ' + ', '.join(plan['missing_required'])] if plan['missing_required'] else []}, source)
    if args.plan or not plan['ready']:
        return plan, 0 if plan['ready'] else 2
    result = _execute(create_model_from_solution, str(base), **options)
    return {**plan, 'status': 'succeeded', 'result': result}, 0


def _cleanup(args):
    model = _model(args.model)
    if args.full:
        if args.lte or args.file:
            raise ModelStagingError('--full cannot be combined with --lte or --file.')
        plan = build_full_cleanup_plan(model)
        if args.plan or not plan['ready']:
            return plan, 0 if plan['ready'] else 2
        if not plan['entry_count']:
            return {**plan, 'status': 'unchanged'}, 0
        result = _execute(run_full_cleanup, plan)
        return {**plan, 'status': result['status'], 'result': result}, 1 if result['failures'] else 0
    if args.lte:
        if args.file:
            raise ModelStagingError('--file cannot be combined with --lte; use workspace-relative paths such as lte/POPHYD without --lte.')
        lte = model / 'lte'
        if lte.is_symlink() or not lte.is_dir():
            raise ModelWorkflowError('LTE workspace must be a real directory.')
        cleanup = inspect_lte_cleanup(lte)
        plan = _activity({**cleanup, 'command': 'cleanup', 'model': str(model),
            'workspace': 'lte', 'warnings': []}, model)
        if args.plan or not plan['ready']:
            return plan, 0 if plan['ready'] else 2
        if not plan['entry_count']:
            return {**plan, 'status': 'unchanged'}, 0
        result = _execute(cleanup_lte_workspace, str(model.parent), model_relpath=model.name,
             expected_entries=cleanup['entries'])
        return {**plan, 'status': 'succeeded', 'result': result}, 0
    plan = build_cleanup_plan(model, selected_names=args.file)
    # Empty cleanup is an idempotent no-op, provided no other preflight failed.
    plan['errors'] = [error for error in plan['errors'] if error != 'No model cleanup candidates were found.']
    plan.update(command='cleanup', workspace='all',
                ready=not plan['errors'])
    if args.plan or not plan['ready']:
        return plan, 0 if plan['ready'] else 2
    if not plan['entry_count']:
        return {**plan, 'status': 'unchanged'}, 0
    result = _execute(run_plan, plan)
    return {**plan, 'status': result['status'], 'result': result}, 0 if result['status'] == 'succeeded' else 1


def _out2in(args):
    model = _model(args.model)
    plan = build_reseed_plan(model)
    if args.plan or not plan['ready']:
        return plan, 0 if plan['ready'] else 2
    result = _execute(run_reseed_plan, plan)
    return {**plan, 'status': result['status'], 'result': result}, 0


def _set(args):
    model = _model(args.model)
    plan = plan_parameter_edit(model, args.file, args.assignments, keep_teff_logg=args.keep_teff_logg)
    if args.plan or not plan['ready']:
        return plan, 0 if plan['ready'] else 2
    if not plan['changed']:
        return {**plan, 'status': 'unchanged'}, 0
    saved = _execute(save_quick_model_parameter_edit, str(model.parent), model_relpath=model.name,
        file_relpath=args.file, expected_digest=plan['expected_digest'],
        reviewed_digest=plan['proposed_digest'], values=plan['values'],
        keep_temperature_logg=args.keep_teff_logg)
    return {**plan, 'status': 'succeeded', 'backup': str(model / saved['backup_relpath']),
            'modified_marker': saved['modified_marker'],
            'warnings': [*plan['warnings'], *[message for message in (saved.get('marker_error'), saved.get('timestamp_error')) if message]]}, 0


def _get(args):
    model = _model(args.model)
    key = args.key.strip().upper()
    record = load_model_parameter_file(str(model.parent), model_relpath=model.name,
                                       file_relpath=args.file)
    matches = control_occurrences(record['contents']).get(key, [])
    if not matches:
        raise ModelEditorError(f'[{key}] is not explicitly set in {args.file}.')
    if len(matches) != 1:
        raise ModelEditorError(f'[{key}] occurs more than once in {args.file}; a single value is ambiguous.')
    value = matches[0]['value'].strip()
    if not value:
        raise ModelEditorError(f'[{key}] has no explicit value in {args.file}.')
    return {'command': 'get', 'model': str(model), 'file': args.file,
            'key': key, 'value': value}, 0


def _show(args):
    model = _model(args.model)
    card = _card(model, args.file)
    structure = inspect_structure_update(model)
    return {'command': 'show', 'model': str(model), 'file': args.file,
            'parameters': [{'key': field['key'], 'value': field['value'], 'label': field['label'],
                            'unit': field.get('unit', ''), 'optional': bool(field.get('missing'))}
                           for field in card['fields']],
            'warnings': [*card['issues'], *([structure['message']] if structure['required'] else [])],
            'luminosity_scaling': card['luminosity_scaling']}, 0


def _structure(args):
    from .runner_config import resolve_runner_config
    model = _model(args.model)
    if args.apply:
        if args.plan or args.candidate or args.review_file or args.operation != 'update':
            raise ValueError('--apply cannot be combined with generation options.')
        if args.apply.stat().st_size > 16 * 1024 * 1024:
            raise ValueError('Structure review is too large.')
        plan = json.loads(args.apply.read_text())
        saved = _execute(apply_structure_plan, model, plan)
        return {'command': 'structure', 'ready': True, 'status': saved['status'],
                'model': str(model), 'result': saved, 'warnings': plan['warnings']}, 0
    native, _ = resolve_runner_config(cmfgen_root=args.cmfgen_root, require_roots=False)
    candidate = None
    if args.candidate:
        if args.candidate.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('Candidate exceeds the 2 MiB limit.')
        candidate = args.candidate.read_bytes().decode('utf-8')
    plan = build_structure_plan(model, cmfgen_root=native.get('cmfgen_root'),
        velocity_type=args.velocity_type, connection_velocity=args.connection_velocity, candidate=candidate,
        operation=args.operation, new_depths=args.new_depths, start_depth=args.start_depth,
        end_depth=args.end_depth, points=args.points, radii=args.radii)
    if args.review_file:
        with args.review_file.open('x') as stream:
            json.dump(plan, stream, indent=2)
    return {'command': 'structure', 'ready': True, 'model': str(model),
            'status': 'review_required', 'summary': plan['summary'], 'diffs': plan['diffs'],
            'operation': plan['operation_label'],
            'warnings': plan['warnings'], 'retire': plan['retire'],
            'review_file': str(args.review_file) if args.review_file else None}, 0


def _text(report):
    command = report.get('command')
    if report.get('error'):
        print('ERROR: ' + report['error'])
        return
    if command == 'get':
        print(report['value'])
        return
    if command == 'copy':
        print(f"Copy: {report['source_path']} -> {report['destination_path']}")
        for entry in report['entries']:
            print(f"  {entry['source_name']} -> {entry['destination_name']}")
        print(f"{report['entry_count']} files, {report['human_size']}")
    elif command == 'show':
        print(f"{report['model']} / {report['file']}")
        for field in report['parameters']:
            print(f"  {field['key']}={field['value'] or '(unset)'}" + (f"  [{field['unit']}]" if field['unit'] else ''))
    elif command == 'set':
        print(f"Edit: {report['model']} / {report['file']}")
        for line in report['diff_lines']:
            print(line['text'])
        if report.get('backup'):
            print('Checkpoint: ' + report['backup'])
    elif command == 'structure':
        print(f"Structure: {report['model']}")
        if report.get('operation'):
            print('Operation: ' + report['operation'])
        for text in report.get('diffs', {}).values():
            print(text)
        if report.get('review_file'):
            print('Review saved: ' + report['review_file'])
        if report.get('result'):
            print('Recovery: ' + report['result']['archive_path'])
    elif command == 'out2in':
        print(f"Out2in: {report['model']}")
        for entry in report['entries']:
            print(f"  Copy {entry['source']} -> {entry['destination']}")
        for entry in report['checkpoints']:
            print(f"  Retire {entry['name']}")
        if report.get('result', {}).get('archive_path'):
            print('Recovery: ' + report['result']['archive_path'])
    elif command == 'cleanup':
        print(f"Cleanup: {report['model']} ({report['workspace']})")
        print('Recovery: ' + ('none; permanently delete temporary files, recovery data, and history' if report.get('full') else 'compact; keep fresh inputs, history, and log excerpts; omit calculated state'))
        for entry in report['entries']:
            print(f"  {entry['name']} ({entry['human_size']}) — {entry['reason']}")
        print(f"{report['entry_count']} candidates, {report['human_size']}")
        result = report.get('result', {})
        archive = result.get('archive_path') or result.get('journal')
        if archive:
            print('Recovery: ' + archive)
    result = report.get('result', {})
    problems = []
    if command in {'cleanup', 'out2in'}:
        recovery = result.get('recovery', result.get('cleanup', {}).get('recovery', {}))
        problems.extend(recovery.get('warnings', []))
        problems.extend(f"{failure['name']}: {failure['error']}" for failure in result.get('failures', []))
        for step in result.get('passes', []):
            problems.extend(step.get('problems', []))
    for warning in dict.fromkeys([*report.get('warnings', []), *problems]):
        print('WARNING: ' + warning)
    for error in report.get('errors', []):
        print('ERROR: ' + error)
    if command != 'show':
        print('Status: ' + report.get('status', 'ready (plan only)' if report['ready'] else 'blocked'))


def build_parser():
    parser = argparse.ArgumentParser(description='Inspect and maintain CMFGEN models using the same rules as the viewer UI.')
    commands = parser.add_subparsers(dest='command', required=True)
    show = commands.add_parser('show', help='List current quick-editable parameters')
    show.add_argument('model', type=Path)
    show.add_argument('--file', choices=QUICK_PARAMETER_FILES, default='VADAT')
    get = commands.add_parser('get', help='Print one explicit control value for use in scripts')
    get.add_argument('model', type=Path)
    get.add_argument('key', metavar='KEY')
    get.add_argument('--file', choices=QUICK_PARAMETER_FILES, default='VADAT')
    copy = commands.add_parser('copy', help='Create a fresh model seeded from a solution')
    copy.add_argument('source', type=Path)
    copy.add_argument('destination', type=Path)
    copy.add_argument('--template-root', type=Path, help='Override the shared cmfgenrc template_root')
    cleanup = commands.add_parser('cleanup', help='Clean main, LTE, and observer workspaces, preserving scientific products and checkpoints')
    cleanup.add_argument('model', type=Path)
    cleanup.add_argument('--full', action='store_true', help="Permanently remove temporary files in all workspaces, recovery archives, script metadata and locks, and this model's run/job history; no new recovery archive")
    cleanup.add_argument('--lte', action='store_true', help='Restrict cleanup to the LTE workspace')
    cleanup.add_argument('--file', action='append', metavar='NAME', help='Select a candidate by model-relative path, e.g. BAMAT, lte/POPHYD, obs/fort.63; repeatable')
    out2in = commands.add_parser('out2in', help='Refresh *_IN and GAMMAS_IN from outputs and retire binary checkpoints')
    out2in.add_argument('model', type=Path)
    edit = commands.add_parser('set', help='Change quick parameters, with backups and stale-solution marking')
    edit.add_argument('model', type=Path)
    edit.add_argument('assignments', nargs='+', metavar='KEY=VALUE')
    edit.add_argument('--file', choices=QUICK_PARAMETER_FILES, default='VADAT')
    edit.add_argument('--keep-teff-logg', action='store_true', help='Scale RSTAR and MASS with LSTAR, preserving Teff and log g')
    structure = commands.add_parser('structure', help='Review and apply a RVSIG_COL structure update')
    structure.add_argument('model', type=Path)
    structure.add_argument('--cmfgen-root', type=Path)
    structure.add_argument('--velocity-type', type=int, choices=(1, 2, 6), default=2)
    structure.add_argument('--connection-velocity', type=float, default=10.0)
    structure.add_argument('--operation', choices=OPERATIONS, default='update')
    structure.add_argument('--new-depths', type=int, help='Target depth count for new_nd')
    structure.add_argument('--start-depth', type=int, default=1, help='First depth of the insertion range (1 = outermost)')
    structure.add_argument('--end-depth', type=int, default=2, help='Last depth of the insertion range')
    structure.add_argument('--points', type=int, default=1, help='Points per interval for insert, or total for outer')
    structure.add_argument('--radii', help='Comma/space separated radii in 10^10 cm, largest first')
    structure.add_argument('--candidate', type=Path, help='Review an externally prepared RVSIG_COL instead of native generation')
    structure.add_argument('--review-file', type=Path, help='Save the candidate review to a new JSON file')
    structure.add_argument('--apply', type=Path, help='Apply a previously saved, unchanged review JSON file')
    structure.add_argument('--plan', action='store_true', help='Generate a candidate without modifying the model (default)')
    for command in (copy, cleanup, out2in, edit):
        command.add_argument('--plan', action='store_true', help='Show the planned operation without modifying files')
    for command in (show, get, copy, cleanup, out2in, edit, structure):
        command.add_argument('--json', action='store_true', help='Print a structured JSON report')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        report, code = {'show': _show, 'get': _get, 'copy': _copy, 'cleanup': _cleanup, 'out2in': _out2in, 'set': _set, 'structure': _structure}[args.command](args)
    except MaintenanceExecutionError as exc:
        report, code = {'command': args.command, 'status': 'failed', 'error': str(exc)}, 1
    except (ValueError, OSError) as exc:
        report, code = {'command': args.command, 'status': 'blocked', 'error': str(exc)}, 2
    except KeyboardInterrupt:
        report, code = {'command': args.command, 'status': 'cancelled', 'error': 'Interrupted.'}, 130
    if args.json:
        print(json.dumps(report, indent=2))
    elif args.command == 'get' and code:
        print('ERROR: ' + report['error'], file=sys.stderr)
    else:
        _text(report)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
