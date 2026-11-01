"""Mouse control, including continuous (cancellable) scrolling and drag & drop."""
from __future__ import annotations

import threading
import time
from typing import Optional

from .base import ActionBase, ActionResult, IS_WIN


class Mouse(ActionBase):
    def __init__(self, ctx):
        super().__init__(ctx)
        self._scroll_stop: Optional[threading.Event] = None
        self._scroll_thread: Optional[threading.Thread] = None
        self._speed = float(self.s.get("scroll_speed"))
        self._last_click = (0.0, (-1, -1))
        self._dragging = False

    # ---- movement ---------------------------------------------------------
    def move(self, direction: str) -> ActionResult:
        step = int(self.s.get("mouse_step"))
        dx, dy = {"up": (0, -step), "down": (0, step), "left": (-step, 0), "right": (step, 0)}[direction]
        self.ctx.pag().moveRel(dx, dy, duration=0.15)
        return ActionResult()

    def center(self) -> ActionResult:
        pag = self.ctx.pag()
        w, h = pag.size()
        pag.moveTo(w // 2, h // 2, duration=0.2)
        return ActionResult()

    # ---- clicks ------------------------------------------------------------
    def _debounced(self, pos) -> bool:
        cooldown = int(self.s.get("click_cooldown_ms")) / 1000.0
        t, p = self._last_click
        return time.time() - t < cooldown and abs(p[0] - pos[0]) < 6 and abs(p[1] - pos[1]) < 6

    def click(self, button: str = "left", clicks: int = 1) -> ActionResult:
        pag = self.ctx.pag()
        pos = tuple(pag.position())[:2] if not self.ctx.dry else (960, 540)
        if self._debounced(pos):
            return ActionResult(True, skipped=True, detail="duplicate click suppressed")
        pag.click(button=button, clicks=clicks, interval=0.08)
        self._last_click = (time.time(), pos)
        return ActionResult(detail=f"{button} x{clicks} at {pos}")

    def click_at(self, x: int, y: int, button: str = "left", clicks: int = 1) -> ActionResult:
        if self._debounced((x, y)):
            return ActionResult(True, skipped=True, detail="duplicate click suppressed")
        pag = self.ctx.pag()
        pag.moveTo(x, y, duration=0.2)
        pag.click(button=button, clicks=clicks, interval=0.08)
        self._last_click = (time.time(), (x, y))
        return ActionResult(detail=f"click at ({x},{y})")

    # ---- drag & drop ---------------------------------------------------------
    def drag_start(self) -> ActionResult:
        self.ctx.pag().mouseDown()
        self._dragging = True
        return ActionResult()

    def drag_drop(self) -> ActionResult:
        if not self._dragging:
            return ActionResult.fail("ড্র্যাগ শুরু করা হয়নি।", "drop without drag")
        self.ctx.pag().mouseUp()
        self._dragging = False
        return ActionResult()

    def release_all(self) -> None:
        if self._dragging:
            try:
                self.ctx.pag().mouseUp()
            except Exception:
                pass
            self._dragging = False

    # ---- wheel ---------------------------------------------------------------
    def wheel(self, notches: float) -> None:
        """Positive = up, negative = down. One notch = WHEEL_DELTA (120)."""
        delta = int(notches * 120)
        if IS_WIN and not self.ctx.dry:
            import ctypes
            ctypes.windll.user32.mouse_event(0x0800, 0, 0, delta & 0xFFFFFFFF, 0)
        else:
            self.ctx.pag().scroll(delta)

    def scroll_step(self, direction: str, notches: int = 5) -> ActionResult:
        self.wheel(notches if direction == "up" else -notches)
        return ActionResult()

    def start_scrolling(self, direction: str) -> ActionResult:
        self.stop_scrolling()
        stop = threading.Event()
        self._scroll_stop = stop
        sign = 1 if direction == "up" else -1

        def loop():
            try:
                while not stop.is_set():
                    self.wheel(sign * self._speed)
                    stop.wait(int(self.s.get("scroll_interval_ms")) / 1000.0)
            except Exception:                       # e.g. pyautogui fail-safe triggered
                stop.set()

        t = threading.Thread(target=loop, daemon=True, name="bvc-scroll")
        self._scroll_thread = t
        t.start()
        return ActionResult(detail=f"continuous scroll {direction}, speed {self._speed:.1f}")

    def stop_scrolling(self) -> bool:
        was = self.is_scrolling
        if self._scroll_stop:
            self._scroll_stop.set()
        if self._scroll_thread and self._scroll_thread.is_alive():
            self._scroll_thread.join(timeout=1.0)
        self._scroll_stop = self._scroll_thread = None
        return was

    @property
    def is_scrolling(self) -> bool:
        return bool(self._scroll_thread and self._scroll_thread.is_alive())

    def change_speed(self, factor: float) -> ActionResult:
        self._speed = max(0.5, min(15.0, self._speed * factor))
        return ActionResult(detail=f"speed {self._speed:.1f}")
