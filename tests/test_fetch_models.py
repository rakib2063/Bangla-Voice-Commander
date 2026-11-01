"""fetch_models.py logic with a fake downloader (no network, no huggingface_hub needed)."""
import os, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import fetch_models as fm


def make_tokens(path: Path, chars):
    path.write_text("\n".join(f"{c} {i}" for i, c in enumerate(chars)) + "\n", encoding="utf-8")


def good_downloader(repo, filename, dest):
    p = Path(dest) / filename
    if filename == "model.onnx":
        p.write_bytes(b"\0" * (fm.MIN_MODEL_BYTES + 10))
    else:
        make_tokens(p, sorted(fm.bangla_chars_needed()) + list(" abcdefghijklmnop"))
    return p


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fm_"))

    def test_success_path(self):
        src = fm.fetch_tts(self.tmp / "t", ["csukuangfj/vits-mms-ben"], good_downloader, synth=False)
        self.assertIn("csukuangfj/vits-mms-ben", src)
        self.assertIn("Bangla coverage 100%", src)
        self.assertTrue((self.tmp / "t" / "model.onnx").exists())

    def test_404_gives_clear_error_and_does_not_pass_silently(self):
        def dl(repo, filename, dest):
            raise fm.FetchError(f"Hugging Face repo '{repo}' does not exist or is private (404)")
        with self.assertRaises(fm.FetchError) as cm:
            fm.fetch_tts(self.tmp / "t", ["a/missing", "b/also-missing"], dl, synth=False)
        msg = str(cm.exception)
        self.assertIn("a/missing", msg)
        self.assertIn("b/also-missing", msg)
        self.assertIn("--tts-dir", msg)
        self.assertIn("not silently skipped", msg)

    def test_falls_back_to_second_repo(self):
        def dl(repo, filename, dest):
            if repo == "bad/repo":
                raise fm.FetchError("404")
            return good_downloader(repo, filename, dest)
        src = fm.fetch_tts(self.tmp / "t", ["bad/repo", "good/repo"], dl, synth=False)
        self.assertIn("good/repo", src)

    def test_rejects_fake_small_model(self):
        def dl(repo, filename, dest):
            p = Path(dest) / filename
            p.write_text("version https://git-lfs.github.com/spec/v1" if filename == "model.onnx" else "a 0\n")
            return p
        with self.assertRaises(fm.FetchError) as cm:
            fm.fetch_tts(self.tmp / "t", ["x/y"], dl, synth=False)
        self.assertIn("not a real model", str(cm.exception))
        self.assertFalse((self.tmp / "t" / "model.onnx").exists())      # rejected files are removed

    def test_rejects_model_without_bangla_tokens(self):
        def dl(repo, filename, dest):
            p = Path(dest) / filename
            if filename == "model.onnx":
                p.write_bytes(b"\0" * (fm.MIN_MODEL_BYTES + 1))
            else:
                make_tokens(p, list("abcdefghijklmnopqrstuvwxyz _-"))
            return p
        with self.assertRaises(fm.FetchError) as cm:
            fm.fetch_tts(self.tmp / "t", ["x/y"], dl, synth=False)
        self.assertIn("does not cover Bangla", str(cm.exception))

    def test_local_dir_option(self):
        src_dir = self.tmp / "mine"
        src_dir.mkdir()
        good_downloader("-", "model.onnx", src_dir)
        good_downloader("-", "tokens.txt", src_dir)
        src = fm.fetch_tts(self.tmp / "t", [], local_dir=src_dir, synth=False)
        self.assertIn("local folder", src)

    def test_token_parser_handles_space_symbol(self):
        p = self.tmp / "tokens.txt"
        p.write_text("  0\na 1\nক 2\n", encoding="utf-8")        # first symbol is a space
        self.assertEqual(fm.read_tokens(p), {" ", "a", "ক"})

    def test_license_text_keeps_noncommercial_restriction(self):
        fm.write_licenses(self.tmp, "Hugging Face repo csukuangfj/vits-mms-ben")
        txt = (self.tmp / "models" / "MODEL_LICENSES.txt").read_text(encoding="utf-8")
        for needle in ("CC-BY-NC 4.0", "NON-COMMERCIAL USE ONLY", "Attribution", "csukuangfj/vits-mms-ben", "MIT"):
            self.assertIn(needle, txt)

    def test_old_404_url_is_gone(self):
        src = (ROOT / "tools" / "fetch_models.py").read_text(encoding="utf-8")
        self.assertNotIn("releases/download/tts-models/vits-mms-ben", src.replace("the old\n.../releases/download/tts-models/vits-mms-ben.tar.bz2", ""))
        self.assertNotIn("urlretrieve", src)


if __name__ == "__main__":
    unittest.main()
