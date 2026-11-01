"""Keyboard control. Unicode (Bangla) text is typed through the clipboard."""
from __future__ import annotations

import time

from .base import ActionBase, ActionResult

# intent -> (kind, keys)
KEYSPECS = {
    "key_enter": ("press", "enter"), "key_escape": ("press", "esc"), "key_tab": ("press", "tab"),
    "key_space": ("press", "space"), "key_backspace": ("press", "backspace"),
    "copy": ("hotkey", ("ctrl", "c")), "paste": ("hotkey", ("ctrl", "v")), "cut": ("hotkey", ("ctrl", "x")),
    "select_all": ("hotkey", ("ctrl", "a")), "undo": ("hotkey", ("ctrl", "z")), "redo": ("hotkey", ("ctrl", "y")),
    "save": ("hotkey", ("ctrl", "s")), "delete_sel": ("press", "delete"), "send_message": ("press", "enter"),
    "switch_app": ("hotkey", ("alt", "tab")),
}


class Keyboard(ActionBase):
    def press(self, key: str) -> ActionResult:
        self.ctx.pag().press(key)
        return ActionResult(detail=f"press {key}")

    def hotkey(self, *keys: str) -> ActionResult:
        self.ctx.pag().hotkey(*keys)
        return ActionResult(detail="+".join(keys))

    def run_spec(self, intent: str) -> ActionResult:
        kind, keys = KEYSPECS[intent]
        return self.press(keys) if kind == "press" else self.hotkey(*keys)

    def type_text(self, text: str) -> ActionResult:
        if not text:
            return ActionResult.fail("কী লিখব বুঝতে পারিনি।")
        if self.ctx.dry:
            self.ctx.record("type_text", text)
            return ActionResult(detail=f"typed {len(text)} chars")
        try:
            import pyperclip
        except ImportError:
            return ActionResult.fail("pyperclip ইনস্টল করা নেই।", "pyperclip missing")
        try:
            old = pyperclip.paste()
        except Exception:
            old = None
        pyperclip.copy(text)
        time.sleep(0.05)
        self.ctx.pag().hotkey("ctrl", "v")
        time.sleep(0.2)
        if old is not None:
            try:
                pyperclip.copy(old)
            except Exception:
                pass
        return ActionResult(detail=f"typed {len(text)} chars via clipboard")
