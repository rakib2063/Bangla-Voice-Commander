from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

ACCENT = "#5b8cff"
GREEN = "#2ecc71"
RED = "#ff4d4f"
AMBER = "#ffb020"

STYLE = """
QWidget { background: #0f1218; color: #e6e9f0; font-size: 14px; }
QMainWindow, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget { background: #0f1218; }
QLabel { background: transparent; }
QLabel#muted { color: #8b93a7; }
QLabel#h1 { font-size: 22px; font-weight: 600; }
QLabel#h2 { font-size: 15px; font-weight: 600; color: #c9d1e6; }
QLabel#heard { font-size: 26px; font-weight: 600; }
QLabel#pill { background: #1c2230; border: 1px solid #2a3144; border-radius: 12px; padding: 4px 12px; }
QFrame#card { background: #171b24; border: 1px solid #232938; border-radius: 14px; }
QFrame#card QLabel, QFrame#card QCheckBox, QFrame#card QRadioButton { background: transparent; }
QFrame#banner { background: #3a2a0c; border: 1px solid #b27a14; border-radius: 12px; }
QFrame#banner QLabel { background: transparent; color: #ffd98a; }
QListWidget#nav { background: #0b0e13; border: none; padding: 8px; outline: 0; min-width: 190px; max-width: 190px; }
QListWidget#nav::item { padding: 11px 14px; border-radius: 10px; margin: 2px 0; color: #9aa3b8; }
QListWidget#nav::item:selected { background: #1b2336; color: #ffffff; }
QListWidget#nav::item:hover { background: #151b29; }
QPushButton { background: #232b3d; border: 1px solid #2f3850; border-radius: 10px; padding: 9px 16px; }
QPushButton:hover { background: #2b3550; }
QPushButton:pressed { background: #1c2335; }
QPushButton:disabled { color: #5d6579; background: #1a2030; }
QPushButton#primary { background: #4a7bff; border: none; font-weight: 600; }
QPushButton#primary:hover { background: #5b8cff; }
QPushButton#stop { background: #d93a3d; border: none; font-weight: 700; }
QPushButton#stop:hover { background: #ff4d4f; }
QPushButton#mode { background: #1c2230; }
QPushButton#mode:checked { background: #28407a; border: 1px solid #5b8cff; font-weight: 600; }
QPushButton#big { font-size: 17px; padding: 16px 20px; }
QLineEdit, QPlainTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox, QTableWidget, QListWidget {
    background: #121722; border: 1px solid #2a3144; border-radius: 8px; padding: 6px; selection-background-color: #28407a; }
QComboBox QAbstractItemView { background: #121722; selection-background-color: #28407a; }
QHeaderView::section { background: #1a2030; border: none; padding: 6px; color: #9aa3b8; }
QTableWidget { gridline-color: #232938; }
QProgressBar { background: #121722; border: 1px solid #2a3144; border-radius: 6px; height: 12px; text-align: center; }
QProgressBar::chunk { background: #2ecc71; border-radius: 5px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1px solid #3a4560; background: #121722; }
QCheckBox::indicator:checked { background: #4a7bff; border-color: #4a7bff; }
QScrollBar:vertical { background: #0f1218; width: 10px; }
QScrollBar::handle:vertical { background: #2a3144; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QGroupBox { border: 1px solid #232938; border-radius: 12px; margin-top: 14px; padding-top: 14px; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: #c9d1e6; }
QToolTip { background: #1c2230; color: #e6e9f0; border: 1px solid #2f3850; }
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    f = QFont()
    f.setFamilies(["Segoe UI", "Nirmala UI", "Noto Sans Bengali", "Kalpurush", "Arial"])
    f.setPointSize(10)
    app.setFont(f)
    app.setStyleSheet(STYLE)
