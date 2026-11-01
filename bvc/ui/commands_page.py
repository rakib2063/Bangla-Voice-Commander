"""Custom command manager: create / edit / delete / test voice macros without touching source code."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

STEP_TYPES = [("open_app", "অ্যাপ খোলো (নাম বা .exe পাথ)"), ("open_url", "ওয়েবসাইট খোলো"),
              ("hotkey", "কিবোর্ড শর্টকাট (যেমন ctrl+t)"), ("type", "লেখা টাইপ করো"),
              ("wait", "অপেক্ষা (সেকেন্ড)"), ("say", "বলো"), ("command", "অন্য ভয়েস কমান্ড চালাও")]


class CommandsPage(QWidget):
    def __init__(self, service, db):
        super().__init__()
        self.service, self.db, self.cid = service, db, None
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        h = QLabel("কাস্টম কমান্ড")
        h.setObjectName("h1")
        left.addWidget(h)
        self.listw = QListWidget()
        self.listw.currentItemChanged.connect(self._select)
        new = QPushButton("＋ নতুন কমান্ড")
        new.clicked.connect(self.new)
        left.addWidget(self.listw, 1)
        left.addWidget(new)
        root.addLayout(left, 2)

        right = QVBoxLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("কমান্ডের নাম (যেমন: আমার কাজ)")
        self.phrases = QPlainTextEdit()
        self.phrases.setPlaceholderText("কোন কোন বাক্য বললে চলবে — প্রতি লাইনে একটি\nযেমন: আমার কাজ শুরু করো")
        self.phrases.setMaximumHeight(90)
        self.enabled = QCheckBox("চালু আছে")
        self.enabled.setChecked(True)
        self.steps = QTableWidget(0, 2)
        self.steps.setHorizontalHeaderLabels(["ধাপ", "মান"])
        self.steps.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.steps.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for w in (QLabel("নাম"), self.name, QLabel("ট্রিগার বাক্য"), self.phrases, self.enabled,
                  QLabel("ধাপগুলো (উপর থেকে নিচে চলবে)"), self.steps):
            right.addWidget(w) if not isinstance(w, QTableWidget) else right.addWidget(w, 1)
        r = QHBoxLayout()
        for text, fn in (("＋ ধাপ", lambda: self.add_step()), ("− ধাপ মুছো", self.del_step),
                         ("↑", lambda: self.move(-1)), ("↓", lambda: self.move(1))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            r.addWidget(b)
        right.addLayout(r)
        r = QHBoxLayout()
        save, test, delete = QPushButton("💾 সেভ"), QPushButton("▶ পরীক্ষা"), QPushButton("🗑 মুছে ফেলো")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        test.clicked.connect(self.test)
        delete.clicked.connect(self.delete)
        for b in (save, test, delete):
            r.addWidget(b)
        right.addLayout(r)
        note = QLabel("নিরাপত্তা: শাটডাউন/রিস্টার্ট/ডিলিট/সেন্ড কমান্ড কাস্টম কমান্ডের ভেতরে চালানো যায় না।")
        note.setObjectName("muted")
        note.setWordWrap(True)
        right.addWidget(note)
        root.addLayout(right, 4)
        self.reload()

    def reload(self, select: int | None = None):
        self.listw.blockSignals(True)
        self.listw.clear()
        for c in self.db.list_custom():
            it = QListWidgetItem(("" if c["enabled"] else "⏸ ") + c["name"])
            it.setData(256, c)
            self.listw.addItem(it)
            if select == c["id"]:
                self.listw.setCurrentItem(it)
        self.listw.blockSignals(False)
        if select is None:
            self.new()

    def new(self):
        self.cid = None
        self.name.clear()
        self.phrases.clear()
        self.enabled.setChecked(True)
        self.steps.setRowCount(0)
        self.add_step()

    def _select(self, cur, _prev):
        if not cur:
            return
        c = cur.data(256)
        self.cid = c["id"]
        self.name.setText(c["name"])
        self.phrases.setPlainText("\n".join(c["phrases"]))
        self.enabled.setChecked(c["enabled"])
        self.steps.setRowCount(0)
        for st in c["steps"]:
            self.add_step(st.get("type", "open_app"), st.get("value", ""))

    def add_step(self, kind: str = "open_app", value: str = ""):
        row = self.steps.rowCount()
        self.steps.insertRow(row)
        cb = QComboBox()
        for k, label in STEP_TYPES:
            cb.addItem(label, k)
        cb.setCurrentIndex(max(0, [k for k, _ in STEP_TYPES].index(kind) if kind in dict(STEP_TYPES) else 0))
        self.steps.setCellWidget(row, 0, cb)
        self.steps.setItem(row, 1, QTableWidgetItem(str(value)))

    def del_step(self):
        r = self.steps.currentRow()
        if r >= 0:
            self.steps.removeRow(r)

    def move(self, d: int):
        r = self.steps.currentRow()
        t = r + d
        if r < 0 or not 0 <= t < self.steps.rowCount():
            return
        a, b = self._row(r), self._row(t)
        self._set_row(r, *b)
        self._set_row(t, *a)
        self.steps.setCurrentCell(t, 1)

    def _row(self, r):
        return self.steps.cellWidget(r, 0).currentData(), (self.steps.item(r, 1).text() if self.steps.item(r, 1) else "")

    def _set_row(self, r, kind, val):
        cb = self.steps.cellWidget(r, 0)
        cb.setCurrentIndex([k for k, _ in STEP_TYPES].index(kind))
        self.steps.setItem(r, 1, QTableWidgetItem(val))

    def save(self) -> bool:
        name = self.name.text().strip()
        phrases = [p.strip() for p in self.phrases.toPlainText().splitlines() if p.strip()]
        steps = [{"type": k, "value": v} for k, v in (self._row(r) for r in range(self.steps.rowCount())) if v or k == "say"]
        if not name or not phrases or not steps:
            QMessageBox.warning(self, "অসম্পূর্ণ", "নাম, অন্তত একটি বাক্য এবং অন্তত একটি ধাপ দিন।")
            return False
        self.cid = self.db.save_custom(self.cid, name, phrases, steps, self.enabled.isChecked())
        self.reload(select=self.cid)
        return True

    def delete(self):
        if self.cid and QMessageBox.question(self, "নিশ্চিত?", "কমান্ডটি মুছে ফেলবেন?") == QMessageBox.StandardButton.Yes:
            self.db.delete_custom(self.cid)
            self.reload()

    def test(self):
        if self.save():
            phrase = [p for p in self.phrases.toPlainText().splitlines() if p.strip()][0]
            self.service.engine.handle_text(phrase, source="text")
