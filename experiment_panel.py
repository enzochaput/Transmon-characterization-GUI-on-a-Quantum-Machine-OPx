"""
Generic experiment panel.

Builds the form AUTOMATICALLY from the experiment's parameter schema
(experiments.py): one row per ParamSpec, with unit and explanatory tooltip.
Handles running/stopping the acquisition (in a thread), the progress bar, the live
plot, the automatic extraction (fit + extracted values + write-back buttons for the
calibration cascade), saving, and a log.
"""

from __future__ import annotations
import html
from collections import OrderedDict

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QLabel,
    QDoubleSpinBox, QSpinBox, QPushButton, QProgressBar, QPlainTextEdit,
    QScrollArea, QSizePolicy, QSplitter,
)

from mpl_canvas import MplCanvas, make_toolbar
from worker import AcquisitionWorker
from backend import frame_to_save_data

QUALITY_STYLE = {
    "good": ("#22543d", "#f0fff4", "#9ae6b4", "fit OK"),
    "uncertain": ("#7b341e", "#fffaf0", "#fbd38d", "check the fit"),
    "failed": ("#742a2a", "#fff5f5", "#feb2b2", "extraction failed"),
}

WB_STYLE = {
    "good": ("QPushButton{background:#ecc94b;color:#1a202c;padding:5px 10px;"
             "border-radius:5px;text-align:left;}"
             "QPushButton:hover{background:#d69e2e;}"
             "QPushButton:disabled{background:#c6f6d5;color:#22543d;}"),
    "uncertain": ("QPushButton{background:#fbd38d;color:#7b341e;padding:5px 10px;"
                  "border-radius:5px;text-align:left;}"
                  "QPushButton:hover{background:#f6ad55;}"
                  "QPushButton:disabled{background:#c6f6d5;color:#22543d;}"),
}


def make_spinbox(spec):
    """Spin box configured from a ParamSpec (shared with the global-parameters window)."""
    if spec.ptype == "int":
        w = QSpinBox()
        w.setRange(int(spec.minimum if spec.minimum is not None else -2**31),
                   int(spec.maximum if spec.maximum is not None else 2**31 - 1))
        if spec.step:
            w.setSingleStep(int(spec.step))
    else:
        w = QDoubleSpinBox()
        w.setDecimals(spec.decimals)
        w.setRange(spec.minimum if spec.minimum is not None else -1e12,
                   spec.maximum if spec.maximum is not None else 1e12)
        if spec.step:
            w.setSingleStep(spec.step)
    w.setKeyboardTracking(False)      # emit valueChanged on Enter / focus-out, not per key
    w.setMinimumWidth(105)
    w.setValue(spec.coerce(spec.default))
    return w


class ExperimentPanel(QWidget):
    def __init__(self, experiment, backend, session=None, store=None, lock=None, parent=None):
        super().__init__(parent)
        self.exp = experiment
        self.backend = backend
        self.session = session
        self.store = store
        self.lock = lock
        self.widgets = OrderedDict()   # key -> (spec, widget)
        self.thread = None
        self.worker = None
        self.last_frame = None
        self.last_result = None
        self._run_ctx = {}
        self._syncing = False
        self._wb_buttons = []
        self._build()
        self._wire_store()
        if self.lock is not None:
            self.lock.busy_changed.connect(self._on_lock_changed)
            self._on_lock_changed(self.lock.busy, self.lock.name)

    # ------------------------------------------------------------------ UI --------
    def _build(self):
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # ---- Left column: description + form + controls -------------------------
        left = QWidget()
        lyt = QVBoxLayout(left)
        lyt.setContentsMargins(12, 12, 12, 12)

        title = QLabel(self.exp.name)
        f = QFont()
        f.setPointSize(14)
        f.setBold(True)
        title.setFont(f)
        title.setWordWrap(True)
        lyt.addWidget(title)

        cat = QLabel(f"Category: {self.exp.category}")
        cat.setStyleSheet("color:#666;")
        lyt.addWidget(cat)

        desc = QLabel(self.exp.description)
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#333; background:#f5f7fa; padding:8px; border-radius:6px;")
        lyt.addWidget(desc)

        if self.exp.outputs:
            out = QLabel("➜ What you get: " + self.exp.outputs)
            out.setWordWrap(True)
            out.setStyleSheet("color:#2b6cb0; font-style:italic;")
            lyt.addWidget(out)

        # Grouped form
        form_host = self._build_form()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_host)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        lyt.addWidget(scroll, 1)

        # Buttons + progress
        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("▶  Run")
        self.btn_run.setStyleSheet(
            "QPushButton{background:#2b6cb0;color:white;padding:8px 16px;"
            "border-radius:6px;font-weight:bold;}"
            "QPushButton:hover{background:#2c5282;}"
            "QPushButton:disabled{background:#a0aec0;}")
        self.btn_stop = QPushButton("■  Stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet(
            "QPushButton{background:#e53e3e;color:white;padding:8px 16px;border-radius:6px;}"
            "QPushButton:disabled{background:#ccc;}")
        self.btn_defaults = QPushButton("↺ Defaults")
        self.btn_defaults.setToolTip("Reset the sweep parameters of this measurement to their "
                                     "defaults (global parameters are not touched).")
        self.btn_defaults.setEnabled(bool(self.exp.params))
        self.btn_run.clicked.connect(self.start)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_defaults.clicked.connect(self._reset_local_defaults)
        btn_row.addWidget(self.btn_run)
        btn_row.addWidget(self.btn_stop)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_defaults)
        lyt.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        lyt.addWidget(self.progress)

        self.results = QLabel("")
        self.results.setWordWrap(True)
        self.results.setTextFormat(Qt.TextFormat.RichText)
        self.results.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.results.setVisible(False)
        lyt.addWidget(self.results)

        # "Write to config" buttons (calibration cascade)
        self.wb_container = QWidget()
        self.wb_layout = QVBoxLayout(self.wb_container)
        self.wb_layout.setContentsMargins(0, 0, 0, 0)
        self.wb_layout.setSpacing(4)
        self.wb_container.setVisible(False)
        lyt.addWidget(self.wb_container)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(110)
        self.log.setPlaceholderText("Log…")
        lyt.addWidget(self.log)

        left.setMaximumWidth(440)
        splitter.addWidget(left)

        # ---- Right column: plot -------------------------------------------------
        right = QWidget()
        rlyt = QVBoxLayout(right)
        rlyt.setContentsMargins(6, 6, 6, 6)
        self.canvas = MplCanvas(right)
        rlyt.addWidget(make_toolbar(self.canvas, right))
        rlyt.addWidget(self.canvas, 1)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([430, 760])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

        if self.exp.plot == "action":
            self.canvas.show_placeholder("One-shot action — see the log on the left")

    def _build_form(self):
        host = QWidget()
        vbox = QVBoxLayout(host)
        vbox.setContentsMargins(0, 0, 0, 0)

        if not self.exp.params:
            lbl = QLabel("No parameter to set for this action. It uses the global LO/IF "
                         "values (⚙ Global parameters).")
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color:#666; padding:8px;")
            vbox.addWidget(lbl)
            vbox.addStretch(1)
            return host

        groups = OrderedDict()
        for spec in self.exp.params:
            groups.setdefault(spec.group, []).append(spec)

        for gname, specs in groups.items():
            box = QGroupBox(gname)
            form = QFormLayout(box)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            for spec in specs:
                w = make_spinbox(spec)
                self.widgets[spec.key] = (spec, w)
                is_global = self.store is not None and self.store.has(spec.key)
                txt = spec.label + (f"  [{spec.unit}]" if spec.unit else "")
                label = QLabel(("● " if is_global else "") + txt)
                tip = spec.help + ("\n\n● Global parameter: shared by every measurement."
                                   if is_global else "")
                label.setToolTip(tip)
                w.setToolTip(tip)
                form.addRow(label, w)
            vbox.addWidget(box)

        if any(self.store is not None and self.store.has(k) for k in self.widgets):
            hint = QLabel("● = global parameter (shared by every measurement)")
            hint.setStyleSheet("color:#718096; font-size:11px;")
            vbox.addWidget(hint)
        vbox.addStretch(1)
        return host

    # ---- store synchronisation ------------------------------------------------
    def _wire_store(self):
        """Bind this panel's global parameters to the shared store: initial value from
        the store + two-way synchronisation."""
        if self.store is None:
            return
        for key, (spec, w) in self.widgets.items():
            if self.store.has(key):
                self._syncing = True
                w.setValue(spec.coerce(self.store.get(key)))
                self._syncing = False
                w.valueChanged.connect(lambda val, k=key: self._on_widget_changed(k, val))
        self.store.changed.connect(self._on_store_changed)

    def _on_widget_changed(self, key, val):
        if self._syncing:
            return
        if self.store is not None and self.store.has(key):
            self.store.set(key, val)

    def _on_store_changed(self, key, val):
        if key in self.widgets:
            spec, w = self.widgets[key]
            self._syncing = True
            w.setValue(spec.coerce(val))
            self._syncing = False

    def _reset_local_defaults(self):
        for key, (spec, w) in self.widgets.items():
            if self.store is None or not self.store.has(key):
                w.setValue(spec.coerce(spec.default))

    def _collect_values(self):
        return {key: spec.coerce(w.value()) for key, (spec, w) in self.widgets.items()}

    def _context(self):
        """Snapshot of every parameter: global store + this form (form wins)."""
        ctx = dict(self.store.to_dict()) if self.store is not None else {}
        ctx.update(self._collect_values())
        return ctx

    def _on_lock_changed(self, busy, name):
        mine = self.thread is not None
        self.btn_run.setEnabled(not busy or mine)
        if busy and not mine:
            self.btn_run.setToolTip(f"“{name}” is running — one acquisition at a time.")
        else:
            self.btn_run.setToolTip("")

    # ------------------------------------------------------------ Acquisition -----
    def start(self):
        if self.thread is not None:
            return
        if self.lock is not None and not self.lock.acquire(self, self.exp.name):
            self.log.appendPlainText(f"“{self.lock.name}” is already running.")
            return
        values = self._collect_values()
        self._run_ctx = self._context()
        self.last_frame = None
        self.last_result = None
        self.log.clear()
        self.log.appendPlainText(f"[{getattr(self.backend, 'name', 'backend')}] "
                                 f"Starting “{self.exp.name}”")
        params_txt = ", ".join(f"{k}={v}" for k, v in values.items())
        if values:
            self.log.appendPlainText("Parameters: " + params_txt)

        # Open the acquisition in the session (≙ aqm.acquisition_cell)
        if self.exp.plot == "action":
            pass                                   # nothing to save for one-shot actions
        elif self.session is not None and self.session.is_ready:
            try:
                self.session.start(self.exp.save_name, description=params_txt)
                self.log.appendPlainText(
                    f"Acquisition opened (user: {self.session.user or '—'})")
            except Exception as exc:
                self.log.appendPlainText(f"[session] cannot start: {exc}")
        else:
            self.log.appendPlainText("No session defined → the measurement will not be saved.")

        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        self.results.setVisible(False)
        self._clear_writebacks()
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        if self.exp.plot != "action":
            self.canvas.begin()

        self.thread = QThread()
        self.worker = AcquisitionWorker(self.backend, self.exp, self._run_ctx)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.frame.connect(self._on_frame)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self._on_finished)
        self.thread.start()

    def stop(self):
        if self.worker is not None:
            self.worker.stop()
            self.log.appendPlainText("Stop requested…")

    def shutdown(self):
        """Stop and join the acquisition thread (window closing)."""
        if self.worker is not None:
            self.worker.stop()
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(3000)

    def _on_frame(self, fr):
        self.last_frame = fr
        if "n_done" in fr and "n_total" in fr:
            unit = "shots" if fr.get("kind") == "iq" else (
                "repetitions" if fr.get("kind") == "hist" else "averages")
            self.progress.setFormat(f"%p%   ·   {fr['n_done']}/{fr['n_total']} {unit}")
        if fr.get("kind") == "action":
            self.log.setPlainText(fr.get("log", ""))
        else:
            self.canvas.plot_frame(self.exp, fr)

    def _on_error(self, msg):
        self.log.appendPlainText("ERROR: " + msg)

    def _on_finished(self, completed):
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait()
        self.thread = None
        self.worker = None
        self.btn_stop.setEnabled(False)
        if self.lock is not None:
            self.lock.release(self)
        else:
            self.btn_run.setEnabled(True)
        if completed:
            self.log.appendPlainText("Done ✓")
            self._extract_and_show()
            self._save_measurement()
        else:
            self.log.appendPlainText("Interrupted — data not saved.")

    # ---- automatic extraction -------------------------------------------------
    def _extract_and_show(self):
        """Extract the quantities of interest, overlay the fit and show the values."""
        if self.last_frame is None or self.exp.plot == "action":
            return
        from analysis import analyze
        res = analyze(self.exp, self.last_frame, self._run_ctx)
        self.last_result = res
        self.canvas.overlay(res)
        if res.results or res.notes:
            self.results.setText(self._results_html(res))
            fg, bg, border, _ = QUALITY_STYLE.get(res.quality, QUALITY_STYLE["good"])
            self.results.setStyleSheet(
                f"color:{fg}; background:{bg}; border:1px solid {border};"
                "border-radius:6px; padding:8px;")
            self.results.setVisible(True)
        for lab, val in res.results:
            self.log.appendPlainText(f"  {lab}: {val}")
        if res.quality != "failed":
            self._show_writebacks(res.writebacks, res.quality)

    @staticmethod
    def _results_html(res):
        fg, _, _, badge = QUALITY_STYLE.get(res.quality, QUALITY_STYLE["good"])
        rows = "".join(
            f"<tr><td style='padding-right:10px'>{html.escape(k)}</td>"
            f"<td><b>{html.escape(v)}</b></td></tr>" for k, v in res.results)
        meta = []
        if res.model:
            meta.append("Model: " + html.escape(res.model))
        if res.r2 is not None:
            meta.append(f"R² = {res.r2:.4f}")
        notes = "".join(f"<div style='color:#c05621; margin-top:4px'>⚠ {html.escape(n)}</div>"
                        for n in res.notes)
        meta_html = (f"<div style='color:#4a5568; font-size:11px; margin-top:4px'>"
                     f"{' · '.join(meta)}</div>") if meta else ""
        return (f"<b>Extracted results</b> &nbsp;<span style='color:{fg}'>● {badge}</span>"
                f"<table style='margin-top:4px'>{rows}</table>{meta_html}{notes}")

    # ---- calibration cascade: write the extracted values back -------------------
    def _clear_writebacks(self):
        self._wb_buttons = []
        while self.wb_layout.count():
            item = self.wb_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.wb_container.setVisible(False)

    def _show_writebacks(self, writebacks, quality="good"):
        self._clear_writebacks()
        if not writebacks or self.store is None:
            return
        head = QHBoxLayout()
        lab = QLabel("→ Write to config:")
        lab.setStyleSheet("color:#4a5568;")
        head.addWidget(lab)
        head.addStretch(1)
        self.btn_apply_all = QPushButton("Apply all")
        self.btn_apply_all.setStyleSheet(
            "QPushButton{background:#2f855a;color:white;padding:4px 10px;border-radius:5px;}"
            "QPushButton:disabled{background:#a0aec0;}")
        self.btn_apply_all.clicked.connect(self._apply_all)
        head.addWidget(self.btn_apply_all)
        host = QWidget()
        host.setLayout(head)
        self.wb_layout.addWidget(host)

        style = WB_STYLE.get(quality, WB_STYLE["good"])
        for label, key, val in writebacks:
            spec = self.store.specs.get(key)
            if spec is None:
                continue
            new = spec.clamp(val)
            unit = f" {spec.unit}" if spec.unit else ""
            warn = "⚠ " if quality == "uncertain" else ""
            b = QPushButton(f"{warn}↳ {label} = {spec.format(new)}{unit}")
            b.setToolTip(f"{key}: {spec.format(self.store.get(key))} → {spec.format(new)}{unit}"
                         + ("\nThe fit is uncertain: check the plot before applying."
                            if quality == "uncertain" else ""))
            b.setStyleSheet(style)
            b.clicked.connect(lambda _=False, k=key, vv=new, btn=b: self._writeback(k, vv, btn))
            self.wb_layout.addWidget(b)
            self._wb_buttons.append(b)
        self.wb_container.setVisible(True)

    def _writeback(self, key, value, btn):
        if self.store is not None:
            old = self.store.get(key)
            self.store.set(key, value)      # propagates to every form (and is persisted)
            spec = self.store.specs[key]
            self.log.appendPlainText(f"{key}: {spec.format(old)} → {spec.format(value)}")
        btn.setText("✓ " + btn.text().replace("⚠ ", "").lstrip("↳ "))
        btn.setEnabled(False)
        if all(not b.isEnabled() for b in self._wb_buttons):
            self.btn_apply_all.setEnabled(False)

    def _apply_all(self):
        for b in list(self._wb_buttons):
            if b.isEnabled():
                b.click()

    # ---- saving ----------------------------------------------------------------
    def _save_measurement(self):
        """Save data + figure like the notebook (automatic name/title/timestamp)."""
        if self.session is None or not self.session.is_ready:
            return
        if self.exp.plot == "action" or self.last_frame is None:
            return
        try:
            data = frame_to_save_data(self.last_frame)
            res = self.last_result
            extra = {}
            if res is not None:
                extra["analysis_summary"] = "\n".join(f"{k}: {v}" for k, v in res.results)
                extra["analysis_quality"] = res.quality
                extra["extracted"] = {k: float(v) for _, k, v in res.writebacks}
            info = self.session.save(params=self._run_ctx, data=data, extra=extra)
            if info is not None:
                # Automatic figure title: folder\name\timestamp (as in the notebook)
                self.canvas.stamp(self.exp, info.title)
                self.session.save_fig(self.canvas.fig)
                self.log.appendPlainText("Saved ✓")
                self.log.appendPlainText(f"  → {info.title}")
        except Exception as exc:
            self.log.appendPlainText(f"[save] error: {exc}")
