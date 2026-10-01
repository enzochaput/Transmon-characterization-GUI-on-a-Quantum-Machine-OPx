"""
Acquisition session: saves measurements EXACTLY like the notebook.

The notebook uses the `labmate` library (AcquisitionAnalysisManager): for every
measurement it automatically creates `<experiment_name>/<timestamp>__<name>.h5` in
the data folder, stores the data, a COPY of `configuration.py` and
`calibration_db.json`, and the figure — with an automatic title
`folder\\experiment_name\\timestamp`.

This module wraps exactly that behaviour:
    session = Session()
    session.configure(data_dir, ["configuration.py", "calibration_db.json"], user="enzo")
    session.start("Resonator_spectroscopy")          # -> aqm.acquisition_cell(...)
    info = session.save(params={...}, data={...})    # -> aqm.save_acquisition(...)
    session.save_fig(fig)                            # -> aqm.save_fig(...)

If `labmate` is not installed, an equivalent fallback is used (same folders/naming,
data in .npz, configuration copied, figure as .png) so that the application still
works — install `labmate` for files strictly identical to the notebook.

Every measurement also stores the full parameter snapshot used for the run (form +
global parameters), so a data file is self-describing even when the GUI values
differ from configuration.py. The latest global parameters are kept in
<data folder>/calibration_params.json and reloaded with the session.
"""

from __future__ import annotations
import os
import json
import time
import shutil
from dataclasses import dataclass
from pathlib import Path

try:
    from labmate.acquisition_notebook import AcquisitionAnalysisManager
    HAS_LABMATE = True
except Exception:
    HAS_LABMATE = False


@dataclass
class SaveInfo:
    directory: str
    experiment_name: str
    time_stamp: str

    @property
    def title(self) -> str:
        # Title format taken from the notebook: folder\name\timestamp
        return f"{self.directory}\\{self.experiment_name}\\{self.time_stamp}"


class Session:
    def __init__(self):
        self.aqm = None
        self.data_dir = None
        self.config_files = []
        self.user = ""
        self._project_dir = Path(__file__).resolve().parent

    # -------------------------------------------------------------- configuration
    @property
    def is_ready(self) -> bool:
        return self.data_dir is not None

    @property
    def backend_name(self) -> str:
        if not self.is_ready:
            return "not defined"
        return "labmate" if HAS_LABMATE else "fallback (labmate not installed)"

    def default_config_files(self):
        """configuration.py and calibration_db.json shipped with the project."""
        files = []
        for name in ("configuration.py", "calibration_db.json"):
            p = self._project_dir / name
            if p.exists():
                files.append(str(p))
        return files

    def configure(self, data_dir: str, config_files=None, user: str = ""):
        data_dir = os.path.expanduser(str(data_dir).strip())
        os.makedirs(data_dir, exist_ok=True)
        self.data_dir = data_dir
        self.user = user.strip()
        self.config_files = list(config_files) if config_files else self.default_config_files()

        if HAS_LABMATE:
            # shell=None: pure Python context (outside IPython), as in PyCharm
            self.aqm = AcquisitionAnalysisManager(data_dir, shell=None)
            if self.config_files:
                self.aqm.set_config_file(self.config_files)
        else:
            self.aqm = None
        return self.is_ready

    # ---------------------------------------------------------------- acquisition
    def start(self, experiment_name: str, description: str = ""):
        """Start a new acquisition (≙ aqm.acquisition_cell(name))."""
        if not self.is_ready:
            return
        if HAS_LABMATE and self.aqm is not None:
            # 'cell' provides cell content -> avoids the warning outside IPython
            self.aqm.acquisition_cell(experiment_name, cell=description or experiment_name)
        else:
            self._fallback_start(experiment_name)

    def save(self, params: dict, data: dict, extra: dict | None = None) -> SaveInfo | None:
        """Save the data (≙ aqm.save_acquisition(...))."""
        if not self.is_ready:
            return None
        kwds = dict(params)
        kwds.update(data)
        kwds.update(extra or {})
        if self.user:
            kwds["user"] = self.user

        if HAS_LABMATE and self.aqm is not None:
            self.aqm.save_acquisition(**kwds)
            tmp = self.aqm.acquisition_tmp_data
            return SaveInfo(str(tmp.directory), str(tmp.experiment_name), str(tmp.time_stamp))
        return self._fallback_save(kwds)

    # -- persistence of the calibrated parameters (cascade) -----------------------
    def params_path(self):
        if not self.is_ready:
            return None
        return os.path.join(self.data_dir, "calibration_params.json")

    def save_params(self, values: dict):
        """Save the current global parameters (latest calibration)."""
        path = self.params_path()
        if path is None:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(values, f, indent=2)
        except Exception:
            pass

    def load_params(self):
        """Reload the calibrated parameters of the session, or None."""
        path = self.params_path()
        if path is None or not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def save_fig(self, fig):
        """Save the figure next to the data (≙ aqm.save_fig(fig))."""
        if not self.is_ready:
            return
        if HAS_LABMATE and self.aqm is not None:
            try:
                # the GUI figure already uses a constrained layout
                self.aqm.save_fig(fig, tight_layout=False)
            except TypeError:          # older labmate without the keyword
                try:
                    self.aqm.save_fig(fig)
                except Exception:
                    pass
            except Exception:
                pass
        else:
            self._fallback_save_fig(fig)

    # ------------------------------------------------------------------- fallback --
    # (used only when labmate is not installed)
    def _fallback_start(self, experiment_name):
        self._fb_name = experiment_name
        self._fb_ts = time.strftime("%Y_%m_%d__%H_%M_%S")
        self._fb_dir = Path(self.data_dir) / experiment_name
        self._fb_dir.mkdir(parents=True, exist_ok=True)

    def _fallback_save(self, kwds):
        import numpy as np
        base = f"{self._fb_ts}__{self._fb_name}"
        arrays = {}
        for k, v in kwds.items():
            if isinstance(v, dict):
                arrays[k] = np.asarray(json.dumps(v))
            else:
                arrays[k] = np.asarray(v)
        np.savez(self._fb_dir / (base + ".npz"), **arrays)
        # copy of the configuration files (like labmate's 'configs' group)
        cfg_dir = self._fb_dir / (base + "_configs")
        cfg_dir.mkdir(exist_ok=True)
        for f in self.config_files:
            try:
                shutil.copy(f, cfg_dir / Path(f).name)
            except Exception:
                pass
        self._fb_base = base
        return SaveInfo(str(self.data_dir), self._fb_name, self._fb_ts)

    def _fallback_save_fig(self, fig):
        try:
            fig.savefig(self._fb_dir / (self._fb_base + "_FIG.png"), dpi=120)
        except Exception:
            pass
