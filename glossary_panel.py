"""
Help pages.

GlossaryPanel        one scrollable page with a search bar, listing every parameter
                     grouped by theme. Each parameter is described once (content in
                     param_docs.py); the measurements using / calibrating it are
                     computed automatically.
ExtractionHelpPanel  for every experiment: the fit model used by the automatic
                     extraction and the parameters it can write back.
"""

from __future__ import annotations
import html

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QScrollArea, QFrame,
)

from param_docs import GROUPS, DOCS, experiments_using, experiments_calibrating, spec_for


CARD_STYLE = (
    "QFrame#card{background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;}"
    "QFrame#card QLabel{color:#1a202c;}"
)


def _title(text, size=15):
    lab = QLabel(text)
    f = QFont()
    f.setPointSize(size)
    f.setBold(True)
    lab.setFont(f)
    return lab


def _card():
    card = QFrame()
    card.setObjectName("card")
    card.setStyleSheet(CARD_STYLE)
    v = QVBoxLayout(card)
    v.setContentsMargins(12, 10, 12, 10)
    v.setSpacing(3)
    return card, v


def _line(v, prefix, txt, color="#2d3748"):
    lab = QLabel(f"<b>{html.escape(prefix)}</b> {html.escape(txt)}")
    lab.setWordWrap(True)
    lab.setStyleSheet(f"color:{color};")
    lab.setTextFormat(Qt.TextFormat.RichText)
    v.addWidget(lab)


class GlossaryPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = []   # (group_header, [(card, search_text)])
        self._build()

    def _build(self):
        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(16, 14, 16, 12)
        lyt.addWidget(_title("Parameter glossary"))

        sub = QLabel("Every parameter explained once: what it is, what happens when you "
                     "change it, a typical order of magnitude, and the measurements involved.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#4a5568;")
        lyt.addWidget(sub)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search a parameter (name, keyword)…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.search.setStyleSheet(
            "QLineEdit{color:#1a202c;background:#ffffff;border:1px solid #cbd5e0;"
            "border-radius:6px;padding:6px;}")
        lyt.addWidget(self.search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        self.vbox = QVBoxLayout(host)
        self.vbox.setContentsMargins(0, 6, 0, 0)
        self.vbox.setSpacing(6)
        self._populate()
        self.vbox.addStretch(1)
        scroll.setWidget(host)
        lyt.addWidget(scroll, 1)

    def _populate(self):
        for group_name, keys in GROUPS:
            header = _title(group_name, 12)
            header.setStyleSheet("color:#2b6cb0; margin-top:8px;")
            self.vbox.addWidget(header)
            cards = []
            for key in keys:
                doc = DOCS.get(key)
                if doc is None:
                    continue
                card, text = self._make_card(key, doc)
                self.vbox.addWidget(card)
                cards.append((card, text))
            self._entries.append((header, cards))

    def _make_card(self, key, doc):
        spec = spec_for(key)
        label = spec.label if spec else key
        unit = f"  [{spec.unit}]" if (spec and spec.unit) else ""
        used = experiments_using(key)
        cal = experiments_calibrating(key)
        used_txt = ", ".join(used) if used else "— (global parameter, see ⚙ Global parameters)"

        card, v = _card()
        head = QLabel(f"{html.escape(label)}{html.escape(unit)}   ·   <code>{key}</code>")
        hf = QFont()
        hf.setBold(True)
        hf.setPointSize(11)
        head.setFont(hf)
        head.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(head)

        _line(v, "What it is:", doc["what"])
        _line(v, "Effect:", doc["effect"])
        _line(v, "Typical:", doc["typical"])
        _line(v, "Used in:", used_txt, color="#2b6cb0")
        if cal:
            _line(v, "Calibrated by:", ", ".join(cal), color="#2f855a")

        search_text = " ".join([key, label, doc["what"], doc["effect"],
                                doc["typical"], used_txt, " ".join(cal)]).lower()
        return card, search_text

    def _filter(self, text):
        q = text.strip().lower()
        for header, cards in self._entries:
            any_visible = False
            for card, stext in cards:
                visible = (q in stext) if q else True
                card.setVisible(visible)
                any_visible = any_visible or visible
            header.setVisible(any_visible)


class ExtractionHelpPanel(QWidget):
    """How every quantity is extracted automatically at the end of a measurement."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from experiments import EXPERIMENTS
        from analysis import METHODS

        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(16, 14, 16, 12)
        lyt.addWidget(_title("Automatic extraction"))
        sub = QLabel(
            "When a measurement completes, the data are fitted automatically: the fit is "
            "drawn in red, the extracted values (with 1σ uncertainties) and the fit quality "
            "appear under the Run button, and yellow buttons write the new values to the "
            "global parameters (“Apply all” applies them together). Orange buttons mean the "
            "fit is uncertain: check the plot first. Corrections are always computed "
            "relative to the values used for the run, so they also apply to real data.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#4a5568;")
        lyt.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        vbox = QVBoxLayout(host)
        vbox.setContentsMargins(0, 6, 0, 0)
        vbox.setSpacing(6)
        for e in sorted(EXPERIMENTS, key=lambda x: x.order):
            if e.id not in METHODS:
                continue
            model, writes = METHODS[e.id]
            card, v = _card()
            head = QLabel(f"<b>{html.escape(e.name)}</b>  "
                          f"<span style='color:#718096'>· {html.escape(e.category)}</span>")
            head.setTextFormat(Qt.TextFormat.RichText)
            v.addWidget(head)
            _line(v, "Method:", model)
            _line(v, "Writes back:", writes, color="#2f855a")
            vbox.addWidget(card)
        vbox.addStretch(1)
        scroll.setWidget(host)
        lyt.addWidget(scroll, 1)
