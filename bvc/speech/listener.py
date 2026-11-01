"""Microphone capture + voice-activity detection. Emits one float32 16 kHz array per utterance.

Nothing is written to disk: audio lives only in RAM until it has been transcribed.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from typing import Callable, Optional

import numpy as np

log = logging.getLogger("bvc.listener")
SR = 16000
FRAME_MS = 30
FRAME = SR * FRAME_MS // 1000          # 480 samples
MAX_UTTERANCE_MS = 12000


class VAD:
    """webrtcvad when installed, otherwise an adaptive energy detector."""

    def __init__(self, aggressiveness: int, energy_threshold: float):
        self._min_energy = float(energy_threshold)
        self._floor = 100.0
        self._webrtc = None
        try:
            import webrtcvad
            self._webrtc = webrtcvad.Vad(max(0, min(3, int(aggressiveness))))
        except Exception:
            log.info("webrtcvad not available - using energy VAD")

    @property
    def backend(self) -> str:
        return "webrtcvad" if self._webrtc else "energy"

    def is_speech(self, frame: bytes, rms: float) -> bool:
        if self._webrtc:
            try:
                return bool(self._webrtc.is_speech(frame, SR)) and rms > 80
            except Exception:
                pass
        thr = max(self._min_energy, self._floor * 2.5)
        speech = rms > thr
        if not speech:
            self._floor = 0.95 * self._floor + 0.05 * rms
        return speech


class MicListener:
    def __init__(self, settings, on_utterance: Callable[[np.ndarray], None],
                 on_level: Optional[Callable[[float], None]] = None,
                 is_blocked: Optional[Callable[[], bool]] = None,
                 on_error: Optional[Callable[[str], None]] = None):
        self.s = settings
        self.on_utterance = on_utterance
        self.on_level = on_level or (lambda v: None)
        self.is_blocked = is_blocked or (lambda: False)
        self.on_error = on_error or (lambda m: None)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="bvc-mic")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None

    def _run(self) -> None:
        try:
            import sounddevice as sd
        except Exception as e:
            self.on_error(f"sounddevice লোড করা যায়নি: {e}")
            return
        frames: "queue.Queue[bytes]" = queue.Queue(maxsize=400)

        def cb(indata, n, t, status):
            try:
                frames.put_nowait(indata.tobytes())
            except queue.Full:
                pass

        vad = VAD(self.s.get("vad_aggressiveness"), self.s.get("energy_threshold"))
        end_frames = max(3, int(self.s.get("end_silence_ms")) // FRAME_MS)
        min_ms = int(self.s.get("min_speech_ms"))
        pre: deque = deque(maxlen=10)
        recent: deque = deque(maxlen=8)
        voiced: list[bytes] = []
        active, silence = False, 0
        try:
            with sd.InputStream(samplerate=SR, channels=1, dtype="int16", blocksize=FRAME,
                                device=self.s.get("mic_device"), callback=cb):
                log.info("microphone open (VAD=%s)", vad.backend)
                while not self._stop.is_set():
                    try:
                        frame = frames.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    pcm = np.frombuffer(frame, dtype=np.int16)
                    rms = float(np.sqrt(np.mean(pcm.astype(np.float32) ** 2))) if pcm.size else 0.0
                    self.on_level(min(1.0, rms / 6000.0))
                    if self.is_blocked():                      # muted / assistant is speaking
                        pre.clear(); recent.clear(); voiced = []; active = False; silence = 0
                        continue
                    if len(frame) != FRAME * 2:
                        continue
                    sp = vad.is_speech(frame, rms)
                    recent.append(sp)
                    if not active:
                        pre.append(frame)
                        if sum(recent) >= 5:
                            active, voiced, silence = True, list(pre), 0
                    else:
                        voiced.append(frame)
                        silence = 0 if sp else silence + 1
                        total_ms = len(voiced) * FRAME_MS
                        if silence >= end_frames or total_ms >= MAX_UTTERANCE_MS:
                            speech_ms = total_ms - silence * FRAME_MS
                            if speech_ms >= min_ms:
                                audio = np.frombuffer(b"".join(voiced), dtype=np.int16).astype(np.float32) / 32768.0
                                try:
                                    self.on_utterance(audio)
                                except Exception:
                                    log.exception("utterance handler failed")
                            pre.clear(); recent.clear(); voiced = []; active = False; silence = 0
        except Exception as e:
            log.exception("microphone error")
            self.on_error(f"মাইক্রোফোন খোলা যায়নি: {e}")


def list_input_devices() -> list[tuple[int, str]]:
    try:
        import sounddevice as sd
        out = []
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0:
                out.append((i, d["name"]))
        return out
    except Exception:
        return []
