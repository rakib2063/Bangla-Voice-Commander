"""Offline speech-to-text (faster-whisper / CTranslate2). Models are loaded ONLY from local folders:

    <app>/models/whisper/<name>/model.bin   (+ config.json, tokenizer.json, vocabulary.*)

No network access is ever attempted. Run tools/fetch_models.py once (at build time) to populate them.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from ..nlp.intents import PROMPT_HINT
from ..paths import model_roots

log = logging.getLogger("bvc.stt")

_HALLUCINATIONS = {"ধন্যবাদ", "thanks for watching", "thank you", "thank you for watching",
                   "subtitles by the amara.org community", "বন্ধুরা", "চ্যানেলটি সাবস্ক্রাইব করুন", "you", "."}


@dataclass
class Transcript:
    text: str
    language: str = ""
    confidence: float = 0.0


def available_models() -> list[tuple[str, str]]:
    out, seen = [], set()
    for root in model_roots():
        w = root / "whisper"
        if w.is_dir():
            for d in sorted(w.iterdir()):
                if (d / "model.bin").exists() and d.name not in seen:
                    seen.add(d.name)
                    out.append((d.name, d.name))
    return out


def find_model_dir(name: str) -> Optional[Path]:
    custom = Path(name)
    if custom.is_absolute() and (custom / "model.bin").exists():
        return custom
    for root in model_roots():
        d = root / "whisper" / name
        if (d / "model.bin").exists():
            return d
    return None


class Recognizer:
    name = "base"
    ready = False

    def load(self, progress: Callable[[str], None]) -> None: ...
    def transcribe(self, audio: np.ndarray) -> Transcript: ...


class FasterWhisperRecognizer(Recognizer):
    name = "faster-whisper (offline)"

    def __init__(self, settings):
        self.s = settings
        self.model = None
        self._lock = threading.Lock()

    def load(self, progress):
        from faster_whisper import WhisperModel
        name = (self.s.get("custom_model_path") or "").strip() or self.s.get("whisper_model")
        path = find_model_dir(name)
        if path is None:
            have = ", ".join(n for n, _ in available_models()) or "কোনোটিই নেই"
            raise FileNotFoundError(
                f"স্পিচ মডেল '{name}' পাওয়া যায়নি। উপলব্ধ: {have}। "
                f"মডেল ফোল্ডারে (models\\whisper\\{name}) ফাইলগুলো রাখুন — README দেখুন।")
        device = self.s.get("whisper_device")
        if device == "auto":
            try:
                import ctranslate2
                device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            except Exception:
                device = "cpu"
        compute = self.s.get("whisper_compute")
        if compute == "auto":
            compute = "float16" if device == "cuda" else "int8"
        threads = max(2, min(8, (os.cpu_count() or 4) - 1))
        progress(f"অফলাইন মডেল লোড হচ্ছে: {path.name} ({device}/{compute})…")
        try:
            self.model = WhisperModel(str(path), device=device, compute_type=compute, cpu_threads=threads,
                                      local_files_only=True)
        except Exception:
            if device != "cpu":
                log.warning("GPU load failed - falling back to CPU", exc_info=True)
                self.model = WhisperModel(str(path), device="cpu", compute_type="int8", cpu_threads=threads,
                                          local_files_only=True)
            else:
                raise
        # warm-up so the first real command is fast
        self.model.transcribe(np.zeros(16000, dtype=np.float32), language="bn", beam_size=1)
        self.ready = True
        progress(f"মডেল প্রস্তুত ({path.name}, অফলাইন)।")

    def transcribe(self, audio: np.ndarray) -> Transcript:
        if not self.model:
            return Transcript("")
        lang = self.s.get("whisper_language")
        lang = None if lang == "auto" else lang
        with self._lock:
            segments, info = self.model.transcribe(
                audio, language=lang, beam_size=int(self.s.get("whisper_beam")), temperature=0.0,
                condition_on_previous_text=False, vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
                initial_prompt=PROMPT_HINT if lang in ("bn", None) else None,
                no_speech_threshold=0.6, without_timestamps=True)
            parts, conf = [], []
            for seg in segments:
                if seg.no_speech_prob > 0.6 or seg.avg_logprob < -1.2:
                    continue
                parts.append(seg.text.strip())
                conf.append(float(np.exp(seg.avg_logprob)))
        text = " ".join(p for p in parts if p).strip()
        if text.lower().strip(" .!।") in _HALLUCINATIONS:
            return Transcript("")
        return Transcript(text, getattr(info, "language", ""), float(np.mean(conf)) if conf else 0.0)


def make_recognizer(settings) -> Recognizer:
    return FasterWhisperRecognizer(settings)
