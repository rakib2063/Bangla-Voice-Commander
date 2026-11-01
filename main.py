"""Bangla Voice Commander - entry point.

    BanglaVoiceCommander.exe                    start the app
    BanglaVoiceCommander.exe --selftest         verify offline models, TTS, parser, mic (writes a JSON report)
"""
import argparse
import json
import logging
import logging.handlers
import os
import socket
import sys
import time


def setup_logging() -> None:
    from bvc.paths import logs_dir
    h = logging.handlers.RotatingFileHandler(logs_dir() / "bvc.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[h])


def network_reachable() -> bool:
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=2).close()
        return True
    except OSError:
        return False


# ------------------------------------------------------------------------------------------------
def selftest(report_path: str) -> int:
    """Everything the app needs at run time, verified without touching the network."""
    import numpy as np
    from bvc.config import Settings
    from bvc.db import Database
    from bvc.nlp.parser import Parser
    from bvc.speech.listener import list_input_devices
    from bvc.speech.recognizer import available_models, make_recognizer
    from bvc.tts import TTS

    rep: dict = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "frozen": bool(getattr(sys, "frozen", False)),
                 "network_reachable": network_reachable(), "checks": {}, "roundtrip": []}
    ok_all = True

    def check(name, fn):
        nonlocal ok_all
        t0 = time.time()
        try:
            detail = fn()
            rep["checks"][name] = {"ok": True, "detail": str(detail), "sec": round(time.time() - t0, 2)}
        except Exception as e:
            ok_all = False
            rep["checks"][name] = {"ok": False, "detail": f"{type(e).__name__}: {e}", "sec": round(time.time() - t0, 2)}

    db = Database()
    settings = Settings(db)
    parser = Parser()
    check("parser", lambda: [parser.parse(t).intent for t in ("নিচে স্ক্রল করো", "Stop", "ফেসবুক খোলো")] == ["scroll_down", "stop_all", "open_target"] or (_ for _ in ()).throw(AssertionError("wrong intents")))
    check("models_present", lambda: available_models() or (_ for _ in ()).throw(FileNotFoundError("no whisper model")))
    rec = make_recognizer(settings)
    check("whisper_load_offline", lambda: rec.load(lambda m: None) or "loaded")
    tts = TTS(settings)
    check("tts_model_present", lambda: str(tts.tts_model_dir() or (_ for _ in ()).throw(FileNotFoundError("tts model missing"))))

    def roundtrip():
        """Bangla phrase -> offline TTS -> offline Whisper -> parser. A real end-to-end offline check."""
        from pathlib import Path
        import wave
        from bvc.paths import cache_dir
        phrases = [("নিচে স্ক্রল করো", "scroll_down"), ("উপরে যাও", "scroll_up"), ("থামো", "stop_all"),
                   ("ফেসবুক খোলো", "open_target"), ("নতুন ট্যাব খোলো", "new_tab"), ("ভলিউম বাড়াও", "vol_up")]
        hits = 0
        for text, want in phrases:
            p = Path(cache_dir()) / "selftest.wav"
            tts.synth_to_wav(text, p)
            with wave.open(str(p), "rb") as w:
                sr, raw = w.getframerate(), w.readframes(w.getnframes())
            x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
            if sr != 16000:
                x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * 16000 / sr)), np.arange(len(x)), x).astype(np.float32)
            x = np.concatenate([np.zeros(4000, np.float32), x, np.zeros(8000, np.float32)])
            heard = rec.transcribe(x).text
            m = parser.parse(heard)
            got = m.intent if m else None
            hits += got == want
            rep["roundtrip"].append({"said": text, "heard": heard, "intent": got, "expected": want, "pass": got == want})
        return f"{hits}/{len(phrases)} synthetic phrases understood"
    if rep["checks"]["whisper_load_offline"]["ok"] and rep["checks"]["tts_model_present"]["ok"]:
        check("roundtrip_tts_to_stt_to_command", roundtrip)

    devs = list_input_devices()
    rep["checks"]["microphone"] = {"ok": bool(devs), "detail": f"{len(devs)} input device(s)" if devs else "no microphone found (informational)"}
    rep["overall_ok"] = ok_all
    os.makedirs(os.path.dirname(os.path.abspath(report_path)), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    if sys.stdout:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0 if ok_all else 1


# ------------------------------------------------------------------------------------------------
def seed_examples(db) -> None:
    if db.list_custom():
        return
    db.save_custom(None, "আমার কাজ", ["আমার কাজ শুরু করো", "কাজ শুরু করো"], [
        {"type": "open_app", "value": "ক্রোম"}, {"type": "wait", "value": "2"},
        {"type": "open_url", "value": "facebook.com"}, {"type": "open_url", "value": "youtube.com"},
        {"type": "say", "value": "আপনার কাজ শুরু হয়েছে।"}])


def run_gui() -> int:
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox
    from bvc import APP_NAME
    from bvc.config import Settings
    from bvc.db import Database
    from bvc.paths import resource_dir
    from bvc.service import VoiceService
    from bvc.speech.recognizer import available_models
    from bvc.speech.listener import list_input_devices
    from bvc.ui.main_window import Bridge, MainWindow
    from bvc.ui.theme import apply_theme

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    icon = resource_dir() / "assets" / "icon.ico"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    apply_theme(app)
    db = Database()
    settings = Settings(db)
    seed_examples(db)
    bridge = Bridge()
    service = VoiceService(settings, db, bridge.emit_event)
    win = MainWindow(service, settings, db, bridge)
    win.show()
    service.register_hotkey()

    problems = []
    if not available_models():
        problems.append("কোনো অফলাইন স্পিচ মডেল পাওয়া যায়নি (models\\whisper\\small)। অ্যাপটি পুনরায় ইনস্টল করুন অথবা README দেখুন।")
    if not list_input_devices():
        problems.append("কোনো মাইক্রোফোন পাওয়া যায়নি। মাইক লাগিয়ে Windows Settings → Privacy → Microphone-এ অনুমতি দিন।")
    if service.tts.tts_model_dir() is None and settings.get("tts_engine") == "offline":
        problems.append("অফলাইন বাংলা TTS মডেল নেই — ভয়েস ফিডব্যাক বন্ধ থাকবে, উত্তর স্ক্রিনে দেখানো হবে।")
    if problems:
        bridge.emit_event("error", message=" | ".join(problems))
    if settings.get("start_listening_on_launch") and not problems:
        service.start_listening()
    return app.exec()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--report", default=None)
    args, _ = ap.parse_known_args()
    setup_logging()
    if args.selftest:
        from bvc.paths import logs_dir
        return selftest(args.report or str(logs_dir() / "selftest.json"))
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
