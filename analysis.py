"""
Automatic extraction of the quantities of interest (the notebook "analysis_cell").

    analyze(experiment, frame, ctx) -> AnalysisResult

`ctx` is the parameter snapshot taken when the measurement was launched (form values
+ global calibration parameters such as qubit_IF, resonator_IF, rotation_angle…).
Corrections are always computed relative to these CURRENT values — never relative
to the simulator's hidden truth — so the same code works on real hardware data.

Every analysis returns:
    results    [(label, formatted value)]          shown in the panel
    fit        (x, y) dense fitted curve           overlaid in red (1D)
    vlines / hlines / points / lines               extra overlays
    writebacks [(button label, global key, value)] calibration cascade
    model, r2, quality ("good" | "uncertain" | "failed"), notes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from fitting import (
    fit_damped_cosine, fit_exp_decay, fit_gaussian, fit_lorentzian, fit_rabi_amplitude,
    fit_ramsey_2d, fit_two_lorentzians, hist_bins, least_squares_fit, noise_sigma, smooth,
    symmetry_center, _lorentz,
)


@dataclass
class AnalysisResult:
    results: List[Tuple[str, str]] = field(default_factory=list)
    fit: Optional[Tuple[np.ndarray, np.ndarray]] = None
    vlines: List[float] = field(default_factory=list)
    hlines: List[float] = field(default_factory=list)
    points: List[Tuple[float, float]] = field(default_factory=list)
    lines: List[Tuple[np.ndarray, np.ndarray, dict]] = field(default_factory=list)
    # Values that can be written back to the global parameters (calibration cascade):
    # (button label, global parameter key, value)
    writebacks: List[Tuple[str, str, float]] = field(default_factory=list)
    model: str = ""
    r2: Optional[float] = None
    quality: str = "good"
    notes: List[str] = field(default_factory=list)


def _failed(msg, notes=None) -> AnalysisResult:
    return AnalysisResult(results=[("Extraction", msg)], quality="failed", notes=notes or [])


# ---- formatting / quality helpers ------------------------------------------------
def fmt(v, err=None, unit="", dec=None) -> str:
    """'48.2 ± 0.6 µs' — the number of decimals follows the uncertainty."""
    if v is None or not np.isfinite(v):
        return "n/a"
    if err is not None and np.isfinite(err) and err > 0:
        d = int(np.clip(1 - np.floor(np.log10(err)), 0, 8))
        s = f"{v:.{d}f} ± {err:.{d}f}"
    elif dec is not None:
        s = f"{v:.{dec}f}"
    else:
        s = f"{v:.4g}"
    return f"{s} {unit}".strip()


def _quality(fit, rel_key=None, max_rel=0.1, min_r2=0.6, abs_err=None, abs_max=None):
    if fit is None or not fit.ok:
        return "failed"
    bad = (not np.isfinite(fit.r2)) or fit.r2 < min_r2
    if rel_key is not None and fit.rel_err(rel_key) > max_rel:
        bad = True
    if abs_err is not None and abs_max is not None and not (np.isfinite(abs_err) and abs_err <= abs_max):
        bad = True
    return "uncertain" if bad else "good"


def _round4(t_ns, minimum=16):
    """Pulse lengths must be multiples of 4 ns (clock cycle), ≥ 16 ns."""
    return int(max(minimum, 4 * round(float(t_ns) / 4)))


def _g(v, key, default):
    try:
        return float(v.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def _arr(fr, key):
    return np.asarray(fr[key], float)


# ==================================================================================
def analyze(exp, frame, ctx) -> AnalysisResult:
    fn = _DISPATCH.get(exp.id)
    if fn is None:
        return AnalysisResult()
    try:
        return fn(exp, frame, ctx)
    except Exception as e:  # never crash the UI because of a fit
        return _failed(f"failed ({type(e).__name__}: {e})")


# ---- Time of flight ---------------------------------------------------------------
def _an_tof(exp, fr, v):
    t, I, Q = _arr(fr, "x"), _arr(fr, "I"), _arr(fr, "Q")
    Iu, Qu = I - I.mean(), Q - Q.mean()
    env = smooth(np.abs(Iu + 1j * Qu), 5)
    lo, hi = np.percentile(env, [10, 90])
    sig = max(noise_sigma(I), 1e-9)
    if hi - lo < 6 * sig:
        return _failed("no readout pulse detected",
                       ["Increase readout_amp, resonator_LO_gain or n_avg."])
    th = 0.5 * (lo + hi)
    run = np.convolve((env > th).astype(int), np.ones(8, int), mode="valid")
    cand = np.where(run == 8)[0]
    if not len(cand):
        return _failed("no stable pulse edge found")
    i0 = int(cand[0])
    tof = _round4(t[i0], minimum=24)
    pre = slice(0, i0 - 10) if i0 - 10 >= 30 else slice(None)
    mI, mQ = float(I[pre].mean()), float(Q[pre].mean())
    new_I = _g(v, "adc_offset_I", 0.0) - mI
    new_Q = _g(v, "adc_offset_Q", 0.0) - mQ
    level = float(max(np.max(np.abs(I - mI)), np.max(np.abs(Q - mQ))))
    raw_peak = float(max(np.max(np.abs(I)), np.max(np.abs(Q))))
    notes = []
    if raw_peak >= 0.499:
        notes.append("ADC saturated (±0.5 V): lower resonator_LO_gain or readout_amp.")
    elif level < 0.05:
        notes.append(f"Signal uses only {100 * level / 0.5:.0f} % of the ADC range: up to "
                     f"+{20 * np.log10(0.4 / level):.0f} dB of gain available.")
    if i0 < 30:
        notes.append("The pulse arrives at the very start of the window: the true time of "
                     "flight may be shorter than measured.")
    return AnalysisResult(
        results=[
            ("Time of flight", f"{tof} ns"),
            ("DC offset I measured", fmt(mI, dec=6, unit="V")),
            ("DC offset Q measured", fmt(mQ, dec=6, unit="V")),
            ("New adc_offset_I", fmt(new_I, dec=6, unit="V")),
            ("New adc_offset_Q", fmt(new_Q, dec=6, unit="V")),
            ("Peak ADC level", f"{level:.3f} V ({100 * level / 0.5:.0f} % of range)"),
        ],
        vlines=[float(tof)],
        lines=[(t, env, dict(color="#4a5568", lw=0.8, label="envelope")),
               (np.array([t[0], t[-1]]), np.array([th, th]),
                dict(color="#a0aec0", lw=0.8, ls=":", label="threshold"))],
        writebacks=[("time_of_flight", "time_of_flight", tof),
                    ("adc_offset_I", "adc_offset_I", new_I),
                    ("adc_offset_Q", "adc_offset_Q", new_Q)],
        model="first sustained crossing of the half-amplitude envelope, rounded to 4 ns",
        quality="uncertain" if notes and raw_peak >= 0.499 else "good", notes=notes)


# ---- Resonator ----------------------------------------------------------------------
def _an_resonator(exp, fr, v):
    x, y = _arr(fr, "x"), _arr(fr, "y")
    fit = fit_lorentzian(x, y ** 2, sign=-1)       # Lorentzian in power |S21|²
    if not fit.ok:
        return _failed("no resonance found")
    x0, ex0 = fit["x0"], fit.err("x0")
    fwhm, efwhm = 2 * abs(fit["g"]), 2 * fit.err("g")
    f_abs = _g(v, "resonator_LO", 6.5) * 1000 + x0
    q_l = f_abs / fwhm if fwhm > 0 else float("nan")
    xs = np.linspace(x.min(), x.max(), 800)
    notes = []
    if min(x0 - x.min(), x.max() - x0) < fwhm:
        notes.append("Resonance close to the sweep edge: widen or recentre the sweep.")
    depth = -fit["A"] / fit["C"] if fit["C"] else float("nan")
    q = _quality(fit, abs_err=ex0, abs_max=0.2 * fwhm, min_r2=0.5)
    return AnalysisResult(
        results=[
            ("Resonator IF", fmt(x0, ex0, "MHz")),
            ("Resonator frequency", f"{f_abs / 1000:.6f} GHz"),
            ("Linewidth κ/2π (FWHM)", fmt(fwhm, efwhm, "MHz")),
            ("Loaded quality factor", f"{q_l:,.0f}"),
            ("Dip depth (power)", f"{100 * depth:.0f} %"),
        ],
        fit=(xs, np.sqrt(np.clip(fit.model(xs), 0, None))),
        vlines=[x0], writebacks=[("resonator_IF", "resonator_IF", x0)],
        model="Lorentzian dip in |S21|²: C + A / (1 + ((f−f0)/γ)²)",
        r2=fit.r2, quality=q if not notes else "uncertain", notes=notes)


def _an_res_vs_power(exp, fr, v):
    x, a, Z = _arr(fr, "x"), _arr(fr, "y"), _arr(fr, "z")
    dx = float(np.median(np.abs(np.diff(x))))
    rows = []
    for r in range(len(a)):
        z = Z[r]
        if not np.all(np.isfinite(z)):
            continue
        zs = smooth(z, 7)
        i = int(np.argmin(zs))
        sig = noise_sigma(z) / np.sqrt(7)
        depth = float(np.median(zs) - zs[i])
        if sig > 0 and depth / sig > 8 and 0 < i < len(x) - 1:
            y0, y1, y2 = zs[i - 1], zs[i], zs[i + 1]
            den = y0 - 2 * y1 + y2
            xi = x[i] + (0.5 * (y0 - y2) / den * dx if den else 0.0)
            rows.append((float(a[r]), float(xi), r))
    if len(rows) < 3:
        return _failed("resonance not visible in enough rows",
                       ["Increase n_avg or the maximum amplitude."])
    nq = max(2, len(rows) // 4)
    low = rows[:nq]
    f_high = float(np.median([p for _, p, _ in rows[-3:]]))     # highest powers
    # refine the low-power frequency on the average of the lowest usable rows
    zlow = np.mean([Z[r] for _, _, r in low], axis=0)
    fit = fit_lorentzian(x, zlow ** 2, sign=-1)
    f_low = fit["x0"] if fit.ok else float(np.median([p for _, p, _ in low]))
    e_low = fit.err("x0") if fit.ok else float("nan")
    shift = f_high - f_low
    rIF = _g(v, "resonator_IF", -103.8771)
    res = [("Low-power resonance Δf", fmt(f_low, e_low, "MHz")),
           ("Low-power resonator IF", fmt(rIF + f_low, e_low, "MHz")),
           ("High-power resonance Δf", fmt(f_high, dec=4, unit="MHz")),
           ("Usable rows", f"{len(rows)}/{len(a)}")]
    hl, notes = [], []
    if abs(shift) > max(5 * dx, 0.15):
        # walk down from the top while the dip stays closer to the bare frequency
        k = len(rows) - 1
        while k > 0 and abs(rows[k - 1][1] - f_high) < abs(rows[k - 1][1] - f_low):
            k -= 1
        if k > 0:
            a_c = float(np.sqrt(rows[k - 1][0] * rows[k][0]))
            hl.append(a_c)
            res += [("Dressed → bare shift", fmt(shift, dec=3, unit="MHz")),
                    ("Punch-out at prefactor", f"{a_c:.3g}"),
                    ("Stay below prefactor", f"≈ {0.5 * a_c:.3g}")]
    else:
        notes.append("No punch-out within the amplitude range.")
    return AnalysisResult(
        results=res, vlines=[f_low, f_high] if abs(shift) > dx else [f_low], hlines=hl,
        writebacks=[("resonator_IF (low power)", "resonator_IF", rIF + f_low)],
        model="dip tracking per row; Lorentzian on the low-power rows",
        r2=fit.r2 if fit.ok else None, quality="good" if fit.ok else "uncertain", notes=notes)


# ---- Qubit spectroscopy -------------------------------------------------------------
def _line_fit(x, y):
    fit = fit_lorentzian(x, y)
    if not fit.ok:
        return fit, None
    fwhm = 2 * abs(fit["g"])
    return fit, fwhm


def _an_two_tones(exp, fr, v):
    x, y = _arr(fr, "x"), _arr(fr, "y")
    fit, fwhm = _line_fit(x, y)
    if not fit.ok:
        return _failed("no qubit line found")
    x0, ex0 = fit["x0"], fit.err("x0")
    q_if = _g(v, "qubit_IF", 136.6) + x0
    f01 = _g(v, "qubit_LO", 5.7) * 1000 + q_if
    notes = []
    if fit["A"] < 0:
        notes.append("The line appears as a dip (readout-phase dependent) — fitted anyway.")
    if fwhm > 10:
        notes.append(f"Power-broadened line (FWHM {fwhm:.0f} MHz): lower saturation_amp, "
                     "and refine the frequency with a Ramsey measurement.")
    return AnalysisResult(
        results=[("Line detuning", fmt(x0, ex0, "MHz")),
                 ("New qubit IF", fmt(q_if, ex0, "MHz")),
                 ("Qubit frequency 0→1", f"{f01 / 1000:.6f} GHz"),
                 ("Linewidth (FWHM)", fmt(fwhm, 2 * fit.err('g'), "MHz"))],
        fit=fit.curve(x, 1500), vlines=[x0],
        writebacks=[("qubit_IF", "qubit_IF", q_if)],
        model="Lorentzian: C + A / (1 + ((f−f0)/γ)²)", r2=fit.r2,
        quality=_quality(fit, abs_err=ex0, abs_max=0.2 * fwhm, min_r2=0.5), notes=notes)


def _an_two_tones_qm(exp, fr, v):
    x, y = _arr(fr, "x"), _arr(fr, "y")
    fit, fwhm = _line_fit(x, y)
    if not fit.ok:
        return _failed("no qubit line found")
    x0, ex0 = fit["x0"], fit.err("x0")
    f01 = _g(v, "qubit_LO", 5.7) * 1000 + x0
    return AnalysisResult(
        results=[("Qubit IF", fmt(x0, ex0, "MHz")),
                 ("Change vs current qubit_IF", fmt(x0 - _g(v, "qubit_IF", 136.6), dec=4, unit="MHz")),
                 ("Qubit frequency 0→1", f"{f01 / 1000:.6f} GHz"),
                 ("Linewidth (FWHM)", fmt(fwhm, 2 * fit.err('g'), "MHz"))],
        fit=fit.curve(x, 1500), vlines=[x0],
        writebacks=[("qubit_IF", "qubit_IF", x0)],
        model="Lorentzian: C + A / (1 + ((f−f0)/γ)²)", r2=fit.r2,
        quality=_quality(fit, abs_err=ex0, abs_max=0.2 * fwhm, min_r2=0.5))


def _an_2tones_vs_power(exp, fr, v):
    x, a, Z = _arr(fr, "x"), _arr(fr, "y"), _arr(fr, "z")
    dx = float(np.median(np.abs(np.diff(x))))
    finite = np.all(np.isfinite(Z), axis=1)
    if finite.sum() < 3:
        return _failed("not enough rows")
    top = Z[finite][-max(1, finite.sum() // 3):]
    med = np.median(top)
    sgn = 1.0 if (top.max() - med) >= (med - top.min()) else -1.0
    S = sgn * Z

    # 1) 0→1 line on the lower half of the amplitude range, extrapolated to zero power
    pts = []
    half = a <= a[finite].min() + 0.5 * (a[finite].max() - a[finite].min())
    for r in np.where(finite & half)[0]:
        z = S[r]
        sig = noise_sigma(z)
        if not sig or (smooth(z, 3).max() - np.median(z)) / sig < 6:
            continue
        f = fit_lorentzian(x, z, sign=1)
        if f.ok and np.isfinite(f.err("x0")) and f.err("x0") < 5 * dx:
            pts.append((a[r], f["x0"], max(f.err("x0"), 1e-3), 2 * abs(f["g"])))
    if not pts:
        return _failed("0→1 line not visible at low power", ["Increase n_avg or the amplitudes."])
    A2 = np.array([p[0] ** 2 for p in pts])
    X0 = np.array([p[1] for p in pts])
    W = 1 / np.array([p[2] for p in pts]) ** 2
    if len(pts) >= 2 and np.ptp(A2) > 0:
        M = np.vstack([np.ones_like(A2), A2]).T
        cov = np.linalg.inv(M.T @ (W[:, None] * M))
        coef = cov @ (M.T @ (W * X0))
        delta0, e_delta0 = float(coef[0]), float(np.sqrt(cov[0, 0]))
        if abs(coef[1]) < 2 * np.sqrt(cov[1, 1]):     # Stark slope not significant
            delta0 = float(np.sum(W * X0) / np.sum(W))
            e_delta0 = float(1 / np.sqrt(np.sum(W)))
    else:
        delta0, e_delta0 = float(X0[0]), float(pts[0][2])
    fwhm_low = float(pts[0][3])

    res = [("0→1 line at zero power (Δ)", fmt(delta0, e_delta0, "MHz")),
           ("New qubit IF", fmt(_g(v, "qubit_IF", 136.6) + delta0, e_delta0, "MHz"))]
    wbs = [("qubit_IF", "qubit_IF", _g(v, "qubit_IF", 136.6) + delta0)]
    vl, notes, r2 = [delta0], [], None

    # 2) two-photon 0→2 line on the top rows
    prof = np.mean(S[finite][-max(1, finite.sum() // 3):], axis=0)
    sig_p = noise_sigma(prof)
    main = least_squares_fit(_lorentz, x, prof,
                             [prof.max() - np.median(prof), delta0, fwhm_low, np.median(prof)],
                             ["A", "x0", "g", "C"],
                             ([0, delta0 - 3 * fwhm_low - 3 * dx, dx / 4, -np.inf],
                              [np.inf, delta0 + 3 * fwhm_low + 3 * dx, np.ptp(x), np.inf]))
    found = False
    if main.ok:
        resid = prof - main.model(x)
        excl = np.abs(x - main["x0"]) < max(1.5 * 2 * abs(main["g"]), 3 * dx)
        resid[excl] = -np.inf
        i2 = int(np.argmax(resid))
        if np.isfinite(resid[i2]) and sig_p and resid[i2] > 5 * sig_p:
            two = fit_two_lorentzians(x, prof, (main["A"], main["x0"], abs(main["g"]),
                                                resid[i2], x[i2], max(2 * dx, abs(main["g"]) / 2),
                                                main["C"]))
            if two.ok:
                x1, x2 = two["x1"], two["x2"]
                if abs(x2 - delta0) < abs(x1 - delta0):
                    x1, x2 = x2, x1
                alpha = 2 * (x2 - x1)
                r2 = two.r2
                vl.append(x2)
                found = True
                res += [("Two-photon 0→2 line (Δ)", fmt(x2, dec=2, unit="MHz")),
                        ("Anharmonicity α ≈ 2·(f02/2 − f01)", fmt(alpha, dec=1, unit="MHz"))]
                if -450 < alpha < -50:
                    wbs.append(("anharmonicity", "anharmonicity", alpha))
                else:
                    notes.append("Unexpected anharmonicity for a transmon — not proposed.")
    if not found:
        notes.append("Two-photon line not resolved (finer df or more power needed).")
    return AnalysisResult(results=res, vlines=vl, writebacks=wbs, r2=r2, notes=notes,
                          model="Lorentzian per row, f(a) = f0 + k·a² ; double Lorentzian at high power",
                          quality="good" if len(pts) >= 2 else "uncertain")


# ---- Rabi ---------------------------------------------------------------------------
def _chevron_center(x, Z):
    """Detuning of the chevron symmetry axis (mirror symmetry of the whole map),
    falling back to the column-averaged profile. The uncertainty is not estimated."""
    d, _ = symmetry_center(x, Z)
    if d is not None:
        return d, float("nan")
    prof = np.nanmean(Z, axis=0)
    fit = fit_lorentzian(x, prof)
    if fit.ok and x.min() <= fit["x0"] <= x.max():
        return fit["x0"], fit.err("x0")
    i = int(np.argmax(np.abs(prof - np.median(prof))))
    return float(x[i]), float("nan")


def _center_columns(x, Z, delta, n=3):
    """Average of the n columns closest to the chevron centre (less noise; the
    detuning error of ±1 column is negligible against the Rabi frequency)."""
    idx = np.argsort(np.abs(x - delta))[:n]
    return np.nanmean(Z[:, idx], axis=1)


def _an_chevron_amp(exp, fr, v):
    x, a, Z = _arr(fr, "x"), _arr(fr, "y"), _arr(fr, "z")
    delta, e_delta = _chevron_center(x, Z)
    fit = fit_rabi_amplitude(a, _center_columns(x, Z, delta))
    if not fit.ok:
        return _failed("π amplitude not determined")
    a_pi, e_api = abs(fit["a_pi"]), fit.err("a_pi")
    amp0 = _g(v, "x180_amp", 0.0586)
    q_if = _g(v, "qubit_IF", 136.6) + delta
    notes = []
    new_amp = amp0 * a_pi
    if abs(new_amp) > 0.5:
        notes.append("π amplitude exceeds ±0.5 V: increase qubit_LO_gain or x180_len.")
    return AnalysisResult(
        results=[("Chevron centre (Δ)", fmt(delta, e_delta, "MHz", dec=4)),
                 ("New qubit IF", fmt(q_if, e_delta, "MHz", dec=4)),
                 ("π prefactor (centre column)", fmt(a_pi, e_api)),
                 ("New x180_amp", fmt(new_amp, amp0 * e_api, "V"))],
        vlines=[delta], hlines=[a_pi] if a.min() <= a_pi <= a.max() else [],
        writebacks=[("qubit_IF", "qubit_IF", q_if),
                    ("x180_amp", "x180_amp", float(np.clip(new_amp, -0.5, 0.5)))],
        model="centre: mirror symmetry of the map; π: C + A·e^(−a/λ)·cos(πa/a_π)",
        r2=fit.r2, quality=_quality(fit, "a_pi", 0.05), notes=notes)


def _an_chevron_time(exp, fr, v):
    x, t, Z = _arr(fr, "x"), _arr(fr, "y"), _arr(fr, "z")
    delta, e_delta = _chevron_center(x, Z)
    fit = fit_damped_cosine(t, _center_columns(x, Z, delta))
    if not fit.ok:
        return _failed("Rabi period not determined")
    f, ef = fit["f"], fit.err("f")
    t_pi = 0.5 / f
    e_tpi = 0.5 * ef / f ** 2
    q_if = _g(v, "qubit_IF", 136.6) + delta
    return AnalysisResult(
        results=[("Chevron centre (Δ)", fmt(delta, e_delta, "MHz", dec=4)),
                 ("New qubit IF", fmt(q_if, e_delta, "MHz", dec=4)),
                 ("Rabi frequency (centre)", fmt(1000 * f, 1000 * ef, "MHz")),
                 ("π duration", fmt(t_pi, e_tpi, "ns")),
                 ("x180_len (multiple of 4 ns)", f"{_round4(t_pi)} ns")],
        vlines=[delta], hlines=[t_pi] if t.min() <= t_pi <= t.max() else [],
        writebacks=[("qubit_IF", "qubit_IF", q_if),
                    ("x180_len", "x180_len", _round4(t_pi))],
        model="centre: mirror symmetry of the map; Rabi: C + A·e^(−t/T)·cos(2πft+φ)",
        r2=fit.r2, quality=_quality(fit, "f", 0.05))


def _an_time_rabi(exp, fr, v):
    t, y = _arr(fr, "x"), _arr(fr, "y")          # ns
    fit = fit_damped_cosine(t, y)
    if not fit.ok:
        return _failed("Rabi period not determined")
    f, ef = fit["f"], fit.err("f")
    period = 1 / f
    t_pi = 0.5 * period
    e_tpi = 0.5 * ef / f ** 2
    k = max(0, int(np.ceil((t.min() / t_pi - 1) / 2)))   # first odd multiple of t_pi in range
    mark = (2 * k + 1) * t_pi
    notes = []
    if fit["T"] < period:
        notes.append("Oscillations damp within one period: check the drive frequency.")
    return AnalysisResult(
        results=[("Rabi period", fmt(period, 2 * e_tpi, "ns")),
                 ("Rabi frequency", fmt(1000 * f, 1000 * ef, "MHz")),
                 ("π duration", fmt(t_pi, e_tpi, "ns")),
                 ("x180_len (multiple of 4 ns)", f"{_round4(t_pi)} ns"),
                 ("Damping time", fmt(fit["T"] / 1000, fit.err("T") / 1000, "µs"))],
        fit=fit.curve(t, 1200), vlines=[mark] if mark <= t.max() else [],
        writebacks=[("x180_len", "x180_len", _round4(t_pi))],
        model="C + A·e^(−t/T)·cos(2πft + φ)", r2=fit.r2,
        quality=_quality(fit, "f", 0.05), notes=notes)


def _an_power_rabi(exp, fr, v):
    a, y = _arr(fr, "x"), _arr(fr, "y")
    fit = fit_rabi_amplitude(a, y)
    if not fit.ok:
        return _failed("π amplitude not determined")
    a_pi, e_api = abs(fit["a_pi"]), fit.err("a_pi")
    amp0 = _g(v, "x180_amp", 0.0586)
    new_amp = amp0 * a_pi
    notes = []
    if a_pi > a.max():
        notes.append("The π amplitude lies outside the sweep: increase a_max.")
    if abs(new_amp) > 0.5:
        notes.append("π amplitude exceeds ±0.5 V: increase qubit_LO_gain or x180_len.")
    return AnalysisResult(
        results=[("π prefactor", fmt(a_pi, e_api)),
                 ("New x180_amp (π)", fmt(new_amp, amp0 * e_api, "V")),
                 ("x90 amplitude (π/2)", fmt(new_amp / 2, amp0 * e_api / 2, "V"))],
        fit=fit.curve(a, 800), vlines=[a_pi] if a_pi <= a.max() else [],
        writebacks=[("x180_amp", "x180_amp", float(np.clip(new_amp, -0.5, 0.5)))],
        model="C + A·e^(−a/λ)·cos(π a / a_π)", r2=fit.r2,
        quality=_quality(fit, "a_pi", 0.05) if not notes else "uncertain", notes=notes)


# ---- Coherence ----------------------------------------------------------------------
def _an_t1(exp, fr, v):
    x, y = _arr(fr, "x"), _arr(fr, "y")          # µs
    fit = fit_exp_decay(x, y)
    if not fit.ok:
        return _failed("T1 not determined")
    T1, e = fit["T"], fit.err("T")
    notes = []
    if x.max() < 2 * T1:
        notes.append(f"Sweep covers only {x.max() / T1:.1f}·T1: extend tau_max to ≥ 3·T1.")
    return AnalysisResult(
        results=[("T1", fmt(T1, e, "µs")),
                 ("Contrast", fmt(fit["A"], fit.err("A"))),
                 ("Suggested thermalization (3·T1)", fmt(3 * T1, dec=1, unit="µs"))],
        fit=fit.curve(x),
        writebacks=[("qubit_T1", "qubit_T1", T1),
                    ("thermalization_time (3·T1)", "thermalization_time", 3 * T1)],
        model="A·e^(−τ/T1) + C", r2=fit.r2,
        quality=_quality(fit, "T", 0.1) if not notes else "uncertain", notes=notes)


def _an_t1_hist(exp, fr, v):
    s = np.asarray(fr["samples"], float)
    s = s[np.isfinite(s)]
    if len(s) < 3:
        return _failed("not enough successful T1 fits")
    mean, std, med = float(np.mean(s)), float(np.std(s, ddof=1)), float(np.median(s))
    sem = std / np.sqrt(len(s))
    counts, edges = np.histogram(s, bins=hist_bins(len(s)))
    centers = 0.5 * (edges[1:] + edges[:-1])
    g = fit_gaussian(centers, counts)
    fit = None
    if g.ok:
        xs = np.linspace(edges[0], edges[-1], 400)
        fit = (xs, g.model(xs))
    return AnalysisResult(
        results=[("Mean T1", fmt(mean, sem, "µs")),
                 ("Std deviation", fmt(std, dec=1, unit="µs")),
                 ("Median T1", fmt(med, dec=1, unit="µs")),
                 ("Relative spread", f"{100 * std / mean:.1f} %"),
                 ("Successful fits", f"{len(s)}")],
        fit=fit, vlines=[mean],
        writebacks=[("qubit_T1 (mean)", "qubit_T1", mean),
                    ("thermalization_time (3·T1)", "thermalization_time", 3 * mean)],
        model="each repetition: A·e^(−τ/T1) + C ; histogram: Gaussian",
        r2=g.r2 if g.ok else None, quality="good" if len(s) >= 10 else "uncertain")


def _an_ramsey(exp, fr, v):
    x, tau, Z = _arr(fr, "x"), _arr(fr, "y"), _arr(fr, "z")    # MHz, µs
    d0, _ = _chevron_center(x, Z)
    col = int(np.argmin(np.abs(x - d0)))
    dec = fit_exp_decay(tau, Z[:, col])
    T0 = dec["T"] if dec.ok else (tau.max() - tau.min()) / 3
    fit = fit_ramsey_2d(x, tau, Z, d0, T0)
    if not fit.ok:
        return _failed("2D Ramsey fit failed")
    delta, e_delta = fit["delta"], fit.err("delta")
    T2, e_T2 = fit["T"], fit.err("T")
    q_if = _g(v, "qubit_IF", 136.6) + delta
    notes = []
    if not (x.min() <= delta <= x.max()):
        notes.append("Chevron centre outside the frequency window: widen freq_span.")
    if tau.max() < 2 * T2:
        notes.append("Increase tau_max to ≥ 2·T2* for a reliable T2*.")
    return AnalysisResult(
        results=[("Qubit detuning δ", fmt(1000 * delta, 1000 * e_delta, "kHz")),
                 ("New qubit IF", fmt(q_if, e_delta, "MHz")),
                 ("Qubit frequency 0→1",
                  f"{(_g(v, 'qubit_LO', 5.7) * 1000 + q_if) / 1000:.7f} GHz"),
                 ("T2*", fmt(T2, e_T2, "µs"))],
        vlines=[delta],
        writebacks=[("qubit_IF", "qubit_IF", q_if), ("qubit_T2_star", "qubit_T2_star", T2)],
        model="global 2D fit: C + A·e^(−τ/T2*)·cos(2π(Δ−δ)τ)", r2=fit.r2,
        quality=_quality(fit, "T", 0.15, min_r2=0.3) if not notes else "uncertain", notes=notes)


def _an_vz_ramsey(exp, fr, v):
    x, y = _arr(fr, "x"), _arr(fr, "y")          # µs
    fit = fit_damped_cosine(x, y)
    if not fit.ok:
        return _failed("Ramsey fringes not fitted")
    f_meas, ef = fit["f"], fit.err("f")
    T2, e_T2 = fit["T"], fit.err("T")
    det = _g(v, "detuning", 0.5)
    corr = det - f_meas                           # qua-libs: detuning to add to qubit_IF
    q_if = _g(v, "qubit_IF", 136.6) + corr
    notes = []
    if not (0.25 * abs(det) < f_meas < 1.75 * abs(det)):
        notes.append("Fringe frequency far from the imposed detuning: the sign of the "
                     "correction is ambiguous — check with the Ramsey chevron or a larger "
                     "imposed detuning.")
    if x.max() < 2 * T2:
        notes.append("Increase tau_max to ≥ 2·T2* for a reliable T2*.")
    q = _quality(fit, "f", 0.05)
    if notes and q == "good":
        q = "uncertain"
    return AnalysisResult(
        results=[("Fringe frequency", fmt(f_meas, ef, "MHz")),
                 ("Qubit detuning (to add)", fmt(1000 * corr, 1000 * ef, "kHz")),
                 ("New qubit IF", fmt(q_if, ef, "MHz")),
                 ("T2*", fmt(T2, e_T2, "µs"))],
        fit=fit.curve(x, 1500),
        writebacks=[("qubit_IF", "qubit_IF", q_if), ("qubit_T2_star", "qubit_T2_star", T2)],
        model="C + A·e^(−τ/T2*)·cos(2πfτ + φ)", r2=fit.r2, quality=q, notes=notes)


def _an_echo(exp, fr, v):
    x, y = _arr(fr, "x"), _arr(fr, "y")          # µs, total 2τ
    fit = fit_exp_decay(x, y)
    if not fit.ok:
        return _failed("echo decay not fitted")
    T2, e = fit["T"], fit.err("T")
    notes = []
    if x.max() < 2 * T2:
        notes.append("Increase tau_max: the echo decay is truncated.")
    return AnalysisResult(
        results=[("T2 (Hahn echo)", fmt(T2, e, "µs")),
                 ("Contrast", fmt(abs(fit["A"]), fit.err("A")))],
        fit=fit.curve(x),
        writebacks=[("qubit_T2_echo", "qubit_T2_echo", T2)],
        model="A·e^(−2τ/T2) + C", r2=fit.r2,
        quality=_quality(fit, "T", 0.1) if not notes else "uncertain", notes=notes)


# ---- Readout ------------------------------------------------------------------------
def _an_iq(exp, fr, v):
    Ig, Qg, Ie, Qe = (_arr(fr, k) for k in ("gI", "gQ", "eI", "eQ"))
    if len(Ig) < 50 or len(Ie) < 50:
        return _failed("not enough shots")
    # Same convention as qualang_tools.analysis.two_state_discriminator
    ang = float(np.arctan2(Qe.mean() - Qg.mean(), Ig.mean() - Ie.mean()))
    C, S = np.cos(ang), np.sin(ang)
    if np.mean((Ig - Ie) * C - (Qg - Qe) * S) > 0:
        ang += np.pi
        C, S = np.cos(ang), np.sin(ang)
    Igr, Qgr = Ig * C - Qg * S, Ig * S + Qg * C
    Ier, Qer = Ie * C - Qe * S, Ie * S + Qe * C
    # threshold minimising the false detections
    cand = np.quantile(np.concatenate([Igr, Ier]), np.linspace(0.01, 0.99, 1500))
    sg, se = np.sort(Igr), np.sort(Ier)
    errors = (len(sg) - np.searchsorted(sg, cand)) / len(sg) + np.searchsorted(se, cand) / len(se)
    thr = float(cand[int(np.argmin(errors))])
    gg, ee = float(np.mean(Igr < thr)), float(np.mean(Ier > thr))
    fid = 0.5 * (gg + ee)
    sep = float(np.hypot(Ie.mean() - Ig.mean(), Qe.mean() - Qg.mean()))
    sigma = 0.5 * (np.std(Qgr) + np.std(Qer))      # transverse spread (not polluted by decay)
    snr = sep / (2 * sigma) if sigma > 0 else float("nan")
    theta0 = _g(v, "rotation_angle", 0.0)
    new_theta = float(np.mod(theta0 + ang, 2 * np.pi))
    ang_disp = float(np.angle(np.exp(1j * ang)))
    # decision boundary in the measured frame: Re(z·e^{iφ}) = thr
    s = np.linspace(min(Qgr.min(), Qer.min()), max(Qgr.max(), Qer.max()), 2)
    zb = (thr + 1j * s) * np.exp(-1j * ang)
    notes = []
    if fid < 0.8:
        notes.append("Low fidelity: optimise the readout frequency/amplitude/length first.")
    return AnalysisResult(
        results=[("Rotation to add", f"{ang_disp:.4f} rad ({np.degrees(ang_disp):.1f}°)"),
                 ("New rotation_angle", f"{new_theta:.4f} rad ({np.degrees(new_theta):.1f}°)"),
                 ("Threshold (rotated I)", f"{thr:.6f}"),
                 ("Readout fidelity", f"{100 * fid:.2f} %"),
                 ("P(g|g) / P(e|e)", f"{100 * gg:.1f} % / {100 * ee:.1f} %"),
                 ("Blob separation / SNR", f"{sep:.4f} V / {snr:.2f}")],
        points=[(Ig.mean(), Qg.mean()), (Ie.mean(), Qe.mean())],
        lines=[(zb.real, zb.imag, dict(color="#1a202c", lw=1.4, ls="--", label="threshold"))],
        writebacks=[("rotation_angle", "rotation_angle", new_theta),
                    ("ge_threshold", "ge_threshold", thr)],
        model="two-state discriminator (rotate → optimal threshold)",
        quality="good" if fid >= 0.8 else "uncertain", notes=notes)


def _an_readout_opt(exp, fr, v):
    x, y = _arr(fr, "x"), _arr(fr, "y")
    fit = fit_lorentzian(x, y, sign=1)
    if not fit.ok:
        return _failed("no maximum found")
    x0, ex0 = fit["x0"], fit.err("x0")
    r_if = _g(v, "resonator_IF", -103.8771) + x0
    return AnalysisResult(
        results=[("Optimal shift Δf", fmt(x0, ex0, "MHz")),
                 ("Optimal readout IF", fmt(r_if, ex0, "MHz"))],
        fit=fit.curve(x, 800), vlines=[x0],
        writebacks=[("resonator_IF (optimal)", "resonator_IF", r_if)],
        model="peak fit: C + A / (1 + ((f−f0)/γ)²)", r2=fit.r2,
        quality=_quality(fit, abs_err=ex0, abs_max=0.1 * abs(fit["g"]) + 0.05, min_r2=0.5))


_DISPATCH = {
    "time_of_flight": _an_tof,
    "resonator_1tone": _an_resonator,
    "resonator_vs_power": _an_res_vs_power,
    "two_tones": _an_two_tones,
    "two_tones_qm": _an_two_tones_qm,
    "two_tones_vs_power": _an_2tones_vs_power,
    "rabi_chevron_amp": _an_chevron_amp,
    "rabi_chevron_time": _an_chevron_time,
    "time_rabi": _an_time_rabi,
    "power_rabi": _an_power_rabi,
    "t1": _an_t1,
    "t1_histogram": _an_t1_hist,
    "ramsey": _an_ramsey,
    "virtual_z_ramsey": _an_vz_ramsey,
    "echo": _an_echo,
    "iq_blobs": _an_iq,
    "readout_opt_freq": _an_readout_opt,
}


# Short description of every extraction, shown on the "Extraction methods" help page.
METHODS = {
    "time_of_flight": ("Envelope of the raw ADC trace; first sustained crossing of the "
                       "half-amplitude level, rounded to 4 ns. DC offsets from the "
                       "pre-pulse baseline.",
                       "time_of_flight, adc_offset_I, adc_offset_Q"),
    "resonator_1tone": ("Lorentzian dip fitted to |S21|² → centre, FWHM = κ/2π, Q_L = f/κ.",
                        "resonator_IF"),
    "resonator_vs_power": ("Dip tracked row by row; Lorentzian on the lowest usable "
                           "powers; punch-out where the dip jumps to the bare frequency.",
                           "resonator_IF"),
    "two_tones": ("Lorentzian (peak or dip) → line centre relative to qubit_IF.", "qubit_IF"),
    "two_tones_qm": ("Lorentzian (peak or dip) → absolute qubit IF.", "qubit_IF"),
    "two_tones_vs_power": ("Lorentzian per row, centre extrapolated to zero power "
                           "(f0 + k·a²); double Lorentzian at high power for the "
                           "two-photon line → α = 2·(f02/2 − f01).",
                           "qubit_IF, anharmonicity"),
    "rabi_chevron_amp": ("Chevron centre = mirror-symmetry axis of the map; amplitude Rabi "
                         "fit C + A·e^(−a/λ)·cos(πa/a_π) on the centre columns.",
                         "qubit_IF, x180_amp"),
    "rabi_chevron_time": ("Chevron centre = mirror-symmetry axis of the map; damped cosine "
                          "on the centre columns → t_π = 1/(2f).", "qubit_IF, x180_len"),
    "time_rabi": ("Damped cosine C + A·e^(−t/T)·cos(2πft+φ) → t_π = 1/(2f), rounded to "
                  "4 ns.", "x180_len"),
    "power_rabi": ("C + A·e^(−a/λ)·cos(πa/a_π) → x180_amp × a_π.", "x180_amp"),
    "t1": ("Exponential decay A·e^(−τ/T1) + C.", "qubit_T1, thermalization_time = 3·T1"),
    "t1_histogram": ("Exponential fit of every repetition; mean ± s.e.m., spread, Gaussian "
                     "overlay.", "qubit_T1, thermalization_time"),
    "ramsey": ("Global 2D fit C + A·e^(−τ/T2*)·cos(2π(Δ−δ)τ) over the whole chevron.",
               "qubit_IF, qubit_T2_star"),
    "virtual_z_ramsey": ("Damped cosine → fringe frequency f; correction = imposed detuning − "
                         "f (qua-libs convention).", "qubit_IF, qubit_T2_star"),
    "echo": ("Exponential decay vs total free evolution 2τ.", "qubit_T2_echo"),
    "iq_blobs": ("Two-state discriminator (as qualang_tools): rotation aligning g→e on I, "
                 "threshold minimising false assignments, fidelity = (P(g|g)+P(e|e))/2.",
                 "rotation_angle (+= angle), ge_threshold"),
    "readout_opt_freq": ("Peak fit of the g–e separation vs readout frequency.", "resonator_IF"),
}
