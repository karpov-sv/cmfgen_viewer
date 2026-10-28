"""Read-only archive access and explicitly reviewed recovery housekeeping."""
from flask import abort, current_app, redirect, render_template, request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .browser import make_breadcrumb
from .model_editor import _resolve_model, ModelEditorError
from .model_history import (HistoryError, list_archives, archive_files, load_archived_control,
                            preview_housekeeping, apply_housekeeping)
from .history_inputs import preview_inputs, apply_inputs
from .model_activity import inspect_model_activity
from .view_common import bp, _viewer_config, _notification_url


def history_signer():
    return URLSafeTimedSerializer(current_app.secret_key, salt='model-history-cleanup')


@bp.route('/model-actions/history/<path:source_path>', methods=['GET', 'POST'])
def model_history(source_path):
    config = _viewer_config()
    try:
        _, model = _resolve_model(str(config['basepath']), source_path)
    except ModelEditorError:
        abort(404)
    writable = bool(config.get('read_write_enabled'))
    error, review, token = '', None, None
    inputs_review, inputs_token, inputs_problem = None, None, ''
    try:
        days = int(request.args.get('older_than', request.form.get('older_than', '0')))
        if days < 0:
            raise ValueError
    except ValueError:
        days = 0
    if request.method == 'POST':
        if not writable:
            abort(403)
        try:
            if request.form.get('action') == 'preview_inputs':
                inputs_review = preview_inputs(model, request.form.get('archive', ''))
                inputs_token = history_signer().dumps({'model': str(model), 'inputs': inputs_review})
            elif request.form.get('action') == 'restore_inputs':
                signed = history_signer().loads(request.form.get('review_token', ''), max_age=1800)
                if signed['model'] != str(model):
                    raise HistoryError('Recovery preview belongs to another model.')
                result = apply_inputs(model, signed['inputs'])
                try:
                    from .summary_cache import delete_model_summary_entries
                    delete_model_summary_entries(str(config['summary_cache_db']),
                        basepath=str(config['basepath']), relpaths=[source_path])
                except Exception:
                    current_app.logger.warning('Could not invalidate summary after input recovery', exc_info=True)
                return redirect(_notification_url('viewer.model_main_computation', source_path=source_path,
                    message='Saved inputs restored for a fresh run. Previous inputs and derived state were archived under ' + result['backup'] + '. No calculation was started.',
                    warning=' '.join(result['recovery']['warnings'])))
            elif request.form.get('action') == 'apply':
                signed = history_signer().loads(request.form.get('review_token', ''), max_age=1800)
                if signed['model'] != str(model):
                    raise HistoryError('Cleanup preview belongs to another model.')
                warnings = apply_housekeeping(model, signed['review'])
                return redirect(_notification_url('viewer.model_history', source_path=source_path,
                    message=f"{'Compacted' if signed['review']['action'] == 'compact' else 'Deleted'} {len(signed['review']['entries'])} archive(s).",
                    warning=' '.join(warnings)))
            else:
                action = request.form.get('cleanup_action', '')
                review = preview_housekeeping(model, request.form.getlist('archive_id'), action)
                token = history_signer().dumps({'model': str(model), 'review': review})
        except (HistoryError, OSError, BadSignature, KeyError) as exc:
            error = str(exc) if not isinstance(exc, BadSignature) else 'Review expired or is invalid; preview again.'
    archives, warnings = list_archives(model)
    selected, files, comparison = None, [], None
    archive_id = request.args.get('archive', request.form.get('archive', ''))
    if inputs_review:
        archive_id = inputs_review['archive_id']
    try:
        if archive_id:
            selected, files = archive_files(model, archive_id)
            if request.args.get('file') and inputs_review is None:
                comparison = load_archived_control(model, archive_id, request.args['file'])
    except (ModelEditorError, OSError) as exc:
        error = str(exc)
    if selected and selected.get('stage') in {'main', 'test'} and inputs_review is None:
        try:
            preview_inputs(model, archive_id)
        except (ModelEditorError, OSError) as exc:
            inputs_problem = str(exc)
    activity = inspect_model_activity(model)
    return render_template('model_history.html', source_path=source_path,
        archives=[entry for entry in archives if entry['age_days'] >= days], older_than=days,
        total_size=sum(entry['size'] for entry in archives), total_count=len(archives),
        error=error, warnings=warnings, selected=selected, files=files, comparison=comparison,
        controls=[file for file in files if file.get('target')],
        review=review, review_token=token, writable=writable, activity=activity,
        inputs_review=inputs_review, inputs_token=inputs_token, inputs_problem=inputs_problem,
        breadcrumb=make_breadcrumb(source_path) + [{'name': 'History and recovery', 'path': None}])
