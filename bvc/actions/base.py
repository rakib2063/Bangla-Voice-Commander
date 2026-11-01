"""Shared plumbing for the action modules (dry-run support, result type)."""
from __future__ import annotations

import logging
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

log = logging.getLogger("bvc.actions")
IS_WIN = sys.platform == "win32"


@dataclass
class ActionResult:
    ok: bool = True
    speak: Optional[str] = None      # overrides the default spoken feedback
    detail: str = ""                 # how it was done / why it failed (shown in history)
    skipped: bool = False            # intentionally ignored (e.g. duplicate click) - stay silent

    @staticmethod
    def fail(speak: str, detail: str = "") -> "ActionResult":
        return ActionResult(False, speak, detail or speak)


class _Point:
    def __init__(self, x, y):
        self.x, self.y = x, y


class _Recorder:
    """Stands in for pyautogui in dry-run mode: records calls instead of acting."""

    def __init__(self, calls: list):
        self._calls = calls

    def size(self):
        return (1920, 1080)

    def position(self):
        return _Point(960, 540)

    def screenshot(self, *a, **k):
        class _Img:
            def save(_s, path):
                self._calls.append(("screenshot.save", (str(path),)))
        return _Img()

    def __getattr__(self, name):
        def rec(*args, **kwargs):
            self._calls.append((name, args))
        return rec


class Ctx:
    """Context shared by every action class."""

    def __init__(self, settings, dry_run: Optional[bool] = None):
        self.settings = settings
        self._dry = dry_run
        self.calls: list = []                 # dry-run journal
        self._pag = None
        self._lock = threading.Lock()

    @property
    def dry(self) -> bool:
        return bool(self._dry if self._dry is not None else self.settings.get("dry_run"))

    @property
    def win(self) -> bool:
        return IS_WIN and not self.dry

    def record(self, name: str, *args: Any) -> None:
        self.calls.append((name, args))
        log.info("[dry-run] %s %s", name, args)

    def pag(self):
        if self.dry:
            return _Recorder(self.calls)
        with self._lock:
            if self._pag is None:
                import pyautogui
                pyautogui.FAILSAFE = True       # slam the mouse into a screen corner to abort
                pyautogui.PAUSE = 0.02
                self._pag = pyautogui
            return self._pag

    def need_windows(self) -> Optional[ActionResult]:
        if self.dry or IS_WIN:
            return None
        return ActionResult.fail("এই সুবিধাটি শুধু উইন্ডোজে কাজ করে।", "not running on Windows")


class ActionBase:
    def __init__(self, ctx: Ctx):
        self.ctx = ctx

    @property
    def s(self):
        return self.ctx.settings

    def pause(self, sec: float) -> None:
        if not self.ctx.dry:
            time.sleep(sec)
