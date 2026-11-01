"""Deterministic Bangla/English command parser.

Pipeline: normalise -> custom commands -> exact phrase -> parametric families
          -> contiguous phrase inside longer speech -> fuzzy phrase -> unknown "open X".
Nothing here executes anything; it only returns a Match.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from .intents import INTENT_PHRASES, SENSITIVE
from .lexicon import Lexicon, Target
from .normalizer import Tok, canon_words, clean, light, skel_words, skeleton, tokenize

_NUM_WORDS = {
    "শূন্য": 0, "এক": 1, "দুই": 2, "দুটি": 2, "তিন": 3, "চার": 4, "পাঁচ": 5, "ছয়": 6, "ছয়": 6, "সাত": 7, "আট": 8,
    "নয়": 9, "দশ": 10, "এগারো": 11, "বারো": 12, "তেরো": 13, "চৌদ্দ": 14, "পনেরো": 15, "ষোলো": 16, "সতেরো": 17,
    "আঠারো": 18, "উনিশ": 19, "বিশ": 20, "একুশ": 21, "বাইশ": 22, "তেইশ": 23, "চব্বিশ": 24, "পঁচিশ": 25,
    "ছাব্বিশ": 26, "সাতাশ": 27, "আটাশ": 28, "ঊনত্রিশ": 29, "ত্রিশ": 30, "চল্লিশ": 40, "পঞ্চাশ": 50, "ষাট": 60,
    "সত্তর": 70, "আশি": 80, "নব্বই": 90, "একশো": 100, "একশ": 100,
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100,
}
_NUM_SKEL = {skeleton(k): v for k, v in _NUM_WORDS.items()}
_DOMAIN = re.compile(r"^(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/\S*)?$", re.I)


def parse_number(token: str) -> Optional[int]:
    t = clean(token)
    if t.isdigit():
        return int(t)
    return _NUM_SKEL.get(skeleton(t))


@dataclass
class Match:
    intent: str
    params: dict = field(default_factory=dict)
    score: float = 1.0
    via: str = "exact"

    @property
    def sensitive(self) -> bool:
        return self.intent in SENSITIVE


# ---- helpers for prefix / suffix families -------------------------------------------------
def _canon(seq: tuple) -> tuple:
    out: list[str] = []
    for p in seq:
        out += canon_words(p)
    return tuple(out)


def _fam(*variants: tuple) -> list[tuple]:
    return sorted({_canon(v) for v in variants}, key=len, reverse=True)


F_TYPE_PRE = _fam(("লেখো",), ("টাইপ", "করো"), ("টাইপ",), ("write",), ("dictate",))
F_YT_PRE = _fam(("ইউটিউবে", "সার্চ", "করো"), ("ইউটিউব", "সার্চ"), ("ইউটিউবে", "খোঁজো"), ("ইউটিউবে", "দেখো"))
F_YT_SUF = _fam(("ইউটিউবে", "সার্চ", "করো"), ("ইউটিউব", "সার্চ", "করো"), ("ইউটিউবে", "খোঁজো"), ("ইউটিউব", "খোঁজো"))
F_G_PRE = _fam(("গুগলে", "সার্চ", "করো"), ("গুগল", "সার্চ"), ("গুগলে", "খোঁজো"), ("সার্চ", "করো"), ("সার্চ",), ("গুগল",))
F_G_SUF = _fam(("গুগলে", "সার্চ", "করো"), ("গুগল", "সার্চ", "করো"), ("গুগলে", "খোঁজো"), ("সার্চ", "করো"), ("সার্চ",))
F_FIND_PRE = _fam(("পেজে", "খোঁজো"), ("খোঁজো",), ("find",), ("পেজে", "find"))
F_FIND_SUF = _fam(("পেজে", "খোঁজো"), ("খোঁজো",))
F_CLICK_PRE = _fam(("ক্লিক", "করো"), ("ক্লিক",))
F_CLICK_SUF = _fam(("ক্লিক", "করো"), ("ক্লিক",), ("চাপো",), ("সিলেক্ট", "করো"))
CLICK_NOISE = {"বাটনে", "বাটন", "লিংকে", "লিংক", "button", "link", "the", "on", "এ", "এর", "এখানে", "অপশনে",
               "অপশন", "to", "করো", "চাপো", "যাও", "খোলো", "ক্লিক", "at"}
F_OPEN_SUF = _fam(("খোলো",), ("ওপেন", "করো"), ("ওপেন",), ("চালু", "করো"), ("চালাও",), ("যাও",), ("লঞ্চ", "করো"),
                  ("দেখাও",))
F_OPEN_PRE = _fam(("ওপেন",), ("launch",), ("go", "to"), ("খোলো",), ("start",))
F_CLOSE_SUF = _fam(("বন্ধ", "করো"), ("ক্লোজ", "করো"), ("ক্লোজ",), ("বন্ধ",))
F_CLOSE_PRE = _fam(("ক্লোজ",), ("quit",), ("exit",))
VOL_WORDS = {"ভলিউম"}
BRIGHT_WORDS = {skeleton(w) for w in ("ব্রাইটনেস", "brightness", "উজ্জ্বলতা")}
SET_NOISE = {"করো", "শতাংশ", "percent", "সেট", "set", "এ", "to", "পার্সেন্ট", "%", "দাও", "রাখো"}
CLICK_NUMBER_NOISE = {"নম্বর", "ক্লিক", "করো", "চাপো", "যাও", "খোলো", "এ", "on", "at", "to", "click", "the", "সিলেক্ট"}


def _strip_prefix(words: list[str], fams: list[tuple]) -> Optional[int]:
    for f in fams:
        if len(words) > len(f) and tuple(words[:len(f)]) == f:
            return len(f)
    return None


def _strip_suffix(words: list[str], fams: list[tuple]) -> Optional[int]:
    for f in fams:
        if len(words) > len(f) and tuple(words[-len(f):]) == f:
            return len(f)
    return None


class Parser:
    def __init__(self, aliases: Optional[dict] = None):
        self.lexicon = Lexicon(aliases)
        self._exact: dict[str, str] = {}
        self._phrases: list[tuple[str, list[str], str]] = []
        for intent, phrases in INTENT_PHRASES.items():
            for ph in phrases:
                words = canon_words(ph)
                if not words:
                    continue
                key = skel_words(words)
                self._exact.setdefault(key, intent)
                self._phrases.append((intent, words, key))

    # ------------------------------------------------------------------
    def parse(self, text: str, custom: Optional[list[dict]] = None) -> Optional[Match]:
        raw, toks = tokenize(text)
        if not toks:
            return None
        words = [t.c for t in toks]
        key = skel_words(words)

        m = self._match_custom(key, custom)
        if m:
            return m
        if key in self._exact:
            return Match(self._exact[key], {}, 1.0, "exact")

        for fn in (self._p_type, self._p_search, self._p_find, self._p_click_number, self._p_click_name,
                   self._p_vol_set, self._p_bright_set, self._p_open_close):
            m = fn(raw, toks, words)
            if m:
                return m

        m = self._contiguous(words)
        if m:
            return m
        m = self._fuzzy(key)
        if m:
            return m
        return self._p_open_unknown(raw, toks, words)

    # ---- custom ---------------------------------------------------------
    def _match_custom(self, key: str, custom: Optional[list[dict]]) -> Optional[Match]:
        best, best_c = 0.0, None
        for c in custom or []:
            if not c.get("enabled", True):
                continue
            for ph in c.get("phrases", []):
                k = skel_words(canon_words(ph))
                if not k:
                    continue
                r = 1.0 if k == key else SequenceMatcher(None, key, k).ratio()
                if r > best:
                    best, best_c = r, c
        if best_c is not None and best >= 0.9:
            return Match("custom", {"id": best_c["id"], "name": best_c["name"]}, best, "custom")
        return None

    # ---- parametric families -------------------------------------------
    @staticmethod
    def _rawspan(raw, toks, a, b):
        sub = toks[a:b]
        if not sub:
            return ""
        return " ".join(raw[sub[0].s:sub[-1].e]).strip()

    def _p_type(self, raw, toks, words):
        n = _strip_prefix(words, F_TYPE_PRE)
        if n:
            text = self._rawspan(raw, toks, n, len(toks))
            if text:
                return Match("type_text", {"text": text}, 0.98, "param")
        return None

    def _p_search(self, raw, toks, words):
        for intent, pre, suf in (("search_youtube", F_YT_PRE, F_YT_SUF), ("search_google", F_G_PRE, F_G_SUF)):
            a = _strip_prefix(words, pre) or 0
            b = _strip_suffix(words[a:], suf) or 0
            if (a or b) and len(words) - a - b > 0:
                q = self._rawspan(raw, toks, a, len(toks) - b)
                q = re.sub(r"^(?:গুগলে|ইউটিউবে)\s+", "", q)
                if q:
                    return Match(intent, {"query": q}, 0.98, "param")
        return None

    def _p_find(self, raw, toks, words):
        a = _strip_prefix(words, F_FIND_PRE) or 0
        b = 0 if a else (_strip_suffix(words, F_FIND_SUF) or 0)
        if (a or b) and len(words) - a - b > 0:
            q = self._rawspan(raw, toks, a, len(toks) - b)
            if q:
                return Match("find_text", {"query": q}, 0.95, "param")
        return None

    def _p_click_number(self, raw, toks, words):
        if not any(w in ("নম্বর", "ক্লিক") for w in words):
            return None
        nums = [parse_number(w) for w in words if parse_number(w) is not None]
        rest = [w for w in words if parse_number(w) is None and w not in CLICK_NUMBER_NOISE]
        if len(nums) == 1 and not rest and 0 < nums[0] < 1000:
            return Match("click_number", {"n": nums[0]}, 0.98, "param")
        return None

    def _p_click_name(self, raw, toks, words):
        a = _strip_prefix(words, F_CLICK_PRE) or 0
        b = 0 if a else (_strip_suffix(words, F_CLICK_SUF) or 0)
        if not (a or b):
            return None
        inner = list(toks[a:len(toks) - b])
        while inner and inner[0].c in CLICK_NOISE:
            inner.pop(0)
        while inner and inner[-1].c in CLICK_NOISE:
            inner.pop()
        if not inner:
            return None
        name = " ".join(raw[inner[0].s:inner[-1].e])
        return Match("click_name", {"name": name}, 0.95, "param")

    def _level(self, words, markers, intent):
        if not any(skeleton(w) in markers or w in VOL_WORDS for w in words):
            return None
        nums = [parse_number(w) for w in words if parse_number(w) is not None]
        rest = [w for w in words if parse_number(w) is None and skeleton(w) not in markers
                and w not in VOL_WORDS and w not in SET_NOISE]
        if len(nums) == 1 and not rest and 0 <= nums[0] <= 100:
            return Match(intent, {"level": nums[0]}, 0.98, "param")
        return None

    def _p_vol_set(self, raw, toks, words):
        if "ভলিউম" in words:
            return self._level(words, set(), "vol_set")
        return None

    def _p_bright_set(self, raw, toks, words):
        if any(skeleton(w) in BRIGHT_WORDS for w in words):
            return self._level(words, BRIGHT_WORDS, "bright_set")
        return None

    def _domain_in(self, raw) -> Optional[str]:
        for r in raw:
            if _DOMAIN.match(r.strip(".,!?।")):
                return r.strip(".,!?।")
        return None

    def _p_open_close(self, raw, toks, words):
        # open / go to
        a = _strip_prefix(words, F_OPEN_PRE) or 0
        b = _strip_suffix(words[a:], F_OPEN_SUF) or 0
        if a or b:
            target_words = words[a:len(words) - b]
            dom = self._domain_in(raw)
            if dom and len(target_words) <= 2:
                url = dom if dom.lower().startswith("http") else "https://" + dom
                return Match("open_target", {"kind": "url", "value": url, "label": dom}, 0.97, "param")
            t = self.lexicon.resolve(target_words)
            if t:
                return Match("open_target", {"kind": t.kind, "value": t.value, "label": t.label}, 0.97, "param")
        # close app
        a = _strip_prefix(words, F_CLOSE_PRE) or 0
        b = _strip_suffix(words[a:], F_CLOSE_SUF) or 0
        if a or b:
            t = self.lexicon.resolve(words[a:len(words) - b])
            if t and t.kind in ("app", "url"):
                procs = t.procs
                if t.kind == "url":      # closing "Facebook" = close the current browser tab
                    return Match("close_tab", {"label": t.label}, 0.9, "param")
                return Match("close_app", {"label": t.label, "procs": list(procs)}, 0.97, "param")
        return None

    def _p_open_unknown(self, raw, toks, words):
        a = _strip_prefix(words, F_OPEN_PRE) or 0
        b = _strip_suffix(words[a:], F_OPEN_SUF[:5]) or 0       # not "যাও"/"দেখাও": too generic
        if (a or b) and len(words) - a - b > 0:
            name = self._rawspan(raw, toks, a, len(toks) - b)
            return Match("open_unknown", {"name": name}, 0.6, "param")
        return None

    # ---- phrase matching ---------------------------------------------------
    def _contiguous(self, words: list[str]) -> Optional[Match]:
        best = None
        n = len(words)
        for intent, pw, _k in self._phrases:
            L = len(pw)
            if L > n or (L == 1 and n > 3) or (L == 2 and n > 5):
                continue
            extra = n - L
            if extra > 2:
                continue
            for i in range(0, n - L + 1):
                if words[i:i + L] == pw:
                    score = (L, -extra)
                    if best is None or score > best[0]:
                        best = (score, intent)
                    break
        if best:
            return Match(best[1], {}, 0.9, "contains")
        return None

    def _fuzzy(self, key: str) -> Optional[Match]:
        if len(key) < 4:
            return None
        best, best_i = 0.0, None
        for intent, _pw, k in self._phrases:
            if abs(len(k) - len(key)) > max(4, len(k) // 3):
                continue
            r = SequenceMatcher(None, key, k).ratio()
            if r > best:
                best, best_i = r, intent
        if best_i is None:
            return None
        need = 0.92 if best_i in SENSITIVE or best_i == "stop_all" else 0.84
        if best >= need:
            return Match(best_i, {}, best, "fuzzy")
        return None


_default: Optional[Parser] = None


def parse(text: str, custom: Optional[list[dict]] = None) -> Optional[Match]:
    global _default
    if _default is None:
        _default = Parser()
    return _default.parse(text, custom)
