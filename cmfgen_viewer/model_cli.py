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
from .runner import run_plan
from .runner_cleanup import build_cleanup_plan
from .runner_config import resolve_recovery_policy, resolve_viewer_defaults


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
        if args.lte or args.file or args.keep_large_files is not None:
            raise ModelStagingError('--full cannot be combined with --lte, --file, or recovery-retention flags.')
        plan = build_full_cleanup_plan(model)
        if args.plan or not plan['ready']:
            return plan, 0 if plan['ready'] else 2
        if not plan['entry_count']:
            return {**plan, 'status': 'unchanged'}, 0
        result = _execute(run_full_cleanup, plan)
        return {**plan, 'status': result['status'], 'result': result}, 1 if result['failures'] else 0
    keep = resolve_recovery_policy(args.keep_large_files)
    if args.lte:
        if args.file:
            raise ModelStagingError('--file is only available for main-folder cleanup; LTE cleanup uses its reviewed candidate policy.')
        lte = model / 'lte'
        if lte.is_symlink() or not lte.is_dir():
            raise ModelWorkflowError('LTE workspace must be a real directory.')
        cleanup = inspect_lte_cleanup(lte)
        plan = _activity({**cleanup, 'command': 'cleanup', 'model': str(model),
            'workspace': 'lte', 'keep_large_files': keep, 'warnings': []}, model)
        if args.plan or not plan['ready']:
            return plan, 0 if plan['ready'] else 2
        if not plan['entry_count']:
            return {**plan, 'status': 'unchanged'}, 0
        result = _execute(cleanup_lte_workspace, str(model.parent), model_relpath=model.name,
            keep_large_files=keep, expected_entries=cleanup['entries'])
        return {**plan, 'status': 'succeeded', 'result': result}, 0
    plan = build_cleanup_plan(model, selected_names=args.file)
    # Empty cleanup is an idempotent no-op, provided no other preflight failed.
    plan['errors'] = [error for error in plan['errors'] if error != 'No model cleanup candidates were found.']
    plan.update(command='cleanup', workspace='model', keep_large_files=keep,
                ready=not plan['errors'])
    if args.plan or not plan['ready']:
        return plan, 0 if plan['ready'] else 2
    if not plan['entry_count']:
        return {**plan, 'status': 'unchanged'}, 0
    result = _execute(run_plan, plan)
    return {**plan, 'status': result['status'], 'result': result}, 0 if result['status'] == 'succeeded' else 1


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
    return {'command': 'show', 'model': str(model), 'file': args.file,
            'parameters': [{'key': field['key'], 'value': field['value'], 'label': field['label'],
                            'unit': field.get('unit', ''), 'optional': bool(field.get('missing'))}
                           for field in card['fields']],
            'warnings': card['issues'], 'luminosity_scaling': card['luminosity_scaling']}, 0


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
    elif command == 'cleanup':
        print(f"Cleanup: {report['model']} ({report['workspace']})")
        print('Recovery: ' + ('none; permanently delete temporary files, recovery data, and history' if report.get('full') else 'full-size files and logs' if report['keep_large_files'] else 'compact; omit artifacts above 2 MiB and retain log excerpts'))
        for entry in report['entries']:
            print(f"  {entry['name']} ({entry['human_size']}) — {entry['reason']}")
        print(f"{report['entry_count']} candidates, {report['human_size']}")
        result = report.get('result', {})
        archive = result.get('archive_path') or result.get('journal')
        if archive:
            print('Recovery: ' + archive)
    result = report.get('result', {})
    problems = []
    if command == 'cleanup':
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
    cleanup = commands.add_parser('cleanup', help='Clean known temporary files, preserving scientific products and checkpoints')
    cleanup.add_argument('model', type=Path)
    cleanup.add_argument('--full', action='store_true', help="Permanently remove temporary files in all workspaces, recovery archives, and this model's run/job history; no new recovery archive")
    cleanup.add_argument('--lte', action='store_true', help='Clean the LTE workspace instead of the main folder')
    cleanup.add_argument('--file', action='append', metavar='NAME', help='Select a main-folder candidate; repeat to select more')
    cleanup.add_argument('--keep-large-files', action=argparse.BooleanOptionalAction, default=None,
                         help='Keep recovery artifacts above 2 MiB and full logs (otherwise use cmfgenrc, default compact)')
    edit = commands.add_parser('set', help='Change quick parameters, with backups and stale-solution marking')
    edit.add_argument('model', type=Path)
    edit.add_argument('assignments', nargs='+', metavar='KEY=VALUE')
    edit.add_argument('--file', choices=QUICK_PARAMETER_FILES, default='VADAT')
    edit.add_argument('--keep-teff-logg', action='store_true', help='Scale RSTAR and MASS with LSTAR, preserving Teff and log g')
    for command in (copy, cleanup, edit):
        command.add_argument('--plan', action='store_true', help='Show the planned operation without modifying files')
    for command in (show, get, copy, cleanup, edit):
        command.add_argument('--json', action='store_true', help='Print a structured JSON report')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        report, code = {'show': _show, 'get': _get, 'copy': _copy, 'cleanup': _cleanup, 'set': _set}[args.command](args)
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
