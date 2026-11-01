"""Windows system control: apps, windows, volume, brightness, lock, screenshot, power."""
from __future__ import annotations

import difflib
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from ..paths import screenshots_dir
from .base import IS_WIN, ActionBase, ActionResult, log

BROWSER_PROCS = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe"}
CREATE_NO_WINDOW = 0x08000000


def foreground_info() -> tuple[str, str]:
    """(window title, process name) of the foreground window."""
    if not IS_WIN:
        return ("", "")
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        hwnd = u.GetForegroundWindow()
        n = u.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, buf, n + 1)
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        name = ""
        try:
            import psutil
            name = psutil.Process(pid.value).name()
        except Exception:
            pass
        return buf.value, name
    except Exception as e:
        log.debug("foreground_info: %s", e)
        return ("", "")


def is_browser_foreground() -> bool:
    return foreground_info()[1].lower() in BROWSER_PROCS


class System(ActionBase):
    # ---- applications --------------------------------------------------------
    def launch(self, value: str, label: str = "") -> ActionResult:
        bad = self.ctx.need_windows()
        if bad:
            return bad
        if self.ctx.dry:
            self.ctx.record("launch", value)
            return ActionResult(detail=f"launch {value}")
        try:
            r = subprocess.run(["cmd", "/c", "start", "", value], creationflags=CREATE_NO_WINDOW,
                               capture_output=True, timeout=8)
            if r.returncode != 0:
                return ActionResult.fail(f"{label or value} খুলতে পারিনি।", f"start returned {r.returncode}")
            return ActionResult(detail=f"started {value}")
        except Exception as e:
            return ActionResult.fail(f"{label or value} খুলতে পারিনি।", str(e))

    def open_by_name(self, name: str) -> ActionResult:
        """Fuzzy-match an installed app by its Start Menu shortcut name (English names)."""
        bad = self.ctx.need_windows()
        if bad:
            return bad
        if self.ctx.dry:
            self.ctx.record("open_by_name", name)
            return ActionResult(detail=f"open_by_name {name}")
        dirs = [Path(os.environ.get("ProgramData", "")) / "Microsoft/Windows/Start Menu/Programs",
                Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs"]
        q = name.lower().strip()
        best, best_p = 0.0, None
        for d in dirs:
            if not d.exists():
                continue
            for p in d.rglob("*.lnk"):
                sc = difflib.SequenceMatcher(None, q, p.stem.lower()).ratio()
                if q in p.stem.lower():
                    sc = max(sc, 0.9)
                if sc > best:
                    best, best_p = sc, p
        if best_p is not None and best >= 0.7:
            os.startfile(str(best_p))
            return ActionResult(True, f"{best_p.stem} খোলা হচ্ছে।", f"start menu: {best_p.name}")
        return ActionResult.fail(f"{name} নামে কোনো অ্যাপ খুঁজে পাইনি। কাস্টম কমান্ডে যোগ করে নিতে পারেন।",
                                 "app not found")

    def close_app(self, procs: list[str], label: str) -> ActionResult:
        """Gracefully close (WM_CLOSE) every visible window of the given processes."""
        bad = self.ctx.need_windows()
        if bad:
            return bad
        if not procs:
            return ActionResult.fail(f"{label} এভাবে বন্ধ করা সমর্থিত নয়।", "no process names")
        if self.ctx.dry:
            self.ctx.record("close_app", tuple(procs))
            return ActionResult(detail="close_app " + ",".join(procs))
        import ctypes
        from ctypes import wintypes
        import psutil
        u = ctypes.windll.user32
        wanted = {p.lower() for p in procs}
        count = [0]
        Proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, _l):
            if u.IsWindowVisible(hwnd) and u.GetWindowTextLengthW(hwnd) > 0:
                pid = wintypes.DWORD()
                u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                try:
                    if psutil.Process(pid.value).name().lower() in wanted:
                        u.PostMessageW(hwnd, 0x0010, 0, 0)       # WM_CLOSE (lets apps ask to save)
                        count[0] += 1
                except Exception:
                    pass
            return True

        u.EnumWindows(Proc(cb), 0)
        if count[0] == 0:
            return ActionResult.fail(f"{label} চালু নেই।", "no matching window")
        return ActionResult(True, f"{label} বন্ধ করা হচ্ছে।", f"closed {count[0]} window(s)")

    # ---- windows ----------------------------------------------------------------
    def _show(self, cmd: int, what: str) -> ActionResult:
        bad = self.ctx.need_windows()
        if bad:
            return bad
        if self.ctx.dry:
            self.ctx.record("ShowWindow", cmd)
            return ActionResult(detail=what)
        import ctypes
        u = ctypes.windll.user32
        u.ShowWindow(u.GetForegroundWindow(), cmd)
        return ActionResult(detail=what)

    def minimize(self): return self._show(6, "minimize")
    def maximize(self): return self._show(3, "maximize")
    def restore(self): return self._show(9, "restore")

    def show_desktop(self):
        self.ctx.pag().hotkey("win", "d")
        return ActionResult()

    def close_window(self) -> ActionResult:
        bad = self.ctx.need_windows()
        if bad:
            return bad
        if self.ctx.dry:
            self.ctx.record("WM_CLOSE", "foreground")
            return ActionResult()
        import ctypes
        u = ctypes.windll.user32
        u.PostMessageW(u.GetForegroundWindow(), 0x0010, 0, 0)
        return ActionResult()

    def lock(self) -> ActionResult:
        bad = self.ctx.need_windows()
        if bad:
            return bad
        if self.ctx.dry:
            self.ctx.record("LockWorkStation")
            return ActionResult()
        import ctypes
        ctypes.windll.user32.LockWorkStation()
        return ActionResult()

    def screenshot(self) -> ActionResult:
        path = screenshots_dir() / time.strftime("screenshot_%Y%m%d_%H%M%S.png")
        img = self.ctx.pag().screenshot()
        img.save(str(path))
        return ActionResult(True, "স্ক্রিনশট নেওয়া হয়েছে। Pictures ফোল্ডারে সেভ হয়েছে।", f"saved {path}")

    # ---- volume (pycaw) ----------------------------------------------------------
    def _endpoint(self):
        import comtypes
        try:
            comtypes.CoInitialize()
        except Exception:
            pass
        from pycaw.pycaw import AudioUtilities
        dev = AudioUtilities.GetSpeakers()
        ev = getattr(dev, "EndpointVolume", None)
        if ev is not None:                                   # newer pycaw
            return ev
        from ctypes import POINTER, cast
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import IAudioEndpointVolume
        iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(iface, POINTER(IAudioEndpointVolume))

    def volume(self, action: str, level: Optional[int] = None) -> ActionResult:
        if self.ctx.dry:
            self.ctx.record("volume", action, level)
            return ActionResult(detail=f"volume {action} {level}")
        bad = self.ctx.need_windows()
        if bad:
            return bad
        try:
            ep = self._endpoint()
            cur = ep.GetMasterVolumeLevelScalar()
            if action == "up":
                ep.SetMasterVolumeLevelScalar(min(1.0, cur + 0.10), None)
            elif action == "down":
                ep.SetMasterVolumeLevelScalar(max(0.0, cur - 0.10), None)
            elif action == "mute":
                ep.SetMute(1, None)
            elif action == "unmute":
                ep.SetMute(0, None)
            elif action == "set" and level is not None:
                ep.SetMasterVolumeLevelScalar(max(0, min(100, level)) / 100.0, None)
            now = round(ep.GetMasterVolumeLevelScalar() * 100)
            return ActionResult(True, None if action != "set" else f"ভলিউম {level} শতাংশ করা হয়েছে।",
                                f"volume now {now}%")
        except Exception as e:
            log.warning("pycaw failed (%s) - falling back to media keys", e)
            key = {"up": "volumeup", "down": "volumedown", "mute": "volumemute", "unmute": "volumemute"}.get(action)
            if not key:
                return ActionResult.fail("ভলিউম নিয়ন্ত্রণ করা যায়নি।", f"pycaw error: {e}")
            pag = self.ctx.pag()
            for _ in range(5 if action in ("up", "down") else 1):
                pag.press(key)
            return ActionResult(detail="media keys fallback")

    def mute_toggle(self) -> ActionResult:
        self.ctx.pag().press("volumemute")
        return ActionResult(detail="media key mute toggle")

    # ---- brightness ----------------------------------------------------------------
    def brightness(self, action: str, level: Optional[int] = None) -> ActionResult:
        if self.ctx.dry:
            self.ctx.record("brightness", action, level)
            return ActionResult()
        try:
            import screen_brightness_control as sbc
            cur = sbc.get_brightness()[0]
            new = {"up": cur + 10, "down": cur - 10}.get(action, level if level is not None else cur)
            sbc.set_brightness(max(0, min(100, int(new))))
            return ActionResult(detail=f"brightness {cur}->{new}")
        except Exception as e:
            return ActionResult.fail("এই কম্পিউটারে ব্রাইটনেস নিয়ন্ত্রণ সমর্থিত নয়।", f"sbc: {e}")

    # ---- power (the engine asks for confirmation BEFORE calling these) -----------------
    def power(self, kind: str) -> ActionResult:
        flag = {"shutdown": "/s", "restart": "/r"}[kind]
        bad = self.ctx.need_windows()
        if bad:
            return bad
        if self.ctx.dry:
            self.ctx.record("shutdown", flag)
            return ActionResult(detail=f"shutdown {flag} /t 15")
        r = subprocess.run(["shutdown", flag, "/t", "15", "/c", "Bangla Voice Commander"],
                           creationflags=CREATE_NO_WINDOW, capture_output=True)
        if r.returncode != 0:
            return ActionResult.fail("শাটডাউন শুরু করা যায়নি।", r.stderr.decode(errors="ignore"))
        return ActionResult(detail=f"{kind} scheduled in 15s")

    def cancel_power(self) -> ActionResult:
        if self.ctx.dry:
            self.ctx.record("shutdown", "/a")
            return ActionResult()
        bad = self.ctx.need_windows()
        if bad:
            return bad
        r = subprocess.run(["shutdown", "/a"], creationflags=CREATE_NO_WINDOW, capture_output=True)
        if r.returncode != 0:
            return ActionResult.fail("বাতিল করার মতো কোনো শাটডাউন চলছে না।", "no shutdown pending")
        return ActionResult()
