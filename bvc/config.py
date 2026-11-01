"""Settings with defaults, persisted in SQLite."""
from __future__ import annotations

import threading
from typing import Any, Callable

from .db import Database

DEFAULTS: dict[str, Any] = {
    # speech recognition
    "whisper_model": "small",            # folder name under models/whisper/ (bundled, offline)
    "custom_model_path": "",             # absolute path to any CTranslate2 Whisper folder (overrides the above)
    "whisper_device": "auto",            # auto | cpu | cuda
    "whisper_compute": "auto",           # auto | int8 | float16 | ...
    "whisper_language": "bn",            # bn | en | auto
    "whisper_beam": 3,
    # microphone / VAD
    "mic_device": None,                  # None = system default, else device index
    "vad_aggressiveness": 2,             # 0..3 (webrtcvad)
    "end_silence_ms": 500,
    "min_speech_ms": 250,
    "energy_threshold": 350,             # only used by the fallback energy VAD
    # behaviour
    "mode": "command",                   # command | continuous
    "require_wake_word": False,
    "wake_word": "কমান্ডার",
    "start_listening_on_launch": False,
    "confirm_timeout_s": 15,
    "click_cooldown_ms": 800,
    "scroll_speed": 3.0,                 # wheel notches per tick in continuous mode
    "scroll_interval_ms": 120,
    "mouse_step": 120,
    "browser": "default",                # default | chrome | edge | firefox | brave
    "emergency_hotkey": "ctrl+alt+q",
    "dry_run": False,                    # log actions instead of executing them
    # voice feedback
    "tts_enabled": True,
    "tts_engine": "offline",             # offline (bundled sherpa-onnx Bangla) | pyttsx3 (Windows SAPI) | off
    "tts_speed": 1.0,
    # privacy
    "keep_history": True,
    "history_days": 30,
    # user-extendable lexicon: {"নাম": {"kind": "url|app|uri", "value": "..."}}
    "aliases": {},
    # override accessible names used by the Facebook module (see README)
    "facebook_labels": {},
}


class Settings:
    def __init__(self, db: Database):
        self._db = db
        self._lock = threading.RLock()
        self._values = dict(DEFAULTS)
        self._values.update({k: v for k, v in db.all_settings().items() if k in DEFAULTS})
        self._listeners: list[Callable[[dict], None]] = []

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._values.get(key, default if default is not None else DEFAULTS.get(key))

    __getitem__ = get

    def set(self, key: str, value: Any) -> None:
        self.update({key: value})

    def update(self, changes: dict) -> None:
        with self._lock:
            for k, v in changes.items():
                self._values[k] = v
                self._db.set_setting(k, v)
        for cb in list(self._listeners):
            cb(dict(changes))

    def on_change(self, cb: Callable[[dict], None]) -> None:
        self._listeners.append(cb)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._values)
