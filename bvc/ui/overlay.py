"""Transparent, click-through overlay that draws numbered labels on clickable controls."""
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget


class Overlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._items = []
        self._dpr = 1.0

    def show_items(self, items) -> None:
        """items: [(number, (left, top, right, bottom) in physical pixels, name)]"""
        screen = QGuiApplication.primaryScreen()
        self._dpr = screen.devicePixelRatio() or 1.0
        self._items = list(items)
        self.setGeometry(screen.geometry())
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = QFont("Segoe UI", 9)
        font.setBold(True)
        p.setFont(font)
        d = self._dpr
        for num, (l, t, r, b), _name in self._items:
            x, y, w, h = int(l / d), int(t / d), int((r - l) / d), int((b - t) / d)
            p.setPen(QPen(QColor(255, 210, 63, 200), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRect(x, y, w, h), 3, 3)
            label = QRect(x, y, 10 + 8 * len(str(num)), 17)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 210, 63))
            p.drawRoundedRect(label, 4, 4)
            p.setPen(QColor(20, 20, 20))
            p.drawText(label, Qt.AlignmentFlag.AlignCenter, str(num))
        p.end()
