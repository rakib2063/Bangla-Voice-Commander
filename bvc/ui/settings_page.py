"""Settings: speech recognition, microphone, automation, voice feedback, privacy."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from ..paths import data_dir
from ..speech.listener import list_input_devices
from ..speech.recognizer import available_models

RECOGNIZER_KEYS = {"whisper_model", "custom_model_path", "whisper_device", "whisper_compute", "whisper_language",
                   "whisper_beam", "stt_backend"}


class SettingsPage(QWidget):
    def __init__(self, service, settings, db):
        super().__init__()
        self.service, self.s, self.db = service, settings, db
        self.fields: dict = {}
        outer = QVBoxLayout(self)
        h = QLabel("সেটিংস")
        h.setObjectName("h1")
        outer.addWidget(h)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self.lay = QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        models = available_models() or [("(কোনো মডেল পাওয়া যায়নি)", "")]
        mics = [("সিস্টেম ডিফল্ট", None)] + [(f"{n}", i) for i, n in list_input_devices()]
        self.group("🗣  স্পিচ রিকগনিশন (সম্পূর্ণ অফলাইন)", [
            ("whisper_model", "মডেল", "combo", models),
            ("whisper_language", "ভাষা", "combo", [("বাংলা", "bn"), ("ইংরেজি", "en"), ("স্বয়ংক্রিয়", "auto")]),
            ("whisper_device", "ডিভাইস", "combo", [("স্বয়ংক্রিয়", "auto"), ("CPU", "cpu"), ("GPU (CUDA)", "cuda")]),
            ("whisper_beam", "নির্ভুলতা বনাম গতি (beam 1–5)", "spin", (1, 5)),
        ])
        self.group("🎙  মাইক্রোফোন ও ভয়েস ডিটেকশন", [
            ("mic_device", "মাইক্রোফোন", "combo", mics),
            ("vad_aggressiveness", "ভয়েস ডিটেকশন সংবেদনশীলতা (0 কম – 3 বেশি কঠোর)", "spin", (0, 3)),
            ("end_silence_ms", "কথা শেষ ধরার বিরতি (ms)", "spin", (200, 2000)),
            ("energy_threshold", "ফলব্যাক শব্দসীমা", "spin", (50, 3000)),
        ])
        self.group("🖱  অটোমেশন", [
            ("scroll_speed", "স্ক্রল গতি (notch/tick)", "dspin", (0.5, 15.0)),
            ("scroll_interval_ms", "স্ক্রল বিরতি (ms)", "spin", (30, 1000)),
            ("mouse_step", "মাউস সরানোর দূরত্ব (px)", "spin", (20, 600)),
            ("click_cooldown_ms", "দ্রুত পরপর ক্লিক ঠেকানোর সময় (ms)", "spin", (200, 3000)),
            ("confirm_timeout_s", "নিশ্চিতকরণের সময় (সেকেন্ড)", "spin", (5, 60)),
            ("browser", "ব্রাউজার", "combo", [("ডিফল্ট", "default"), ("Chrome", "chrome"), ("Edge", "edge"),
                                              ("Firefox", "firefox"), ("Brave", "brave")]),
            ("require_wake_word", "কমান্ডের আগে ওয়েক-ওয়ার্ড লাগবে", "check", None),
            ("wake_word", "ওয়েক-ওয়ার্ড", "line", None),
            ("emergency_hotkey", "জরুরি স্টপ হটকি", "line", None),
            ("dry_run", "ড্রাই-রান (কিছু চালাবে না, শুধু লগ করবে)", "check", None),
        ])
        self.group("🔊  ভয়েস ফিডব্যাক", [
            ("tts_enabled", "বাংলায় উত্তর বলো", "check", None),
            ("tts_engine", "TTS ইঞ্জিন", "combo", [("অফলাইন (বান্ডেল করা)", "offline"), ("Windows SAPI বাংলা ভয়েস", "pyttsx3"),
                                                  ("বন্ধ", "off")]),
        ])
        self.group("🔒  গোপনীয়তা", [
            ("keep_history", "কমান্ডের ইতিহাস সংরক্ষণ করো (শুধু টেক্সট — অডিও কখনোই নয়)", "check", None),
            ("history_days", "ইতিহাস কত দিন রাখবে", "spin", (1, 365)),
            ("start_listening_on_launch", "অ্যাপ খুললেই শোনা শুরু করো", "check", None),
        ])
        r = QHBoxLayout()
        clear = QPushButton("ইতিহাস মুছে ফেলো")
        clear.clicked.connect(lambda: (db.clear_history(), QMessageBox.information(self, "ঠিক আছে", "ইতিহাস মুছে ফেলা হয়েছে।")))
        folder = QPushButton("ডেটা ফোল্ডার খোলো")
        folder.clicked.connect(lambda: os.startfile(str(data_dir())) if hasattr(os, "startfile") else None)
        save = QPushButton("💾  সেটিংস সেভ করো")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        for b in (clear, folder, save):
            r.addWidget(b)
        outer.addLayout(r)
        self.load()

    def group(self, title, specs):
        g = QGroupBox(title)
        f = QFormLayout(g)
        for key, label, kind, opt in specs:
            if kind == "combo":
                w = QComboBox()
                for text, val in opt:
                    w.addItem(text, val)
            elif kind == "spin":
                w = QSpinBox()
                w.setRange(*opt)
            elif kind == "dspin":
                w = QDoubleSpinBox()
                w.setRange(*opt)
                w.setSingleStep(0.5)
            elif kind == "check":
                w = QCheckBox()
            else:
                w = QLineEdit()
            self.fields[key] = (w, kind)
            f.addRow(label, w)
        self.lay.addWidget(g)

    def load(self):
        for key, (w, kind) in self.fields.items():
            v = self.s.get(key)
            if kind == "combo":
                i = w.findData(v)
                w.setCurrentIndex(max(0, i))
            elif kind in ("spin",):
                w.setValue(int(v))
            elif kind == "dspin":
                w.setValue(float(v))
            elif kind == "check":
                w.setChecked(bool(v))
            else:
                w.setText(str(v or ""))

    def save(self):
        changes = {}
        for key, (w, kind) in self.fields.items():
            v = (w.currentData() if kind == "combo" else w.value() if kind in ("spin", "dspin")
                 else w.isChecked() if kind == "check" else w.text().strip())
            if v != self.s.get(key):
                changes[key] = v
        if not changes:
            return
        self.s.update(changes)
        if RECOGNIZER_KEYS & set(changes):
            self.service.reload_recognizer()
        QMessageBox.information(self, "সেভ হয়েছে", "সেটিংস সেভ হয়েছে।" +
                                ("\nমাইক/ভয়েস ডিটেকশনের পরিবর্তন পরের বার শোনা শুরু করলে কার্যকর হবে।"
                                 if {"mic_device", "vad_aggressiveness", "end_silence_ms"} & set(changes) else ""))
