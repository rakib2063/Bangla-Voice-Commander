"""Bangla text-to-speech - fully offline.

 1. offline : bundled sherpa-onnx + MMS Bangla VITS model (models/tts/vits-mms-ben). Speech is synthesised
              locally; each phrase is cached as a .wav so repeated feedback is instant.
 2. pyttsx3 : Windows SAPI - works only if a Bangla voice is installed in Windows.
If neither is available the app stays silent and shows the feedback text on screen instead.
No network access is ever used.
"""
from __future__ import annotations

import hashlib
import logging
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from .paths import cache_dir, model_roots

log = logging.getLogger("bvc.tts")


class TTS:
    def __init__(self, settings):
        self.s = settings
        self._q: "queue.Queue[Optional[str]]" = queue.Queue()
        self._speaking = threading.Event()
        self._last_end = 0.0
        self._stop_play = threading.Event()
        self._alias = None
        self._pyttsx = None
        self._sherpa_tts = None
        self._warned_no_voice = False
        self._thread = threading.Thread(target=self._worker, daemon=True, name="bvc-tts")
        self._thread.start()

    # ---- public ------------------------------------------------------------------
    @property
    def speaking(self) -> bool:
        """True while speaking and shortly afterwards (prevents the mic hearing the app)."""
        return self._speaking.is_set() or (time.time() - self._last_end) < 0.5

    def say(self, text: Optional[str]) -> None:
        if text and self.s.get("tts_enabled") and self.s.get("tts_engine") != "off":
            self._q.put(text)

    def stop(self) -> None:
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass
        self._stop_play.set()

    def shutdown(self) -> None:
        self.stop()
        self._q.put(None)

    # ---- worker ---------------------------------------------------------------------
    def _worker(self) -> None:
        while True:
            text = self._q.get()
            if text is None:
                return
            self._stop_play.clear()
            self._speaking.set()
            try:
                self._speak(text)
            except Exception:
                log.exception("TTS failed")
            finally:
                self._last_end = time.time()
                self._speaking.clear()

    def _speak(self, text: str) -> None:
        engine = self.s.get("tts_engine")
        if engine == "offline":
            try:
                path = self._offline_wav(text)
                if path:
                    self._play_file(path)
                    return
            except Exception:
                log.warning("offline TTS failed - trying Windows SAPI", exc_info=True)
        self._speak_pyttsx3(text)

    # ---- sherpa-onnx (bundled MMS Bangla) -------------------------------------------------
    def tts_model_dir(self) -> Optional[Path]:
        for root in model_roots():
            d = root / "tts" / "vits-mms-ben"
            if (d / "model.onnx").exists() and (d / "tokens.txt").exists():
                return d
        return None

    def _sherpa(self):
        if self._sherpa_tts is None:
            import sherpa_onnx
            d = self.tts_model_dir()
            if d is None:
                raise FileNotFoundError("models/tts/vits-mms-ben not found")
            cfg = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=str(d / "model.onnx"), lexicon="",
                                                          tokens=str(d / "tokens.txt")),
                num_threads=2, provider="cpu"))
            self._sherpa_tts = sherpa_onnx.OfflineTts(cfg)
        return self._sherpa_tts

    def synth_to_wav(self, text: str, path: Path) -> bool:
        import wave
        import numpy as np
        audio = self._sherpa().generate(text, sid=0, speed=float(self.s.get("tts_speed") or 1.0))
        samples = np.asarray(audio.samples, dtype=np.float32)
        if samples.size == 0:
            return False
        pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(int(audio.sample_rate))
            w.writeframes(pcm.tobytes())
        return True

    def _offline_wav(self, text: str) -> Optional[Path]:
        if self.tts_model_dir() is None:
            return None
        key = hashlib.sha1(f"mms-ben|{self.s.get('tts_speed')}|{text}".encode("utf-8")).hexdigest()
        d = cache_dir() / "tts"
        d.mkdir(exist_ok=True)
        path = d / f"{key}.wav"
        if path.exists() and path.stat().st_size > 0:
            return path
        return path if self.synth_to_wav(text, path) else None

    def _play_file(self, path: Path) -> None:
        if sys.platform != "win32":
            log.info("(no audio playback off Windows) %s", path.name)
            return
        import ctypes
        winmm = ctypes.windll.winmm
        alias = f"bvc{int(time.time() * 1000) % 10**9}"

        def mci(cmd: str):
            buf = ctypes.create_unicode_buffer(256)
            err = winmm.mciSendStringW(cmd, buf, 255, 0)
            return err, buf.value
        err, _ = mci(f'open "{path}" type waveaudio alias {alias}')
        if err:
            raise RuntimeError(f"MCI open failed ({err})")
        try:
            mci(f"play {alias}")
            time.sleep(0.05)
            while not self._stop_play.is_set():
                err, mode = mci(f"status {alias} mode")
                if err or mode != "playing":
                    break
                time.sleep(0.04)
            if self._stop_play.is_set():
                mci(f"stop {alias}")
        finally:
            mci(f"close {alias}")

    def _speak_pyttsx3(self, text: str) -> None:
        try:
            import pyttsx3
        except ImportError:
            return
        if self._pyttsx is None:
            self._pyttsx = pyttsx3.init()
            for v in self._pyttsx.getProperty("voices"):
                blob = f"{v.name} {getattr(v, 'languages', '')} {v.id}".lower()
                if any(k in blob for k in ("bengali", "bangla", "bn-bd", "bn-in", "bn_")):
                    self._pyttsx.setProperty("voice", v.id)
                    self._bn_voice = True
                    break
            else:
                self._bn_voice = False
        if not getattr(self, "_bn_voice", False):
            if not self._warned_no_voice:
                log.warning("No offline Bangla voice available - feedback is shown on screen only.")
                self._warned_no_voice = True
            return
        self._pyttsx.say(text)
        self._pyttsx.runAndWait()


def list_pyttsx3_voices() -> list[str]:
    try:
        import pyttsx3
        return [v.name for v in pyttsx3.init().getProperty("voices")]
    except Exception:
        return []
