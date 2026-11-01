"""Ties microphone -> VAD -> recognizer -> command engine together."""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Optional

from .engine import CommandEngine
from .speech.listener import MicListener
from .speech.recognizer import Recognizer, make_recognizer
from .tts import TTS

log = logging.getLogger("bvc.service")


class VoiceService:
    def __init__(self, settings, db, emit: Callable):
        self.s, self.db, self.emit = settings, db, emit
        self.tts = TTS(settings)
        self.engine = CommandEngine(settings, db, self.tts, emit)
        self.recognizer: Optional[Recognizer] = None
        self.listener: Optional[MicListener] = None
        self.muted = False
        self._q: "queue.Queue" = queue.Queue(maxsize=4)
        self._level_tick = 0
        self._starting = False
        self._worker = threading.Thread(target=self._loop, daemon=True, name="bvc-stt")
        self._worker.start()

    # ---- listening control -------------------------------------------------------------------
    @property
    def listening(self) -> bool:
        return bool(self.listener and self.listener.running)

    def start_listening(self) -> None:
        if self.listening or self._starting:
            return
        self._starting = True
        threading.Thread(target=self._start_bg, daemon=True, name="bvc-start").start()

    def _start_bg(self) -> None:
        try:
            if self.recognizer is None or not self.recognizer.ready:
                self.emit("status", state="loading", text="লোড হচ্ছে…")
                self.recognizer = make_recognizer(self.s)
                self.recognizer.load(lambda m: self.emit("model", message=m))
            self.listener = MicListener(self.s, self._on_audio, self._on_level, self._blocked,
                                        lambda m: self._fail(m))
            self.listener.start()
            self.emit("status", state="listening", text="শুনছি…")
            self.tts.say("শুনছি।")
        except Exception as e:
            log.exception("start failed")
            self._fail(f"শুরু করা যায়নি: {e}")
        finally:
            self._starting = False

    def stop_listening(self) -> None:
        if self.listener:
            self.listener.stop()
            self.listener = None
        self.engine.emergency_stop(announce=False)
        self.emit("level", value=0.0)
        self.emit("status", state="idle", text="বন্ধ")

    def set_muted(self, muted: bool) -> None:
        self.muted = muted
        self.emit("status", state="muted" if muted else "listening", text="মাইক মিউট" if muted else "শুনছি…")

    def reload_recognizer(self) -> None:
        was = self.listening
        if was:
            self.stop_listening()
        self.recognizer = None
        if was:
            self.start_listening()

    def shutdown(self) -> None:
        try:
            if self.listener:
                self.listener.stop()
            self.engine.shutdown()
            self.tts.shutdown()
            self._q.put(None)
        except Exception:
            log.exception("shutdown")

    def register_hotkey(self) -> None:
        hk = self.s.get("emergency_hotkey")
        if not hk:
            return
        try:
            import keyboard
            keyboard.add_hotkey(hk, lambda: self.engine.emergency_stop(), suppress=False)
            log.info("emergency hotkey: %s", hk)
        except Exception as e:
            log.warning("global hotkey unavailable: %s", e)

    # ---- pipeline -------------------------------------------------------------------------------
    def _fail(self, message: str) -> None:
        self.emit("error", message=message)
        self.emit("status", state="error", text=message)

    def _blocked(self) -> bool:
        return self.muted or self.tts.speaking

    def _on_level(self, v: float) -> None:
        self._level_tick += 1
        if self._level_tick % 3 == 0:
            self.emit("level", value=v)

    def _on_audio(self, audio) -> None:
        try:
            self._q.put_nowait(audio)
        except queue.Full:
            log.warning("recogniser is behind - dropping an utterance")

    def _loop(self) -> None:
        while True:
            audio = self._q.get()
            if audio is None:
                return
            if self.recognizer is None or not self.recognizer.ready:
                continue
            try:
                self.emit("status", state="thinking", text="বুঝছি…")
                t0 = time.time()
                tr = self.recognizer.transcribe(audio)
                log.info("heard %r (%.2fs, conf=%.2f)", tr.text, time.time() - t0, tr.confidence)
                if tr.text:
                    self.engine.handle_text(tr.text, source="voice")
            except Exception as e:
                log.exception("recognition failed")
                self.emit("error", message=f"রিকগনিশনে সমস্যা: {e}")
            finally:
                if self.listening:
                    self.emit("status", state="sleeping" if self.engine.asleep else "listening",
                              text="ঘুমিয়ে আছি (বলুন: জাগো)" if self.engine.asleep else "শুনছি…")
