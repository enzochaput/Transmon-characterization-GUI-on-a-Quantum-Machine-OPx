
# Qubit characterization GUI (OPX + Octave)

PyQt6 interface that runs a superconducting-qubit characterization workflow on a Quantum Machines OPX + Octave, with automatic extraction of the results
and a calibration cascade.



<img width="1468" height="926" alt="Capture d’écran 2026-10-01 à 15 55 23" src="https://github.com/user-attachments/assets/eb4b2ce2-6242-435b-ae1e-067ab6d26385" />


## Getting started

Before the first measurement, open the Connection window (button in the top bar) and
enter the address of the QOP server, the cluster name (or the port on QOP versions older
than 2.2), and the Octave address. The default values are the ones from
`configuration.py`, and whatever you enter is saved in `~/.qubit_gui/connection.json`.
"Test connection" checks that the server answers; if you skip it, the first measurement
connects on its own.

Then fill in your name and the data folder, click "Set session", pick an experiment,
adjust the parameters and run it.

## What happens during a run

Before anything is sent to the OPX, the parameters are checked against the hardware
limits: amplitudes below 0.5 V (including amplitude × prefactor), prefactors in [-2, 2),
IFs within ±400 MHz, pulse lengths that are multiples of 4 ns and at least 16 ns, and a
time of flight of at least 24 ns. If something is off, you get a message and nothing
runs.

The QUA configuration is rebuilt for every run from the global parameters and the
values in the form (see `qm_config.py`, which follows the structure of
`configuration.py`). A Quantum Machine is opened with this configuration and the
program of the experiment is executed. Results are fetched while the program runs, so
the plot updates as averages accumulate, and the Stop button halts the job.

When the run finishes, the data are fitted automatically. The extracted values come
with their uncertainty and can be written back to the global parameters with the yellow
buttons. The HDF5 file contains the raw data, all the parameters, the extracted values
and the exact QUA configuration that was used (`qua_config_json`).

Only one measurement can run at a time.

## QUA programs

The programs are based on the qua-libs examples for a single fixed-frequency transmon
with an Octave. The averaging loop is the outermost loop, averaging is done in the
stream processing, and results are fetched live. Spectroscopy measurements return |IQ|,
measurements of the qubit state return the I quadrature with the rotated integration
weights, and the time-of-flight measurement returns the raw ADC traces. It is run with
`time_of_flight = 24 ns`, so the time axis gives the absolute delay.

| Experiment | Sequence |
|---|---|
| Time of flight | `reset_phase`, then `measure` with an ADC stream |
| Resonator spectroscopy, vs power | sweep of the resonator frequency (and of the readout amplitude) |
| Qubit spectroscopy, QM variant, vs power | sweep of the qubit frequency with a saturation pulse (and its amplitude) |
| Rabi chevrons | frequency sweep with `x180` scaled in amplitude or stretched in duration |
| Time Rabi / Power Rabi | `x180` with a variable duration / a variable amplitude |
| T1, T1 histogram | `x180`, wait τ, measure (the histogram repeats the run and fits each one) |
| Ramsey chevron | frequency sweep, `x90` – τ – `x90` |
| Ramsey (virtual Z) | `x90` – τ – frame rotation by detuning·τ – `x90` |
| Hahn echo | `x90` – τ – `x180` – τ – `-x90` |
| IQ blobs | single shots with the qubit in g, then after an `x180` |
| Readout frequency | for each frequency, one measurement in g and one in e |
| Mixer calibration | `calibrate_element()` on the resonator and the qubit |

## Code layout

- `connection.py`, `connection_dialog.py`: connection settings and the QuantumMachinesManager
- `qm_config.py`: builds the QUA configuration from the GUI parameters
- `qua_programs.py`: the QUA program of each experiment and the live fetching
- `backend.py`: checks the parameters, opens the Quantum Machine and runs the program
- `experiments.py`: list of experiments and their parameters
- `analysis.py`, `fitting.py`: fits and extraction of the results
- `param_store.py`, `params_dialog.py`: global parameters
- `main_window.py`, `experiment_panel.py`, `glossary_panel.py`, `mpl_canvas.py`: interface
- `session.py`: saving with labmate

The `tests/` folder is not used by the application. `test_programs.py` builds the
configuration and the program of every experiment and validates them with the QM SDK,
without hardware. `test_extraction.py` checks the fits on synthetic data whose
parameters are known.
If you change the structure of `configuration.py` (elements, ports, pulses), mirror it in
`qm_config.py`.
<img width="1470" height="923" alt="Capture d’écran 2026-10-01 à 15 55 56" src="https://github.com/user-attachments/assets/7bfb311c-03b4-458c-b46e-26dce3a547cf" />


