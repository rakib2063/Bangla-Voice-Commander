"""Windows UI Automation helpers: find controls by accessible name, label clickable controls.

Chrome / Edge expose page content through UI Automation once an assistive technology
queries them. If a page's elements are not found, open chrome://accessibility and enable
"Native accessibility API support" (see README).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, Optional

from ..nlp.normalizer import canon_words, skel_words
from .base import IS_WIN, log

CLICKABLE = {"ButtonControl", "HyperlinkControl", "MenuItemControl", "TabItemControl", "CheckBoxControl",
             "RadioButtonControl", "EditControl", "ComboBoxControl", "ListItemControl", "SplitButtonControl",
             "TreeItemControl", "DocumentControl"}


@dataclass
class UiItem:
    name: str
    ctype: str
    rect: tuple  # left, top, right, bottom (physical pixels)

    @property
    def center(self):
        return ((self.rect[0] + self.rect[2]) // 2, (self.rect[1] + self.rect[3]) // 2)


def available() -> bool:
    if not IS_WIN:
        return False
    try:
        import uiautomation  # noqa: F401
        return True
    except Exception:
        return False


def _walk(max_items: int, timeout: float, types: Optional[set]):
    import uiautomation as auto
    root = auto.GetForegroundControl()
    if root is None:
        return
    rr = root.BoundingRectangle
    start, n = time.time(), 0
    for ctrl, _depth in auto.WalkControl(root, includeTop=False, maxDepth=30):
        if time.time() - start > timeout or n >= max_items:
            break
        try:
            if types and ctrl.ControlTypeName not in types:
                continue
            if ctrl.IsOffscreen:
                continue
            r = ctrl.BoundingRectangle
            if r.width() < 6 or r.height() < 6:
                continue
            if r.right < rr.left or r.left > rr.right or r.bottom < rr.top or r.top > rr.bottom:
                continue
            n += 1
            yield UiItem(ctrl.Name or "", ctrl.ControlTypeName, (r.left, r.top, r.right, r.bottom))
        except Exception:                       # control vanished while walking
            continue


def numbered_items(max_items: int = 80, timeout: float = 4.0) -> list[UiItem]:
    """Visible interactive controls of the foreground window, for the numbered overlay."""
    if not available():
        return []
    items = [i for i in _walk(max_items * 3, timeout, CLICKABLE) if i.ctype != "DocumentControl"]
    # drop containers that fully swallow another item with the same name; keep reading order
    items.sort(key=lambda i: (i.rect[1] // 12, i.rect[0]))
    return items[:max_items]


def _score(query: str, name: str) -> float:
    q = skel_words(canon_words(query)) or query.lower()
    n = skel_words(canon_words(name)) or name.lower()
    if not q or not n:
        return 0.0
    if q == n:
        return 1.0
    if q in n:
        return 0.9
    return SequenceMatcher(None, q, n).ratio()


def find_by_name(query: str, min_score: float = 0.78, timeout: float = 5.0) -> Optional[UiItem]:
    if not available():
        return None
    best, best_i = 0.0, None
    for it in _walk(2000, timeout, CLICKABLE - {"DocumentControl"}):
        if not it.name:
            continue
        sc = _score(query, it.name)
        if sc > best:
            best, best_i = sc, it
    return best_i if best >= min_score else None


def find_exact_names(names: Iterable[str], timeout: float = 4.0) -> list[UiItem]:
    """All visible controls whose accessible name equals one of `names` (case-insensitive)."""
    if not available():
        return []
    wanted = {n.lower() for n in names}
    out = []
    for it in _walk(3000, timeout, CLICKABLE - {"DocumentControl"}):
        if it.name and it.name.strip().lower() in wanted:
            out.append(it)
    return out


def foreground_rect() -> Optional[tuple]:
    if not available():
        return None
    try:
        import uiautomation as auto
        r = auto.GetForegroundControl().BoundingRectangle
        return (r.left, r.top, r.right, r.bottom)
    except Exception as e:
        log.debug("foreground_rect failed: %s", e)
        return None


def focused_is_edit() -> bool:
    """True when a text box has keyboard focus (so single-letter shortcuts would be typed)."""
    if not available():
        return False
    try:
        import uiautomation as auto
        c = auto.GetFocusedControl()
        return bool(c) and c.ControlTypeName in ("EditControl", "ComboBoxControl")
    except Exception:
        return False
