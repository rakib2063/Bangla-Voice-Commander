"""Download the offline models into ./models (run ONCE on a machine with internet, at build time).

    python tools/fetch_models.py                 # whisper 'small' + Bangla TTS
    python tools/fetch_models.py --whisper medium

Layout produced (this is what gets bundled into the installer):
    models/whisper/<size>/model.bin ...          faster-whisper (CTranslate2) model   - MIT
    models/tts/vits-mms-ben/model.onnx,tokens.txt Meta MMS-TTS Bangla via sherpa-onnx  - CC-BY-NC 4.0
"""
import argparse
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WHISPER_REPOS = {"tiny": "Systran/faster-whisper-tiny", "base": "Systran/faster-whisper-base",
                 "small": "Systran/faster-whisper-small", "medium": "Systran/faster-whisper-medium"}
TTS_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-mms-ben.tar.bz2"

LICENSES = """Bundled model licences
======================
* faster-whisper models (Systran/faster-whisper-*): CTranslate2 conversions of OpenAI Whisper. MIT licence.
  Whisper (c) OpenAI. https://github.com/openai/whisper
* Silero VAD (inside faster-whisper): MIT licence.
* MMS-TTS Bangla (facebook/mms-tts-ben) via sherpa-onnx 'vits-mms-ben': CC-BY-NC 4.0 (Meta Platforms).
  NON-COMMERCIAL use only, attribution required. Replace models/tts/vits-mms-ben with another sherpa-onnx VITS
  model if you need commercial redistribution.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--whisper", default="small", choices=sorted(WHISPER_REPOS))
    ap.add_argument("--skip-tts", action="store_true")
    a = ap.parse_args()

    from huggingface_hub import snapshot_download
    dest = ROOT / "models" / "whisper" / a.whisper
    print(f"[1/2] Whisper '{a.whisper}' -> {dest}")
    snapshot_download(WHISPER_REPOS[a.whisper], local_dir=str(dest),
                      allow_patterns=["config.json", "model.bin", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"])
    assert (dest / "model.bin").exists(), "model.bin missing"

    if not a.skip_tts:
        tdest = ROOT / "models" / "tts" / "vits-mms-ben"
        print(f"[2/2] Bangla TTS -> {tdest}")
        tdest.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            arc = Path(tmp) / "tts.tar.bz2"
            urllib.request.urlretrieve(TTS_URL, arc)
            with tarfile.open(arc) as tf:
                tf.extractall(tmp)
            src = next(Path(tmp).glob("vits-mms-ben"))
            for name in ("model.onnx", "tokens.txt"):
                shutil.copy2(src / name, tdest / name)
    (ROOT / "models" / "MODEL_LICENSES.txt").write_text(LICENSES, encoding="utf-8")
    print("done.")


if __name__ == "__main__":
    sys.exit(main())
