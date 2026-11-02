"""fetch_models.py logic with a fake downloader (no network, no huggingface_hub needed)."""
import os, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import fetch_models as fm


def make_tokens(path: Path, chars):
    path.write_text("\n".join(f"{c} {i}" for i, c in enumerate(chars)) + "\n", encoding="utf-8")


SRC = [("willwade/mms-tts-multilingual-models-onnx", "ben")]


def good_downloader(repo, filename, dest):
    """Mimics hf_hub_download: writes dest/_hf/<remote path> and returns it."""
    name = Path(filename).name
    p = Path(dest) / "_hf" / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    if name == "model.onnx":
        p.write_bytes(b"\0" * (fm.MIN_MODEL_BYTES + 10))
    else:
        make_tokens(p, sorted(fm.bangla_chars_needed()) + list(" abcdefghijklmnop"))
    return p


def flat_good(dest):
    """Plain files for the --tts-dir test."""
    good_downloader("-", "model.onnx", dest)
    good_downloader("-", "tokens.txt", dest)


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fm_"))

    def test_success_flattens_subfolder(self):
        src = fm.fetch_tts(self.tmp / "t", SRC, good_downloader, synth=False)
        self.assertIn("willwade/mms-tts-multilingual-models-onnx/ben", src)
        self.assertIn("Bangla coverage 100%", src)
        self.assertTrue((self.tmp / "t" / "model.onnx").exists())       # flat, not ben/model.onnx
        self.assertTrue((self.tmp / "t" / "tokens.txt").exists())
        self.assertFalse((self.tmp / "t" / "_hf").exists())             # temp download dir cleaned up

    def test_requests_the_ben_subfolder(self):
        asked = []
        def dl(repo, filename, dest):
            asked.append((repo, filename))
            return good_downloader(repo, filename, dest)
        fm.fetch_tts(self.tmp / "t", SRC, dl, synth=False)
        self.assertEqual(asked, [("willwade/mms-tts-multilingual-models-onnx", "ben/model.onnx"),
                                 ("willwade/mms-tts-multilingual-models-onnx", "ben/tokens.txt")])

    def test_default_source_is_the_verified_one(self):
        self.assertEqual(fm.TTS_SOURCES, SRC)

    def test_404_gives_clear_error_and_does_not_pass_silently(self):
        def dl(repo, filename, dest):
            raise fm.FetchError(f"Hugging Face repo '{repo}' does not exist or is private (404)")
        with self.assertRaises(fm.FetchError) as cm:
            fm.fetch_tts(self.tmp / "t", [("a/missing", ""), ("b/also-missing", "ben")], dl, synth=False)
        msg = str(cm.exception)
        self.assertIn("a/missing", msg)
        self.assertIn("b/also-missing/ben", msg)
        self.assertIn("--tts-dir", msg)
        self.assertIn("not silently skipped", msg)

    def test_falls_back_to_second_source(self):
        def dl(repo, filename, dest):
            if repo == "bad/repo":
                raise fm.FetchError("404")
            return good_downloader(repo, filename, dest)
        src = fm.fetch_tts(self.tmp / "t", [("bad/repo", ""), ("good/repo", "ben")], dl, synth=False)
        self.assertIn("good/repo", src)

    def test_rejects_fake_small_model(self):
        def dl(repo, filename, dest):
            p = Path(dest) / "_hf" / filename
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("version https://git-lfs.github.com/spec/v1" if filename.endswith("model.onnx") else "a 0\n")
            return p
        with self.assertRaises(fm.FetchError) as cm:
            fm.fetch_tts(self.tmp / "t", SRC, dl, synth=False)
        self.assertIn("not a real model", str(cm.exception))
        self.assertFalse((self.tmp / "t" / "model.onnx").exists())      # rejected files are removed

    def test_rejects_model_without_bangla_tokens(self):
        def dl(repo, filename, dest):
            p = Path(dest) / "_hf" / filename
            p.parent.mkdir(parents=True, exist_ok=True)
            if filename.endswith("model.onnx"):
                p.write_bytes(b"\0" * (fm.MIN_MODEL_BYTES + 1))
            else:
                make_tokens(p, list("abcdefghijklmnopqrstuvwxyz _-"))
            return p
        with self.assertRaises(fm.FetchError) as cm:
            fm.fetch_tts(self.tmp / "t", SRC, dl, synth=False)
        self.assertIn("does not cover Bangla", str(cm.exception))

    def test_local_dir_option(self):
        src_dir = self.tmp / "mine"
        src_dir.mkdir()
        (src_dir / "model.onnx").write_bytes(b"\0" * (fm.MIN_MODEL_BYTES + 5))
        make_tokens(src_dir / "tokens.txt", sorted(fm.bangla_chars_needed()) + list(" ab"))
        src = fm.fetch_tts(self.tmp / "t", [], local_dir=src_dir, synth=False)
        self.assertIn("local folder", src)

    def test_parse_source(self):
        self.assertEqual(fm.parse_source("u/r:ben"), ("u/r", "ben"))
        self.assertEqual(fm.parse_source("u/r"), ("u/r", ""))

    def test_token_parser_handles_space_symbol(self):
        p = self.tmp / "tokens.txt"
        p.write_text("  0\na 1\nক 2\n", encoding="utf-8")        # first symbol is a space
        self.assertEqual(fm.read_tokens(p), {" ", "a", "ক"})

    def test_license_text_keeps_noncommercial_restriction(self):
        fm.write_licenses(self.tmp, "Hugging Face willwade/mms-tts-multilingual-models-onnx/ben")
        txt = (self.tmp / "models" / "MODEL_LICENSES.txt").read_text(encoding="utf-8")
        for needle in ("CC-BY-NC 4.0", "NON-COMMERCIAL USE ONLY", "Attribution", "willwade", "Meta Platforms", "MIT"):
            self.assertIn(needle, txt)

    def test_known_bad_sources_are_not_used(self):
        src = (ROOT / "tools" / "fetch_models.py").read_text(encoding="utf-8")
        code = src.split('"""', 2)[2]                                   # ignore the module docstring that documents them
        self.assertNotIn("csukuangfj/vits-mms-ben", code)
        self.assertNotIn("tts-models/vits-mms-ben", code)
        self.assertNotIn("urlretrieve", code)


if __name__ == "__main__":
    unittest.main()
