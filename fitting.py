"""
Robust curve fitting used by the extraction layer (analysis.py) and by the
simulator (T1 histogram).

Every fit goes through `least_squares_fit`, which uses scipy.optimize.curve_fit
when scipy is installed and falls back to a small built-in Levenberg–Marquardt
solver otherwise, so the GUI never hard-depends on scipy.

Each fit:
    * builds data-driven initial guesses (FFT, extrema, 1/e crossing, half-max…),
    * tries several starting points and keeps the best one,
    * returns a FitResult with best parameters, 1σ uncertainties, R² and a callable
      model (used to draw the fit on the plot).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

try:
    from scipy.optimize import curve_fit as _curve_fit
    HAS_SCIPY = True
except Exception:  # pragma: no cover - depends on the environment
    HAS_SCIPY = False


# ==================================================================================
# Result container
# ==================================================================================
@dataclass
class FitResult:
    ok: bool
    params: Dict[str, float] = field(default_factory=dict)
    errors: Dict[str, float] = field(default_factory=dict)
    r2: float = float("nan")
    model: Optional[Callable] = None
    message: str = ""

    def __getitem__(self, key):
        return self.params[key]

    def err(self, key) -> float:
        return float(self.errors.get(key, float("nan")))

    def rel_err(self, key) -> float:
        v = self.params.get(key, float("nan"))
        e = self.err(key)
        if not np.isfinite(e) or v == 0:
            return float("inf")
        return abs(e / v)

    def curve(self, x, n: int = 600):
        """Dense (x, y) of the fitted model over the range of x, for overlays."""
        xs = np.linspace(np.nanmin(x), np.nanmax(x), n)
        return xs, self.model(xs)


FAILED = FitResult(ok=False, message="fit failed")


# ==================================================================================
# Small numerical helpers
# ==================================================================================
def smooth(y, w: int = 5):
    """Centered moving average that keeps the array length (edges renormalised)."""
    y = np.asarray(y, float)
    if w <= 1 or len(y) < w:
        return y.copy()
    k = np.ones(w)
    num = np.convolve(np.nan_to_num(y), k, mode="same")
    den = np.convolve(np.isfinite(y).astype(float), k, mode="same")
    return num / np.maximum(den, 1e-12)


def noise_sigma(y) -> float:
    """Robust white-noise estimate from first differences (insensitive to slow signal)."""
    y = np.asarray(y, float)
    y = y[np.isfinite(y)]
    if len(y) < 4:
        return float("nan")
    d = np.diff(y)
    mad = np.median(np.abs(d - np.median(d)))
    return float(1.4826 * mad / np.sqrt(2.0))


def dominant_frequency(x, y) -> Optional[float]:
    """Dominant frequency of an oscillating signal (units = 1/units of x).

    Hann window + zero padding + parabolic interpolation of the spectral peak, so
    the estimate is much finer than the raw 1/span FFT resolution.
    """
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = len(y)
    if n < 6:
        return None
    dx = float(np.median(np.diff(x)))
    if dx <= 0:
        return None
    y = y - np.mean(y)
    nfft = int(2 ** np.ceil(np.log2(16 * n)))
    spec = np.abs(np.fft.rfft(y * np.hanning(n), n=nfft))
    freqs = np.fft.rfftfreq(nfft, d=dx)
    span = dx * (n - 1)
    spec[freqs < 0.5 / span] = 0.0          # drop DC / slow drifts
    k = int(np.argmax(spec))
    if spec[k] <= 0 or k == 0:
        return None
    if 0 < k < len(spec) - 1:
        a, b, c = spec[k - 1], spec[k], spec[k + 1]
        den = a - 2 * b + c
        shift = 0.5 * (a - c) / den if den != 0 else 0.0
        return float(freqs[k] + shift * (freqs[1] - freqs[0]))
    return float(freqs[k])


def hist_bins(n: int) -> int:
    """Number of histogram bins used both by the plot and by the overlay fit."""
    return int(min(30, max(5, n // 5)))


def symmetry_center(x, Z, n_grid: int = 401):
    """Mirror axis x = d of a 2D map Z[row, x] (chevrons are symmetric in detuning).

    Minimises the mean squared difference between Z(x) and Z(2d − x) over the
    overlapping region; d is searched in the central half of the window and refined
    with a parabola. Returns (d, curvature-based uncertainty) or (None, nan).
    """
    x = np.asarray(x, float)
    Z = np.asarray(Z, float)
    if x[0] > x[-1]:
        x, Z = x[::-1], Z[:, ::-1]
    rows = np.all(np.isfinite(Z), axis=1)
    Z = Z[rows] - np.nanmean(Z[rows])
    if Z.shape[0] == 0 or len(x) < 7:
        return None, float("nan")
    span = x[-1] - x[0]
    ds = np.linspace(x[0] + 0.25 * span, x[-1] - 0.25 * span, n_grid)
    cost = np.full(n_grid, np.inf)
    for k, d in enumerate(ds):
        xm = 2 * d - x
        ok = (xm >= x[0]) & (xm <= x[-1])
        if ok.sum() < 5:
            continue
        Zm = np.array([np.interp(xm[ok], x, row) for row in Z])
        cost[k] = float(np.mean((Z[:, ok] - Zm) ** 2))
    k = int(np.argmin(cost))
    if not np.isfinite(cost[k]):
        return None, float("nan")
    d = float(ds[k])
    err = float(ds[1] - ds[0])
    if 0 < k < n_grid - 1 and np.all(np.isfinite(cost[k - 1:k + 2])):
        a, b, c = cost[k - 1], cost[k], cost[k + 1]
        den = a - 2 * b + c
        if den > 0:
            d += 0.5 * (a - c) / den * (ds[1] - ds[0])
    return d, err


def _r2(y, yfit) -> float:
    ss_res = float(np.sum((y - yfit) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


# ==================================================================================
# Core least-squares engine
# ==================================================================================
def _lm(func, x, y, p0, lo, hi, n_iter=300):
    """Minimal bounded Levenberg–Marquardt (used only when scipy is missing)."""
    p = np.array(p0, float)

    def res(pp):
        return func(x, *pp) - y

    r = res(p)
    cost = float(r @ r)
    lam = 1e-3
    J = np.zeros((len(x), len(p)))
    for _ in range(n_iter):
        for j in range(len(p)):
            h = 1e-6 * max(abs(p[j]), 1e-6)
            dp = p.copy()
            dp[j] += h
            J[:, j] = (res(dp) - r) / h
        A = J.T @ J
        g = J.T @ r
        improved = False
        small = False
        for _ in range(12):
            try:
                step = np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-12), -g)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            pn = np.clip(p + step, lo, hi)
            rn = res(pn)
            cn = float(rn @ rn)
            if np.isfinite(cn) and cn < cost:
                small = abs(cost - cn) < 1e-12 * max(cost, 1e-30)
                p, r, cost = pn, rn, cn
                lam = max(lam / 10, 1e-12)
                improved = True
                break
            lam *= 10
        if not improved or small:
            break
    dof = max(1, len(x) - len(p))
    cov = np.linalg.pinv(J.T @ J) * cost / dof
    return p, cov


def least_squares_fit(func, x, y, p0, names: Sequence[str], bounds=None) -> FitResult:
    """Fit `func(x, *p)` to (x, y). Returns a FitResult (never raises)."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < len(p0) + 2:
        return FitResult(ok=False, message="not enough points")

    n = len(p0)
    lo = np.full(n, -np.inf) if bounds is None else np.asarray(bounds[0], float)
    hi = np.full(n, np.inf) if bounds is None else np.asarray(bounds[1], float)
    p0 = np.array(p0, float)
    # start strictly inside the bounds (curve_fit refuses infeasible x0)
    for i in range(n):
        if np.isfinite(lo[i]) and np.isfinite(hi[i]):
            eps = 1e-9 * (hi[i] - lo[i])
            p0[i] = min(max(p0[i], lo[i] + eps), hi[i] - eps)
        elif np.isfinite(lo[i]):
            p0[i] = max(p0[i], lo[i] + 1e-12 * max(1.0, abs(lo[i])))
        elif np.isfinite(hi[i]):
            p0[i] = min(p0[i], hi[i] - 1e-12 * max(1.0, abs(hi[i])))

    try:
        if HAS_SCIPY:
            popt, pcov = _curve_fit(func, x, y, p0=p0, bounds=(lo, hi), maxfev=20000)
        else:
            popt, pcov = _lm(func, x, y, p0, lo, hi)
    except Exception as exc:  # noqa: BLE001
        return FitResult(ok=False, message=f"{type(exc).__name__}: {exc}")

    yfit = func(x, *popt)
    if not np.all(np.isfinite(yfit)):
        return FitResult(ok=False, message="non-finite model")
    with np.errstate(invalid="ignore"):
        perr = np.sqrt(np.abs(np.diag(pcov))) if pcov is not None else np.full(n, np.nan)
    params = {k: float(v) for k, v in zip(names, popt)}
    errors = {k: float(e) if np.isfinite(e) else float("nan") for k, e in zip(names, perr)}
    p_final = tuple(popt)
    return FitResult(ok=True, params=params, errors=errors, r2=_r2(y, yfit),
                     model=lambda xx, _p=p_final: func(np.asarray(xx, float), *_p))


def _best(results: List[FitResult]) -> FitResult:
    good = [r for r in results if r.ok and np.isfinite(r.r2)]
    return max(good, key=lambda r: r.r2) if good else FAILED


# ==================================================================================
# Models
# ==================================================================================
def _exp_decay(t, A, T, C):
    return A * np.exp(-t / T) + C


def fit_exp_decay(x, y) -> FitResult:
    """y = A·exp(-x/T) + C   (T1, echo, …). Parameters: A, T, C."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 5:
        return FitResult(ok=False, message="not enough points")
    n = len(x)
    span = float(x.max() - x.min())
    ys = smooth(y, max(3, n // 25))
    C0 = float(np.median(ys[-max(3, n // 10):]))
    A0 = float(np.median(ys[: max(3, n // 20)]) - C0)
    T0 = span / 3
    if A0 != 0:
        r = (ys - C0) / A0
        idx = np.where(r < 1 / np.e)[0]
        if len(idx):
            T0 = max(float(x[idx[0]] - x[0]), span / 50)
    dx = float(np.min(np.diff(np.sort(x)))) if n > 1 else 1.0
    bounds = ([-np.inf, max(dx / 10, 1e-12), -np.inf], [np.inf, 100 * span, np.inf])
    tries = [least_squares_fit(_exp_decay, x, y, [A0, T0 * k, C0], ["A", "T", "C"], bounds)
             for k in (1.0, 0.4, 2.5)]
    return _best(tries)


def _damped_cos(t, A, f, phi, T, C):
    return C + A * np.exp(-t / T) * np.cos(2 * np.pi * f * t + phi)


def fit_damped_cosine(x, y, f_guess: Optional[float] = None) -> FitResult:
    """y = C + A·exp(-x/T)·cos(2π f x + φ)   (time Rabi, Ramsey).

    Parameters: A (>0), f (>0), phi, T, C.
    """
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 8:
        return FitResult(ok=False, message="not enough points")
    span = float(x.max() - x.min())
    dx = float(np.median(np.diff(x)))
    f0 = f_guess or dominant_frequency(x, y)
    if not f0:
        return FitResult(ok=False, message="no oscillation found")
    A0 = 0.5 * float(np.percentile(y, 95) - np.percentile(y, 5))
    C0 = float(np.mean(y))
    bounds = ([0, 0.2 / span, -4 * np.pi, span / 50, -np.inf],
              [np.inf, 0.5 / dx, 4 * np.pi, 1e3 * span, np.inf])
    tries = []
    for ff in (f0, 0.9 * f0, 1.1 * f0):
        for phi in (0.0, 0.5 * np.pi, np.pi, 1.5 * np.pi):
            for T in (span, span / 4):
                tries.append(least_squares_fit(_damped_cos, x, y, [A0, ff, phi, T, C0],
                                               ["A", "f", "phi", "T", "C"], bounds))
    return _best(tries)


def _rabi_amp(a, A, a_pi, lam, C):
    return C + A * np.exp(-a / lam) * np.cos(np.pi * a / a_pi)


def fit_rabi_amplitude(x, y) -> FitResult:
    """Amplitude (power) Rabi: y = C + A·exp(-a/λ)·cos(π a / a_π).

    Zero phase because the rotation angle is proportional to amplitude; A may be
    negative (the sign of the readout signal is irrelevant). Parameters: A, a_pi, lam, C.
    """
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 6:
        return FitResult(ok=False, message="not enough points")
    span = float(x.max() - x.min())
    xmax = float(np.max(np.abs(x)))
    ys = smooth(y, max(3, len(y) // 30))
    i0 = int(np.argmin(np.abs(x)))
    guesses = set()
    f = dominant_frequency(x, y)
    if f:
        guesses.add(0.5 / f)
    j = int(np.argmax(np.abs(ys - ys[i0])))  # farthest from the a≈0 signal = first π
    if abs(x[j]) > 0:
        guesses.add(abs(float(x[j])))
    if not guesses:
        return FitResult(ok=False, message="no oscillation found")
    C0 = float(np.mean(y))
    A0 = float(ys[i0] - C0) or 0.5 * float(np.ptp(ys))
    bounds = ([-np.inf, span / 50, span / 3, -np.inf], [np.inf, 20 * xmax, 1e4 * span, np.inf])
    tries = [least_squares_fit(_rabi_amp, x, y, [A0, g, 1e3 * span, C0],
                               ["A", "a_pi", "lam", "C"], bounds) for g in guesses]
    return _best(tries)


def _lorentz(x, A, x0, g, C):
    return C + A / (1 + ((x - x0) / g) ** 2)


def fit_lorentzian(x, y, sign: Optional[int] = None) -> FitResult:
    """y = C + A / (1 + ((x-x0)/γ)²) — peak (A>0) or dip (A<0).

    sign=+1 / -1 forces a peak / dip; None picks the larger deviation from the
    baseline. Parameters: A, x0, g (HWHM), C.
    """
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 6:
        return FitResult(ok=False, message="not enough points")
    span = float(x.max() - x.min())
    dx = float(np.median(np.abs(np.diff(x))))
    ys = smooth(y, max(3, len(y) // 100 * 2 + 3))
    C0 = float(np.median(ys))
    dev = ys - C0
    if sign is None:
        i = int(np.argmax(np.abs(dev)))
    else:
        i = int(np.argmax(dev * sign))
    A0 = float(dev[i])
    if A0 == 0:
        return FitResult(ok=False, message="flat data")
    above = np.where(dev * np.sign(A0) > abs(A0) / 2)[0]
    g0 = max(0.5 * len(above) * dx, dx)
    lo_A, hi_A = (-np.inf, np.inf)
    if sign == 1:
        lo_A = 0.0
    elif sign == -1:
        hi_A = 0.0
    bounds = ([lo_A, x.min(), dx / 4, -np.inf], [hi_A, x.max(), span, np.inf])
    tries = [least_squares_fit(_lorentz, x, y, [A0, float(x[i]), g0 * k, C0],
                               ["A", "x0", "g", "C"], bounds) for k in (1.0, 0.4, 2.5)]
    return _best(tries)


def _two_lorentz(x, A1, x1, g1, A2, x2, g2, C):
    return C + A1 / (1 + ((x - x1) / g1) ** 2) + A2 / (1 + ((x - x2) / g2) ** 2)


def fit_two_lorentzians(x, y, guess) -> FitResult:
    """Sum of two Lorentzians. `guess` = (A1, x1, g1, A2, x2, g2, C)."""
    x = np.asarray(x, float)
    span = float(np.nanmax(x) - np.nanmin(x))
    dx = float(np.nanmedian(np.abs(np.diff(x))))
    bounds = ([-np.inf, np.nanmin(x), dx / 4, -np.inf, np.nanmin(x), dx / 4, -np.inf],
              [np.inf, np.nanmax(x), span, np.inf, np.nanmax(x), span, np.inf])
    return least_squares_fit(_two_lorentz, x, y, list(guess),
                             ["A1", "x1", "g1", "A2", "x2", "g2", "C"], bounds)


def _gauss(x, A, x0, s, C):
    return C + A * np.exp(-((x - x0) ** 2) / (2 * s ** 2))


def fit_gaussian(x, y) -> FitResult:
    """y = C + A·exp(-(x-x0)²/2σ²). Parameters: A, x0, s, C."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 5:
        return FitResult(ok=False, message="not enough points")
    span = float(x.max() - x.min()) or 1.0
    C0 = float(np.min(y))
    i = int(np.argmax(y))
    A0 = float(y[i] - C0)
    w = y - C0
    s0 = float(np.sqrt(np.sum(w * (x - x[i]) ** 2) / max(np.sum(w), 1e-12))) or span / 6
    bounds = ([0, x.min(), span / 200, -np.inf], [np.inf, x.max(), 2 * span, np.inf])
    return least_squares_fit(_gauss, x, y, [A0, float(x[i]), s0, C0], ["A", "x0", "s", "C"], bounds)


# ---- 2D Ramsey chevron ------------------------------------------------------------
def _ramsey2d(XT, A, delta, T, C):
    X, T_ = XT
    return C + A * np.exp(-T_ / T) * np.cos(2 * np.pi * (X - delta) * T_)


def fit_ramsey_2d(det, tau, Z, delta_guess: float, T_guess: float) -> FitResult:
    """Global fit of a Ramsey chevron Z[tau, det] = C + A·e^{-τ/T}·cos(2π(Δ-δ)τ).

    det in MHz, tau in µs → δ in MHz, T in µs. Parameters: A, delta, T, C.
    """
    X, T_ = np.meshgrid(np.asarray(det, float), np.asarray(tau, float))
    z = np.asarray(Z, float).ravel()
    xt = np.vstack([X.ravel(), T_.ravel()])
    m = np.isfinite(z)
    xt, z = xt[:, m], z[m]
    if len(z) < 10:
        return FitResult(ok=False, message="not enough points")
    span_t = float(np.nanmax(tau) - np.nanmin(tau))
    span_f = float(np.nanmax(det) - np.nanmin(det))
    A0 = 0.5 * float(np.percentile(z, 95) - np.percentile(z, 5))
    C0 = float(np.mean(z))

    def f(xx, A, d, T, C):
        return _ramsey2d(xx, A, d, T, C)

    bounds = ([-np.inf, np.nanmin(det) - 0.5 * span_f, span_t / 100, -np.inf],
              [np.inf, np.nanmax(det) + 0.5 * span_f, 100 * span_t, np.inf])
    # least_squares_fit expects 1D x; wrap the 2D grid by index
    idx = np.arange(z.size, dtype=float)

    def g(ii, A, d, T, C):
        return f(xt[:, ii.astype(int)], A, d, T, C)

    tries = [least_squares_fit(g, idx, z, [s * A0, delta_guess, T_guess * k, C0],
                               ["A", "delta", "T", "C"], bounds)
             for s in (1, -1) for k in (1.0, 0.5, 2.0)]
    best = _best(tries)
    if best.ok:
        p = (best["A"], best["delta"], best["T"], best["C"])
        best.model = lambda XX, TT, _p=p: _ramsey2d((XX, TT), *_p)
    return best
