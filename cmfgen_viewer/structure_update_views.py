"""Review native RVSIG_COL revisions without running in a live model folder."""
import time
import uuid
import subprocess

from flask import abort, current_app, redirect, render_template, request, url_for

from .model_editor import _resolve_model, ModelEditorError
from .model_editor_views import _after_parameter_save, _editor_breadcrumb
from .runner_config import resolve_runner_config
from .structure_update import (LIMIT, OPERATIONS, apply_structure_plan, build_structure_plan,
                               inspect_structure_update)
from .view_common import _viewer_config, bp, _notification_url


@bp.route('/model-actions/structure/<path:source_path>', methods=['GET', 'POST'])
def model_structure_update(source_path):
    config = _viewer_config()
    if not config.get('read_write_enabled'):
        abort(403)
    basepath = str(config.get('basepath', '.'))
    try:
        _, model = _resolve_model(basepath, source_path)
    except ModelEditorError:
        abort(404)
    cache = current_app.extensions.setdefault('structure_reviews', {})
    now = time.monotonic()
    for token, entry in list(cache.items()):
        if now - entry['created'] > 3600:
            cache.pop(token, None)
    error, plan, token = '', None, ''
    velocity_type, connection = '2', '10'
    grid_options = dict(operation='update', new_depths='', start_depth='1', end_depth='2', points='1', radii='')
    if request.method == 'POST':
        action = request.form.get('action', '')
        try:
            if action == 'apply':
                token = request.form.get('review_token', '')
                entry = cache.get(token)
                if entry is None or entry['source_path'] != source_path:
                    raise ValueError('Review expired or belongs to another model; generate a new candidate.')
                plan = entry['plan']
                saved = apply_structure_plan(model, plan)
                cache.pop(token, None)
                _after_parameter_save(config, basepath=basepath, source_path=source_path,
                    file_relpath='VADAT', saved={'affects_solution': True})
                return redirect(_notification_url('viewer.model_parameters', source_path=source_path,
                    message='Structure updated; previous files and checkpoints were archived at ' + saved['archive_path']))
            if action != 'preview':
                abort(400)
            velocity_type = request.form.get('velocity_type', '2')
            connection = request.form.get('connection_velocity', '10')
            grid_options.update({key: request.form[key] for key in grid_options if key in request.form})
            upload = request.files.get('candidate')
            candidate = None
            if upload and upload.filename:
                data = upload.stream.read(LIMIT + 1)
                if len(data) > LIMIT:
                    raise ValueError('Candidate exceeds the 2 MiB limit.')
                candidate = data.decode('utf-8')
            native, _ = resolve_runner_config(cmfgen_root=config.get('cmfgen_root'), require_roots=False)
            plan = build_structure_plan(model, cmfgen_root=native.get('cmfgen_root'),
                velocity_type=int(velocity_type), connection_velocity=float(connection), candidate=candidate,
                **grid_options)
            token = uuid.uuid4().hex
            if len(cache) >= 16:
                cache.pop(next(iter(cache)))
            cache[token] = {'created': now, 'source_path': source_path, 'plan': plan}
        except (ValueError, OSError) as exc:
            error = str(exc)
        except subprocess.TimeoutExpired:
            error = 'Native structure revision timed out. No model files were changed.'
    return render_template('model_structure_update.html', source_path=source_path,
        structure_status=inspect_structure_update(model), plan=plan, review_token=token,
        error=error, velocity_type=velocity_type, connection_velocity=connection,
        operations=OPERATIONS, grid_options=grid_options,
        breadcrumb=_editor_breadcrumb(source_path, 'Update structure'))
