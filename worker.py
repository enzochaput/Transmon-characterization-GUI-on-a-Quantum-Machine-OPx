"""
Acquisition worker running in a QThread, and the global run lock.

The worker iterates over the backend generator (frame by frame), throttles it a
little to give the "live" effect, and forwards every frame to the interface through
Qt signals. The interface stays responsive (Stop button usable) during acquisition.

RunLock: the OPX runs one program at a time, so only one acquisition may run at once
across all experiment panels.
"""

from __future__ import annotations
import time
from PyQt6.QtCore import QObject, pyqtSignal


class AcquisitionWorker(QObject):
    frame = pyqtSignal(dict)       # one data frame (see backend.py)
    progress = pyqtSignal(int)     # 0..100
    finished = pyqtSignal(bool)    # True = completed, False = stopped or failed
    error = pyqtSignal(str)        # error message

    def __init__(self, backend, experiment, ctx, frame_delay=0.04):
        super().__init__()
        self.backend = backend
        self.experiment = experiment
        self.ctx = ctx
        self.frame_delay = frame_delay
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        gen = None
        completed = False
        try:
            gen = self.backend.run(self.experiment, self.ctx)
            last = 0
            for fr in gen:
                if self._stop:
                    break
                last = int(fr.get("progress", 0))
                self.progress.emit(last)
                self.frame.emit(fr)
                if self.frame_delay:
                    time.sleep(self.frame_delay)
            completed = (not self._stop) and last >= 100
        except Exception as exc:  # noqa: BLE001 - reported cleanly to the UI
            self.error.emit(f"{type(exc).__name__}: {exc}")
        finally:
            if gen is not None:
                try:
                    gen.close()
                except Exception:
                    pass
            self.finished.emit(completed)


class RunLock(QObject):
    """Allows a single acquisition at a time (one OPX program)."""
    busy_changed = pyqtSignal(bool, str)   # (busy, experiment name)

    def __init__(self):
        super().__init__()
        self.owner = None
        self.name = ""

    @property
    def busy(self) -> bool:
        return self.owner is not None

    def acquire(self, owner, name) -> bool:
        if self.owner is not None and self.owner is not owner:
            return False
        self.owner, self.name = owner, name
        self.busy_changed.emit(True, name)
        return True

    def release(self, owner):
        if self.owner is owner:
            self.owner, self.name = None, ""
            self.busy_changed.emit(False, "")
