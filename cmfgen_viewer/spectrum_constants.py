"""Physical units and defaults shared by spectrum calculations and plots."""

from __future__ import annotations

LIGHT_SPEED_ANGSTROM_PER_10P15_HZ = 2997.92458


LIGHT_SPEED_CM_PER_S = 2.99792458e10


ANGSTROM_PER_CM = 1e8


JANSKY_TO_CGS_HZ = 1e-23


JY_TO_FLAMBDA_ANGSTROM_FACTOR = (
    JANSKY_TO_CGS_HZ * LIGHT_SPEED_CM_PER_S * ANGSTROM_PER_CM
)


LIGHT_SPEED_KM_PER_S = 299792.458


MAX_MODEL_TIME_LINES = 4


MAX_SPECIES_ROWS = 12


MAX_SERIES_POINTS = 5000


OBSERVED_ERROR_BAR_COLOR = "rgba(33, 37, 41, 0.45)"


OBSERVED_ERROR_BAR_THICKNESS = 1.2


OBSERVED_ERROR_BAR_CAP_WIDTH = 0


PHOTOMETRY_FIT_FLUX_ERR_FALLBACK_FRACTION = 0.02


FIT_DIFF_STEPS = {
    "redshift": 1e-4,
    "broadening_km_s": 1.0,
    "ebv": 0.01,
    "distance_kpc": 0.05,
}


ABSOLUTE_FIT_BOUNDS = {
    "redshift": (-0.02, 0.02),
    "broadening_km_s": (0.0, 800.0),
    "ebv": (0.0, 3.0),
    "distance_kpc": (0.05, 50.0),
}


NORMALIZED_FIT_BOUNDS = {
    "redshift": (-0.02, 0.02),
    "broadening_km_s": (0.0, 800.0),
}


FIT_CANCELED_MESSAGE = "Fit canceled."


SPECTRUM_TRANSFORM_DEFAULTS = {
    "redshift": 0.0,
    "broadening_km_s": 0.0,
    "ebv": 0.0,
    "distance_kpc": 1.0,
    "normalization": 1.0,
}


DEFAULT_SPECTRUM_LAMBDA_MAX_ANGSTROM = 250000.0
