"""
Octave configuration working for QOP222 and qm-qua==1.1.5 and newer.
"""

from pathlib import Path
import numpy as np
from qualang_tools.config.waveform_tools import drag_gaussian_pulse_waveforms
from qualang_tools.units import unit
from qm.octave import QmOctaveConfig
import os


#######################
# AUXILIARY FUNCTIONS #
#######################
u = unit(coerce_to_integer=True)

# def IQ_imbalance(g, phi):
#     """
#     Creates the correction matrix for the mixer imbalance caused by the gain and phase imbalances, more information can
#     be seen here:
#     https://docs.qualang.io/libs/examples/mixer-calibration/#non-ideal-mixer
#     :param g: relative gain imbalance between the 'I' & 'Q' ports. (unit-less), set to 0 for no gain imbalance.
#     :param phi: relative phase imbalance between the 'I' & 'Q' ports (radians), set to 0 for no phase imbalance.
#     """
#     c = np.cos(phi)
#     s = np.sin(phi)
#     N = 1 / ((1 - g**2) * (2 * c**2 - 1))
#     return [float(N * x) for x in [(1 - g) * c, (1 + g) * s, (1 - g) * s, (1 + g) * c]]


######################
# Network parameters #
######################
qop_ip = "192.168.88.242"  # Write the OPX IP address
cluster_name = "Cluster_1"  # Write your cluster_name if version >= QOP220
qop_port = None  # Write the QOP port if version < QOP220
octave_ip = "192.168.88.252"  # Write the OPX IP address
octave_port = 80  # Write the QOP port if version < QOP220

# Path to save data
save_dir = Path().absolute() / "QM" / "INSTALLATION" / "data"

############################
# Set octave configuration #
############################

octave_config = QmOctaveConfig()
octave_config.set_calibration_db(os.getcwd())
octave_config.add_device_info("octave1", octave_ip, octave_port)

#####################
# OPX configuration #
#####################

#############################################
#                  Qubits                   #
#############################################
# Qubit 1
#qubit_LO = 2.8 * u.GHz # res 1
qubit_LO = 5.7* u.GHz#5.3* u.GHz
qubit_LO_gain =10#20#dBm
#qubit_IF = (3.7644-3.9) * u.GHz 
qubit_IF =-0.4*u.MHz+ 137* u.MHz#326* u.MHz#-122* u.MHz+0.621*u.MHz-0.022*u.MHz
#qubit_IF = -132.1* u.MHz 

qubit_T1 = int(50* u.us)
thermalization_time = 3 * qubit_T1

# Continuous wave
const_len = 100
const_amp = 0.125
# Saturation_pulse
saturation_len = 60# * u.us #0.3 * u.us
saturation_amp = 0.45#0.45 # 0.3#-0.01 #qubit2
# Square pi pulse
square_pi_len = 400 * u.ns
square_pi_amp = 0.2
# Drag pulses
drag_coef = 0
anharmonicity = -200 * u.MHz
AC_stark_detuning = 0 * u.MHz

x180_len = 60 #120#40 #20
# x180_len = 16
x180_sigma = x180_len / 5
# x180_amp =0.0537 # qubit1
x180_amp = 0.0586#0.1#0.45 #0.25 #


#############################################
#                Resonators                 #
#############################################
#  Resonator
resonator_LO = 6.5 * u.GHz #res 3
resonator_LO_gain =-20#0 #-5 #dB
resonator_IF = -103.8771*u.MHz #-167.13 * u.MHz #(6.13478 - 6.3)* u.MHz
#readout_len = 0.6 * u.us
readout_len = 0.5* u.us#0.5* u.us#1 * u.us
readout_amp = 0.49#0.20#0.3 #0.49

# time_of_flight = 24 +500
time_of_flight =256 + 8#+ 72
depletion_time = 1 * u.us # time to de-energize the resonator

# IQ Plane Angle
rotation_angle = ((92.9+214.6+272.8)/ 180) * np.pi
# Threshold for single shot g-e discrimination
ge_threshold =-2.017e-02 #3.2e-4


x180_wf, x180_der_wf = np.array(
    drag_gaussian_pulse_waveforms(x180_amp, x180_len, x180_sigma, drag_coef, anharmonicity, AC_stark_detuning)
)

x180_I_wf = x180_wf
x180_Q_wf = x180_der_wf

x90_len = x180_len
x90_sigma = x90_len / 5
x90_amp = x180_amp / 2

x90_wf, x90_der_wf = np.array(
    drag_gaussian_pulse_waveforms(x90_amp, x90_len, x90_sigma, drag_coef, anharmonicity, AC_stark_detuning)
)
x90_I_wf = x90_wf
x90_Q_wf = x90_der_wf

minus_x90_len = x180_len
minus_x90_sigma = minus_x90_len / 5
minus_x90_amp = -x90_amp
minus_x90_wf, minus_x90_der_wf = np.array(
    drag_gaussian_pulse_waveforms(
        minus_x90_amp,
        minus_x90_len,
        minus_x90_sigma,
        drag_coef,
        anharmonicity,
        AC_stark_detuning,
    )
)
minus_x90_I_wf = minus_x90_wf
minus_x90_Q_wf = minus_x90_der_wf
# No DRAG when alpha=0, it's just a gaussian.

y180_len = x180_len
y180_sigma = y180_len / 5
y180_amp = x180_amp
y180_wf, y180_der_wf = np.array(
    drag_gaussian_pulse_waveforms(y180_amp, y180_len, y180_sigma, drag_coef, anharmonicity, AC_stark_detuning)
)
y180_I_wf = (-1) * y180_der_wf
y180_Q_wf = y180_wf
# No DRAG when alpha=0, it's just a gaussian.

y90_len = x180_len
y90_sigma = y90_len / 5
y90_amp = y180_amp / 2
y90_wf, y90_der_wf = np.array(
    drag_gaussian_pulse_waveforms(y90_amp, y90_len, y90_sigma, drag_coef, anharmonicity, AC_stark_detuning)
)
y90_I_wf = (-1) * y90_der_wf
y90_Q_wf = y90_wf
# No DRAG when alpha=0, it's just a gaussian.

minus_y90_len = y180_len
minus_y90_sigma = minus_y90_len / 5
minus_y90_amp = -y90_amp
minus_y90_wf, minus_y90_der_wf = np.array(
    drag_gaussian_pulse_waveforms(
        minus_y90_amp,
        minus_y90_len,
        minus_y90_sigma,
        drag_coef,
        anharmonicity,
        AC_stark_detuning,
    )
)
minus_y90_I_wf = (-1) * minus_y90_der_wf
minus_y90_Q_wf = minus_y90_wf
# No DRAG when alpha=0, it's just a gaussian.


opt_weights = False
if opt_weights:
    from qualang_tools.config.integration_weights_tools import convert_integration_weights

    weights = np.load("optimal_weights.npz")
    opt_weights_real = convert_integration_weights(weights["weights_real"])
    opt_weights_minus_imag = convert_integration_weights(weights["weights_minus_imag"])
    opt_weights_imag = convert_integration_weights(weights["weights_imag"])
    opt_weights_minus_real = convert_integration_weights(weights["weights_minus_real"])
else:
    opt_weights_real = [(1.0, readout_len)]
    opt_weights_minus_imag = [(1.0, readout_len)]
    opt_weights_imag = [(1.0, readout_len)]
    opt_weights_minus_real = [(1.0, readout_len)]


#############################################
#                  Config                   #
#############################################
config = {
    "version": 1,
    "controllers": {
        "con1": {
            "analog_outputs": {
                1: {"offset": 0.0},  # I resonator
                2: {"offset": 0.0},  # Q resonator
                3: {"offset": 0.0},  # I qubit
                4: {"offset": 0.0},  # Q qubit
                # 5: {"offset": 0.0},  # flux line
                # 6: {"offset": 0.0},  # flux line
                # 9: {"offset": 0.0},  # I lf qubit
                # 10: {"offset": 0.0},  # Q lf qubit
            },
            "digital_outputs": {
                1: {},
            },
            "analog_inputs": {
                1: {"offset": 0.012892, "gain_db": 10},  # I from down-conversion
                2: {"offset": 0.007190, "gain_db": 10},  # Q from down-conversion
            },
        },
    },
    "elements": {
        # "octave": {
        #     "RF_inputs": {"port": ("octave1", 3)},
        #     "intermediate_frequency": 50e6,
        #     "operations": {
        #         "cw": "const_pulse",
        #     },
        # },
        # "lf_qubit": {
        #     "mixInputs": {
        #         "I": ("con1", 3),
        #         "Q": ("con1", 4),
        #         "lo_frequency": lf_qubit_LO,
        #         "mixer": "mixer_qubit",
        #     },
        #     "intermediate_frequency": lf_qubit_IF,
        #     "operations": {
        #         "cw": "const_pulse",
        #         "saturation": "saturation_pulse",
        #         "pi": "pi_pulse",
        #         "pi_half": "pi_half_pulse",
        #         "x180": "x180_pulse",
        #         "x90": "x90_pulse",
        #         "-x90": "-x90_pulse",
        #         "y90": "y90_pulse",
        #         "y180": "y180_pulse",
        #         "-y90": "-y90_pulse",
        #     },
        # },
        "resonator": {
            "RF_inputs": {"port": ("octave1", 1)},
            "RF_outputs": {"port": ("octave1", 1)},
            "intermediate_frequency": resonator_IF,
            "operations": {
                "cw": "const_pulse",
                "readout": "readout_pulse",
            },
            "time_of_flight": time_of_flight,
            "smearing": 0,
            "digitalInputs": {
                "switch": {
                    "port": ("con1", 1),
                    "delay": 136,  # default value was 136
                    "buffer": 0,
                },
        },
        },
        "qubit": {
            "RF_inputs": {"port": ("octave1", 2)},
            "intermediate_frequency": qubit_IF,
            "operations": {
                "cw": "const_pulse",
                "saturation": "saturation_pulse",
                "pi": "pi_pulse",
                "pi_half": "pi_half_pulse",
                "x180": "x180_pulse",
                "x90": "x90_pulse",
                "-x90": "-x90_pulse",
                "y90": "y90_pulse",
                "y180": "y180_pulse",
                "-y90": "-y90_pulse",
            },

        },
        # "hs_qubit": {
        #     "RF_inputs": {"port": ("octave1", 5)},
        #     "intermediate_frequency": hs_qubit_IF,
        #     "operations": {
        #         "cw": "const_pulse",
        #         "saturation": "saturation_pulse",
        #         "pi": "pi_pulse",
        #         "pi_half": "pi_half_pulse",
        #         "x180": "hs_x180_pulse",
        #         "x90": "hs_x90_pulse",
        #         "dummy": "dummy_pulse",
        #     },
        # },
        # "flux_line": {
        #     "singleInput": {
        #         "port": ("con1", 5),
        #     },
        #     "operations": {
        #         "const": "const_flux_pulse",
        #     },
        # },
        # "flux_line_sticky": {
        #     "singleInput": {
        #         "port": ("con1", 5),
        #     },
        #     "sticky": {"analog": True, "duration": 20},
        #     "operations": {
        #         "const": "const_flux_pulse",
        #     },
        # },
    },
    "octaves": {
        "octave1": {
            "RF_outputs": {
                1: {
                    "LO_frequency": resonator_LO,
                    "LO_source": "internal",
                    "output_mode": "always_on",
                    "gain": resonator_LO_gain,
                },
                2: {
                    "LO_frequency": qubit_LO,
                    "LO_source": "internal",
                    "output_mode": "always_on",
                    "gain": qubit_LO_gain,
                },
            },
            "RF_inputs": {
                1: {
                    "LO_frequency": resonator_LO,
                    "LO_source": "internal",
                },
            },
            "connectivity": "con1",
        }
    },
    "pulses": {
        "const_pulse": {
            "operation": "control",
            "length": const_len,
            "waveforms": {
                "I": "const_wf",
                "Q": "zero_wf",
            },
        },
        "saturation_pulse": {
            "operation": "control",
            "length": saturation_len,
            "waveforms": {"I": "saturation_drive_wf", "Q": "zero_wf"},
        },
        "pi_pulse": {
            "operation": "control",
            "length": square_pi_len,
            "waveforms": {
                "I": "pi_wf",
                "Q": "zero_wf",
            },
        },
        "pi_half_pulse": {
            "operation": "control",
            "length": square_pi_len,
            "waveforms": {
                "I": "pi_half_wf",
                "Q": "zero_wf",
            },
        },
        "x90_pulse": {
            "operation": "control",
            "length": x90_len,
            "waveforms": {
                "I": "x90_I_wf",
                "Q": "x90_Q_wf",
            },
        },
        "x180_pulse": {
            "operation": "control",
            "length": x180_len,
            "waveforms": {
                "I": "x180_I_wf",
                "Q": "x180_Q_wf",
            },
        },
        "-x90_pulse": {
            "operation": "control",
            "length": minus_x90_len,
            "waveforms": {
                "I": "minus_x90_I_wf",
                "Q": "minus_x90_Q_wf",
            },
        },
        "y90_pulse": {
            "operation": "control",
            "length": y90_len,
            "waveforms": {
                "I": "y90_I_wf",
                "Q": "y90_Q_wf",
            },
        },
        "y180_pulse": {
            "operation": "control",
            "length": y180_len,
            "waveforms": {
                "I": "y180_I_wf",
                "Q": "y180_Q_wf",
            },
        },
        "-y90_pulse": {
            "operation": "control",
            "length": minus_y90_len,
            "waveforms": {
                "I": "minus_y90_I_wf",
                "Q": "minus_y90_Q_wf",
            },
        },
       "readout_pulse": {
            "operation": "measurement",
            "length": readout_len,
            "waveforms": {
                "I": "readout_wf",
                "Q": "zero_wf",
            },
    
            "integration_weights": {
                "cos": "cosine_weights",
                "sin": "sine_weights",
                "minus_sin": "minus_sine_weights",
                "rotated_cos": "rotated_cosine_weights",
                "rotated_sin": "rotated_sine_weights",
                "rotated_minus_sin": "rotated_minus_sine_weights",
                "opt_cos": "opt_cosine_weights",
                "opt_sin": "opt_sine_weights",
                "opt_minus_sin": "opt_minus_sine_weights",
            },
            "digital_marker": "ON",
        },
    },
    "waveforms": {
        "const_wf": {"type": "constant", "sample": const_amp},
        "saturation_drive_wf": {"type": "constant", "sample": saturation_amp},
        "pi_wf": {"type": "constant", "sample": square_pi_amp},
        "pi_half_wf": {"type": "constant", "sample": square_pi_amp / 2},
        "zero_wf": {"type": "constant", "sample": 0.0},
        "x90_I_wf": {"type": "arbitrary", "samples": x90_I_wf.tolist()},
        "x90_Q_wf": {"type": "arbitrary", "samples": x90_Q_wf.tolist()},
        "x180_I_wf": {"type": "arbitrary", "samples": x180_I_wf.tolist()},
        "x180_Q_wf": {"type": "arbitrary", "samples": x180_Q_wf.tolist()},
        "minus_x90_I_wf": {"type": "arbitrary", "samples": minus_x90_I_wf.tolist()},
        "minus_x90_Q_wf": {"type": "arbitrary", "samples": minus_x90_Q_wf.tolist()},
        "y90_Q_wf": {"type": "arbitrary", "samples": y90_Q_wf.tolist()},
        "y90_I_wf": {"type": "arbitrary", "samples": y90_I_wf.tolist()},
        "y180_Q_wf": {"type": "arbitrary", "samples": y180_Q_wf.tolist()},
        "y180_I_wf": {"type": "arbitrary", "samples": y180_I_wf.tolist()},
        "minus_y90_Q_wf": {"type": "arbitrary", "samples": minus_y90_Q_wf.tolist()},
        "minus_y90_I_wf": {"type": "arbitrary", "samples": minus_y90_I_wf.tolist()},
        "readout_wf": {"type": "constant", "sample": readout_amp},
    },
    "digital_waveforms": {
        "ON": {"samples": [(1, 0)]},
    },
    "integration_weights": {
        "cosine_weights": {
            "cosine": [(1.0, readout_len)],
            "sine": [(0.0, readout_len)],
        },
        "sine_weights": {
            "cosine": [(0.0, readout_len)],
            "sine": [(1.0, readout_len)],
        },
        "minus_sine_weights": {
            "cosine": [(0.0, readout_len)],
            "sine": [(-1.0, readout_len)],
        },
        "opt_cosine_weights": {
            "cosine": opt_weights_real,
            "sine": opt_weights_minus_imag,
        },
        "opt_sine_weights": {
            "cosine": opt_weights_imag,
            "sine": opt_weights_real,
        },
        "opt_minus_sine_weights": {
            "cosine": opt_weights_minus_imag,
            "sine": opt_weights_minus_real,
        },
        "rotated_cosine_weights": {
            "cosine": [(np.cos(rotation_angle), readout_len)],
            "sine": [(np.sin(rotation_angle), readout_len)],
        },
        "rotated_sine_weights": {
            "cosine": [(-np.sin(rotation_angle), readout_len)],
            "sine": [(np.cos(rotation_angle), readout_len)],
        },
        "rotated_minus_sine_weights": {
            "cosine": [(np.sin(rotation_angle), readout_len)],
            "sine": [(-np.cos(rotation_angle), readout_len)],
        },
    },
}
