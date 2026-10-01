"""
Registry of the characterization experiments.

Each Experiment describes one notebook measurement: name, category, order in the
workflow, description, parameter list (ParamSpec) and plot type.

IMPORTANT — parameter model: an experiment form exposes not only the SWEEP
parameters of the notebook cell, but also the PHYSICAL parameters actually used
to run the measurement (readout pulse, Octave LO frequencies and gains, π / π/2
pulses, thermalization time…). In the notebook these values come from
configuration.py or are hard-coded in the cell; here they are gathered, editable,
and saved with every measurement.

Default values are taken from configuration.py (BS106 / Cooldown3).
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List

from parameters import ParamSpec, p_int, p_float


# Plot types: "trace", "line", "map2d", "hist", "iq", "action" (see mpl_canvas.py).

@dataclass
class Experiment:
    id: str
    name: str
    category: str
    order: int
    plot: str
    description: str
    params: List[ParamSpec] = field(default_factory=list)
    xlabel: str = ""
    ylabel: str = ""
    outputs: str = ""
    ylog: bool = False             # log-scale y axis (2D maps with geometric sweeps)

    @property
    def save_name(self) -> str:
        """File-system safe name used for the data folder (labmate / fallback)."""
        return re.sub(r"[^A-Za-z0-9_\-]+", "_", self.name).strip("_")


# ==================================================================================
# Reusable parameter factories (defaults = configuration.py)
# ==================================================================================
GRP_ACQ = "Acquisition"
GRP_SWEEP = "Sweep"
GRP_READOUT = "Readout (resonator)"
GRP_RES = "Resonator (Octave)"
GRP_QUBIT = "Qubit (Octave)"
GRP_PULSE = "Qubit pulses"
GRP_SEQ = "Sequence"
GRP_DISC = "g/e discrimination"


def n_avg(default=100, extra=""):
    return p_int("n_avg", "Averages (n_avg)", default, minimum=1, maximum=5_000_000,
                 step=10, group=GRP_ACQ,
                 help=("Number of averaged repetitions. Noise decreases as 1/√n_avg, "
                       "at the cost of acquisition time. " + extra).strip())

# --- Readout / resonator ----------------------------------------------------------
def readout_amp(default=0.49):
    return p_float("readout_amp", "Readout amplitude (readout_amp)", default, "V",
                   minimum=-0.5, maximum=0.5, step=0.01, decimals=4, group=GRP_READOUT,
                   help="Amplitude of the readout pulse sent to the resonator. OPX analog "
                        "outputs are limited to ±0.5 V.")

def readout_len(default=500):
    return p_float("readout_len", "Readout length (readout_len)", default, "ns",
                   minimum=16, step=50, decimals=1, group=GRP_READOUT,
                   help="Readout pulse length = integration window.")

def resonator_LO(default=6.5):
    return p_float("resonator_LO", "Resonator LO", default, "GHz", step=0.1, decimals=4,
                   group=GRP_RES,
                   help="Octave local-oscillator frequency of the readout channel.")

def resonator_LO_gain(default=-20):
    return p_float("resonator_LO_gain", "Resonator LO gain", default, "dB",
                   minimum=-20, maximum=20, step=1, decimals=1, group=GRP_RES,
                   help="Octave RF output gain of the readout channel (−20 to +20 dB).")

def depletion_time(default=1000):
    return p_float("depletion_time", "Resonator depletion (depletion_time)", default, "ns",
                   minimum=0, step=100, decimals=0, group=GRP_SEQ,
                   help="Wait after the readout so that the resonator empties its photons.")

# --- Qubit / Octave ---------------------------------------------------------------
def qubit_LO(default=5.7):
    return p_float("qubit_LO", "Qubit LO", default, "GHz", step=0.1, decimals=4, group=GRP_QUBIT,
                   help="Octave local-oscillator frequency of the qubit drive channel.")

def qubit_LO_gain(default=10):
    return p_float("qubit_LO_gain", "Qubit LO gain", default, "dB",
                   minimum=-20, maximum=20, step=1, decimals=1, group=GRP_QUBIT,
                   help="Octave RF output gain of the qubit drive (−20 to +20 dB).")

# --- Pulses -----------------------------------------------------------------------
def saturation_len(default=60):
    return p_float("saturation_len", "Saturation length (saturation_len)", default, "ns",
                   minimum=16, step=100, decimals=0, group=GRP_PULSE,
                   help="Length of the saturation pulse used in qubit spectroscopy. "
                        "Longer = qubit more saturated.")

def saturation_amp(default=0.45):
    return p_float("saturation_amp", "Saturation amplitude (saturation_amp)", default, "",
                   minimum=-2, maximum=2, step=0.05, decimals=3, group=GRP_PULSE,
                   help="Amplitude of the saturation pulse ([-2 ; 2)).")

def x180_amp(default=0.0586):
    return p_float("x180_amp", "π amplitude (x180_amp)", default, "V",
                   minimum=-0.5, maximum=0.5, step=0.005, decimals=4, group=GRP_PULSE,
                   help="Amplitude of the π pulse (x180). The π/2 pulse (x90) is half of it. "
                        "Limited to ±0.5 V by the OPX outputs.")

def x180_len(default=60):
    return p_int("x180_len", "π length (x180_len)", default, "ns", minimum=16, maximum=100000,
                 step=4, group=GRP_PULSE,
                 help="Length of the π pulse (DRAG gaussian, σ = length/5). "
                      "Must be a multiple of 4 ns, minimum 16 ns.")

def anharmonicity(default=-200):
    return p_float("anharmonicity", "Anharmonicity", default, "MHz", step=10, decimals=1,
                   group=GRP_PULSE,
                   help="Qubit anharmonicity (1→2 minus 0→1 transition). Used by DRAG.")

def thermalization_time(default=150):
    return p_float("thermalization_time", "Thermalization (thermalization_time)", default, "µs",
                   minimum=0, step=10, decimals=1, group=GRP_SEQ,
                   help="Wait between repetitions so that the qubit relaxes to |0> "
                        "(typically ~3·T1).")

# --- Discrimination ---------------------------------------------------------------
def rotation_angle(default=10.128):
    return p_float("rotation_angle", "IQ rotation angle", default, "rad", step=0.05,
                   decimals=4, group=GRP_DISC,
                   help="Angle applied to the IQ plane to align the g/e separation on one axis.")

def ge_threshold(default=-0.02017):
    return p_float("ge_threshold", "g/e threshold (ge_threshold)", default, "", step=0.001,
                   decimals=6, group=GRP_DISC,
                   help="Single-shot discrimination threshold between |0> and |1>.")


def _tau(key, label, default, maximum, step, help):
    return p_int(key, label, default, "cycles", minimum=4 if key == "tau_min" else 5,
                 maximum=maximum, step=step, group=GRP_SWEEP, help=help)


# ==================================================================================
# EXPERIMENT LIST
# ==================================================================================
EXPERIMENTS: List[Experiment] = [

    # --- Getting started --------------------------------------------------------
    Experiment(
        id="time_of_flight", name="Time of flight", category="Getting started", order=0,
        plot="trace", xlabel="Time since pulse sent (ns)", ylabel="ADC (V)",
        outputs="time_of_flight, analog input DC offsets I/Q, ADC headroom",
        description=(
            "Sends a readout pulse and records the raw ADC traces.\n\n"
            "Set up the readout channel (amplitude, length, resonator LO and gain), then "
            "extract: the time_of_flight (delay to apply to the acquisition window), the DC "
            "offsets of the analog inputs, and the ADC level to fill ±0.5 V without saturating."
        ),
        params=[
            n_avg(1000, "Averaging smooths the ADC trace."),
            readout_amp(), readout_len(),
            resonator_LO(), resonator_LO_gain(),
            depletion_time(),
        ],
    ),

    # --- Resonator --------------------------------------------------------------
    Experiment(
        id="resonator_1tone", name="Resonator spectroscopy (1-tone)",
        category="Resonator", order=1, plot="line",
        xlabel="Readout IF (MHz)", ylabel="|IQ| (a.u.)",
        outputs="resonator frequency (resonator_IF), linewidth κ, loaded Q",
        description=(
            "Sweeps the readout frequency and measures |IQ|. The dip marks the readout "
            "resonator resonance, which is written to resonator_IF."
        ),
        params=[
            n_avg(100),
            p_float("f_min", "Sweep start", -105, "MHz", step=1, decimals=3, group=GRP_SWEEP,
                    help="Lower bound of the IF sweep around the resonator LO."),
            p_float("f_max", "Sweep stop", -97, "MHz", step=1, decimals=3, group=GRP_SWEEP,
                    help="Upper bound of the IF sweep."),
            p_float("df", "Frequency step", 20, "kHz", step=5, decimals=2, group=GRP_SWEEP,
                    help="Sweep resolution. Finer = more points = longer."),
            readout_amp(), readout_len(),
            resonator_LO(), resonator_LO_gain(),
            depletion_time(),
        ],
    ),
    Experiment(
        id="resonator_vs_power", name="Resonator vs readout power",
        category="Resonator", order=2, plot="map2d", ylog=True,
        xlabel="Δf from resonator_IF (MHz)", ylabel="Readout amplitude prefactor",
        outputs="low-power resonator frequency, punch-out power, dressed–bare shift",
        description=(
            "2D map frequency × readout amplitude: shows how the resonator moves with power "
            "(“punch-out”) to choose the readout power. Each row is normalised by its "
            "amplitude, so low-power rows are noisier."
        ),
        params=[
            n_avg(100),
            p_float("f_min", "Δf start", -1, "MHz", step=0.5, decimals=3, group=GRP_SWEEP,
                    help="Start of the frequency sweep around resonator_IF."),
            p_float("f_max", "Δf stop", 2.5, "MHz", step=0.5, decimals=3, group=GRP_SWEEP,
                    help="End of the frequency sweep around resonator_IF."),
            p_float("df", "Frequency step", 5, "kHz", step=1, decimals=2, group=GRP_SWEEP,
                    help="Frequency resolution."),
            p_float("a_min", "Min amplitude", 0.0001, "", minimum=0, maximum=2, step=0.01,
                    decimals=4, group=GRP_SWEEP,
                    help="Minimum amplitude prefactor (geometric sweep), [0 ; 2)."),
            p_float("a_max", "Max amplitude", 0.49, "", minimum=0, maximum=2, step=0.01,
                    decimals=4, group=GRP_SWEEP, help="Maximum amplitude prefactor, [0 ; 2)."),
            p_int("n_a", "Number of amplitudes", 50, minimum=2, maximum=2000, step=10,
                  group=GRP_SWEEP, help="Number of amplitude levels (geometric scale)."),
            readout_len(),
            resonator_LO(), resonator_LO_gain(),
            depletion_time(),
        ],
    ),

    # --- Qubit spectroscopy -----------------------------------------------------
    Experiment(
        id="two_tones", name="Qubit spectroscopy (2-tone)",
        category="Qubit spectroscopy", order=3, plot="line",
        xlabel="Detuning from qubit_IF (MHz)", ylabel="|IQ| (a.u.)",
        outputs="0→1 transition frequency (qubit_IF)",
        description=(
            "A drive saturates the qubit while the resonator is read out. On resonance with "
            "the |0>→|1> transition the resonator response changes: this locates the qubit "
            "frequency. Strong drives shift the line slightly (AC Stark): refine with Ramsey."
        ),
        params=[
            n_avg(100),
            p_float("start", "Detuning start", -200, "MHz", step=5, decimals=2, group=GRP_SWEEP,
                    help="Lower bound of the sweep around qubit_IF."),
            p_float("stop", "Detuning stop", 200, "MHz", step=5, decimals=2, group=GRP_SWEEP,
                    help="Upper bound of the sweep around qubit_IF."),
            p_float("df", "Frequency step", 100, "kHz", step=10, decimals=2, group=GRP_SWEEP,
                    help="Sweep resolution."),
            qubit_LO(), qubit_LO_gain(),
            saturation_len(60), saturation_amp(),
            readout_amp(), readout_len(),
            thermalization_time(),
        ],
    ),
    Experiment(
        id="two_tones_qm", name="Qubit spectroscopy (QM variant)",
        category="Qubit spectroscopy", order=4, plot="line",
        xlabel="Qubit IF (MHz)", ylabel="|IQ| (a.u.)",
        outputs="refined 0→1 transition frequency (qubit_IF)",
        description=(
            "Variant where the length and amplitude of the saturation pulse are set directly "
            "to bring the qubit into a mixed state, then the drive IF is swept around a chosen "
            "centre."
        ),
        params=[
            n_avg(1000),
            p_float("center", "Sweep centre (IF)", 137, "MHz", step=5, decimals=2, group=GRP_SWEEP,
                    help="Centre of the sweep, as an absolute qubit IF."),
            p_float("span", "Half-width (span)", 100, "MHz", step=5, decimals=2, group=GRP_SWEEP,
                    help="The sweep goes from centre−span to centre+span."),
            p_float("df", "Frequency step", 100, "kHz", step=10, decimals=2, group=GRP_SWEEP,
                    help="Sweep resolution."),
            qubit_LO(), qubit_LO_gain(),
            saturation_len(10000), saturation_amp(1.0),
            readout_amp(), readout_len(),
            thermalization_time(),
        ],
    ),
    Experiment(
        id="two_tones_vs_power", name="Qubit spectroscopy vs drive power",
        category="Qubit spectroscopy", order=5, plot="map2d",
        xlabel="Detuning from qubit_IF (MHz)", ylabel="Drive amplitude prefactor",
        outputs="low-power qubit frequency, two-photon 0→2 line, anharmonicity",
        description=(
            "2D map frequency × drive amplitude: the 0→1 line broadens and shifts with power "
            "(AC Stark) and the two-photon |0>→|2> transition appears at high power, at "
            "f01 + α/2, which gives the anharmonicity α."
        ),
        params=[
            n_avg(1000),
            p_float("span", "Half-width (span)", 200, "MHz", step=5, decimals=2, group=GRP_SWEEP,
                    help="Frequency sweep from −span to +span around qubit_IF."),
            p_float("df", "Frequency step", 10, "MHz", step=1, decimals=2, group=GRP_SWEEP,
                    help="Frequency resolution (in MHz for this measurement)."),
            p_float("a_min", "Min amplitude", 0.0, "", minimum=0, maximum=2, step=0.05,
                    decimals=3, group=GRP_SWEEP, help="Minimum drive amplitude prefactor, [0 ; 2)."),
            p_float("a_max", "Max amplitude", 1.9, "", minimum=0, maximum=2, step=0.05,
                    decimals=3, group=GRP_SWEEP, help="Maximum drive amplitude prefactor, [0 ; 2)."),
            p_int("n_a", "Number of amplitudes", 21, minimum=2, maximum=500, step=5,
                  group=GRP_SWEEP, help="Number of amplitude levels (linear)."),
            qubit_LO(), qubit_LO_gain(),
            saturation_len(60),
            readout_amp(), readout_len(),
            thermalization_time(),
        ],
    ),

    # --- Rabi -------------------------------------------------------------------
    Experiment(
        id="rabi_chevron_amp", name="Rabi chevron (amplitude)",
        category="Rabi", order=6, plot="map2d",
        xlabel="Detuning from qubit_IF (MHz)", ylabel="Drive amplitude prefactor",
        outputs="refined qubit frequency, π amplitude",
        description=(
            "2D map detuning × pulse amplitude. The chevron is symmetric around the qubit "
            "frequency (refines qubit_IF) and its central column calibrates the π amplitude."
        ),
        params=[
            n_avg(20),
            p_float("span", "Half-width (span)", 15, "MHz", step=1, decimals=2, group=GRP_SWEEP,
                    help="Frequency sweep from −span to +span around qubit_IF."),
            p_float("df", "Frequency step", 250, "kHz", step=10, decimals=2, group=GRP_SWEEP,
                    help="Frequency resolution."),
            p_float("a_min", "Min amplitude", 0.0, "", minimum=0, maximum=2, step=0.05,
                    decimals=3, group=GRP_SWEEP, help="Minimum amplitude prefactor, [0 ; 2)."),
            p_float("a_max", "Max amplitude", 2.0, "", minimum=0, maximum=2, step=0.05,
                    decimals=3, group=GRP_SWEEP, help="Maximum amplitude prefactor, [0 ; 2)."),
            p_int("n_a", "Number of amplitudes", 61, minimum=2, maximum=500, step=5,
                  group=GRP_SWEEP, help="Number of amplitude levels (linear)."),
            x180_amp(), x180_len(),
            qubit_LO(), qubit_LO_gain(),
            thermalization_time(),
        ],
    ),
    Experiment(
        id="rabi_chevron_time", name="Rabi chevron (duration)",
        category="Rabi", order=7, plot="map2d",
        xlabel="Detuning from qubit_IF (MHz)", ylabel="Pulse duration (ns)",
        outputs="refined qubit frequency, Rabi period, π duration",
        description=(
            "2D map detuning × pulse duration. The Rabi fringes form a chevron centred on the "
            "qubit frequency; its central column gives the Rabi period."
        ),
        params=[
            n_avg(100),
            p_float("span", "Half-width (span)", 10, "MHz", step=1, decimals=2, group=GRP_SWEEP,
                    help="Frequency sweep from −span to +span."),
            p_float("df", "Frequency step", 500, "kHz", step=10, decimals=2, group=GRP_SWEEP,
                    help="Frequency resolution."),
            p_int("t_min", "Min duration", 4, "cycles", minimum=4, maximum=100000, step=1,
                  group=GRP_SWEEP, help="Minimum duration in clock cycles (1 cycle = 4 ns). Min 4."),
            p_int("t_max", "Max duration", 200, "cycles", minimum=5, maximum=100000, step=10,
                  group=GRP_SWEEP, help="Maximum duration in clock cycles."),
            p_int("dt", "Duration step", 1, "cycles", minimum=1, maximum=1000, step=1,
                  group=GRP_SWEEP, help="Duration step, in clock cycles."),
            x180_amp(),
            qubit_LO(), qubit_LO_gain(),
            thermalization_time(),
        ],
    ),
    Experiment(
        id="time_rabi", name="Time Rabi",
        category="Rabi", order=8, plot="line",
        xlabel="Pulse duration (ns)", ylabel="Signal (a.u.)",
        outputs="Rabi period, π pulse duration (x180_len)",
        description=(
            "At the qubit frequency, sweeps the pulse DURATION. The Rabi oscillation period "
            "gives the duration of a π rotation at the current amplitude."
        ),
        params=[
            n_avg(2000),
            p_int("t_min", "Min duration", 25, "cycles", minimum=4, maximum=100000, step=1,
                  group=GRP_SWEEP, help="Minimum duration in cycles (1 cycle = 4 ns). Min 4."),
            p_int("t_max", "Max duration", 250, "cycles", minimum=5, maximum=100000, step=10,
                  group=GRP_SWEEP, help="Maximum duration in cycles (1 cycle = 4 ns)."),
            p_int("dt", "Duration step", 1, "cycles", minimum=1, maximum=1000, step=1,
                  group=GRP_SWEEP, help="Duration step, in cycles."),
            x180_amp(),
            qubit_LO(), qubit_LO_gain(),
            thermalization_time(),
        ],
    ),
    Experiment(
        id="power_rabi", name="Power Rabi",
        category="Rabi", order=9, plot="line",
        xlabel="Amplitude prefactor", ylabel="Signal (a.u.)",
        outputs="π pulse amplitude (x180_amp)",
        description=(
            "At fixed duration, sweeps the pulse AMPLITUDE. The Rabi oscillation gives the "
            "amplitude of a π rotation. Calibrates x180_amp."
        ),
        params=[
            n_avg(2000),
            p_float("a_min", "Min amplitude", 0.0, "", minimum=0, maximum=2, step=0.05,
                    decimals=3, group=GRP_SWEEP, help="Minimum amplitude prefactor, [0 ; 2)."),
            p_float("a_max", "Max amplitude", 1.2, "", minimum=0, maximum=2, step=0.05,
                    decimals=3, group=GRP_SWEEP, help="Maximum amplitude prefactor, [0 ; 2)."),
            p_int("n_a", "Number of amplitudes", 100, minimum=2, maximum=2000, step=10,
                  group=GRP_SWEEP, help="Number of amplitude levels (linear)."),
            x180_amp(), x180_len(),
            qubit_LO(), qubit_LO_gain(),
            thermalization_time(),
        ],
    ),

    # --- Coherence --------------------------------------------------------------
    Experiment(
        id="t1", name="T1 (energy relaxation)",
        category="Coherence", order=10, plot="line",
        xlabel="Wait time τ (µs)", ylabel="Excited-state signal (a.u.)",
        outputs="relaxation time T1 (→ thermalization_time = 3·T1)",
        description=(
            "π pulse, then a variable wait τ before readout. The exponential decay gives T1."
        ),
        params=[
            n_avg(2000),
            _tau("tau_min", "τ min", 4, 10_000_000, 1,
                 "Minimum wait in cycles (1 cycle = 4 ns). Min 4."),
            _tau("tau_max", "τ max", 25000, 10_000_000, 100,
                 "Maximum wait in cycles. 25000 ≈ 100 µs."),
            p_int("d_tau", "τ step", 100, "cycles", minimum=1, maximum=100000, step=10,
                  group=GRP_SWEEP, help="Wait-time step, in cycles."),
            x180_amp(), x180_len(),
            thermalization_time(),
        ],
    ),
    Experiment(
        id="t1_histogram", name="T1 histogram",
        category="Coherence", order=11, plot="hist",
        xlabel="Fitted T1 (µs)", ylabel="Counts",
        outputs="mean T1, spread and time fluctuations of T1",
        description=(
            "Repeats the T1 measurement, fits every repetition and histograms the fitted "
            "values — characterises the temporal fluctuations of T1."
        ),
        params=[
            n_avg(2000),
            _tau("tau_min", "τ min", 4, 10_000_000, 1, "Minimum wait in cycles (1 cycle = 4 ns)."),
            _tau("tau_max", "τ max", 25000, 10_000_000, 100, "Maximum wait in cycles."),
            p_int("d_tau", "τ step", 100, "cycles", minimum=1, maximum=100000, step=10,
                  group=GRP_SWEEP, help="Wait-time step, in cycles."),
            p_int("n_repeat", "Number of T1 repetitions", 100, minimum=2, maximum=100000, step=10,
                  group=GRP_ACQ, help="Number of successive T1 measurements for the histogram."),
            x180_amp(), x180_len(),
            thermalization_time(),
        ],
    ),
    Experiment(
        id="ramsey", name="Ramsey chevron (frequency × time)",
        category="Coherence", order=12, plot="map2d",
        xlabel="Detuning from qubit_IF (MHz)", ylabel="Wait time τ (µs)",
        outputs="precise qubit frequency (qubit_IF), T2*",
        description=(
            "π/2 — wait τ — π/2 while sweeping detuning and time. A global 2D fit of the "
            "Ramsey fringes gives the qubit frequency (centre of the chevron) and T2*."
        ),
        params=[
            n_avg(100),
            p_float("freq_span", "Half-width (span)", 1.5, "MHz", step=0.1, decimals=3,
                    group=GRP_SWEEP, help="Frequency sweep from −span to +span around qubit_IF."),
            p_float("df", "Frequency step", 15, "kHz", step=1, decimals=2, group=GRP_SWEEP,
                    help="Frequency resolution."),
            _tau("tau_max", "τ max", 5000, 1_000_000, 100, "Maximum wait in cycles. 5000 ≈ 20 µs."),
            p_int("d_tau", "τ step", 50, "cycles", minimum=1, maximum=100000, step=10,
                  group=GRP_SWEEP, help="Wait-time step, in cycles."),
            x180_amp(), x180_len(),
            thermalization_time(),
        ],
    ),
    Experiment(
        id="virtual_z_ramsey", name="Ramsey (virtual Z)",
        category="Coherence", order=13, plot="line",
        xlabel="Wait time τ (µs)", ylabel="Signal (a.u.)",
        outputs="qubit frequency correction (qubit_IF), T2*",
        description=(
            "Ramsey where the detuning is imposed by virtual Z rotations. The damped "
            "oscillation gives the residual qubit detuning (measured frequency − imposed "
            "detuning) and T2*. Choose an imposed detuning larger than the expected error."
        ),
        params=[
            n_avg(1000),
            _tau("tau_min", "τ min", 4, 1_000_000, 1, "Minimum wait in cycles (1 cycle = 4 ns). Min 4."),
            _tau("tau_max", "τ max", 7500, 1_000_000, 100, "Maximum wait in cycles. 7500 ≈ 30 µs."),
            p_int("d_tau", "τ step", 10, "cycles", minimum=1, maximum=100000, step=5,
                  group=GRP_SWEEP, help="Wait-time step, in cycles."),
            p_float("detuning", "Imposed detuning", 0.5, "MHz", step=0.1, decimals=3,
                    group=GRP_SWEEP,
                    help="Detuning emulated by virtual Z rotations: sets the fringe frequency."),
            x180_amp(), x180_len(),
            thermalization_time(),
        ],
    ),
    Experiment(
        id="echo", name="Hahn echo (T2)",
        category="Coherence", order=14, plot="line",
        xlabel="Total free evolution 2τ (µs)", ylabel="Signal (a.u.)",
        outputs="echo coherence time T2 (Hahn)",
        description=(
            "π/2 — τ — π — τ — π/2. The refocusing π pulse cancels slow frequency noise, so "
            "the decay of the echo gives T2 (Hahn echo), usually longer than T2*."
        ),
        params=[
            n_avg(1000),
            _tau("tau_min", "τ min", 4, 1_000_000, 1,
                 "Minimum half wait τ in cycles (1 cycle = 4 ns). Min 4."),
            _tau("tau_max", "τ max", 10000, 1_000_000, 100,
                 "Maximum half wait τ in cycles. 10000 ≈ 40 µs (80 µs total)."),
            p_int("d_tau", "τ step", 100, "cycles", minimum=1, maximum=100000, step=10,
                  group=GRP_SWEEP, help="Step of the half wait τ, in cycles."),
            x180_amp(), x180_len(),
            thermalization_time(),
        ],
    ),

    # --- Readout ----------------------------------------------------------------
    Experiment(
        id="iq_blobs", name="IQ blobs (g/e discrimination)",
        category="Readout", order=15, plot="iq",
        xlabel="I (V)", ylabel="Q (V)",
        outputs="IQ rotation angle, g/e threshold, readout fidelity",
        description=(
            "Prepares |0> then |1> and measures I,Q single-shot. The two clouds give the "
            "optimal rotation angle, the discrimination threshold and the readout fidelity."
        ),
        params=[
            p_int("n_runs", "Number of shots (n_runs)", 10000, minimum=100, maximum=5_000_000,
                  step=1000, group=GRP_ACQ,
                  help="Single-shot measurements per state. Larger = better-defined blobs."),
            readout_amp(), readout_len(),
            x180_amp(), x180_len(),
            thermalization_time(),
            rotation_angle(), ge_threshold(),
        ],
    ),
    Experiment(
        id="readout_opt_freq", name="Readout frequency optimization",
        category="Readout", order=16, plot="line",
        xlabel="Δf from resonator_IF (MHz)", ylabel="g–e separation (a.u.)",
        outputs="optimal readout frequency (resonator_IF)",
        description=(
            "Sweeps the readout frequency and measures the |0>/|1> separation in the IQ "
            "plane. The maximum gives the optimal readout frequency."
        ),
        params=[
            n_avg(1000),
            p_float("span", "Half-width (span)", 5, "MHz", step=0.5, decimals=3, group=GRP_SWEEP,
                    help="Sweep from −span to +span around resonator_IF."),
            p_float("df", "Frequency step", 100, "kHz", step=10, decimals=2, group=GRP_SWEEP,
                    help="Sweep resolution."),
            readout_amp(), readout_len(),
            x180_amp(), x180_len(),
            thermalization_time(),
        ],
    ),

    # --- Calibration ------------------------------------------------------------
    Experiment(
        id="mixer_cal", name="Octave mixer calibration",
        category="Calibration", order=17, plot="action",
        xlabel="", ylabel="",
        outputs="DC corrections (I0, Q0), gain/phase — written to calibration_db.json",
        description=(
            "Automatic calibration of the Octave mixers (LO leakage + image sideband "
            "suppression) for the LO/IF frequencies in use. Corrections are written to "
            "calibration_db.json.\n\nOne-shot action, to re-run after any change of LO or gain."
        ),
        params=[],
    ),
]


EXPERIMENTS_BY_ID = {e.id: e for e in EXPERIMENTS}


def categories_in_order():
    seen = []
    for e in sorted(EXPERIMENTS, key=lambda x: x.order):
        if e.category not in seen:
            seen.append(e.category)
    return seen
