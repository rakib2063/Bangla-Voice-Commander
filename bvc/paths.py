"""Filesystem locations.

 * Installed build : user data in %APPDATA%\\BanglaVoiceCommander, models in <install dir>\\models
 * Portable build  : a file named 'portable.flag' next to the .exe keeps ALL data in <exe dir>\\data
 * BVC_HOME env var overrides the data dir (tests).
"""
import os
import sys
from pathlib import Path


def app_dir() -> Path:
    """Directory that contains the program (and the bundled 'models' folder)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def is_portable() -> bool:
    return (app_dir() / "portable.flag").exists()


def data_dir() -> Path:
    override = os.environ.get("BVC_HOME")
    if override:
        base = Path(override)
    elif is_portable():
        base = app_dir() / "data"
    else:
        base = Path(os.environ.get("APPDATA") or Path.home() / ".config") / "BanglaVoiceCommander"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _sub(name: str) -> Path:
    p = data_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def model_roots() -> list[Path]:
    """Folders searched for speech/TTS models: bundled first, then user-added."""
    return [app_dir() / "models", data_dir() / "models"]


def cache_dir() -> Path:
    return _sub("cache")


def logs_dir() -> Path:
    return _sub("logs")


def screenshots_dir() -> Path:
    p = Path.home() / "Pictures" / "BanglaVoiceCommander"
    p.mkdir(parents=True, exist_ok=True)
    return p


def resource_dir() -> Path:
    """Bundled read-only resources (icon etc.)."""
    return Path(getattr(sys, "_MEIPASS", app_dir()))
