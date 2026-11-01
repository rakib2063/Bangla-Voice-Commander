"""Facebook module.

Strategy (no private APIs, resilient to layout changes):
  1. UI Automation: find the real button by its accessible name (English + Bangla labels) and click it.
  2. Facebook's own keyboard shortcuts (J/K next/previous post, L like, C comment) as a fallback.
  3. Plain scrolling when Facebook isn't the active page - and the user is told which method was used.
Accessible names can be overridden in Settings -> `facebook_labels` if Facebook renames them.
"""
from __future__ import annotations

from . import uia
from .base import ActionBase, ActionResult
from .browser import Browser
from .keyboard import Keyboard
from .system import foreground_info, is_browser_foreground

LABELS = {
    "like": ["Like", "লাইক"],
    "unlike": ["Remove Like", "Unlike", "Liked", "লাইক সরান", "আনলাইক"],
    "comment": ["Leave a comment", "Comment", "Write a comment", "মন্তব্য করুন", "মন্তব্য", "কমেন্ট"],
    "mute": ["Mute", "Mute video", "মিউট"],
    "unmute": ["Unmute", "Unmute video", "আনমিউট"],
    "play": ["Play", "Play video", "চালান"],
    "pause": ["Pause", "Pause video", "বিরতি"],
}


class Facebook(ActionBase):
    def __init__(self, ctx, keyboard: Keyboard, mouse, browser: Browser):
        super().__init__(ctx)
        self.kb, self.mouse, self.browser = keyboard, mouse, browser

    # ---- helpers ---------------------------------------------------------------------
    def labels(self, key: str) -> list[str]:
        extra = (self.s.get("facebook_labels") or {}).get(key, [])
        return list(extra) + LABELS[key]

    def is_facebook(self) -> bool:
        if self.ctx.dry:
            return True
        title, _proc = foreground_info()
        return is_browser_foreground() and ("facebook" in title.lower() or "ফেসবুক" in title)

    def _uia_click(self, key: str) -> bool:
        """Click the visible control named like `key`, nearest the upper-middle of the viewport."""
        if self.ctx.dry or not uia.available():
            return False
        items = uia.find_exact_names(self.labels(key))
        if not items:
            return False
        rect = uia.foreground_rect()
        target_y = (rect[1] + (rect[3] - rect[1]) * 0.4) if rect else 400
        it = min(items, key=lambda i: abs(i.center[1] - target_y))
        self.mouse.click_at(*it.center)
        return True

    def _shortcut_ok(self) -> bool:
        return self.ctx.dry or not uia.focused_is_edit()

    # ---- navigation ------------------------------------------------------------------
    def open_home(self) -> ActionResult:
        return self.browser.goto_in_current_tab("https://www.facebook.com/")

    def open_profile(self) -> ActionResult:
        return self.browser.goto_in_current_tab("https://www.facebook.com/me")

    def next_post(self) -> ActionResult:
        return self._post_nav("j", "down")

    def prev_post(self) -> ActionResult:
        return self._post_nav("k", "up")

    def _post_nav(self, key: str, direction: str) -> ActionResult:
        if self.is_facebook() and self._shortcut_ok():
            self.kb.press(key)
            return ActionResult(detail=f"facebook shortcut '{key}' (cannot be verified)")
        self.mouse.scroll_step(direction, 8)
        why = "ফেসবুক সামনে নেই" if not self.is_facebook() else "লেখার বক্সে কার্সর আছে"
        return ActionResult(True, f"{why}, তাই সাধারণ স্ক্রল করেছি।", "fallback: plain scroll")

    # ---- reactions -------------------------------------------------------------------
    def like(self) -> ActionResult:
        if self._uia_click("like"):
            return ActionResult(detail="uia click: Like")
        if self.is_facebook() and self._shortcut_ok():
            self.kb.press("l")
            return ActionResult(detail="facebook shortcut 'l' (cannot be verified)")
        return ActionResult.fail("লাইক বোতামটি খুঁজে পাইনি।", "like button not found")

    def unlike(self) -> ActionResult:
        if self._uia_click("unlike"):
            return ActionResult(detail="uia click: Remove Like")
        return ActionResult.fail("লাইক দেওয়া পোস্ট খুঁজে পাইনি।", "unlike button not found (no blind toggle)")

    def comments_open(self) -> ActionResult:
        if self._uia_click("comment"):
            return ActionResult(detail="uia click: Comment")
        if self.is_facebook() and self._shortcut_ok():
            self.kb.press("c")
            return ActionResult(detail="facebook shortcut 'c' (cannot be verified)")
        return ActionResult.fail("কমেন্ট বোতামটি খুঁজে পাইনি।", "comment button not found")

    def comments_close(self) -> ActionResult:
        self.kb.press("esc")
        return ActionResult(detail="escape")

    # ---- video -------------------------------------------------------------------------
    def video(self, action: str) -> ActionResult:
        key = {"play": "play", "pause": "pause", "mute": "mute", "unmute": "unmute"}[action]
        if self._uia_click(key):
            return ActionResult(detail=f"uia click: {key}")
        if action in ("mute", "unmute"):
            if is_browser_foreground() or self.ctx.dry:
                self.kb.press("m")
                return ActionResult(detail="shortcut 'm' toggles mute (cannot be verified)")
            return ActionResult.fail("ভিডিও পাওয়া যায়নি।", "no video control and no browser")
        if is_browser_foreground() or self.ctx.dry:
            self.kb.press("space" if self._shortcut_ok() else "esc")
            return ActionResult(detail="space toggles play/pause (cannot be verified)")
        return ActionResult.fail("ভিডিও কন্ট্রোল খুঁজে পাইনি।", "no video control and no browser")
