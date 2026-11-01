"""Known websites and applications that can be opened/closed by name."""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from .normalizer import canon_words, skel_words


@dataclass(frozen=True)
class Target:
    kind: str                 # "url" | "app" | "uri"
    value: str                # URL, executable/command, or ms-settings: style URI
    label: str                # display / spoken name
    procs: tuple = ()         # process names for "close"
    key: str = ""


def _t(kind, value, label, names, procs=()):
    return Target(kind, value, label, tuple(procs), key=label), names


_BUILTIN = [
    # websites
    _t("url", "https://www.facebook.com", "ফেসবুক", ["ফেসবুক", "facebook", "fb"]),
    _t("url", "https://www.youtube.com", "ইউটিউব", ["ইউটিউব", "youtube"]),
    _t("url", "https://www.google.com", "গুগল", ["গুগল", "google"]),
    _t("url", "https://mail.google.com", "জিমেইল", ["জিমেইল", "জিমেল", "gmail"]),
    _t("url", "https://www.messenger.com", "মেসেঞ্জার", ["মেসেঞ্জার", "messenger"]),
    _t("url", "https://web.whatsapp.com", "হোয়াটসঅ্যাপ ওয়েব", ["হোয়াটসঅ্যাপ", "হোয়াটসঅ্যাপ ওয়েব", "whatsapp"]),
    _t("url", "https://www.instagram.com", "ইনস্টাগ্রাম", ["ইনস্টাগ্রাম", "ইন্সটাগ্রাম", "instagram"]),
    _t("url", "https://x.com", "এক্স", ["টুইটার", "twitter"]),
    _t("url", "https://www.linkedin.com", "লিংকডইন", ["লিংকডইন", "linkedin"]),
    _t("url", "https://github.com", "গিটহাব", ["গিটহাব", "github"]),
    _t("url", "https://chat.openai.com", "চ্যাটজিপিটি", ["চ্যাটজিপিটি", "chatgpt"]),
    _t("url", "https://claude.ai", "ক্লড", ["ক্লড", "claude"]),
    _t("url", "https://bn.wikipedia.org", "উইকিপিডিয়া", ["উইকিপিডিয়া", "wikipedia"]),
    _t("url", "https://www.prothomalo.com", "প্রথম আলো", ["প্রথম আলো", "প্রথমআলো"]),
    _t("url", "https://www.thedailystar.net", "ডেইলি স্টার", ["ডেইলি স্টার", "ডেইলিস্টার"]),
    _t("url", "https://www.google.com/maps", "গুগল ম্যাপ", ["গুগল ম্যাপ", "ম্যাপ", "google maps"]),
    _t("url", "https://translate.google.com", "গুগল ট্রান্সলেট", ["গুগল ট্রান্সলেট", "ট্রান্সলেট"]),
    _t("url", "https://drive.google.com", "গুগল ড্রাইভ", ["গুগল ড্রাইভ", "ড্রাইভ"]),
    # applications
    _t("app", "chrome", "গুগল ক্রোম", ["ক্রোম", "গুগল ক্রোম", "chrome"], ["chrome.exe"]),
    _t("app", "msedge", "মাইক্রোসফট এজ", ["এজ", "মাইক্রোসফট এজ", "edge"], ["msedge.exe"]),
    _t("app", "firefox", "ফায়ারফক্স", ["ফায়ারফক্স", "firefox"], ["firefox.exe"]),
    _t("app", "notepad", "নোটপ্যাড", ["নোটপ্যাড", "notepad"], ["notepad.exe"]),
    _t("app", "calc", "ক্যালকুলেটর", ["ক্যালকুলেটর", "calculator"], ["CalculatorApp.exe", "calc.exe", "Calculator.exe"]),
    _t("app", "mspaint", "পেইন্ট", ["পেইন্ট", "paint"], ["mspaint.exe"]),
    _t("app", "winword", "ওয়ার্ড", ["ওয়ার্ড", "মাইক্রোসফট ওয়ার্ড", "word"], ["WINWORD.EXE"]),
    _t("app", "excel", "এক্সেল", ["এক্সেল", "excel"], ["EXCEL.EXE"]),
    _t("app", "powerpnt", "পাওয়ারপয়েন্ট", ["পাওয়ারপয়েন্ট", "powerpoint"], ["POWERPNT.EXE"]),
    _t("app", "code", "ভিএস কোড", ["ভিএস কোড", "ভিএসকোড", "vs code", "vscode"], ["Code.exe"]),
    _t("app", "explorer", "ফাইল এক্সপ্লোরার", ["ফাইল এক্সপ্লোরার", "এক্সপ্লোরার", "file explorer", "explorer", "ফাইল ম্যানেজার"], []),
    _t("app", "cmd", "কমান্ড প্রম্পট", ["কমান্ড প্রম্পট", "cmd", "টার্মিনাল"], ["cmd.exe"]),
    _t("app", "taskmgr", "টাস্ক ম্যানেজার", ["টাস্ক ম্যানেজার", "task manager"], ["Taskmgr.exe"]),
    _t("app", "vlc", "ভিএলসি", ["ভিএলসি", "vlc"], ["vlc.exe"]),
    _t("app", "spotify", "স্পটিফাই", ["স্পটিফাই", "spotify"], ["Spotify.exe"]),
    _t("app", "telegram", "টেলিগ্রাম", ["টেলিগ্রাম", "telegram"], ["Telegram.exe"]),
    _t("app", "zoom", "জুম", ["জুম", "zoom"], ["Zoom.exe"]),
    _t("uri", "ms-settings:", "সেটিংস", ["সেটিংস", "সেটিং", "settings"], []),
    _t("uri", "microsoft.windows.camera:", "ক্যামেরা", ["ক্যামেরা", "camera"], []),
    _t("app", "control", "কন্ট্রোল প্যানেল", ["কন্ট্রোল প্যানেল", "control panel"], []),
]


class Lexicon:
    def __init__(self, extras: Optional[dict] = None):
        self._entries: list[tuple[str, Target]] = []
        for target, names in _BUILTIN:
            for n in names:
                self._entries.append((skel_words(canon_words(n)), target))
        for name, spec in (extras or {}).items():
            try:
                t = Target(spec.get("kind", "app"), spec["value"], name, tuple(spec.get("procs", [])), name)
            except (KeyError, AttributeError):
                continue
            self._entries.append((skel_words(canon_words(name)), t))

    def resolve(self, words: list[str]) -> Optional[Target]:
        if not words:
            return None
        cands = [skel_words(words)]
        last = words[-1]
        if last.endswith("ে") and len(last) > 3:           # locative: ফেসবুকে -> ফেসবুক
            cands.append(skel_words(words[:-1] + [last[:-1]]))
        for c in cands:
            for key, t in self._entries:
                if key == c:
                    return t
        best, best_t = 0.0, None
        for c in cands:
            if len(c) < 5:
                continue
            for key, t in self._entries:
                if len(key) < 5:
                    continue
                r = SequenceMatcher(None, c, key).ratio()
                if r > best:
                    best, best_t = r, t
        return best_t if best >= 0.87 else None

    def all_apps(self) -> list[Target]:
        seen, out = set(), []
        for _, t in self._entries:
            if t.key not in seen:
                seen.add(t.key)
                out.append(t)
        return out
