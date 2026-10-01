"""
Application entry point.

Run:  python main.py            (GUI)
      python selftest.py        (headless check of the simulation + extraction chain)

PyQt6 interface for the characterization of superconducting qubits (Quantum Machines
OPX/Octave). Everything runs in SIMULATION MODE on a virtual transmon: no hardware
connection is needed.
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor


def _apply_light_theme(app):
    """Force a consistent light theme on the whole application, whatever the macOS
    light/dark setting — avoids any white text on a light background."""
    app.setStyle("Fusion")
    pal = QPalette()
    C = QColor
    pal.setColor(QPalette.ColorRole.Window, C("#f5f5f7"))
    pal.setColor(QPalette.ColorRole.WindowText, C("#1a202c"))
    pal.setColor(QPalette.ColorRole.Base, C("#ffffff"))
    pal.setColor(QPalette.ColorRole.AlternateBase, C("#eef2f7"))
    pal.setColor(QPalette.ColorRole.Text, C("#1a202c"))
    pal.setColor(QPalette.ColorRole.Button, C("#e2e8f0"))
    pal.setColor(QPalette.ColorRole.ButtonText, C("#1a202c"))
    pal.setColor(QPalette.ColorRole.ToolTipBase, C("#ffffff"))
    pal.setColor(QPalette.ColorRole.ToolTipText, C("#1a202c"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, C("#718096"))
    pal.setColor(QPalette.ColorRole.Highlight, C("#2b6cb0"))
    pal.setColor(QPalette.ColorRole.HighlightedText, C("#ffffff"))
    # Readable disabled states too
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, C("#a0aec0"))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, C("#a0aec0"))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, C("#a0aec0"))
    app.setPalette(pal)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Qubit Characterization GUI")
    _apply_light_theme(app)

    from main_window import MainWindow
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
