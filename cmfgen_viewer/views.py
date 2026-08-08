"""Viewer blueprint assembly and compatibility exports.

Route implementations are grouped by concern in sibling route modules.
Importing them registers every route on the shared viewer blueprint.
"""

from .view_common import (
    _append_transform_query,
    _build_summary_row,
    _bulk_spectra_url,
    _collect_obs_tokens,
    _collect_rel_paths,
    _format_query_float,
    _format_summary_value,
    _grid_fit_source_label,
    _normalize_fit_bounds,
    _normalize_fit_wavelength_range,
    _normalize_grid_fit_source,
    _normalize_spectrum_mode,
    _normalize_transform_params,
    _parse_summary_float,
    _resolve_selected_model_dirs,
    _spectrum_lambda_bounds,
    _spectrum_url,
    bp,
)
from .upload_views import query_vizier_photometry_points
from .grid_catalog import (
    _empty_tlusty_confidence_profiles,
    _summarize_tlusty_confidence_profiles,
)

# Route modules register handlers on the shared blueprint as import side effects.
from . import browser_views as _browser_views  # noqa: E402,F401
from . import grid_views as _grid_views  # noqa: E402,F401
from . import model_views as _model_views  # noqa: E402,F401
from . import model_editor_views as _model_editor_views  # noqa: E402,F401
from . import model_write_views as _model_write_views  # noqa: E402,F401
from . import model_workflow_views as _model_workflow_views  # noqa: E402,F401
from . import model_run_workflow_views as _model_run_workflow_views  # noqa: E402,F401
from . import model_runtime_views as _model_runtime_views  # noqa: E402,F401
from . import spectrum_views as _spectrum_views  # noqa: E402,F401
from . import system_views as _system_views  # noqa: E402,F401
from . import task_views as _task_views  # noqa: E402,F401

__all__ = [
    "bp",
    "query_vizier_photometry_points",
    "_append_transform_query",
    "_build_summary_row",
    "_bulk_spectra_url",
    "_collect_obs_tokens",
    "_collect_rel_paths",
    "_empty_tlusty_confidence_profiles",
    "_format_query_float",
    "_format_summary_value",
    "_grid_fit_source_label",
    "_normalize_fit_bounds",
    "_normalize_fit_wavelength_range",
    "_normalize_grid_fit_source",
    "_normalize_spectrum_mode",
    "_normalize_transform_params",
    "_parse_summary_float",
    "_resolve_selected_model_dirs",
    "_spectrum_lambda_bounds",
    "_spectrum_url",
    "_summarize_tlusty_confidence_profiles",
]
