"""
Main window: session bar (user + data folder), sidebar (experiments grouped by
category) + panel of the selected experiment.

The session bar reproduces the beginning of the notebook:
    aqm = AcquisitionAnalysisManager(path_database)
    aqm.set_config_file(["configuration.py", "calibration_db.json"])
The user enters a name and the database folder, then “Set session” creates the
saving manager. Every measurement is then saved automatically (folder + name +
timestamp) as in the notebook, and the global parameters are persisted to
<data folder>/calibration_params.json whenever they change.
"""

from __future__ import annotations
import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QTreeWidget,
    QTreeWidgetItem, QStackedWidget, QFrame, QLineEdit, QPushButton, QFileDialog,
)

from experiments import EXPERIMENTS, categories_in_order, EXPERIMENTS_BY_ID
from backend import MockBackend
from session import Session, HAS_LABMATE
from experiment_panel import ExperimentPanel
from glossary_panel import GlossaryPanel, ExtractionHelpPanel
from param_store import ParameterStore
from params_dialog import ParamsDialog
from worker import RunLock

GLOSSARY_ID = "__glossary__"
METHODS_ID = "__methods__"

DEFAULT_DATA_DIR = os.path.expanduser("~/QM_data/BS106/Cooldown3/QB3")


class MainWindow(QMainWindow):
    def __init__(self, backend=None):
        super().__init__()
        self.setWindowTitle("Qubit characterization — OPX/Octave (simulation mode)")
        self.resize(1280, 820)
        self.backend = backend or MockBackend()
        self.session = Session()
        self.store = ParameterStore()
        self.lock = RunLock()
        self._params_dialog = None
        self._panels = {}   # exp.id -> panel (created on demand)
        self._persist_timer = QTimer(self)
        self._persist_timer.setSingleShot(True)
        self._persist_timer.setInterval(400)
        self._persist_timer.timeout.connect(self._persist_params)
        self.store.changed.connect(lambda *_: self._persist_timer.start())
        self.lock.busy_changed.connect(lambda *_: self._refresh_status())
        self._build()

    def _build(self):
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_session_bar())

        # ---- Body: sidebar + central area -------------------------------------
        body = QWidget()
        root = QHBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color:#cbd5e0;")
        root.addWidget(sep)

        self.stack = QStackedWidget()
        welcome = QLabel(
            "1) Enter the user and the data folder at the top, then “Set session”.\n"
            "2) Pick an experiment on the left, set the parameters (hover a label for "
            "its explanation) and click “Run”.\n"
            "3) When the measurement ends, the fit and the extracted values appear "
            "automatically; the yellow buttons write them to the global parameters "
            "(calibration cascade).\n\n"
            "Every measurement is saved automatically — folder, name and timestamp — with "
            "a copy of configuration.py and calibration_db.json, exactly as in the "
            "notebook.\n\n"
            "Everything runs in simulation mode (virtual transmon): no OPX connection is "
            "needed."
        )
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome.setWordWrap(True)
        welcome.setStyleSheet("color:#4a5568; font-size:13px; padding:40px;")
        self.stack.addWidget(welcome)
        root.addWidget(self.stack, 1)

        outer.addWidget(body, 1)
        self.setCentralWidget(central)
        self._refresh_status()

    # -------------------------------------------------------------- session bar --
    def _build_session_bar(self):
        bar = QWidget()
        bar.setObjectName("sessionBar")
        # Colours forced explicitly so that it stays readable with the macOS dark theme
        bar.setStyleSheet("""
            QWidget#sessionBar { background:#edf2f7; border-bottom:1px solid #cbd5e0; }
            QWidget#sessionBar QLabel { color:#1a202c; }
            QWidget#sessionBar QLineEdit {
                color:#1a202c; background:#ffffff;
                border:1px solid #cbd5e0; border-radius:4px; padding:3px;
            }
        """)
        lyt = QHBoxLayout(bar)
        lyt.setContentsMargins(12, 8, 12, 8)

        lyt.addWidget(QLabel("User:"))
        self.ed_user = QLineEdit()
        self.ed_user.setPlaceholderText("e.g. enzo")
        self.ed_user.setMaximumWidth(140)
        lyt.addWidget(self.ed_user)

        lyt.addSpacing(10)
        lyt.addWidget(QLabel("Data folder:"))
        self.ed_dir = QLineEdit(DEFAULT_DATA_DIR)
        self.ed_dir.setMinimumWidth(320)
        lyt.addWidget(self.ed_dir, 1)

        btn_browse = QPushButton("Browse…")
        btn_browse.clicked.connect(self._browse_dir)
        lyt.addWidget(btn_browse)

        btn_params = QPushButton("⚙ Global parameters")
        btn_params.setToolTip("Edit every shared physical parameter and calibration result; "
                              "changes propagate everywhere.")
        btn_params.clicked.connect(self._open_params)
        lyt.addWidget(btn_params)

        self.btn_session = QPushButton("Set session")
        self.btn_session.setStyleSheet(
            "QPushButton{background:#2b6cb0;color:white;padding:6px 14px;"
            "border-radius:6px;font-weight:bold;}"
            "QPushButton:hover{background:#2c5282;}")
        self.btn_session.clicked.connect(self._set_session)
        lyt.addWidget(self.btn_session)

        return bar

    def _open_params(self):
        if self._params_dialog is None:
            self._params_dialog = ParamsDialog(self.store, self)
        self._params_dialog.show()
        self._params_dialog.raise_()
        self._params_dialog.activateWindow()

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Choose the data folder",
                                             self.ed_dir.text() or os.path.expanduser("~"))
        if d:
            self.ed_dir.setText(d)

    def _set_session(self):
        data_dir = self.ed_dir.text().strip()
        user = self.ed_user.text().strip()
        if not data_dir:
            self.statusBar().showMessage("Enter a data folder.")
            return
        try:
            self.session.configure(data_dir, config_files=None, user=user)
        except Exception as exc:
            self.statusBar().showMessage(f"Session error: {exc}")
            return
        # Reload the calibrated parameters of this session, if any
        loaded = self.session.load_params()
        if loaded:
            self.store.load_dict(loaded)
        else:
            self._persist_params()
        self._refresh_status()

    def _persist_params(self):
        if self.session.is_ready:
            self.session.save_params(self.store.to_dict())

    def _refresh_status(self):
        if self.session.is_ready:
            cfg = ", ".join(os.path.basename(f) for f in self.session.config_files) or "none"
            msg = (f"Session: {self.session.data_dir}  ·  user: "
                   f"{self.session.user or '—'}  ·  saving: {self.session.backend_name}"
                   f"  ·  config: {cfg}")
        else:
            extra = "" if HAS_LABMATE else "  (labmate not installed → fallback saving)"
            msg = "No session — fill it in, then “Set session”." + extra
        if self.lock.busy:
            msg = f"▶ Running: {self.lock.name}   |   " + msg
        self.statusBar().showMessage(msg)

    # ------------------------------------------------------------------ sidebar --
    def _build_sidebar(self):
        side = QWidget()
        side.setStyleSheet("background:#1a202c;")
        side.setFixedWidth(300)
        slyt = QVBoxLayout(side)
        slyt.setContentsMargins(12, 14, 12, 12)

        head = QLabel("Characterization workflow")
        head.setStyleSheet("color:white;")
        hf = QFont()
        hf.setPointSize(12)
        hf.setBold(True)
        head.setFont(hf)
        slyt.addWidget(head)

        sub = QLabel(f"Measurement backend: {getattr(self.backend, 'name', 'backend')} "
                     "— no hardware required")
        sub.setStyleSheet("color:#90cdf4; font-size:11px;")
        sub.setWordWrap(True)
        slyt.addWidget(sub)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(12)
        self.tree.setStyleSheet("""
            QTreeWidget{background:#1a202c;color:#e2e8f0;border:none;font-size:13px;}
            QTreeWidget::item{padding:5px;}
            QTreeWidget::item:selected{background:#2b6cb0;color:white;border-radius:4px;}
        """)
        self._populate_tree()
        self.tree.currentItemChanged.connect(self._on_select)
        slyt.addWidget(self.tree, 1)

        foot = QLabel("BS106 · Cooldown3")
        foot.setStyleSheet("color:#718096; font-size:10px;")
        slyt.addWidget(foot)
        return side

    def _populate_tree(self):
        # "Help" folder on top: parameter glossary + extraction methods
        aide = QTreeWidgetItem(["📘 Help"])
        aide.setFlags(Qt.ItemFlag.ItemIsEnabled)
        af = aide.font(0)
        af.setBold(True)
        aide.setFont(0, af)
        self.tree.addTopLevelItem(aide)
        for label, key in (("Parameter glossary", GLOSSARY_ID),
                           ("Automatic extraction", METHODS_ID)):
            it = QTreeWidgetItem([label])
            it.setData(0, Qt.ItemDataRole.UserRole, key)
            aide.addChild(it)
        aide.setExpanded(True)

        for cat in categories_in_order():
            parent = QTreeWidgetItem([cat])
            parent.setFlags(Qt.ItemFlag.ItemIsEnabled)
            fnt = parent.font(0)
            fnt.setBold(True)
            parent.setFont(0, fnt)
            self.tree.addTopLevelItem(parent)
            for exp in sorted(EXPERIMENTS, key=lambda x: x.order):
                if exp.category != cat:
                    continue
                child = QTreeWidgetItem([exp.name])
                child.setData(0, Qt.ItemDataRole.UserRole, exp.id)
                child.setToolTip(0, exp.outputs)
                parent.addChild(child)
            parent.setExpanded(True)

    def _on_select(self, current, _previous):
        if current is None:
            return
        exp_id = current.data(0, Qt.ItemDataRole.UserRole)
        if not exp_id:
            return
        if exp_id not in self._panels:
            if exp_id == GLOSSARY_ID:
                panel = GlossaryPanel()
            elif exp_id == METHODS_ID:
                panel = ExtractionHelpPanel()
            else:
                panel = ExperimentPanel(EXPERIMENTS_BY_ID[exp_id], self.backend,
                                        session=self.session, store=self.store, lock=self.lock)
            self._panels[exp_id] = panel
            self.stack.addWidget(panel)
        self.stack.setCurrentWidget(self._panels[exp_id])

    # ------------------------------------------------------------------ closing --
    def closeEvent(self, event):
        for panel in self._panels.values():
            if isinstance(panel, ExperimentPanel):
                panel.shutdown()
        if self._persist_timer.isActive():
            self._persist_timer.stop()
            self._persist_params()
        super().closeEvent(event)
