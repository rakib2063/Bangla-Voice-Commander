"""Download the offline models into ./models. Run ONCE at build time (needs internet); the shipped app never downloads.

    python tools/fetch_models.py                       # Whisper 'small' + Bangla TTS
    python tools/fetch_models.py --whisper medium
    python tools/fetch_models.py --tts-dir C:\\path\\to\\vits-mms-ben     # use a TTS folder you downloaded yourself
    python tools/fetch_models.py --tts-repo user/repo[:subfolder]       # try another Hugging Face repo first

Layout produced (this is what the installer bundles):
    models/whisper/<size>/model.bin, config.json, tokenizer.json, vocabulary.*     faster-whisper - MIT
    models/tts/vits-mms-ben/model.onnx, tokens.txt                                  MMS-TTS Bangla - CC-BY-NC 4.0

TTS source (verified): Hugging Face repo  willwade/mms-tts-multilingual-models-onnx , sub-folder  ben/  holding
'model.onnx' + 'tokens.txt' - an ONNX conversion of Meta's facebook/mms-tts-ben for sherpa-onnx (licence cc-by-nc-4.0).
Two earlier guesses do NOT exist and must not be used again:
  * GitHub release  .../releases/download/tts-models/vits-mms-ben.tar.bz2          -> HTTP 404
  * Hugging Face    csukuangfj/vits-mms-ben                                        -> HTTP 404 (repo does not exist)

The script never hides a failure: if the model cannot be downloaded or does not pass validation it exits with
code 2 and a message explaining what was tried. It does NOT fall back to "no TTS".
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Callable, Iterable, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WHISPER_REPOS = {"tiny": "Systran/faster-whisper-tiny", "base": "Systran/faster-whisper-base",
                 "small": "Systran/faster-whisper-small", "medium": "Systran/faster-whisper-medium"}
TTS_SOURCES = [("willwade/mms-tts-multilingual-models-onnx", "ben")]     # (HF repo, sub-folder holding model.onnx + tokens.txt)
TTS_FILES = ("model.onnx", "tokens.txt")
MIN_MODEL_BYTES = 20 * 1024 * 1024                  # MMS VITS ~100+ MB; anything tiny is an error page / LFS pointer
MIN_BN_COVERAGE = 0.90                              # share of Bangla letters used by the app that tokens.txt must contain
SYNTH_TEST = "ফেসবুক খোলো"

LICENSES = """Bundled model licences
======================
* Speech recognition - faster-whisper models (Systran/faster-whisper-*): CTranslate2 conversions of OpenAI
  Whisper. MIT licence. Whisper (c) OpenAI. https://github.com/openai/whisper
* Voice activity detection - Silero VAD (inside faster-whisper): MIT licence.
* Bangla text-to-speech - Meta MMS-TTS Bengali (facebook/mms-tts-ben), converted to ONNX for sherpa-onnx by
  willwade (huggingface.co/willwade/mms-tts-multilingual-models-onnx, licence field: cc-by-nc-4.0). Actual source used
  for this build: {tts_source}.
      Licence: Creative Commons Attribution-NonCommercial 4.0 International (CC-BY-NC 4.0).
      https://creativecommons.org/licenses/by-nc/4.0/
      >>> NON-COMMERCIAL USE ONLY. You may not sell this software bundle or use it commercially while it contains
      >>> this voice. Attribution: "MMS-TTS Bengali (c) Meta Platforms, Inc., CC-BY-NC 4.0; ONNX conversion by
      >>> willwade (mms-tts-multilingual-models-onnx), using the sherpa-onnx export method."
      For commercial redistribution remove models/tts/vits-mms-ben (voice feedback then falls back to a Windows
      Bangla voice if installed, otherwise on-screen text) or replace it with a commercially licensed model.
* sherpa-onnx runtime: Apache-2.0.
"""


class FetchError(RuntimeError):
    """A download or validation failure with a user-readable message."""


def configure_console_encoding() -> None:
    """Use UTF-8 for Windows/GitHub Actions logs; never let log encoding break a successful build."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                # Some wrapped/non-console streams cannot be reconfigured.
                pass


# ---------------------------------------------------------------------------------------------------------------
def hf_download(repo: str, filename: str, dest: Path) -> Path:
    try:
        from huggingface_hub import hf_hub_download
        from huggingface_hub.utils import EntryNotFoundError, RepositoryNotFoundError
    except ImportError as e:
        raise FetchError("huggingface_hub is not installed (pip install -r requirements-build.txt)") from e
    dest.mkdir(parents=True, exist_ok=True)
    try:
        return Path(hf_hub_download(repo_id=repo, filename=filename, local_dir=str(dest / "_hf")))
    except RepositoryNotFoundError as e:
        raise FetchError(f"Hugging Face repo '{repo}' does not exist or is private (404)") from e
    except EntryNotFoundError as e:
        raise FetchError(f"repo '{repo}' has no file '{filename}'") from e
    except Exception as e:                           # network down, rate limit, disk full ...
        raise FetchError(f"downloading '{filename}' from '{repo}' failed: {type(e).__name__}: {e}") from e


def read_tokens(path: Path) -> set[str]:
    """tokens.txt lines look like '<symbol> <id>'; the symbol itself may be a space."""
    syms: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        i = line.rfind(" ")
        if i >= 0 and line[i + 1:].strip().isdigit():
            syms.add(line[:i])
    return syms


def bangla_chars_needed() -> set[str]:
    from bvc.nlp.responses import CONFIRM_PROMPTS, OK
    text = "".join(OK.values()) + "".join(CONFIRM_PROMPTS.values()) + SYNTH_TEST
    return {c for c in text if "\u0980" <= c <= "\u09ff"}


def validate_tts_dir(d: Path, synth: bool = True) -> str:
    """Raise FetchError unless d holds a usable Bangla sherpa-onnx VITS model. Returns a short report."""
    for f in TTS_FILES:
        if not (d / f).is_file():
            raise FetchError(f"{d}: missing required file '{f}'")
    size = (d / "model.onnx").stat().st_size
    if size < MIN_MODEL_BYTES:
        raise FetchError(f"{d / 'model.onnx'} is only {size} bytes - not a real model (error page or Git-LFS pointer?)")
    syms = read_tokens(d / "tokens.txt")
    if len(syms) < 20:
        raise FetchError(f"{d / 'tokens.txt'} has only {len(syms)} symbols - not a valid tokens file")
    need = bangla_chars_needed()
    missing = sorted(c for c in need if c not in syms)
    coverage = 1 - len(missing) / len(need)
    if coverage < MIN_BN_COVERAGE:
        raise FetchError(f"this TTS model does not cover Bangla script: only {coverage:.0%} of the Bangla letters the app "
                         f"speaks are in tokens.txt (missing: {' '.join(missing)}). It likely needs romanised (uroman) "
                         f"input and cannot be used as-is.")
    report = f"{size / 1e6:.0f} MB model, {len(syms)} symbols, Bangla coverage {coverage:.0%}"
    if synth:
        try:
            import sherpa_onnx
        except ImportError:
            print("WARNING: sherpa_onnx not installed - skipped the synthesis smoke test", file=sys.stderr)
            return report + ", synthesis test SKIPPED"
        try:
            cfg = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=str(d / "model.onnx"), lexicon="",
                                                          tokens=str(d / "tokens.txt")), num_threads=2, provider="cpu"))
            audio = sherpa_onnx.OfflineTts(cfg).generate(SYNTH_TEST, sid=0, speed=1.0)
            n = len(audio.samples)
        except Exception as e:
            raise FetchError(f"model downloaded but sherpa-onnx cannot synthesise with it: {type(e).__name__}: {e}") from e
        if n < audio.sample_rate // 4:
            raise FetchError(f"synthesis of '{SYNTH_TEST}' produced only {n} samples - the model does not handle Bangla text")
        report += f", synthesised {n / audio.sample_rate:.1f}s of speech for '{SYNTH_TEST}'"
    return report


def parse_source(text: str) -> tuple[str, str]:
    """'user/repo' or 'user/repo:subfolder' -> (repo, subfolder)."""
    repo, _, sub = text.partition(":")
    return repo, sub


def fetch_tts(dest: Path, sources: Iterable[tuple[str, str]], downloader: Callable[[str, str, Path], Path] = hf_download,
              local_dir: Optional[Path] = None, synth: bool = True) -> str:
    """Populate dest with model.onnx + tokens.txt (flat) and validate. Returns a source description."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    if local_dir:
        for f in TTS_FILES:
            src = Path(local_dir) / f
            if not src.is_file():
                raise FetchError(f"--tts-dir {local_dir}: file '{f}' not found")
            shutil.copy2(src, dest / f)
        return f"local folder {local_dir} ({validate_tts_dir(dest, synth)})"
    errors: list[str] = []
    for repo, sub in sources:
        label = f"{repo}/{sub}" if sub else repo
        try:
            for f in TTS_FILES:
                remote = f"{sub}/{f}" if sub else f
                print(f"   downloading {repo}: {remote} ...")
                got = Path(downloader(repo, remote, dest))
                if got.resolve() != (dest / f).resolve():       # flatten ben/model.onnx -> model.onnx
                    shutil.copy2(got, dest / f)
            shutil.rmtree(dest / "_hf", ignore_errors=True)
            return f"Hugging Face {label} ({validate_tts_dir(dest, synth)})"
        except FetchError as e:
            errors.append(f"  - {label}: {e}")
            shutil.rmtree(dest / "_hf", ignore_errors=True)
            for f in TTS_FILES:                      # never keep a half-downloaded / rejected model
                (dest / f).unlink(missing_ok=True)
    raise FetchError(
        "Could not obtain the Bangla TTS model. Tried:\n" + "\n".join(errors) + "\n\n"
        "What to do:\n"
        "  1. Check the repo/sub-folder on https://huggingface.co/willwade/mms-tts-multilingual-models-onnx/tree/main (folder 'ben').\n"
        "  2. Try another source:  python tools/fetch_models.py --tts-repo <user>/<repo>[:subfolder]\n"
        "  3. Or download model.onnx + tokens.txt yourself and run:  python tools/fetch_models.py --tts-dir <folder>\n"
        "The build is intentionally stopped: the app is specified to speak Bangla offline, so TTS is not silently skipped.")


def fetch_whisper(size: str, root: Path, downloader=None) -> Path:
    dest = root / "models" / "whisper" / size
    print(f"[1/2] Whisper '{size}' -> {dest}")
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(WHISPER_REPOS[size], local_dir=str(dest),
                          allow_patterns=["config.json", "model.bin", "tokenizer.json", "vocabulary.*",
                                          "preprocessor_config.json"])
    except ImportError as e:
        raise FetchError("huggingface_hub is not installed (pip install -r requirements-build.txt)") from e
    except Exception as e:
        raise FetchError(f"downloading Whisper '{size}' from {WHISPER_REPOS[size]} failed: {type(e).__name__}: {e}") from e
    if not (dest / "model.bin").exists():
        raise FetchError(f"Whisper download finished but {dest / 'model.bin'} is missing")
    return dest


def write_licenses(root: Path, tts_source: str) -> None:
    (root / "models").mkdir(exist_ok=True)
    (root / "models" / "MODEL_LICENSES.txt").write_text(LICENSES.format(tts_source=tts_source), encoding="utf-8")


def main(argv=None) -> int:
    configure_console_encoding()
    ap = argparse.ArgumentParser()
    ap.add_argument("--whisper", default="small", choices=sorted(WHISPER_REPOS))
    ap.add_argument("--tts-repo", action="append", default=[], help="extra Hugging Face source to try first: user/repo[:subfolder]")
    ap.add_argument("--tts-dir", help="folder containing model.onnx + tokens.txt you downloaded yourself")
    ap.add_argument("--no-synth-test", action="store_true", help="skip the sherpa-onnx synthesis smoke test")
    a = ap.parse_args(argv)
    try:
        fetch_whisper(a.whisper, ROOT)
        print("[2/2] Bangla TTS (offline, sherpa-onnx MMS)")
        src = fetch_tts(ROOT / "models" / "tts" / "vits-mms-ben", [parse_source(x) for x in a.tts_repo] + TTS_SOURCES,
                        local_dir=Path(a.tts_dir) if a.tts_dir else None, synth=not a.no_synth_test)
        print("   OK:", src)
        write_licenses(ROOT, src)
    except FetchError as e:
        msg = str(e)
        print(f"\nERROR: {msg}", file=sys.stderr)
        print("::error title=Model download failed::" + re.sub(r"\s*\n\s*", " | ", msg)[:900])   # GitHub Actions annotation
        return 2
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
