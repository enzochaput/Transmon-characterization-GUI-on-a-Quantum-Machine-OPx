"""
Content of the parameter glossary (full help).

Every unique parameter is described once: what it is physically, what happens when
it is increased/decreased, a typical order of magnitude. The list of measurements
using it, the measurements that calibrate it, and its label/unit are computed
automatically from experiments.py / analysis.py (nothing duplicated to maintain).
"""

from __future__ import annotations
import re

# Order of themes and parameters in the glossary
GROUPS = [
    ("Acquisition & averaging", ["n_avg", "n_runs", "n_repeat"]),
    ("Frequency sweep", ["f_min", "f_max", "start", "stop", "center", "span",
                         "freq_span", "df", "detuning"]),
    ("Amplitude sweep", ["a_min", "a_max", "n_a"]),
    ("Time / duration sweep", ["t_min", "t_max", "dt", "tau_min", "tau_max", "d_tau"]),
    ("Readout (resonator)", ["readout_amp", "readout_len", "resonator_LO",
                             "resonator_LO_gain", "resonator_IF", "depletion_time",
                             "time_of_flight", "adc_offset_I", "adc_offset_Q"]),
    ("Qubit (Octave)", ["qubit_LO", "qubit_LO_gain", "qubit_IF"]),
    ("Qubit pulses", ["saturation_len", "saturation_amp", "x180_amp", "x180_len",
                      "anharmonicity"]),
    ("Sequence", ["thermalization_time"]),
    ("g/e discrimination", ["rotation_angle", "ge_threshold"]),
    ("Measured coherence", ["qubit_T1", "qubit_T2_star", "qubit_T2_echo"]),
]

# key -> {what, effect, typical}
DOCS = {
    # --- Acquisition ---------------------------------------------------------
    "n_avg": dict(
        what="Number of times the sequence is repeated and averaged by the OPX.",
        effect="Increase → less noise (it decreases as 1/√n_avg) but the measurement takes proportionally longer. Decrease → faster but noisier.",
        typical="100 for a quick look, 1000–2000 for a clean measurement."),
    "n_runs": dict(
        what="Number of single-shot measurements (one acquisition per shot, no averaging) used to build the IQ clouds.",
        effect="Increase → better-defined g/e clouds, more reliable threshold and fidelity, but longer. Decrease → coarser statistics.",
        typical="10 000 to 50 000 shots."),
    "n_repeat": dict(
        what="Number of successive T1 measurements whose fitted values are histogrammed.",
        effect="Increase → better-sampled T1 distribution (fluctuations become visible) but long total duration.",
        typical="50 to a few hundred."),

    # --- Frequency -----------------------------------------------------------
    "f_min": dict(
        what="Lower bound of the intermediate-frequency (IF) sweep around the LO (or around resonator_IF for the power sweep).",
        effect="Wider window → more chances to catch the peak/dip but more points. Too narrow → the resonance can be missed.",
        typical="A few MHz to ~100 MHz below the expected frequency."),
    "f_max": dict(
        what="Upper bound of the intermediate-frequency (IF) sweep.",
        effect="Same as f_min on the high side: sets the width of the search window.",
        typical="A few MHz to ~100 MHz above the expected frequency."),
    "start": dict(
        what="Start of the detuning sweep around the qubit frequency (qubit_IF).",
        effect="Wider window → covers more detuning but takes longer.",
        typical="−100 to −200 MHz for a wide spectroscopy."),
    "stop": dict(
        what="End of the detuning sweep around the qubit frequency.",
        effect="Sets the upper bound of the qubit search window.",
        typical="+100 to +200 MHz."),
    "center": dict(
        what="Centre of the sweep, as an absolute qubit IF.",
        effect="Put it on the expected transition; the sweep explores center ± span.",
        typical="The roughly known qubit IF."),
    "span": dict(
        what="Half-width of the sweep: the measurement explores −span to +span (or centre ± span).",
        effect="Increase → wider window, less risk of missing the line, but coarser effective resolution at a fixed number of points.",
        typical="5–15 MHz around a known line; 100–200 MHz for a wide search."),
    "freq_span": dict(
        what="Half-width of the frequency sweep of the Ramsey chevron (around qubit_IF).",
        effect="Must bracket the small residual detuning; too wide drowns the fringes.",
        typical="~1–2 MHz."),
    "df": dict(
        what="Frequency step of the sweep (resolution).",
        effect="Smaller → more points, better-resolved line, longer measurement. Larger → fast but a narrow line can be smoothed out or missed.",
        typical="5–50 kHz for the resonator, 0.1–1 MHz for the qubit."),
    "detuning": dict(
        what="Detuning deliberately imposed (through virtual Z rotations) in the virtual-Z Ramsey.",
        effect="Sets the Ramsey fringe frequency: larger → faster fringes. Must be larger than the expected frequency error, otherwise the sign of the correction is ambiguous.",
        typical="0.5–2 MHz."),

    # --- Amplitude -----------------------------------------------------------
    "a_min": dict(
        what="Minimum amplitude prefactor of the sweep (multiplies the base amplitude of the pulse).",
        effect="Must stay within [-2 ; 2). Sets the bottom of the explored power range.",
        typical="0 (or a very small value for a geometric scale)."),
    "a_max": dict(
        what="Maximum amplitude prefactor of the sweep.",
        effect="Too large → saturation / non-linearities (sometimes wanted, e.g. punch-out). Restricted to [-2 ; 2), and the resulting pulse must stay within ±0.5 V.",
        typical="1–2 for a Rabi sweep, ~0.5 for the readout."),
    "n_a": dict(
        what="Number of amplitude levels between a_min and a_max.",
        effect="Increase → finer 2D map in amplitude but longer.",
        typical="20–100."),

    # --- Time / duration -----------------------------------------------------
    "t_min": dict(
        what="Minimum duration of the swept pulse, in clock cycles (1 cycle = 4 ns).",
        effect="The hardware minimum is 4 cycles. Sets the start of the time sweep.",
        typical="4 cycles (16 ns)."),
    "t_max": dict(
        what="Maximum duration of the swept pulse (in 4 ns cycles).",
        effect="Larger → several Rabi oscillations visible (better period estimate) but longer.",
        typical="200–250 cycles (0.8–1 µs)."),
    "dt": dict(
        what="Step of the duration sweep (in 4 ns cycles).",
        effect="Smaller → better-resolved oscillations, more points.",
        typical="1–4 cycles."),
    "tau_min": dict(
        what="Minimum wait time of the sweep (in 4 ns cycles). For the echo, this is the half wait τ.",
        effect="Minimum 4 cycles. Starting point of the decay/oscillation.",
        typical="4 cycles."),
    "tau_max": dict(
        what="Maximum wait time of the sweep (in 4 ns cycles). For the echo, this is the half wait τ.",
        effect="Must cover several T1 (T1), several fringes (Ramsey) or several T2 (echo). Too short → truncated decay and unreliable fit.",
        typical="≈ 3–5 × T1 for T1; ~20–30 µs for Ramsey; ≈ 2–3 × T2/2 for the echo."),
    "d_tau": dict(
        what="Step of the wait-time sweep (in 4 ns cycles).",
        effect="Smaller → better-sampled curve but more points. For Ramsey, it must sample each fringe period several times.",
        typical="10–100 cycles."),

    # --- Readout -------------------------------------------------------------
    "readout_amp": dict(
        what="Amplitude of the readout pulse sent to the resonator.",
        effect="Increase → more signal/SNR, but beyond a threshold the resonator becomes non-linear (punch-out) and the readout loses fidelity (it can also heat the qubit). OPX outputs are limited to ±0.5 V.",
        typical="0.1–0.5 V."),
    "readout_len": dict(
        what="Length of the readout pulse = integration window of the signal.",
        effect="Longer → more photons integrated, better SNR, but slower measurement and more relaxation during the readout. Limited by T1.",
        typical="0.5–2 µs."),
    "resonator_LO": dict(
        what="Octave local-oscillator frequency of the readout channel.",
        effect="Sets the readout RF band: LO + IF = actual resonator frequency. Choose it so that the IF stays in a comfortable range (~100 MHz).",
        typical="~6–7 GHz."),
    "resonator_LO_gain": dict(
        what="Octave RF output gain of the readout channel.",
        effect="Increase → more readout power (like readout_amp but on the analog side). Range −20 to +20 dB.",
        typical="−20 to 0 dB."),
    "resonator_IF": dict(
        what="Intermediate frequency of the readout tone: LO + IF = readout frequency.",
        effect="Set it on the resonator (1-tone spectroscopy), then on the point that best separates |0> and |1> (readout optimisation).",
        typical="−50 to −250 MHz (here ≈ −104 MHz)."),
    "depletion_time": dict(
        what="Wait after the readout so that photons leave the resonator.",
        effect="Too short → residual photons dephase the next measurement. Too long → needlessly slower measurement.",
        typical="~1 µs (a few resonator lifetimes)."),
    "time_of_flight": dict(
        what="Delay between sending the readout pulse and opening the acquisition window (cables, amplifiers, Octave).",
        effect="Too short → the beginning of the window integrates noise only; too long → the end of the pulse is cut. Multiple of 4 ns, ≥ 24 ns.",
        typical="~200–300 ns."),
    "adc_offset_I": dict(
        what="DC offset applied to analog input 1 (I) of the OPX.",
        effect="Compensates the DC level of the down-converted signal; a residual offset biases the demodulated I/Q.",
        typical="A few mV."),
    "adc_offset_Q": dict(
        what="DC offset applied to analog input 2 (Q) of the OPX.",
        effect="Same as adc_offset_I for the Q input.",
        typical="A few mV."),

    # --- Qubit ---------------------------------------------------------------
    "qubit_LO": dict(
        what="Octave local-oscillator frequency of the qubit drive.",
        effect="Sets the drive RF band: LO + IF = qubit frequency. Choose it to keep a reasonable IF.",
        typical="~4–6 GHz."),
    "qubit_LO_gain": dict(
        what="Octave RF output gain of the qubit drive.",
        effect="Increase → stronger drive (faster Rabi, but risk of leakage to |2> and heating). Range −20 to +20 dB. Changing it changes the π amplitude.",
        typical="0–20 dB."),
    "qubit_IF": dict(
        what="Intermediate frequency of the qubit drive: LO + IF = qubit 0→1 frequency.",
        effect="A wrong value detunes every pulse (incomplete rotations, Ramsey fringes). Coarse from 2-tone spectroscopy, precise from Ramsey.",
        typical="50–350 MHz (here ≈ 137 MHz)."),

    # --- Pulses --------------------------------------------------------------
    "saturation_len": dict(
        what="Length of the saturation pulse used in qubit spectroscopy.",
        effect="Longer → qubit more saturated and narrower (Fourier-limited) line; a very short pulse broadens the line.",
        typical="60 ns – 50 µs."),
    "saturation_amp": dict(
        what="Amplitude of the saturation pulse (prefactor).",
        effect="Larger → stronger line but power-broadened and AC-Stark shifted; too large hides the exact position. [-2 ; 2).",
        typical="0.1–0.5."),
    "x180_amp": dict(
        what="Amplitude of the π pulse (x180) that flips |0>↔|1>. The π/2 pulse (x90) is half of it.",
        effect="To calibrate precisely (Power Rabi): too weak or too strong → incomplete rotation, imperfect |1> preparation. Limited to ±0.5 V.",
        typical="A few hundredths to ~0.2 V depending on the length."),
    "x180_len": dict(
        what="Length of the π pulse (DRAG gaussian, σ = length/5).",
        effect="Shorter → faster gate but broader in frequency (risk of exciting |2>) and larger amplitude required. Speed/selectivity trade-off. Multiple of 4 ns.",
        typical="20–120 ns."),
    "anharmonicity": dict(
        what="Difference between the 1→2 and the 0→1 transitions of the qubit (negative for a transmon).",
        effect="Used by the DRAG correction to avoid populating |2>. Must match the measured anharmonicity.",
        typical="≈ −200 MHz."),

    # --- Sequence ------------------------------------------------------------
    "thermalization_time": dict(
        what="Wait between two repetitions so that the qubit relaxes back to |0>.",
        effect="Too short → the qubit is not reset, repetitions contaminate each other. Too long → slow measurement. Usual rule: ~3–5 × T1.",
        typical="~3 × T1 (often 100–300 µs)."),

    # --- Discrimination ------------------------------------------------------
    "rotation_angle": dict(
        what="Angle applied to the IQ plane to align the |0>/|1> separation on a single axis (I).",
        effect="Well set (from the IQ blobs) → all the discrimination information on one quadrature, sharper threshold. The IQ-blobs analysis gives the angle to ADD to the current value.",
        typical="Value from the blob fit (radians)."),
    "ge_threshold": dict(
        what="Threshold on the discriminating quadrature separating |0> from |1> in single shot.",
        effect="Badly placed → state-assignment errors. Recompute it whenever the readout changes.",
        typical="Small value close to zero (depends on the signal scale)."),

    # --- Measured coherence ---------------------------------------------------
    "qubit_T1": dict(
        what="Last measured energy-relaxation time T1.",
        effect="Bookkeeping value; it sets the recommended thermalization_time (3·T1).",
        typical="10–200 µs."),
    "qubit_T2_star": dict(
        what="Last measured Ramsey coherence time T2*.",
        effect="Bookkeeping value; limits the frequency resolution of a Ramsey measurement.",
        typical="1–50 µs, T2* ≤ 2·T1."),
    "qubit_T2_echo": dict(
        what="Last measured Hahn-echo coherence time T2.",
        effect="Bookkeeping value; T2(echo) > T2* when slow (1/f) noise dominates.",
        typical="T2* ≤ T2 ≤ 2·T1."),
}


def experiments_using(key):
    """Names of the experiments (in workflow order) whose form uses this parameter."""
    from experiments import EXPERIMENTS
    return [e.name for e in sorted(EXPERIMENTS, key=lambda x: x.order)
            if any(p.key == key for p in e.params)]


def experiments_calibrating(key):
    """Names of the experiments whose automatic extraction proposes a value for key."""
    from experiments import EXPERIMENTS
    from analysis import METHODS
    pat = re.compile(rf"\b{re.escape(key)}\b")
    return [e.name for e in sorted(EXPERIMENTS, key=lambda x: x.order)
            if e.id in METHODS and pat.search(METHODS[e.id][1])]


def spec_for(key):
    """First ParamSpec found for this parameter (to get its label and unit)."""
    from experiments import EXPERIMENTS
    for e in sorted(EXPERIMENTS, key=lambda x: x.order):
        for p in e.params:
            if p.key == key:
                return p
    from param_store import EXTRA_SPECS
    for s in EXTRA_SPECS:
        if s.key == key:
            return s
    return None
