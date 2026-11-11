"""Wavelength conventions; models use vacuum, uploads retain their native axis.

Ciddor (1996), using the SDSS DR9+ formula. Below 2000 Å use vacuum.
"""

from __future__ import annotations


def normalize_wavelength_medium(value: object = "air") -> str:
    medium = str(value or "air").strip().lower()
    if medium not in {"air", "vacuum"}:
        raise ValueError("Wavelength convention must be air or vacuum.")
    return medium


def vacuum_to_air(wavelength, *, flux_jacobian: bool = False):
    import numpy as np

    wave = np.asarray(wavelength, dtype=float)
    safe = np.maximum(wave, 2000.0)
    s2 = (10000 / safe) ** 2
    a, b = 238.0185 - s2, 57.362 - s2
    index = 1 + 0.05792105 / a + 0.00167917 / b
    if flux_jacobian:
        slope = 0.05792105 / a**2 + 0.00167917 / b**2
        return np.where(wave >= 2000, index**2 / (index + 2 * s2 * slope), 1.0)
    return np.where(wave >= 2000, wave / index, wave)


def air_to_vacuum(wavelength):
    import numpy as np

    wave = np.asarray(wavelength, dtype=float)
    vacuum = np.maximum(wave, 2000.0)
    target = vacuum.copy()
    for _ in range(4):
        vacuum = vacuum * target / vacuum_to_air(vacuum)
    return np.where(wave >= 2000, vacuum, wave)


def to_upload_medium(wavelength, flux, *, medium: str, absolute: bool):
    """Convert a redshifted, broadened vacuum model; preserve integrated flux."""
    if medium != "air":
        return wavelength, flux
    import numpy as np

    values = flux * vacuum_to_air(wavelength, flux_jacobian=True) if absolute else flux
    axis = vacuum_to_air(wavelength)
    # The conventional UV cutoff has a tiny overlap; keep interpolation ordered.
    if np.any(np.diff(axis) <= 0):
        order = np.argsort(axis)
        axis, values = axis[order], values[order]
    return axis, values
