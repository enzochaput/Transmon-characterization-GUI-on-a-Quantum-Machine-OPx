"""
Store of GLOBAL parameters (single source of truth).

Physical/config parameters shared by several measurements (readout pulse, LO
frequencies and gains, π pulse, thermalization, discrimination…) and calibration
results (resonator_IF, qubit_IF, time of flight, T1/T2…) are stored here once. When
one changes (in the "Global parameters" window, in an experiment panel, or through a
"write to config" button), the `changed` signal is emitted and every form using that
parameter updates.

SWEEP parameters (n_avg, f_min, df, τ…) are NOT global: they stay specific to each
measurement. saturation_len / saturation_amp stay local too (specific to each
spectroscopy).
"""

from __future__ import annotations
import json
from collections import OrderedDict
from PyQt6.QtCore import QObject, pyqtSignal

from parameters import p_float, p_int

# Keys considered global (config-level, shared and identical everywhere)
GLOBAL_KEYS = {
    "readout_amp", "readout_len", "resonator_LO", "resonator_LO_gain", "depletion_time",
    "qubit_LO", "qubit_LO_gain",
    "x180_amp", "x180_len", "anharmonicity",
    "thermalization_time",
    "rotation_angle", "ge_threshold",
}

GRP_CAL = "Calibration results"

# Global parameters that do not appear in any experiment form: they are fed by the
# calibration cascade (values from configuration.py).
EXTRA_SPECS = [
    p_float("resonator_IF", "Resonator frequency (resonator_IF)", -103.8771, "MHz",
            minimum=-400, maximum=400, step=0.1, decimals=4, group="Resonator (Octave)",
            help="Intermediate frequency of the readout resonator, from the 1-tone "
                 "spectroscopy or the readout optimisation."),
    p_float("qubit_IF", "Qubit frequency (qubit_IF)", 136.6, "MHz",
            minimum=-400, maximum=400, step=0.1, decimals=4, group="Qubit (Octave)",
            help="Intermediate frequency of the qubit drive, from 2-tone spectroscopy, "
                 "chevrons or Ramsey."),
    p_int("time_of_flight", "Time of flight", 264, "ns", minimum=24, maximum=100000, step=4,
          group="Readout (resonator)",
          help="Delay of the acquisition window, from the Time of flight measurement."),
    p_float("adc_offset_I", "ADC offset I (analog input 1)", 0.012892, "V",
            minimum=-0.5, maximum=0.5, step=0.0001, decimals=6, group="Readout (resonator)",
            help="DC offset of analog input 1, from the Time of flight measurement."),
    p_float("adc_offset_Q", "ADC offset Q (analog input 2)", 0.007190, "V",
            minimum=-0.5, maximum=0.5, step=0.0001, decimals=6, group="Readout (resonator)",
            help="DC offset of analog input 2, from the Time of flight measurement."),
    p_float("qubit_T1", "Measured T1", 50.0, "µs", minimum=0, step=1, decimals=2,
            group=GRP_CAL, help="Last measured energy-relaxation time."),
    p_float("qubit_T2_star", "Measured T2*", 0.0, "µs", minimum=0, step=0.5, decimals=2,
            group=GRP_CAL, help="Last measured Ramsey coherence time."),
    p_float("qubit_T2_echo", "Measured T2 (echo)", 0.0, "µs", minimum=0, step=0.5, decimals=2,
            group=GRP_CAL, help="Last measured Hahn-echo coherence time."),
]


def _collect_specs():
    """First ParamSpec found for every global key (label/unit/default/type),
    completed with the calibration parameters described in EXTRA_SPECS."""
    from experiments import EXPERIMENTS
    specs = OrderedDict()
    for e in sorted(EXPERIMENTS, key=lambda x: x.order):
        for p in e.params:
            if p.key in GLOBAL_KEYS and p.key not in specs:
                specs[p.key] = p
    for s in EXTRA_SPECS:
        specs.setdefault(s.key, s)
    return specs


class ParameterStore(QObject):
    changed = pyqtSignal(str, float)   # (key, new value)

    def __init__(self):
        super().__init__()
        self.specs = _collect_specs()
        self.values = {k: s.coerce(s.default) for k, s in self.specs.items()}

    def has(self, key) -> bool:
        return key in self.values

    def get(self, key, fallback=None):
        return self.values.get(key, fallback)

    def set(self, key, value):
        if key not in self.values:
            return
        v = self.specs[key].clamp(value)
        if v != self.values[key]:
            self.values[key] = v
            self.changed.emit(key, float(v))

    def grouped(self):
        """Specs grouped by theme, in order, to build the window."""
        g = OrderedDict()
        for key, spec in self.specs.items():
            g.setdefault(spec.group, []).append(spec)
        return g

    def reset_defaults(self):
        for k, s in self.specs.items():
            self.set(k, s.default)

    # -- persistence (calibration cascade) ---------------------------------------
    def to_dict(self):
        return dict(self.values)

    def load_dict(self, d):
        for k, v in (d or {}).items():
            if k in self.values:
                try:
                    self.set(k, float(v))
                except (TypeError, ValueError):
                    pass

    def save_json(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.values, f, indent=2)

    def load_json(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.load_dict(json.load(f))
            return True
        except Exception:
            return False
