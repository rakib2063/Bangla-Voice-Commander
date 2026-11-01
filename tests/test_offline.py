"""Static guarantee: the app source never calls online speech / AI / TTS services."""
import os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORBIDDEN = re.compile(r"edge_tts|speech_recognition|recognize_google|import openai|import anthropic|api\.openai|api\.anthropic|requests\.|"
                       r"urllib\.request|http\.client|googleapiclient|azure\.cognitiveservices|boto3", re.I)


class OfflineTests(unittest.TestCase):
    def test_no_online_services_in_runtime_code(self):
        bad = []
        for dp, _dn, fn in os.walk(os.path.join(ROOT, "bvc")):
            for f in fn:
                if f.endswith(".py"):
                    txt = open(os.path.join(dp, f), encoding="utf-8").read()
                    for i, line in enumerate(txt.splitlines(), 1):
                        if FORBIDDEN.search(line) and not line.lstrip().startswith("#"):
                            bad.append(f"{f}:{i}: {line.strip()}")
        self.assertEqual(bad, [])

    def test_whisper_loaded_local_only(self):
        src = open(os.path.join(ROOT, "bvc", "speech", "recognizer.py"), encoding="utf-8").read()
        self.assertIn("local_files_only=True", src)
        self.assertNotIn("download_root", src)

    def test_defaults_are_offline(self):
        from bvc.config import DEFAULTS
        self.assertEqual(DEFAULTS["tts_engine"], "offline")
        self.assertNotIn("stt_backend", DEFAULTS)


if __name__ == "__main__":
    unittest.main()
