/* Shared physical calculations for every spectrum viewer. */
(function (root) {
  "use strict";
  var LIGHT_SPEED_KM_PER_S = 299792.458;

  function polyEval(coeffs, x) {
    var value = 0;
    for (var i = 0; i < coeffs.length; i += 1) {
      value = value * x + coeffs[i];
    }
    return value;
  }

  function buildNaturalSpline(xs, ys) {
    var n = xs.length;
    var y2 = new Array(n).fill(0);
    var u = new Array(n - 1).fill(0);
    y2[0] = 0;
    u[0] = 0;

    for (var i = 1; i < n - 1; i += 1) {
      var sig = (xs[i] - xs[i - 1]) / (xs[i + 1] - xs[i - 1]);
      var p = sig * y2[i - 1] + 2;
      y2[i] = (sig - 1) / p;
      var d1 = (ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]);
      var d0 = (ys[i] - ys[i - 1]) / (xs[i] - xs[i - 1]);
      var dd = (6 * (d1 - d0) / (xs[i + 1] - xs[i - 1]) - sig * u[i - 1]) / p;
      u[i] = dd;
    }

    y2[n - 1] = 0;
    for (var k = n - 2; k >= 0; k -= 1) {
      y2[k] = y2[k] * y2[k + 1] + u[k];
    }
    return {
      xs: xs,
      ys: ys,
      y2: y2
    };
  }

  function evalNaturalSpline(spline, x) {
    var xs = spline.xs;
    var ys = spline.ys;
    var y2 = spline.y2;
    var n = xs.length;
    var xClamped = x;
    if (xClamped <= xs[0]) {
      xClamped = xs[0];
    } else if (xClamped >= xs[n - 1]) {
      xClamped = xs[n - 1];
    }

    var klo = 0;
    var khi = n - 1;
    while (khi - klo > 1) {
      var mid = (khi + klo) >> 1;
      if (xs[mid] > xClamped) {
        khi = mid;
      } else {
        klo = mid;
      }
    }
    var h = xs[khi] - xs[klo];
    if (h === 0) {
      return ys[klo];
    }
    var a = (xs[khi] - xClamped) / h;
    var b = (xClamped - xs[klo]) / h;
    return a * ys[klo] + b * ys[khi] + ((a * a * a - a) * y2[klo] + (b * b * b - b) * y2[khi]) * h * h / 6;
  }

  function buildFmCurveEvaluator(rV) {
    var x0 = 4.596;
    var gamma = 0.99;
    var c4 = 0.41;
    var c3 = 3.23;
    var c2 = -0.824 + 4.717 / rV;
    var c1 = 2.030 - 3.007 * c2;
    var xcutuv = 10000 / 2700;
    var xspluv = [10000 / 2700, 10000 / 2600];

    function uvCurve(x) {
      var xx = x * x;
      var drudeDen = (xx - x0 * x0) * (xx - x0 * x0) + (x * gamma) * (x * gamma);
      var y = c1 + c2 * x + c3 * xx / drudeDen;
      var delta = Math.max(0, x - 5.9);
      y += c4 * (0.5392 * delta * delta + 0.05644 * delta * delta * delta);
      return y + rV;
    }

    var yspluv = [uvCurve(xspluv[0]), uvCurve(xspluv[1])];
    var xsplopir = [0, 10000 / 26500, 10000 / 12200, 10000 / 6000, 10000 / 5470, 10000 / 4670, 10000 / 4110];
    var ysplir = [0, 0.26469, 0.82925].map(function (value) {
      return value * rV / 3.1;
    });
    var ysplop = [
      polyEval([2.13572e-4, 1.00270, -4.22809e-1], rV),
      polyEval([-7.35778e-5, 1.00216, -5.13540e-2], rV),
      polyEval([-3.32598e-5, 1.00184, 7.00127e-1], rV),
      polyEval([-4.45636e-5, 7.97809e-4, -5.46959e-3, 1.01707, 1.19456], rV)
    ];
    var xsSpline = xsplopir.concat(xspluv);
    var ysSpline = ysplir.concat(ysplop).concat(yspluv);
    var spline = buildNaturalSpline(xsSpline, ysSpline);

    return function (wavelengthAngstrom) {
      if (!Number.isFinite(wavelengthAngstrom) || wavelengthAngstrom <= 0) {
        return 0;
      }
      var x = 10000 / wavelengthAngstrom;
      if (x >= xcutuv) {
        return uvCurve(x);
      }
      return evalNaturalSpline(spline, x);
    };
  }

  var fmCurveAt = buildFmCurveEvaluator(3.1);
  function reddeningScaleAt(wavelengthAngstrom, ebv) {
    if (!Number.isFinite(ebv) || ebv === 0) {
      return 1;
    }
    var curve = fmCurveAt(wavelengthAngstrom);
    var factor = Math.pow(10, -0.4 * ebv * curve);
    if (!Number.isFinite(factor) || factor <= 0) {
      return 1;
    }
    return factor;
  }

  function gaussianBroadenAscending(wavelengths, values, sigmaKmPerS) {
    var n = wavelengths.length;
    if (n < 3 || values.length !== n) {
      return values.slice();
    }

    var first = wavelengths[0];
    var last = wavelengths[n - 1];
    if (!Number.isFinite(first) || !Number.isFinite(last) || first <= 0 || last <= first) {
      return values.slice();
    }

    var logMin = Math.log(first);
    var logMax = Math.log(last);
    var dLog = (logMax - logMin) / (n - 1);
    if (!Number.isFinite(dLog) || dLog <= 0) {
      return values.slice();
    }

    var sigmaLog = sigmaKmPerS / LIGHT_SPEED_KM_PER_S;
    var sigmaPixels = sigmaLog / dLog;
    if (!Number.isFinite(sigmaPixels) || sigmaPixels < 0.15) {
      return values.slice();
    }

    var halfWidth = Math.max(1, Math.ceil(4 * sigmaPixels));
    halfWidth = Math.min(halfWidth, 300);

    var kernel = new Array(2 * halfWidth + 1);
    for (var offset = -halfWidth; offset <= halfWidth; offset += 1) {
      kernel[offset + halfWidth] = Math.exp(-0.5 * (offset * offset) / (sigmaPixels * sigmaPixels));
    }

    var sampled = new Array(n);
    var sourceIndex = 0;
    for (var sampleIndex = 0; sampleIndex < n; sampleIndex += 1) {
      var sampleLog = logMin + sampleIndex * dLog;
      var sampleX = Math.exp(sampleLog);
      while (sourceIndex < n - 2 && wavelengths[sourceIndex + 1] < sampleX) {
        sourceIndex += 1;
      }

      var x0 = wavelengths[sourceIndex];
      var x1 = wavelengths[sourceIndex + 1];
      var y0 = values[sourceIndex];
      var y1 = values[sourceIndex + 1];
      if (!Number.isFinite(x0) || !Number.isFinite(x1) || x1 <= x0 || !Number.isFinite(y0) || !Number.isFinite(y1)) {
        sampled[sampleIndex] = Number.isFinite(y0) ? y0 : 0;
        continue;
      }

      var t = (sampleX - x0) / (x1 - x0);
      if (t < 0) {
        t = 0;
      } else if (t > 1) {
        t = 1;
      }
      sampled[sampleIndex] = y0 + (y1 - y0) * t;
    }

    var smoothed = new Array(n);
    for (var i = 0; i < n; i += 1) {
      var weightedSum = 0;
      var weightNorm = 0;
      for (var k = -halfWidth; k <= halfWidth; k += 1) {
        var j = i + k;
        if (j < 0 || j >= n) {
          continue;
        }
        var yValue = sampled[j];
        if (!Number.isFinite(yValue)) {
          continue;
        }
        var weight = kernel[k + halfWidth];
        weightedSum += yValue * weight;
        weightNorm += weight;
      }
      smoothed[i] = weightNorm > 0 ? weightedSum / weightNorm : sampled[i];
    }

    var result = new Array(n);
    for (var p = 0; p < n; p += 1) {
      var x = wavelengths[p];
      if (!Number.isFinite(x) || x <= 0) {
        result[p] = values[p];
        continue;
      }

      var at = (Math.log(x) - logMin) / dLog;
      if (!Number.isFinite(at)) {
        result[p] = values[p];
        continue;
      }
      if (at <= 0) {
        result[p] = smoothed[0];
        continue;
      }
      if (at >= n - 1) {
        result[p] = smoothed[n - 1];
        continue;
      }
      var lo = Math.floor(at);
      var frac = at - lo;
      result[p] = smoothed[lo] + (smoothed[lo + 1] - smoothed[lo]) * frac;
    }

    return result;
  }

  function gaussianBroadenByVelocity(wavelengths, values, sigmaKmPerS) {
    if (!Number.isFinite(sigmaKmPerS) || sigmaKmPerS <= 0) {
      return values.slice();
    }
    if (!Array.isArray(wavelengths) || !Array.isArray(values) || wavelengths.length !== values.length) {
      return values.slice();
    }
    if (wavelengths.length < 3) {
      return values.slice();
    }
    if (wavelengths[0] <= wavelengths[wavelengths.length - 1]) {
      return gaussianBroadenAscending(wavelengths, values, sigmaKmPerS);
    }
    var reversedX = wavelengths.slice().reverse();
    var reversedY = values.slice().reverse();
    return gaussianBroadenAscending(reversedX, reversedY, sigmaKmPerS).reverse();
  }

  function transformSeries(wavelengths, flux, options) {
    var shifted = wavelengths.map(function (value) { return value * (1 + options.redshift); });
    var transformed = flux.slice();
    if (options.mode === "both") {
      var scale = (options.normalization === undefined ? 1 : options.normalization)
        / (options.distance_kpc * options.distance_kpc);
      transformed = flux.map(function (value, index) {
        return value * scale * reddeningScaleAt(shifted[index], options.ebv);
      });
    }
    if (options.broadening_km_s > 0) {
      transformed = gaussianBroadenByVelocity(shifted, transformed, options.broadening_km_s);
    }
    return [shifted, transformed];
  }

  var api = { transformSeries: transformSeries, reddeningScaleAt: reddeningScaleAt, gaussianBroadenByVelocity: gaussianBroadenByVelocity,
              buildNaturalSpline: buildNaturalSpline, evalNaturalSpline: evalNaturalSpline };
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CmfgenSpectrumTransforms = api;
})(typeof window !== "undefined" ? window : globalThis);
