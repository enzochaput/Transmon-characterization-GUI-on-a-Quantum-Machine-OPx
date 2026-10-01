"""
Acquisition backends.

The GUI only talks to the `Backend` interface:

    backend.run(experiment, ctx)  ->  generator of frames

`ctx` is a snapshot of every parameter at launch time: the experiment's form values
plus all global/calibration parameters (LO, IF, pulse amplitudes, rotation angle…).

`MockBackend` simulates a *virtual transmon* (`SimulatedDevice`) whose hidden "true"
parameters are slightly different from configuration.py. Every simulated signal is
computed from the CURRENT configuration (LO + IF, pulse amplitude/length, readout
frequency, IQ rotation…), so the calibration cascade really works: extract a value,
write it back, re-run, and the measurement converges to the hidden truth.
Noise decreases as 1/√n_avg and averages accumulate live, like QUA "live" fetching.

To drive real hardware, write a `QuaBackend` whose `run()` executes the QUA program
and yields the same frames; nothing else in the GUI needs to change.

Frame = dict {"progress": 0..100, "kind": <plot>, ...data...}
    trace -> {"x","I","Q"}         line -> {"x","y"}         map2d -> {"x","y","z"}
    hist  -> {"samples"}           iq   -> {"gI","gQ","eI","eQ"}   action -> {"log"}
Optional: "n_done"/"n_total" (averages or shots acquired so far).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

from fitting import fit_exp_decay

_MAX_1D = 2001     # max points of a simulated 1D sweep
_MAX_2D = 401      # max points per axis of a simulated 2D map


# ==================================================================================
# Backend interface
# ==================================================================================
class Backend(ABC):
    name = "backend"

    @abstractmethod
    def run(self, experiment, ctx: dict):
        """Yield frames for `experiment` using the parameter snapshot `ctx`."""
        raise NotImplementedError


def frame_to_save_data(fr):
    """Last frame -> dict of arrays to save (like `res` in the notebook)."""
    kind = fr.get("kind")
    if kind == "line":
        return {"x": fr["x"], "signal": fr["y"]}
    if kind == "trace":
        return {"t": fr["x"], "adc_I": fr["I"], "adc_Q": fr["Q"]}
    if kind == "map2d":
        return {"x": fr["x"], "y": fr["y"], "Z": fr["z"]}
    if kind == "hist":
        return {"samples": fr["samples"]}
    if kind == "iq":
        return {"I_g": fr["gI"], "Q_g": fr["gQ"], "I_e": fr["eI"], "Q_e": fr["eQ"]}
    return {}


# ==================================================================================
# Virtual device (hidden truth)
# ==================================================================================
def _gain(db, ref):
    """Linear amplitude factor of a gain `db` relative to `ref` dB."""
    return 10.0 ** ((float(db) - ref) / 20.0)


@dataclass
class SimulatedDevice:
    """Hidden parameters of the simulated sample. Frequencies are absolute, in MHz.

    They are deliberately a little off configuration.py so that every calibration
    step has something to correct.
    """
    # Readout resonator
    f_res_g: float = 6500.0 - 103.62     # dressed frequency, qubit in |g>   (IF -103.62)
    two_chi: float = 0.9                 # f_res(|e>) - f_res(|g>)
    kappa: float = 0.8                   # linewidth (FWHM)
    bare_shift: float = 1.6              # bare - dressed frequency (seen above punch-out)
    punchout_drive: float = 0.12         # readout drive (V, at -20 dB gain) of the punch-out
    # Qubit
    f01: float = 5700.0 + 136.72         # 0->1 transition                   (IF 136.72)
    anharmonicity: float = -212.0
    T1: float = 48.0                     # µs
    T1_fluct: float = 4.0                # µs, slow fluctuations (T1 histogram)
    T2_star: float = 7.5                 # µs
    T2_echo: float = 21.0                # µs
    T_rabi: float = 1500.0               # ns, damping of time-Rabi oscillations
    amp_pi_60ns: float = 0.0612          # π amplitude of a 60 ns DRAG gaussian @ 10 dB
    thermal_pop: float = 0.03
    readout_fidelity_e: float = 0.95     # P(read e | in e) in averaged measurements
    # Spectroscopy line (phenomenological)
    sat_amp: float = 0.32                # drive amplitude giving saturation parameter s=1
    sat_amp_2ph: float = 0.6             # same for the two-photon 0->2 line
    intrinsic_hwhm: float = 0.25         # MHz
    ac_stark: float = -0.6               # MHz / V² of drive amplitude
    # Readout chain
    tof: float = 264.0                   # ns
    adc_dc_I: float = -0.013100          # raw DC at the ADC (before config offsets)
    adc_dc_Q: float = -0.007050
    iq_phase: float = 1.1                # raw phase of the demodulated signal (rad)
    iq_scale: float = 0.033              # V, demodulated signal at readout_amp=0.49, 500 ns
    iq_sigma: float = 0.0083             # V, single-shot noise at 500 ns

    # ---- qubit drive -------------------------------------------------------------
    def rotation(self, amp, length_ns, gain_db):
        """Rotation angle (rad) of a DRAG gaussian of amplitude `amp`, length `length_ns`."""
        return np.pi * (np.asarray(amp) / self.amp_pi_60ns) * \
            (np.asarray(length_ns) / 60.0) * _gain(gain_db, 10.0)

    @staticmethod
    def rabi_population(theta, detuning_mhz, t_eff_ns, damping=1.0):
        """Excited population after a pulse of on-resonance angle θ, detuning Δ.

        Generalised Rabi formula with effective (square-equivalent) duration t_eff.
        """
        theta = np.asarray(theta, float)
        t_eff = np.maximum(np.asarray(t_eff_ns, float), 1e-9)
        omega = theta / t_eff                                   # rad/ns
        d = 2 * np.pi * np.asarray(detuning_mhz, float) * 1e-3  # rad/ns
        w = np.sqrt(omega ** 2 + d ** 2)
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = np.where(w > 0, omega ** 2 / np.maximum(w, 1e-30) ** 2, 0.0)
        return ratio * 0.5 * (1 - np.cos(w * t_eff) * damping)

    def spectro_population(self, detuning_mhz, drive_amp, sat_len_ns):
        """Steady-state, power-broadened 0->1 line + two-photon 0->2 line."""
        a = float(drive_amp)
        g0 = np.hypot(self.intrinsic_hwhm, 443.0 / max(float(sat_len_ns), 1.0))
        shift = self.ac_stark * a ** 2
        s1 = (a / self.sat_amp) ** 2
        p1 = 0.5 * s1 / (1 + s1 + ((detuning_mhz - shift) / g0) ** 2)
        s2 = (a / self.sat_amp_2ph) ** 4
        d2 = detuning_mhz - self.anharmonicity / 2 - 2 * shift
        p2 = 0.5 * s2 / (1 + s2 + (d2 / g0) ** 2)
        return np.clip(p1 + p2, 0, 1)

    def readout(self, p_excited, thermalization_us=None):
        """Averaged readout signal (≈ measured excited population, with SPAM)."""
        p0 = self.thermal_pop
        if thermalization_us is not None:
            p0 = p0 + 0.2 * np.exp(-max(float(thermalization_us), 0.0) / self.T1)
        return p0 + (self.readout_fidelity_e - p0) * np.asarray(p_excited)

    # ---- readout resonator -------------------------------------------------------
    def s21(self, f_mhz, state="g", f0=None, kappa=None, depth=1.0):
        """Complex notch response of the readout resonator."""
        if f0 is None:
            f0 = self.f_res_g + (self.two_chi if state == "e" else 0.0)
        k = self.kappa if kappa is None else kappa
        return 1 - depth * (k / 2) / (k / 2 + 1j * (np.asarray(f_mhz) - f0))


# ==================================================================================
# Helpers
# ==================================================================================
def _sweep(a, b, step, cap=_MAX_1D):
    """Inclusive sweep from a to b with ≈ `step`, capped to `cap` points."""
    a, b = float(a), float(b)
    if step is None or step == 0:
        step = (b - a) / 100.0 if b != a else 1.0
    n = int(round(abs((b - a) / step))) + 1
    n = max(2, min(n, cap))
    return np.linspace(a, b, n)


def _f(ctx, key, default):
    try:
        return float(ctx.get(key, default))
    except (TypeError, ValueError):
        return float(default)


# ==================================================================================
class MockBackend(Backend):
    name = "simulation (virtual transmon)"

    def __init__(self, device: SimulatedDevice | None = None, seed=None, n_frames=30):
        self.dev = device or SimulatedDevice()
        self.rng = np.random.default_rng(seed)
        self.n_frames = n_frames

    # ---- dispatch ---------------------------------------------------------------
    def run(self, experiment, ctx: dict):
        sim = getattr(self, f"_sim_{experiment.id}", None)
        if sim is None:
            raise NotImplementedError(f"No simulation for '{experiment.id}'")
        yield from sim(dict(ctx))

    # backwards-compatible alias
    simulate = run

    # ---- generic progressive averaging ------------------------------------------
    def _averaged(self, y_true, sigma1, n_avg, make):
        """Yield frames with the running average of `n_avg` noisy repetitions.

        sigma1 = single-repetition noise (array or scalar). Final noise = σ1/√n_avg.
        """
        n_avg = max(1, int(n_avg))
        k_frames = max(1, min(self.n_frames, n_avg))
        per = n_avg / k_frames
        acc = np.zeros_like(y_true, dtype=float)
        sig = np.broadcast_to(np.asarray(sigma1, float), y_true.shape)
        for k in range(1, k_frames + 1):
            acc += self.rng.normal(0.0, 1.0, y_true.shape) * sig / np.sqrt(per)
            fr = make(y_true + acc / k)
            fr["progress"] = int(round(100 * k / k_frames))
            fr["n_done"] = int(round(per * k))
            fr["n_total"] = n_avg
            yield fr

    def _line(self, x, y_true, ctx, sigma1=0.5):
        yield from self._averaged(y_true, sigma1, ctx.get("n_avg", 100),
                                  lambda y: {"kind": "line", "x": x, "y": y})

    def _map(self, x, y, z_true, ctx, sigma1=0.5):
        yield from self._averaged(z_true, sigma1, ctx.get("n_avg", 100),
                                  lambda z: {"kind": "map2d", "x": x, "y": y, "z": z})

    # ---- common quantities from the current configuration -----------------------
    def _qubit_detuning(self, ctx, extra_mhz=0.0):
        """Drive frequency minus true f01 (MHz) for drive IF = qubit_IF + extra."""
        drive = _f(ctx, "qubit_LO", 5.7) * 1000 + _f(ctx, "qubit_IF", 136.6) + extra_mhz
        return drive - self.dev.f01

    def _readout_freq(self, ctx, extra_mhz=0.0):
        return _f(ctx, "resonator_LO", 6.5) * 1000 + _f(ctx, "resonator_IF", -103.8771) + extra_mhz

    def _therm(self, ctx):
        return _f(ctx, "thermalization_time", 150)

    # ==============================================================================
    # Setup
    # ==============================================================================
    def _sim_time_of_flight(self, ctx):
        d = self.dev
        L = _f(ctx, "readout_len", 500)
        t0 = 24.0                                   # ADC window opened with the minimal ToF
        n = int(max(512, L + 400))
        t = t0 + np.arange(n, dtype=float)          # absolute time since the pulse is sent
        amp = 0.25 * (_f(ctx, "readout_amp", 0.49) / 0.49) * _gain(_f(ctx, "resonator_LO_gain", -20), -20)
        f_if = abs(_f(ctx, "resonator_IF", -103.8771)) / 1000.0  # cycles / ns
        rise = 1.5
        on = (t >= d.tof) & (t < d.tof + L)
        env = np.where(on, 1 - np.exp(-(t - d.tof) / rise), 0.0)
        tail = t >= d.tof + L
        env[tail] = (1 - np.exp(-L / rise)) * np.exp(-(t[tail] - d.tof - L) / rise)
        phase = 2 * np.pi * f_if * t + 0.4
        dcI = d.adc_dc_I + _f(ctx, "adc_offset_I", 0.012892)
        dcQ = d.adc_dc_Q + _f(ctx, "adc_offset_Q", 0.007190)
        I_true = np.clip(dcI + amp * env * np.cos(phase), -0.5, 0.5)
        Q_true = np.clip(dcQ + amp * env * np.sin(phase), -0.5, 0.5)
        both = np.stack([I_true, Q_true])

        def make(v):
            return {"kind": "trace", "x": t, "I": v[0], "Q": v[1]}
        yield from self._averaged(both, 0.15, ctx.get("n_avg", 1000), make)

    # ==============================================================================
    # Resonator
    # ==============================================================================
    def _readout_noise(self, ctx, drive=None):
        """Relative noise of a normalised |IQ| measurement (more power → less noise)."""
        if drive is None:
            drive = _f(ctx, "readout_amp", 0.49) * _gain(_f(ctx, "resonator_LO_gain", -20), -20)
        L = _f(ctx, "readout_len", 500)
        return 0.5 * np.minimum(20.0, 0.49 / np.maximum(drive, 1e-9)) * np.sqrt(500.0 / max(L, 16))

    def _sim_resonator_1tone(self, ctx):
        x = _sweep(ctx["f_min"], ctx["f_max"], ctx["df"] / 1000.0)    # absolute IF (MHz)
        f = _f(ctx, "resonator_LO", 6.5) * 1000 + x
        y = np.abs(self.dev.s21(f, "g"))
        yield from self._line(x, y, ctx, self._readout_noise(ctx) * 0.2)

    def _sim_resonator_vs_power(self, ctx):
        d = self.dev
        x = _sweep(ctx["f_min"], ctx["f_max"], ctx["df"] / 1000.0, cap=_MAX_2D)  # Δf
        a = np.geomspace(max(ctx["a_min"], 1e-5), max(ctx["a_max"], 2e-5),
                         min(int(ctx["n_a"]), _MAX_2D))
        drive = a * _f(ctx, "readout_amp", 0.49) * _gain(_f(ctx, "resonator_LO_gain", -20), -20)
        f = self._readout_freq(ctx, x)
        sig = 1 / (1 + np.exp(-(np.log(drive) - np.log(d.punchout_drive)) / 0.25))
        z = np.empty((len(a), len(x)))
        for r in range(len(a)):
            f0 = d.f_res_g + d.bare_shift * sig[r]
            k = d.kappa * (1 + 0.6 * sig[r] * (1 - sig[r]) * 4)   # broad near the transition
            z[r] = np.abs(d.s21(f, f0=f0, kappa=k, depth=1 - 0.3 * sig[r]))
        noise = (self._readout_noise(ctx, drive) * 0.2)[:, None] * np.ones_like(z)
        yield from self._map(x, a, z, ctx, noise)

    # ==============================================================================
    # Qubit spectroscopy
    # ==============================================================================
    def _drive_amp(self, ctx, amp):
        return float(amp) * _gain(_f(ctx, "qubit_LO_gain", 10), 10.0)

    def _sim_two_tones(self, ctx):
        x = _sweep(ctx["start"], ctx["stop"], ctx["df"] / 1000.0)     # detuning from qubit_IF
        det = self._qubit_detuning(ctx, x)
        p = self.dev.spectro_population(det, self._drive_amp(ctx, _f(ctx, "saturation_amp", 0.45)),
                                        _f(ctx, "saturation_len", 60))
        yield from self._line(x, 0.2 + 1.5 * p, ctx)

    def _sim_two_tones_qm(self, ctx):
        c, s = ctx["center"], ctx["span"]
        x = _sweep(c - s, c + s, ctx["df"] / 1000.0)                   # absolute IF (MHz)
        det = _f(ctx, "qubit_LO", 5.7) * 1000 + x - self.dev.f01
        p = self.dev.spectro_population(det, self._drive_amp(ctx, _f(ctx, "saturation_amp", 1.0)),
                                        _f(ctx, "saturation_len", 10000))
        yield from self._line(x, 0.2 + 1.5 * p, ctx)

    def _sim_two_tones_vs_power(self, ctx):
        s = ctx["span"]
        x = _sweep(-s, s, ctx["df"], cap=_MAX_2D)                      # df in MHz here
        a = np.linspace(ctx["a_min"], ctx["a_max"], min(int(ctx["n_a"]), _MAX_2D))
        det = self._qubit_detuning(ctx, x)
        base = _f(ctx, "saturation_amp", 0.45)
        z = np.array([0.2 + 1.5 * self.dev.spectro_population(
            det, self._drive_amp(ctx, ai * base), _f(ctx, "saturation_len", 60)) for ai in a])
        yield from self._map(x, a, z, ctx)

    # ==============================================================================
    # Rabi
    # ==============================================================================
    def _sim_rabi_chevron_amp(self, ctx):
        d = self.dev
        s = ctx["span"]
        x = _sweep(-s, s, ctx["df"] / 1000.0, cap=_MAX_2D)
        a = np.linspace(ctx["a_min"], ctx["a_max"], min(int(ctx["n_a"]), _MAX_2D))
        L = _f(ctx, "x180_len", 60)
        A, X = np.meshgrid(a, x, indexing="ij")
        theta = d.rotation(A * _f(ctx, "x180_amp", 0.0586), L, _f(ctx, "qubit_LO_gain", 10))
        p = d.rabi_population(theta, self._qubit_detuning(ctx, X), 0.5 * L,
                              np.exp(-np.abs(theta) / (6 * np.pi)))
        yield from self._map(x, a, d.readout(p, self._therm(ctx)), ctx)

    def _sim_rabi_chevron_time(self, ctx):
        d = self.dev
        s = ctx["span"]
        x = _sweep(-s, s, ctx["df"] / 1000.0, cap=_MAX_2D)
        t = _sweep(ctx["t_min"], ctx["t_max"], ctx["dt"], cap=_MAX_2D) * 4.0   # ns
        T, X = np.meshgrid(t, x, indexing="ij")
        theta = d.rotation(_f(ctx, "x180_amp", 0.0586), T, _f(ctx, "qubit_LO_gain", 10))
        p = d.rabi_population(theta, self._qubit_detuning(ctx, X), 0.5 * T, np.exp(-T / d.T_rabi))
        yield from self._map(x, t, d.readout(p, self._therm(ctx)), ctx)

    def _sim_time_rabi(self, ctx):
        d = self.dev
        t = _sweep(ctx["t_min"], ctx["t_max"], ctx["dt"]) * 4.0               # ns
        theta = d.rotation(_f(ctx, "x180_amp", 0.0586), t, _f(ctx, "qubit_LO_gain", 10))
        p = d.rabi_population(theta, self._qubit_detuning(ctx), 0.5 * t, np.exp(-t / d.T_rabi))
        yield from self._line(t, d.readout(p, self._therm(ctx)), ctx)

    def _sim_power_rabi(self, ctx):
        d = self.dev
        a = np.linspace(ctx["a_min"], ctx["a_max"], min(int(ctx["n_a"]), _MAX_1D))
        L = _f(ctx, "x180_len", 60)
        theta = d.rotation(a * _f(ctx, "x180_amp", 0.0586), L, _f(ctx, "qubit_LO_gain", 10))
        p = d.rabi_population(theta, self._qubit_detuning(ctx), 0.5 * L,
                              np.exp(-np.abs(theta) / (6 * np.pi)))
        yield from self._line(a, d.readout(p, self._therm(ctx)), ctx)

    # ==============================================================================
    # Coherence
    # ==============================================================================
    def _pi_population(self, ctx):
        """Population actually reached by the configured π pulse (calibration errors)."""
        d = self.dev
        L = _f(ctx, "x180_len", 60)
        theta = d.rotation(_f(ctx, "x180_amp", 0.0586), L, _f(ctx, "qubit_LO_gain", 10))
        return float(d.rabi_population(theta, self._qubit_detuning(ctx), 0.5 * L))

    def _tau_us(self, ctx, start=None):
        tmin = ctx.get("tau_min", 4) if start is None else start
        return _sweep(tmin, ctx["tau_max"], ctx["d_tau"]) * 4.0 / 1000.0

    def _sim_t1(self, ctx):
        d = self.dev
        tau = self._tau_us(ctx)
        p = self._pi_population(ctx) * np.exp(-tau / d.T1)
        yield from self._line(tau, d.readout(p, self._therm(ctx)), ctx)

    def _sim_t1_histogram(self, ctx):
        d = self.dev
        tau = self._tau_us(ctx)
        n_rep = max(2, int(ctx.get("n_repeat", 100)))
        sigma = 0.5 / np.sqrt(max(1, int(ctx.get("n_avg", 100))))
        p_pi = self._pi_population(ctx)
        samples = []
        chunk = max(1, n_rep // 30)
        y = None
        for start in range(0, n_rep, chunk):
            for _ in range(min(chunk, n_rep - start)):
                T1 = max(5.0, self.rng.normal(d.T1, d.T1_fluct))
                y = d.readout(p_pi * np.exp(-tau / T1), self._therm(ctx))
                y = y + self.rng.normal(0, sigma, tau.size)
                fit = fit_exp_decay(tau, y)
                if fit.ok and 0 < fit["T"] < 20 * (tau[-1] - tau[0]):
                    samples.append(fit["T"])
            yield {"progress": int(100 * min(start + chunk, n_rep) / n_rep), "kind": "hist",
                   "samples": np.array(samples), "last_x": tau, "last_y": y,
                   "n_done": min(start + chunk, n_rep), "n_total": n_rep}

    def _sim_ramsey(self, ctx):
        d = self.dev
        s = ctx["freq_span"]
        x = _sweep(-s, s, ctx["df"] / 1000.0, cap=_MAX_2D)                   # MHz
        tau = _sweep(4, ctx["tau_max"], ctx["d_tau"], cap=_MAX_2D) * 4.0 / 1000.0  # µs
        T, X = np.meshgrid(tau, x, indexing="ij")
        delta = -self._qubit_detuning(ctx)          # true f01 - current drive frequency
        p = 0.5 * (1 + np.cos(2 * np.pi * (X - delta) * T) * np.exp(-T / d.T2_star))
        yield from self._map(x, tau, d.readout(p, self._therm(ctx)), ctx)

    def _sim_virtual_z_ramsey(self, ctx):
        d = self.dev
        tau = self._tau_us(ctx)
        delta = -self._qubit_detuning(ctx)
        f_osc = _f(ctx, "detuning", 0.5) - delta     # qua-libs convention
        p = 0.5 * (1 + np.cos(2 * np.pi * f_osc * tau) * np.exp(-tau / d.T2_star))
        yield from self._line(tau, d.readout(p, self._therm(ctx)), ctx)

    def _sim_echo(self, ctx):
        d = self.dev
        t = 2 * self._tau_us(ctx)                    # total free evolution 2τ (µs)
        p = 0.5 * (1 - np.exp(-t / d.T2_echo))
        yield from self._line(t, d.readout(p, self._therm(ctx)), ctx)

    # ==============================================================================
    # Readout
    # ==============================================================================
    def _iq_centers(self, ctx, f_mhz):
        d = self.dev
        L = _f(ctx, "readout_len", 500)
        scale = d.iq_scale * (_f(ctx, "readout_amp", 0.49) / 0.49) * (L / 500.0) * \
            _gain(_f(ctx, "resonator_LO_gain", -20), -20)
        rot = np.exp(1j * (d.iq_phase + _f(ctx, "rotation_angle", 0.0)))
        return scale * rot * d.s21(f_mhz, "g"), scale * rot * d.s21(f_mhz, "e"), \
            d.iq_sigma * np.sqrt(L / 500.0)

    def _sim_iq_blobs(self, ctx):
        d = self.dev
        n = min(int(ctx.get("n_runs", 10000)), 10000)
        cg, ce, sigma = self._iq_centers(ctx, self._readout_freq(ctx))
        p_pi = self._pi_population(ctx)
        L = _f(ctx, "readout_len", 500)
        p_decay = 1 - np.exp(-(L / 2000.0) / d.T1)   # relaxation during half the readout
        p_th = d.thermal_pop + 0.2 * np.exp(-self._therm(ctx) / d.T1)

        def shots(m, p_e):
            in_e = self.rng.random(m) < p_e
            decays = in_e & (self.rng.random(m) < p_decay)
            c = np.where(in_e, ce, cg).astype(complex)
            # a shot that decays mid-readout lands somewhere between the two blobs
            frac = self.rng.random(m)
            c = np.where(decays, ce + (cg - ce) * frac, c)
            return c + sigma * (self.rng.normal(size=m) + 1j * self.rng.normal(size=m))

        g, e = [], []
        chunk = max(100, n // 30)
        for start in range(0, n, chunk):
            m = min(chunk, n - start)
            g.append(shots(m, p_th))
            e.append(shots(m, p_th * (1 - p_pi) + (1 - p_th) * p_pi))
            G, E = np.concatenate(g), np.concatenate(e)
            yield {"progress": int(100 * (start + m) / n), "kind": "iq",
                   "gI": G.real, "gQ": G.imag, "eI": E.real, "eQ": E.imag,
                   "n_done": start + m, "n_total": n}

    def _sim_readout_opt_freq(self, ctx):
        d = self.dev
        s = ctx["span"]
        x = _sweep(-s, s, ctx["df"] / 1000.0)
        f = self._readout_freq(ctx, x)
        y = np.abs(d.s21(f, "e") - d.s21(f, "g"))
        yield from self._line(x, y, ctx, 0.3)

    # ==============================================================================
    # Calibration
    # ==============================================================================
    def _sim_mixer_cal(self, ctx):
        r_lo, q_lo = _f(ctx, "resonator_LO", 6.5), _f(ctx, "qubit_LO", 5.7)
        r_if, q_if = _f(ctx, "resonator_IF", -103.8771), _f(ctx, "qubit_IF", 136.6)
        lines = [
            "Opening the Quantum Machine…",
            f"Mixer calibration — 'resonator' (LO {r_lo:.4f} GHz, IF {r_if:.4f} MHz)… OK",
            f"Mixer calibration — 'qubit' (LO {q_lo:.4f} GHz, IF {q_if:.4f} MHz)… OK",
            "Corrections written to calibration_db.json.",
            "[simulation mode — no action on the hardware]",
        ]
        log = ""
        for i, ln in enumerate(lines, 1):
            log += ln + "\n"
            yield {"progress": int(100 * i / len(lines)), "kind": "action", "log": log}
