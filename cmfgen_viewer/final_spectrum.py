"""Compatibility imports for the former combined spectrum module.

New code should import the focused metadata, IO, transforms, fitting, or plot
module directly. Existing callers retain their function and constant names.
"""

from .model_metadata import VADAT_ENTRY_RE as VADAT_ENTRY_RE
from .model_metadata import _as_text as _as_text
from .model_metadata import _parse_float_legacy as _parse_float_legacy
from .model_metadata import _parse_mod_sum as _parse_mod_sum
from .model_metadata import _parse_vadat as _parse_vadat
from .model_metadata import _read_model_cached as _read_model_cached
from .model_metadata import _safe_stat as _safe_stat
from .model_metadata import build_model_summary_sections as build_model_summary_sections
from .model_metadata import read_model as read_model
from .spectrum_constants import ABSOLUTE_FIT_BOUNDS as ABSOLUTE_FIT_BOUNDS
from .spectrum_constants import ANGSTROM_PER_CM as ANGSTROM_PER_CM
from .spectrum_constants import FIT_CANCELED_MESSAGE as FIT_CANCELED_MESSAGE
from .spectrum_constants import FIT_DIFF_STEPS as FIT_DIFF_STEPS
from .spectrum_constants import JANSKY_TO_CGS_HZ as JANSKY_TO_CGS_HZ
from .spectrum_constants import (
    JY_TO_FLAMBDA_ANGSTROM_FACTOR as JY_TO_FLAMBDA_ANGSTROM_FACTOR,
)
from .spectrum_constants import (
    LIGHT_SPEED_ANGSTROM_PER_10P15_HZ as LIGHT_SPEED_ANGSTROM_PER_10P15_HZ,
)
from .spectrum_constants import LIGHT_SPEED_CM_PER_S as LIGHT_SPEED_CM_PER_S
from .spectrum_constants import LIGHT_SPEED_KM_PER_S as LIGHT_SPEED_KM_PER_S
from .spectrum_constants import MAX_MODEL_TIME_LINES as MAX_MODEL_TIME_LINES
from .spectrum_constants import MAX_SERIES_POINTS as MAX_SERIES_POINTS
from .spectrum_constants import MAX_SPECIES_ROWS as MAX_SPECIES_ROWS
from .spectrum_constants import NORMALIZED_FIT_BOUNDS as NORMALIZED_FIT_BOUNDS
from .spectrum_constants import (
    OBSERVED_ERROR_BAR_CAP_WIDTH as OBSERVED_ERROR_BAR_CAP_WIDTH,
)
from .spectrum_constants import OBSERVED_ERROR_BAR_COLOR as OBSERVED_ERROR_BAR_COLOR
from .spectrum_constants import (
    OBSERVED_ERROR_BAR_THICKNESS as OBSERVED_ERROR_BAR_THICKNESS,
)
from .spectrum_constants import (
    PHOTOMETRY_FIT_FLUX_ERR_FALLBACK_FRACTION as PHOTOMETRY_FIT_FLUX_ERR_FALLBACK_FRACTION,
)
from .spectrum_fitting import (
    _build_observed_series_for_fit as _build_observed_series_for_fit,
)
from .spectrum_fitting import (
    _estimate_effective_sample_size_from_residuals as _estimate_effective_sample_size_from_residuals,
)
from .spectrum_fitting import _FitCanceledError as _FitCanceledError
from .spectrum_fitting import _resolve_fit_bounds as _resolve_fit_bounds
from .spectrum_fitting import (
    _sample_model_on_observed_grid as _sample_model_on_observed_grid,
)
from .spectrum_fitting import (
    _spectrum_sigma_with_fallback as _spectrum_sigma_with_fallback,
)
from .spectrum_fitting import fit_model_to_observed as fit_model_to_observed
from .spectrum_io import COUNT_RE as COUNT_RE
from .spectrum_io import _load_obs_spectrum_cached as _load_obs_spectrum_cached
from .spectrum_io import _normalize_wavelength_bounds as _normalize_wavelength_bounds
from .spectrum_io import _series_heading as _series_heading
from .spectrum_io import _trim_short_wavelength_floor as _trim_short_wavelength_floor
from .spectrum_io import discover_final_spectrum_files as discover_final_spectrum_files
from .spectrum_io import load_obs_spectrum as load_obs_spectrum
from .spectrum_options import spectrum_fit_bounds as spectrum_fit_bounds
from .spectrum_plots import (
    _downsample_spectrum_with_flux_err as _downsample_spectrum_with_flux_err,
)
from .spectrum_plots import _plot_config as _plot_config
from .spectrum_plots import _plot_layout as _plot_layout
from .spectrum_plots import build_both_plot as build_both_plot
from .spectrum_plots import build_final_model_series as build_final_model_series
from .spectrum_plots import build_normalized_plot as build_normalized_plot
from .spectrum_plots import build_observed_overlay_trace as build_observed_overlay_trace
from .spectrum_plots import build_uploaded_spectrum_plot as build_uploaded_spectrum_plot
from .spectrum_plots import fin_file_label as fin_file_label
from .spectrum_plots import spectrum_data_rows as spectrum_data_rows
from .spectrum_transforms import _apply_transform_arrays as _apply_transform_arrays
from .spectrum_transforms import (
    _build_model_series_for_fit as _build_model_series_for_fit,
)
from .spectrum_transforms import _clean_xy_arrays as _clean_xy_arrays
from .spectrum_transforms import _clean_xy_with_band_width as _clean_xy_with_band_width
from .spectrum_transforms import _fm_curve_spline as _fm_curve_spline
from .spectrum_transforms import (
    _gaussian_broaden_ascending as _gaussian_broaden_ascending,
)
from .spectrum_transforms import (
    _gaussian_broaden_by_velocity as _gaussian_broaden_by_velocity,
)
from .spectrum_transforms import _interp_linear as _interp_linear
from .spectrum_transforms import _jy_to_cgs_per_angstrom as _jy_to_cgs_per_angstrom
from .spectrum_transforms import _reddening_scale as _reddening_scale
from .spectrum_transforms import apply_spectrum_transform as apply_spectrum_transform
