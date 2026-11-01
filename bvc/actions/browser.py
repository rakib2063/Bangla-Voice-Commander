"""Browser control. Works with any foreground browser via standard shortcuts,
and with UI Automation for 'click by name'."""
from __future__ import annotations

import subprocess
import webbrowser
from urllib.parse import quote_plus

from . import uia
from .base import ActionBase, ActionResult, IS_WIN
from .keyboard import Keyboard
from .system import CREATE_NO_WINDOW, is_browser_foreground

_EXE = {"chrome": "chrome", "edge": "msedge", "firefox": "firefox", "brave": "brave"}

NOT_BROWSER = ActionResult.fail("এখন কোনো ব্রাউজার সামনে নেই। আগে ব্রাউজার খুলুন।", "foreground is not a browser")


class Browser(ActionBase):
    def __init__(self, ctx, keyboard: Keyboard, mouse):
        super().__init__(ctx)
        self.kb = keyboard
        self.mouse = mouse

    def _guard(self):
        if self.ctx.dry or is_browser_foreground():
            return None
        return NOT_BROWSER

    # ---- opening pages --------------------------------------------------------------
    def open_url(self, url: str) -> ActionResult:
        if self.ctx.dry:
            self.ctx.record("open_url", url)
            return ActionResult(detail=f"open {url}")
        pref = self.s.get("browser")
        try:
            if pref in _EXE and IS_WIN:
                args = ["cmd", "/c", "start", "", _EXE[pref]]
                if pref in ("chrome", "edge"):
                    args.append("--force-renderer-accessibility")
                subprocess.Popen(args + [url], creationflags=CREATE_NO_WINDOW)
            else:
                webbrowser.open(url, new=2)
            return ActionResult(detail=f"open {url}")
        except Exception as e:
            return ActionResult.fail("ওয়েবসাইট খুলতে পারিনি।", str(e))

    def goto_in_current_tab(self, url: str) -> ActionResult:
        bad = self._guard()
        if bad:
            return self.open_url(url)
        self.kb.hotkey("ctrl", "l")
        self.pause(0.15)
        self.kb.type_text(url)
        self.pause(0.1)
        self.kb.press("enter")
        return ActionResult(detail=f"navigated to {url}")

    def search_google(self, q: str) -> ActionResult:
        return self.open_url(f"https://www.google.com/search?q={quote_plus(q)}&hl=bn")

    def search_youtube(self, q: str) -> ActionResult:
        return self.open_url(f"https://www.youtube.com/results?search_query={quote_plus(q)}")

    # ---- tab / page shortcuts (work on Chrome, Edge, Firefox, Brave...) ---------------------
    def _hk(self, *keys) -> ActionResult:
        bad = self._guard()
        if bad:
            return bad
        return self.kb.hotkey(*keys)

    def new_tab(self): return self._hk("ctrl", "t")
    def close_tab(self): return self._hk("ctrl", "w")
    def next_tab(self): return self._hk("ctrl", "tab")
    def prev_tab(self): return self._hk("ctrl", "shift", "tab")
    def reopen_tab(self): return self._hk("ctrl", "shift", "t")
    def refresh(self): return self._hk("f5")
    def back(self): return self._hk("alt", "left")
    def forward(self): return self._hk("alt", "right")
    def zoom_in(self): return self._hk("ctrl", "=")
    def zoom_out(self): return self._hk("ctrl", "-")
    def fullscreen(self): return self._hk("f11")
    def address_bar(self): return self._hk("ctrl", "l")

    def find_text(self, q: str) -> ActionResult:
        bad = self._guard()
        if bad:
            return bad
        self.kb.hotkey("ctrl", "f")
        self.pause(0.2)
        self.kb.type_text(q)
        self.kb.press("enter")
        return ActionResult(True, f"{q} খোঁজা হচ্ছে।", f"find '{q}'")

    # ---- click by accessible name ---------------------------------------------------
    def click_name(self, name: str) -> ActionResult:
        if self.ctx.dry:
            self.ctx.record("uia.click_name", name)
            return ActionResult(detail=f"click '{name}'")
        if not uia.available():
            return ActionResult.fail("UI Automation পাওয়া যায়নি (uiautomation ইনস্টল করুন)।", "uiautomation missing")
        item = uia.find_by_name(name)
        if not item:
            return ActionResult.fail(f"'{name}' নামে কোনো বোতাম বা লিংক খুঁজে পাইনি।", f"no control named '{name}'")
        x, y = item.center
        res = self.mouse.click_at(x, y)
        res.detail = f"uia '{item.name}' ({item.ctype}) -> {res.detail}"
        return res
