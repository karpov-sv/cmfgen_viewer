"""Flux-conserving, accuracy-checked quadrature for unbroadened photometry."""

from collections import OrderedDict
import math

try:
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover - optional runtime dependency
    np = None

from .spectrum_transforms import _attenuation_from_exponent, _reddening_exponent


class PreparedPhotometrySampler:
    """Compress integration weights, retaining line flux and extinction in bands.

    Native trapezoidal weights include interpolation at the band edges. Grouping
    their flux contributions loses no unreddened band flux. Each band is refined
    until an exponential-averaging error bound meets the tolerance throughout
    the fitted extinction range. Otherwise native contributions are retained.
    Broadening is deliberately handled by the caller's native-spectrum path.
    """

    relative_tolerance = 1e-4

    def __init__(self, wavelength, flux, centers, widths, ebv_bounds=(0.0, 3.0)):
        self.wavelength = wavelength
        self.flux = flux
        self.centers = centers
        self.widths = widths
        self.max_ebv = max(abs(value) for value in ebv_bounds)
        self.cache = OrderedDict()

    def _prepare(self, redshift):
        shifted = self.wavelength * (1.0 + redshift)
        exponents = _reddening_exponent(shifted)
        all_exponents, all_mass, all_bands = [], [], []
        denominators = np.ones(self.centers.size)
        valid_bands = np.zeros(self.centers.size, dtype=bool)
        for band, (center, width) in enumerate(zip(self.centers, self.widths)):
            if width <= 0:
                # Point sampling is performed separately, without approximation.
                continue
            lo = max(float(shifted[0]), center - width / 2)
            hi = min(float(shifted[-1]), center + width / 2)
            if hi <= lo:
                continue
            left = int(np.searchsorted(shifted, lo, side="right"))
            right = int(np.searchsorted(shifted, hi, side="left"))
            nodes = np.r_[lo, shifted[left:right], hi]
            steps = np.diff(nodes)
            weights = np.r_[steps[0], steps[:-1] + steps[1:], steps[-1]] / 2
            indices = np.arange(left, right)
            native_weights = weights[1:-1]
            # Distribute interpolated endpoints to their native neighbors. This
            # preserves the existing order: redden first, interpolate second.
            for endpoint, weight in ((lo, weights[0]), (hi, weights[-1])):
                i = int(np.clip(np.searchsorted(shifted, endpoint, side="right") - 1, 0, shifted.size - 2))
                fraction = (endpoint - shifted[i]) / (shifted[i + 1] - shifted[i])
                indices = np.r_[indices, i, i + 1]
                native_weights = np.r_[native_weights, weight * (1 - fraction), weight * fraction]
            mass = native_weights * self.flux[indices]
            exponent = exponents[indices]
            selected_exponent, selected_mass = exponent, mass
            # Positive contributions permit stable flux-weighted grouping.
            if (
                mass.size > 64 and np.all(mass >= 0) and np.sum(mass) > 0
                and np.all(np.isfinite(exponent))
                # The attenuation helper replaces overflow/underflow by unity.
                # Keep that exceptional behavior on native quadrature.
                and np.max(np.abs(exponent)) * self.max_ebv * np.log(10) < 700
            ):
                resolution = 300
                while resolution <= 19200:
                    groups = np.floor(np.log(shifted[indices] / lo) * resolution).astype(int)
                    _, groups = np.unique(groups, return_inverse=True)
                    grouped_mass = np.bincount(groups, weights=mass)
                    nonzero = grouped_mass > 0
                    grouped_exponent = np.bincount(groups, weights=mass * exponent)[nonzero] / grouped_mass[nonzero]
                    grouped_mass = grouped_mass[nonzero]
                    low = np.full(nonzero.size, np.inf)
                    high = np.full(nonzero.size, -np.inf)
                    np.minimum.at(low, groups, exponent)
                    np.maximum.at(high, groups, exponent)
                    # For positive flux weights and exponent range d, the
                    # ratio of mean(exp(t*k)) to exp(t*mean(k)) is bounded by
                    # exp(t*t*d*d/8). The largest |E(B-V)| covers the entire
                    # fitted interval, including values between test points.
                    error_bound = (self.max_ebv * np.log(10) * (high[nonzero] - low[nonzero])) ** 2 / 8
                    if np.all(error_bound <= np.log1p(self.relative_tolerance)):
                        selected_exponent, selected_mass = grouped_exponent, grouped_mass
                        break
                    if grouped_mass.size >= mass.size:
                        break
                    resolution *= 2
            all_exponents.append(selected_exponent)
            all_mass.append(selected_mass)
            all_bands.append(np.full(selected_mass.size, band, dtype=int))
            denominators[band] = hi - lo
            valid_bands[band] = True
        if all_mass:
            packed = (np.concatenate(all_exponents), np.concatenate(all_mass), np.concatenate(all_bands))
        else:
            packed = (np.empty(0), np.empty(0), np.empty(0, dtype=int))
        return (*packed, denominators, valid_bands)

    def sample(self, transform, *, redshift, ebv, distance_kpc):
        if (
            not all(math.isfinite(value) for value in (redshift, ebv, distance_kpc))
            or redshift <= -1 or distance_kpc <= 0
        ):
            return None
        if redshift not in self.cache:
            self.cache[redshift] = self._prepare(redshift)
            if len(self.cache) > 4:
                self.cache.popitem(last=False)
        self.cache.move_to_end(redshift)
        exponent, mass, bands, denominators, valid = self.cache[redshift]
        sampled = np.full(self.centers.size, np.nan)
        if mass.size:
            integrals = np.bincount(bands, weights=mass * _attenuation_from_exponent(exponent, ebv), minlength=self.centers.size)
            sampled[valid] = integrals[valid] / denominators[valid] / distance_kpc ** 2
        points = self.widths <= 0
        if np.any(points):
            sampled[points] = transform.sample_unbroadened(self.centers[points], redshift=redshift, ebv=ebv, distance_kpc=distance_kpc)
        return sampled
