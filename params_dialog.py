"""
"Global parameters" window: edits in one place every shared physical parameter and
calibration result. Every change goes live into the store (ParameterStore) and
therefore into every form using that parameter.

Non-modal window: it can stay open while switching experiments.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QLabel,
    QScrollArea, QWidget, QPushButton, QFileDialog, QMessageBox,
)

from experiment_panel import make_spinbox


class ParamsDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.widgets = {}         # key -> (spec, widget)
        self._syncing = False
        self.setWindowTitle("Global parameters")
        self.resize(480, 680)
        self._build()
        self.store.changed.connect(self._on_store_changed)

    def _build(self):
        # Colours forced so that it stays readable with the macOS dark theme too
        self.setStyleSheet("""
            QDialog { background:#f7fafc; }
            QLabel { color:#1a202c; }
            QGroupBox { color:#1a202c; font-weight:bold; margin-top:6px; }
            QDoubleSpinBox, QSpinBox {
                color:#1a202c; background:#ffffff;
                border:1px solid #cbd5e0; border-radius:4px; padding:2px;
            }
        """)
        lyt = QVBoxLayout(self)

        title = QLabel("Global parameters")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        title.setFont(f)
        lyt.addWidget(title)

        sub = QLabel("Changed here, they are updated everywhere they are used, and saved "
                     "with the session (calibration_params.json in the data folder).")
        sub.setStyleSheet("color:#4a5568;")
        sub.setWordWrap(True)
        lyt.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        vbox = QVBoxLayout(host)

        for group, specs in self.store.grouped().items():
            box = QGroupBox(group)
            form = QFormLayout(box)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            for spec in specs:
                w = make_spinbox(spec)
                self._syncing = True
                w.setValue(spec.coerce(self.store.get(spec.key)))
                self._syncing = False
                w.setToolTip(spec.help)
                w.valueChanged.connect(lambda val, k=spec.key: self._on_widget_changed(k, val))
                self.widgets[spec.key] = (spec, w)
                label = QLabel(spec.label + (f"  [{spec.unit}]" if spec.unit else ""))
                label.setToolTip(spec.help)
                form.addRow(label, w)
            vbox.addWidget(box)
        vbox.addStretch(1)
        scroll.setWidget(host)
        lyt.addWidget(scroll, 1)

        row = QHBoxLayout()
        b_imp = QPushButton("Import…")
        b_imp.setToolTip("Load global parameters from a JSON file.")
        b_imp.clicked.connect(self._import)
        b_exp = QPushButton("Export…")
        b_exp.setToolTip("Save the global parameters to a JSON file.")
        b_exp.clicked.connect(self._export)
        b_def = QPushButton("Reset to configuration.py")
        b_def.setToolTip("Restore the default values taken from configuration.py.")
        b_def.clicked.connect(self._reset)
        row.addWidget(b_imp)
        row.addWidget(b_exp)
        row.addWidget(b_def)
        row.addStretch(1)
        btn = QPushButton("Close")
        btn.clicked.connect(self.close)
        row.addWidget(btn)
        lyt.addLayout(row)

    def _on_widget_changed(self, key, val):
        if self._syncing:
            return
        self.store.set(key, val)

    def _on_store_changed(self, key, val):
        # update when the value changed elsewhere (in an experiment panel)
        if key in self.widgets:
            spec, w = self.widgets[key]
            self._syncing = True
            w.setValue(spec.coerce(val))
            self._syncing = False

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import global parameters", "",
                                              "JSON (*.json)")
        if path and not self.store.load_json(path):
            QMessageBox.warning(self, "Import", f"Could not read {path}.")

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export global parameters",
                                              "global_parameters.json", "JSON (*.json)")
        if path:
            try:
                self.store.save_json(path)
            except Exception as exc:
                QMessageBox.warning(self, "Export", f"Could not write {path}: {exc}")

    def _reset(self):
        r = QMessageBox.question(self, "Reset", "Restore every global parameter (including "
                                 "calibration results) to the configuration.py values?")
        if r == QMessageBox.StandardButton.Yes:
            self.store.reset_defaults()
