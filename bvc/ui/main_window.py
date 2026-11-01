"""Main window: dashboard, custom commands, history, settings, help."""
from __future__ import annotations

import os
import sys
import time

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QFrame, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QListWidget, QMainWindow, QProgressBar, QPushButton,
                               QStackedWidget, QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

from ..nlp.intents import INTENT_DEFS
from .commands_page import CommandsPage
from .overlay import Overlay
from .settings_page import SettingsPage

STATES = {"idle": ("⏸  বন্ধ", "#8b93a7"), "loading": ("⏳  লোড হচ্ছে…", "#ffb020"), "listening": ("🎤  শুনছি", "#2ecc71"),
          "thinking": ("🧠  বুঝছি…", "#5b8cff"), "muted": ("🔇  মাইক মিউট", "#ffb020"),
          "sleeping": ("😴  ঘুমিয়ে আছি", "#8b93a7"), "error": ("⚠  সমস্যা", "#ff4d4f")}


class Bridge(QObject):
    """Thread-safe bridge: engine/service threads emit, the GUI thread receives."""
    event = Signal(str, dict)

    def emit_event(self, name: str, **data) -> None:
        self.event.emit(name, data)


def card(title: str = ""):
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(8)
    if title:
        t = QLabel(title)
        t.setObjectName("h2")
        lay.addWidget(t)
    return f, lay


class Dashboard(QWidget):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        root = QVBoxLayout(self)
        root.setSpacing(14)
        h = QLabel("ড্যাশবোর্ড")
        h.setObjectName("h1")
        root.addWidget(h)

        # --- confirmation banner ---
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        bl = QHBoxLayout(self.banner)
        self.banner_text = QLabel("")
        self.banner_text.setWordWrap(True)
        yes, no = QPushButton("হ্যাঁ, নিশ্চিত"), QPushButton("না")
        yes.setObjectName("primary")
        yes.clicked.connect(lambda: win.service.engine.confirm(True))
        no.clicked.connect(lambda: win.service.engine.confirm(False))
        bl.addWidget(self.banner_text, 1)
        bl.addWidget(yes)
        bl.addWidget(no)
        self.banner.hide()
        root.addWidget(self.banner)

        row = QHBoxLayout()
        row.setSpacing(14)
        # --- microphone card ---
        c, l = card("মাইক্রোফোন")
        self.status = QLabel("⏸  বন্ধ")
        self.status.setObjectName("pill")
        self.toggle = QPushButton("🎤  শোনা শুরু করো")
        self.toggle.setObjectName("primary")
        self.toggle.setProperty("class", "big")
        self.toggle.setMinimumHeight(54)
        self.toggle.clicked.connect(win.toggle_listening)
        self.mute = QPushButton("🔇  মাইক মিউট")
        self.mute.setCheckable(True)
        self.mute.clicked.connect(lambda on: win.service.set_muted(on) if win.service.listening else None)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        self.model_msg = QLabel("")
        self.model_msg.setObjectName("muted")
        self.model_msg.setWordWrap(True)
        for w in (self.status, self.toggle, self.mute, self.level, self.model_msg):
            l.addWidget(w)
        row.addWidget(c, 3)
        # --- mode card ---
        c, l = card("মোড")
        self.b_cmd, self.b_cont = QPushButton("কমান্ড মোড"), QPushButton("কন্টিনিউয়াস মোড")
        grp = QButtonGroup(self)
        for b, m in ((self.b_cmd, "command"), (self.b_cont, "continuous")):
            b.setCheckable(True)
            b.setObjectName("mode")
            grp.addButton(b)
            b.clicked.connect(lambda _=False, mode=m: win.service.engine.set_mode(mode))
            l.addWidget(b)
        hint = QLabel("কমান্ড মোড: প্রতিটি কমান্ড একবার চলে।\nকন্টিনিউয়াস: নিচে/উপরে বললে থামো না বলা পর্যন্ত স্ক্রল চলে।")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        l.addWidget(hint)
        row.addWidget(c, 3)
        # --- emergency ---
        c, l = card("জরুরি")
        stop = QPushButton("⛔  এখনই থামাও")
        stop.setObjectName("stop")
        stop.setMinimumHeight(70)
        stop.clicked.connect(lambda: win.service.engine.emergency_stop())
        self.hk = QLabel("")
        self.hk.setObjectName("muted")
        l.addWidget(stop)
        l.addWidget(self.hk)
        row.addWidget(c, 2)
        root.addLayout(row)

        # --- last command ---
        c, l = card("সর্বশেষ কমান্ড")
        self.heard = QLabel("—")
        self.heard.setObjectName("heard")
        self.heard.setWordWrap(True)
        self.result = QLabel("")
        self.result.setWordWrap(True)
        self.app = QLabel("")
        self.app.setObjectName("muted")
        for w in (self.heard, self.result, self.app):
            l.addWidget(w)
        root.addWidget(c)

        # --- type a command ---
        c, l = card("টাইপ করে কমান্ড চালান (পরীক্ষার জন্য)")
        r = QHBoxLayout()
        self.line = QLineEdit()
        self.line.setPlaceholderText("যেমন: নিচে স্ক্রল করো")
        go = QPushButton("চালাও")
        go.clicked.connect(self.run_text)
        self.line.returnPressed.connect(self.run_text)
        r.addWidget(self.line, 1)
        r.addWidget(go)
        l.addLayout(r)
        root.addWidget(c)

        # --- recent ---
        c, l = card("সাম্প্রতিক কাজ")
        self.recent = QListWidget()
        self.recent.setMaximumHeight(150)
        l.addWidget(self.recent)
        root.addWidget(c, 1)

    def run_text(self):
        t = self.line.text().strip()
        if t:
            self.line.clear()
            self.win.service.engine.handle_text(t, source="text")

    def set_status(self, state: str, text: str = ""):
        label, color = STATES.get(state, STATES["idle"])
        self.status.setText(label + (f" — {text}" if text and state in ("error", "loading") else ""))
        self.status.setStyleSheet(f"color: {color};")
        self.toggle.setText("⏹  শোনা বন্ধ করো" if state in ("listening", "thinking", "muted", "sleeping", "loading")
                            else "🎤  শোনা শুরু করো")

    def set_mode(self, mode: str):
        self.b_cmd.setChecked(mode == "command")
        self.b_cont.setChecked(mode == "continuous")


class HistoryPage(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        h = QLabel("কমান্ডের ইতিহাস")
        h.setObjectName("h1")
        clear = QPushButton("ইতিহাস মুছে ফেলো")
        clear.clicked.connect(self.clear)
        top.addWidget(h, 1)
        top.addWidget(clear)
        lay.addLayout(top)
        self.t = QTableWidget(0, 5)
        self.t.setHorizontalHeaderLabels(["সময়", "যা শুনেছি", "কমান্ড", "ফলাফল", "বিবরণ"])
        self.t.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.t, 1)

    def refresh(self):
        rows = self.db.recent_history(300)
        self.t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vals = [time.strftime("%H:%M:%S", time.localtime(r["ts"])), r["heard"], r["intent"],
                    "✔" if r["ok"] else "✘", r["detail"] or ""]
            for j, v in enumerate(vals):
                self.t.setItem(i, j, QTableWidgetItem(str(v)))

    def clear(self):
        self.db.clear_history()
        self.refresh()


class HelpPage(QTextBrowser):
    def __init__(self):
        super().__init__()
        cats: dict[str, list] = {}
        for _id, cat, label, phrases in INTENT_DEFS:
            cats.setdefault(cat, []).append((label, phrases[:3]))
        html = ["<h2>কমান্ড তালিকা</h2>",
                "<p>নিচের কমান্ডগুলোর অনেক সমার্থক রূপও বোঝা যায় (ইংরেজি ও বাংলিশসহ)। "
                "যেকোনো সময় বলুন <b>থামো</b> / <b>বন্ধ করো</b> / <b>Stop</b>।</p>",
                "<p><b>প্যারামিটারসহ কমান্ড:</b> “ক্রোম খোলো”, “গুগলে বাংলাদেশের খবর সার্চ করো”, "
                "“লেখো আমি ভালো আছি”, “৫ নম্বরে ক্লিক করো” (আগে “নম্বর দেখাও”), “লগইন বাটনে ক্লিক করো”, "
                "“ভলিউম ৪০ করো”।</p>"]
        for cat, items in cats.items():
            html.append(f"<h3>{cat}</h3><ul>")
            for label, ph in items:
                html.append(f"<li><b>{label}</b> — {' &nbsp;|&nbsp; '.join(ph)}</li>")
            html.append("</ul>")
        self.setHtml("".join(html))


class MainWindow(QMainWindow):
    def __init__(self, service, settings, db, bridge: Bridge):
        super().__init__()
        self.service, self.s, self.db = service, settings, db
        self.setWindowTitle("Bangla Voice Commander — বাংলা ভয়েস কমান্ডার")
        self.resize(1120, 760)
        self.overlay = Overlay()
        central = QWidget()
        self.setCentralWidget(central)
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        for n in ("🏠  ড্যাশবোর্ড", "🧩  কাস্টম কমান্ড", "🕘  ইতিহাস", "⚙  সেটিংস", "❓  সাহায্য"):
            self.nav.addItem(n)
        self.stack = QStackedWidget()
        self.dashboard = Dashboard(self)
        self.commands = CommandsPage(service, db)
        self.history = HistoryPage(db)
        self.settings_page = SettingsPage(service, settings, db)
        for w in (self.dashboard, self.commands, self.history, self.settings_page, HelpPage()):
            wrap = QWidget()
            wl = QVBoxLayout(wrap)
            wl.setContentsMargins(22, 18, 22, 18)
            wl.addWidget(w)
            self.stack.addWidget(wrap)
        self.nav.currentRowChanged.connect(self._page)
        self.nav.setCurrentRow(0)
        lay.addWidget(self.nav)
        lay.addWidget(self.stack, 1)

        bridge.event.connect(self.on_event)
        self.dashboard.set_mode(service.engine.mode)
        self.dashboard.hk.setText(f"গ্লোবাল হটকি: {self.s.get('emergency_hotkey')}\n(মাউস স্ক্রিনের কোণায় নিলেও সব থামবে)")
        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.dashboard.app.setText("সক্রিয় অ্যাপ: " + service.engine.current_app()))
        self.timer.start(1200)

    def _page(self, i: int):
        self.stack.setCurrentIndex(i)
        if i == 2:
            self.history.refresh()
        if i == 1:
            self.commands.reload()

    def toggle_listening(self):
        if self.service.listening or self.service._starting:
            self.service.stop_listening()
        else:
            self.service.start_listening()

    # -------------------------------------------------------------------------------------------
    def on_event(self, name: str, d: dict):
        db = self.dashboard
        if name == "status":
            db.set_status(d["state"], d.get("text", ""))
        elif name == "level":
            db.level.setValue(int(d["value"] * 100))
        elif name == "heard":
            db.heard.setText(d["text"])
            db.result.setText("")
        elif name == "result":
            ok = d["ok"]
            db.result.setText(f"{'✔' if ok else '✘'}  {d.get('label') or d['intent']} — {d['message']}"
                              + ("" if ok or not d.get("detail") else f"\n({d['detail']})"))
            db.result.setStyleSheet(f"color: {'#2ecc71' if ok else '#ff4d4f'};")
            db.recent.insertItem(0, f"{time.strftime('%H:%M:%S')}  {'✔' if ok else '✘'}  {d['heard']}  →  {d['intent']}")
            while db.recent.count() > 30:
                db.recent.takeItem(db.recent.count() - 1)
        elif name == "ignored":
            db.result.setText(f"(উপেক্ষা করা হয়েছে: {d.get('reason', '')})")
            db.result.setStyleSheet("color: #8b93a7;")
        elif name == "confirm":
            db.banner_text.setText(f"⚠ নিশ্চিত করুন: {d['label']}\nশুনেছি: “{d['heard']}” — হ্যাঁ বা না বলুন ({d['timeout']} সেকেন্ড)।")
            db.banner.show()
        elif name == "confirm_done":
            db.banner.hide()
        elif name == "overlay":
            self.overlay.show_items(d["items"])
        elif name == "overlay_hide":
            self.overlay.hide()
        elif name == "mode":
            db.set_mode(d["mode"])
        elif name == "sleep":
            db.set_status("sleeping" if d["asleep"] else "listening")
        elif name == "request_stop_listening":
            self.service.stop_listening()
        elif name == "model":
            db.model_msg.setText(d["message"])
        elif name == "error":
            db.model_msg.setText("⚠ " + d["message"])
            db.model_msg.setStyleSheet("color: #ff4d4f;")
        elif name == "emergency":
            db.level.setValue(0)

    def closeEvent(self, e: QCloseEvent):
        self.overlay.hide()
        self.service.shutdown()
        e.accept()
