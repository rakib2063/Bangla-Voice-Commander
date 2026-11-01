"""Bangla text normalisation.

Goal: make different spellings / ASR variants of the same command compare equal.
 * light()      - Unicode NFC, zero-width removal, whitespace cleanup (keeps punctuation)
 * tokenize()   - canonical tokens that still remember which raw words they came from
 * skeleton()   - phonetic folding used for equality / fuzzy comparison
"""
from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple

_ZW = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_STRIP = re.compile(r"[।॥,.!?;:\"'“”‘’()\[\]{}<>…~`^*=+|\\@#$%&]")
_SPLIT = re.compile(r"[\s\-–—_/]+")

# canonical form -> spelling / conjugation variants (ASR output and natural speech)
_GROUPS = {
    # verbs
    "করো": ["করুন", "কর", "করেন"],
    "খোলো": ["খুলুন", "খোল", "খুলো", "খুল"],
    "যাও": ["যান", "যা", "যেও"],
    "দাও": ["দিন", "দেন", "দে", "দিও"],
    "দেখাও": ["দেখান", "দেখা"],
    "থামো": ["থামুন", "থামাও", "থামান", "থাম", "থেমে"],
    "চালাও": ["চালান", "চালা", "চালিয়ে"],
    "বাড়াও": ["বাড়ান", "বাড়া"],
    "কমাও": ["কমান", "কমা"],
    "লেখো": ["লিখুন", "লিখো", "লেখ", "লিখ", "লেখুন"],
    "খোঁজো": ["খুঁজুন", "খুঁজো", "খুজো", "খোজো", "খুজুন", "খুঁজ", "খোঁজ"],
    "নামো": ["নামুন", "নাম"],
    "ওঠো": ["উঠো", "উঠুন", "ওঠ", "উঠ"],
    "চাপো": ["চাপুন", "চাপ"],
    "সরাও": ["সরান", "সরা"],
    "ফেলো": ["ফেলুন", "ফেল"],
    "নাও": ["নিন", "নে"],
    "তোলো": ["তুলুন", "তোল", "তুলো"],
    "বলো": ["বলুন", "বল"],
    # directions / nouns
    "উপরে": ["ওপরে", "উপর", "ওপর", "উপরের", "ওপরের"],
    "নিচে": ["নীচে", "নিচ", "নীচ", "নিচের", "নীচের"],
    "পেছনে": ["পিছনে", "পেছন", "পিছন", "পিছে"],
    "স্ক্রল": ["স্ক্রোল", "স্ক্রল্", "স্ক্রলিং", "স্ক্রোলিং"],
    "ক্লিক": ["ক্লীক", "ক্লিক্"],
    "ট্যাব": ["টেব", "ট্যাবে", "ট্যাবটি", "ট্যাবটা", "টেবে", "ট্যাব্"],
    "পোস্ট": ["পোষ্ট", "পোস্টে", "পোস্টটি", "পোস্টটা", "পোস্টগুলো"],
    "ফেসবুক": ["ফেইসবুক", "ফেজবুক", "ফেসবুকে", "ফেসবুকের", "ফেসবুকটা", "facebook", "fb"],
    "ইউটিউব": ["ইউটিউবে", "ইউটিউবের", "youtube"],
    "গুগল": ["গুগলে", "গুগল্", "google"],
    "ভলিউম": ["ভলুম", "ভলিয়াম", "ভোলিউম", "volume", "আওয়াজ", "সাউন্ড", "শব্দ", "sound"],
    "ভিডিও": ["ভিডিওটা", "ভিডিওটি", "ভিডিয়ো", "ভিডিওতে", "video"],
    "নম্বর": ["নম্বরে", "নাম্বার", "নাম্বারে", "নং", "নম্বরটি", "নাম্বারটি", "number"],
    "স্টপ": ["ষ্টপ", "stop"],
    "বন্ধ": ["বন্দ"],
    "ক্লোজ": ["ক্লোস", "close"],
    "রিফ্রেশ": ["রিফ্রেস", "refresh"],
    "কমেন্ট": ["কমেন্টস", "কমেন্টগুলো", "মন্তব্য", "মন্তব্যগুলো", "কমেন্টটা", "comment", "comments"],
    "স্ক্রিন": ["স্ক্রীন", "screen"],
    "পরের": ["পরবর্তী", "পরবর্তি", "নেক্সট", "next"],
    "আগের": ["পূর্বের", "প্রিভিয়াস", "পূর্ববর্তী", "previous", "prev"],
    "হ্যাঁ": ["হাঁ", "হ্যা", "হা", "জি", "yes", "yeah"],
    "না": ["নাহ", "no", "nope"],
    "ওপেন": ["open"],
    "সার্চ": ["search", "সার্চ্"],
    "এন্টার": ["এণ্টার", "enter"],
    "টাইপ": ["type"],
}
ALIAS: dict[str, str] = {}
for _canon, _variants in _GROUPS.items():
    for _v in _variants:
        ALIAS[_v.lower()] = _canon

FILLERS = {"প্লিজ", "please", "plz", "একটু", "তো", "ভাই", "আপু", "ভাইয়া"}
_MULTI = {  # raw (cleaned) bigram -> canonical token ("" = drop)
    ("করে", "দাও"): "করো", ("করে", "দিন"): "করো", ("করে", "দেন"): "করো",
    ("দয়া", "করে"): "", ("আমার", "জন্য"): "",
}

_FOLD = str.maketrans({
    "ী": "ি", "ূ": "ু", "ঈ": "ই", "ঊ": "উ", "শ": "স", "ষ": "স", "ণ": "ন",
    "য": "জ", "ৎ": "ত", "ঁ": "", "ঃ": "", "\u09bc": "", "ো": "ু", "ৌ": "ু",
    "ড": "ড", " ": "",
})


class Tok(NamedTuple):
    c: str      # canonical token
    s: int      # first raw token index
    e: int      # one past last raw token index


def light(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = _ZW.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def clean(raw: str) -> str:
    return _STRIP.sub("", raw).translate(_BN_DIGITS).lower()


def canon_token(raw: str) -> str:
    c = clean(raw)
    return ALIAS.get(c, c)


def tokenize(text: str) -> tuple[list[str], list[Tok]]:
    """Return (raw_tokens, canonical_tokens)."""
    raw = [r for r in _SPLIT.split(light(text)) if r]
    toks: list[Tok] = []
    i = 0
    while i < len(raw):
        if i + 1 < len(raw):
            key = (clean(raw[i]), clean(raw[i + 1]))
            if key in _MULTI:
                if _MULTI[key]:
                    toks.append(Tok(_MULTI[key], i, i + 2))
                i += 2
                continue
        c = canon_token(raw[i])
        if c and c not in FILLERS:
            toks.append(Tok(c, i, i + 1))
        i += 1
    return raw, toks


def canon_words(text: str) -> list[str]:
    return [t.c for t in tokenize(text)[1]]


def skeleton(s: str) -> str:
    return unicodedata.normalize("NFC", s).translate(_FOLD)


def skel_words(words: list[str]) -> str:
    return skeleton("".join(words))
