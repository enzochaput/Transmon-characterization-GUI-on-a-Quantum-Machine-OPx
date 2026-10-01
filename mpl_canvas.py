"""
Matplotlib canvas embedded in Qt + plotting logic for every plot type.

Live updates reuse the existing artists (set_data / set_array) instead of rebuilding
the figure for every frame, which keeps the GUI fluid on large 2D maps.
"""

from __future__ import annotations
import numpy as np

import matplotlib
matplotlib.use("QtAgg")  # Qt backend (PyQt6 compatible)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from matplotlib.figure import Figure

from fitting import hist_bins

BLUE = "#2b6cb0"
ORANGE = "#dd6b20"
RED = "#e53e3e"


def _edges(v, log=False):
    """Cell edges for pcolormesh from cell centres (geometric midpoints if log)."""
    v = np.asarray(v, float)
    if len(v) == 1:
        d = abs(v[0]) * 0.1 or 0.5
        return np.array([v[0] - d, v[0] + d])
    if log and np.all(v > 0):
        lv = np.log(v)
        mid = 0.5 * (lv[1:] + lv[:-1])
        e = np.concatenate([[lv[0] - (mid[0] - lv[0])], mid, [lv[-1] + (lv[-1] - mid[-1])]])
        return np.exp(e)
    mid = 0.5 * (v[1:] + v[:-1])
    return np.concatenate([[v[0] - (mid[0] - v[0])], mid, [v[-1] + (v[-1] - mid[-1])]])


class MplCanvas(FigureCanvasQTAgg):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(5, 4), layout="constrained")
        super().__init__(self.fig)
        self.setParent(parent)
        self.ax = None
        self.ax_aux = None
        self._art = {}
        self._live = None
        self.show_placeholder("Select an experiment and press “Run”")

    # -- utilities ---------------------------------------------------------------
    def _reset(self, exp=None, two_panels=False):
        self.fig.clear()
        self._art = {}
        self.ax_aux = None
        if two_panels:
            self.ax_aux, self.ax = self.fig.subplots(1, 2, gridspec_kw={"width_ratios": [1, 1.2]})
        else:
            self.ax = self.fig.add_subplot(111)
        if exp is not None:
            self.ax.set_xlabel(exp.xlabel)
            self.ax.set_ylabel(exp.ylabel)
            if two_panels:
                self.fig.suptitle(exp.name)
            else:
                self.ax.set_title(exp.name)
            self.ax.grid(True, alpha=0.25)

    def show_placeholder(self, text):
        self._live = None
        self._reset()
        self.ax.text(0.5, 0.5, text, ha="center", va="center",
                     transform=self.ax.transAxes, color="#888", fontsize=11)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        for s in self.ax.spines.values():
            s.set_visible(False)
        self.draw_idle()

    def stamp(self, exp, text):
        """Notebook-style title (folder\\name\\timestamp) added when the data are saved."""
        if self.ax_aux is not None:
            self.fig.suptitle(f"{exp.name}\n{text}", fontsize=8, wrap=True)
        else:
            self.fig.suptitle(text, fontsize=7, wrap=True)
        self.draw()

    def begin(self):
        """Call at the start of a run: the next frame rebuilds the figure."""
        self._live = None

    # -- frame plotting ----------------------------------------------------------
    def plot_frame(self, exp, fr):
        kind = fr.get("kind")
        fresh = self._live != (exp.id, kind)
        fn = {"line": self._plot_line, "trace": self._plot_trace, "map2d": self._plot_map,
              "hist": self._plot_hist, "iq": self._plot_iq}.get(kind)
        if fn is None:
            return
        fn(exp, fr, fresh)
        self._live = (exp.id, kind)
        self.draw_idle()

    def _plot_line(self, exp, fr, fresh):
        x, y = fr["x"], fr["y"]
        if fresh:
            self._reset(exp)
            (self._art["line"],) = self.ax.plot(x, y, "-", color=BLUE, lw=1.2,
                                                marker=".", ms=3, label="data")
        else:
            self._art["line"].set_data(x, y)
            self.ax.relim()
            self.ax.autoscale_view()

    def _plot_trace(self, exp, fr, fresh):
        if fresh:
            self._reset(exp)
            (self._art["I"],) = self.ax.plot(fr["x"], fr["I"], color=BLUE, lw=0.9, label="I")
            (self._art["Q"],) = self.ax.plot(fr["x"], fr["Q"], color=ORANGE, lw=0.9, label="Q")
            self.ax.legend(loc="upper right", fontsize=8)
        else:
            self._art["I"].set_data(fr["x"], fr["I"])
            self._art["Q"].set_data(fr["x"], fr["Q"])
            self.ax.relim()
            self.ax.autoscale_view()

    def _plot_map(self, exp, fr, fresh):
        x, y = np.asarray(fr["x"], float), np.asarray(fr["y"], float)
        z = np.ma.masked_invalid(np.asarray(fr["z"], float))
        if fresh:
            self._reset(exp)
            mesh = self.ax.pcolormesh(_edges(x), _edges(y, exp.ylog), z,
                                      shading="flat", cmap="viridis", rasterized=True)
            if exp.ylog:
                self.ax.set_yscale("log")
            self.ax.grid(False)
            cbar = self.fig.colorbar(mesh, ax=self.ax)
            cbar.set_label("Signal (a.u.)")
            self._art["mesh"] = mesh
        else:
            self._art["mesh"].set_array(z)
        if z.count():
            # robust colour scale: a few noisy pixels must not wash out the map
            lo, hi = np.percentile(z.compressed(), [1, 99])
            if hi > lo:
                self._art["mesh"].set_clim(float(lo), float(hi))

    def _plot_hist(self, exp, fr, fresh):
        self._reset(exp, two_panels=True)
        s = np.asarray(fr["samples"], float)
        a = self.ax_aux
        a.set_xlabel("Repetition")
        a.set_ylabel("Fitted T1 (µs)")
        a.grid(True, alpha=0.25)
        if len(s):
            a.plot(np.arange(1, len(s) + 1), s, "o-", color=BLUE, ms=3, lw=0.8)
            self.ax.hist(s, bins=hist_bins(len(s)), color=BLUE, alpha=0.85,
                         edgecolor="white", label="fitted T1")

    def _plot_iq(self, exp, fr, fresh):
        g = np.c_[fr["gI"], fr["gQ"]]
        e = np.c_[fr["eI"], fr["eQ"]]
        if fresh:
            self._reset(exp)
            self._art["g"] = self.ax.scatter(g[:, 0], g[:, 1], s=4, alpha=0.3,
                                             color="#3182ce", label="|0> prepared")
            self._art["e"] = self.ax.scatter(e[:, 0], e[:, 1], s=4, alpha=0.3,
                                             color=RED, label="|1> prepared")
            self.ax.set_aspect("equal", adjustable="datalim")
            self.ax.legend(loc="upper right", fontsize=8, markerscale=3)
        else:
            self._art["g"].set_offsets(g)
            self._art["e"].set_offsets(e)
        self.ax.ignore_existing_data_limits = True
        self.ax.update_datalim(np.vstack([g, e]))
        self.ax.autoscale_view()

    # -- analysis overlay --------------------------------------------------------
    def overlay(self, res):
        """Draw the fit (red), markers, extra lines and points on the current plot."""
        if self.ax is None or res is None:
            return
        ax = self.ax
        if res.fit is not None:
            ax.plot(res.fit[0], res.fit[1], "-", color=RED, lw=1.8, label="fit", zorder=6)
        for xv in res.vlines:
            if np.isfinite(xv):
                ax.axvline(xv, color=RED, ls="--", lw=1.0, zorder=5)
        for yv in res.hlines:
            if np.isfinite(yv):
                ax.axhline(yv, color=RED, ls="--", lw=1.0, zorder=5)
        for xs, ys, kw in res.lines:
            ax.plot(xs, ys, zorder=6, **kw)
        for px, py in res.points:
            ax.plot(px, py, marker="X", ms=11, color="#1a202c", mec="white", mew=1.2, zorder=7)
        handles, labels = ax.get_legend_handles_labels()
        if labels:
            ax.legend(loc="best", fontsize=8)
        self.draw_idle()


def make_toolbar(canvas, parent):
    return NavigationToolbar2QT(canvas, parent)
