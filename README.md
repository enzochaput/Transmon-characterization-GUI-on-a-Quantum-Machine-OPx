<img width="1468" height="926" alt="Capture d’écran 2026-10-01 à 15 55 23" src="https://github.com/user-attachments/assets/2180fd3e-e56f-4eea-a275-7b0cc7a06a38" />
# Qubit characterization GUI (OPX + Octave)

PyQt6 interface that runs a superconducting-qubit characterization workflow on a Quantum Machines OPX + Octave, with automatic extraction of the results
and a calibration cascade.

```bash
pip install PyQt6 numpy scipy matplotlib qm-qua qualang-tools labmate   # scipy, labmate optional
python main.py
```

## First start

1. **🔌 Connection** (top bar): QOP host/IP, cluster name (QOP ≥ 2.2) or port (older QOP),
   Octave name/IP/port and the folder of `calibration_db.json`. Defaults come from
   `configuration.py`; the settings are saved in `~/.qubit_gui/connection.json`.
   **Test connection** opens a `QuantumMachinesManager` and shows the server versions.
   Without a test, the first measurement connects automatically.
2. Enter the user and the data folder, then **Set session** (saving via `labmate`).
3. Pick an experiment, set the parameters and **Run**.

## What happens when you press Run

1. The parameters are checked against the hardware limits before anything is sent
   (pulse amplitudes and prefactor × amplitude < 0.5 V, prefactors in [-2, 2),
   IF within ±400 MHz, lengths multiple of 4 ns and ≥ 16 ns, ToF ≥ 24 ns…).
2. The QUA configuration is **built from the global parameters + the form**
   (`qm_config.py`, same structure as `configuration.py`), a Quantum Machine is opened
   with it and the QUA program of the experiment is executed (`qua_programs.py`).
3. Results are fetched live (running averages + progress); **Stop** halts the job.
4. At the end the data are fitted automatically (red curve, values ± 1σ, quality flag);
   the yellow buttons write the extracted values to the global parameters.
5. The data, every parameter, the extracted values and the full QUA configuration used
   (`qua_config_json`) are saved in the HDF5 file.

Only one acquisition runs at a time.

## Programs

The QUA programs follow the standard qua-libs scripts (single fixed-frequency transmon,
Octave): averaging loop outermost, `stream_processing` averages, live fetching.
Spectroscopies return |IQ| (V), qubit-state measurements the I quadrature demodulated
with the rotated weights (V), Time of flight the raw ADC traces (acquired with
`time_of_flight = 24 ns`, so the time axis is the absolute delay).

| Experiment | Sequence |
|---|---|
| Time of flight | `reset_phase` + `measure` with ADC stream |
| Resonator 1-tone / vs power | `update_frequency(resonator)` (+ `readout*amp(a)`) + measure |
| Qubit 2-tone / QM variant / vs power | `update_frequency(qubit)`, `saturation` (×amp) , measure |
| Rabi chevrons | `update_frequency` + `x180*amp(a)` or `x180` with `duration=t` |
| Time / Power Rabi | `x180` with `duration=t` / `x180*amp(a)` |
| T1 (+ histogram) | `x180` – wait τ – measure (histogram: repeated runs, one fit each) |
| Ramsey chevron | `update_frequency`, `x90` – τ – `x90` |
| Ramsey virtual Z | `x90` – τ – `frame_rotation_2pi(detuning·τ)` – `x90` |
| Hahn echo | `x90` – τ – `x180` – τ – `-x90` |
| IQ blobs | single shots in g, then after `x180` |
| Readout frequency | per frequency: measure g, `x180`, measure e |
| Mixer calibration | `qm.calibrate_element()` for resonator and qubit |

## Files

| File | Role |
|---|---|
| `connection.py`, `connection_dialog.py` | QM connection settings, QuantumMachinesManager |
| `qm_config.py` | QUA configuration built from the GUI parameters |
| `qua_programs.py` | QUA program of every experiment + live fetching |
| `backend.py` | `QuaBackend`: check → open QM → run → frames |
| `experiments.py` | experiment registry and parameter schemas |
| `analysis.py`, `fitting.py` | automatic extraction |
| `param_store.py`, `params_dialog.py` | global parameters |
| `main_window.py`, `experiment_panel.py`, `glossary_panel.py`, `mpl_canvas.py` | GUI |
| `session.py` | labmate saving |
| `tests/` | offline checks only (never used by the application) |

`tests/test_programs.py` builds and validates the config + program of every experiment
with the QM SDK (no hardware). `tests/test_extraction.py` checks the fits on synthetic
data with known values.

If you change the structure of `configuration.py` (elements, ports, pulses), mirror it in
`qm_config.py`.
