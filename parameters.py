"""
Parameter model.

A ParamSpec describes ONE input field of the interface: label, unit, default value,
bounds and, above all, a help text (tooltip) explaining what it is for. This schema
automatically generates the GUI forms, so adding/removing a parameter from an
experiment only requires touching one place (experiments.py).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParamSpec:
    key: str                       # internal identifier, e.g. "n_avg"
    label: str                     # displayed label, e.g. "Averages (n_avg)"
    default: float                 # default value (in the displayed unit)
    unit: str = ""                 # "MHz", "kHz", "ns", "dB", "cycles", "" ...
    ptype: str = "float"           # "float" or "int"
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    step: Optional[float] = None   # spin-box arrow step
    decimals: int = 4              # number of decimals for floats
    help: str = ""                 # tooltip text
    group: str = "Sweep"           # group box in the form

    def coerce(self, value):
        """Return the value with the right Python type."""
        if self.ptype == "int":
            return int(round(float(value)))
        return float(value)

    def clamp(self, value):
        """Coerce and clip the value to [minimum, maximum]."""
        v = float(value)
        if self.minimum is not None:
            v = max(v, float(self.minimum))
        if self.maximum is not None:
            v = min(v, float(self.maximum))
        return self.coerce(v)

    def format(self, value) -> str:
        """Value formatted with the spec's precision (for buttons and logs)."""
        v = self.coerce(value)
        if self.ptype == "int":
            return f"{v:d}"
        return f"{v:.{self.decimals}f}"


# Convenience builders to keep the schemas readable ---------------------------------

def p_int(key, label, default, unit="", minimum=1, maximum=10_000_000,
          step=1, help="", group="Sweep"):
    return ParamSpec(key, label, default, unit=unit, ptype="int",
                     minimum=minimum, maximum=maximum, step=step,
                     decimals=0, help=help, group=group)


def p_float(key, label, default, unit="", minimum=None, maximum=None,
            step=None, decimals=4, help="", group="Sweep"):
    return ParamSpec(key, label, default, unit=unit, ptype="float",
                     minimum=minimum, maximum=maximum, step=step,
                     decimals=decimals, help=help, group=group)
