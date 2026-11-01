import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bvc.nlp.parser import Parser, parse_number

P = Parser()
CUSTOM = [{"id": 7, "name": "আমার কাজ", "phrases": ["আমার কাজ শুরু করো"], "enabled": True}]

CASES = [  # spoken text -> expected intent
    ("ফেসবুক খোলো", "open_target"), ("নিচে স্ক্রল করো", "scroll_down"), ("উপরে যাও", "scroll_up"),
    ("স্ক্রল বন্ধ করো", "scroll_stop"), ("পরের পোস্ট দেখাও", "next_post"), ("আগের পোস্ট দেখাও", "prev_post"),
    ("এখানে ক্লিক করো", "click"), ("ক্রোম খোলো", "open_target"), ("নতুন ট্যাব খোলো", "new_tab"),
    ("ট্যাব বন্ধ করো", "close_tab"), ("পেছনে যাও", "back"), ("সামনে যাও", "forward"),
    ("ভলিউম বাড়াও", "vol_up"), ("ভলিউম কমাও", "vol_down"), ("ভিডিও চালাও", "video_play"),
    ("ভিডিও বন্ধ করো", "video_pause"), ("কম্পিউটার বন্ধ করো", "shutdown"),
    ("ফেসবুক স্ক্রল করতে থাকো।", "scroll_auto_down"),
    ("থামো", "stop_all"), ("বন্ধ করো", "stop_all"), ("Stop", "stop_all"), ("stop", "stop_all"),
    # equivalents from the spec
    ("নিচে যাও", "scroll_down"), ("Scroll down", "scroll_down"), ("Go down", "scroll_down"),
    # ASR / spelling variants
    ("ওপরে যাও", "scroll_up"), ("পিছনে যাও", "back"), ("স্ক্রোল ডাউন", "scroll_down"),
    ("স্ক্রল বন্দ করো", "scroll_stop"), ("ফেইসবুক ওপেন করো", "open_target"), ("ইউটিউব খুলুন", "open_target"),
    ("দয়া করে নিচে স্ক্রল করে দাও", "scroll_down"), ("এবার নিচে যাও প্লিজ", "scroll_down"),
    ("ক্রোম ট্যাব বন্ধ করো", "close_tab"), ("ক্রোম বন্ধ করো", "close_app"),
    ("ফেসবুকে যাও", "open_target"), ("facebook.com খোলো", "open_target"),
    ("লাইক দাও", "like"), ("কমেন্ট খোলো", "comments_open"), ("মিউট করো", "video_mute"),
    ("রিস্টার্ট করো", "restart"), ("হ্যাঁ", "confirm_yes"), ("না", "confirm_no"),
    ("আমার কাজ শুরু করো", "custom"),
]


class ParserTests(unittest.TestCase):
    def test_cases(self):
        bad = []
        for text, want in CASES:
            m = P.parse(text, CUSTOM)
            got = m.intent if m else None
            if got != want:
                bad.append((text, want, got))
        self.assertEqual(bad, [])

    def test_params(self):
        self.assertEqual(P.parse("৫ নম্বরে ক্লিক করো").params["n"], 5)
        self.assertEqual(P.parse("পাঁচ নম্বর ক্লিক করো").params["n"], 5)
        self.assertEqual(P.parse("ভলিউম ৫০ করো").params["level"], 50)
        self.assertEqual(P.parse("ভলিউম পঞ্চাশ করো").params["level"], 50)
        self.assertEqual(P.parse("গুগলে বাংলাদেশের খবর সার্চ করো").params["query"], "বাংলাদেশের খবর")
        self.assertEqual(P.parse("লেখো আমি ভালো আছি").params["text"], "আমি ভালো আছি")
        self.assertEqual(P.parse("লগইন বাটনে ক্লিক করো").params["name"], "লগইন")
        self.assertEqual(P.parse("ক্রোম খোলো").params["value"], "chrome")
        self.assertEqual(P.parse("facebook.com খোলো").params["value"], "https://facebook.com")

    def test_unknown_is_not_guessed(self):
        for t in ("আজকে আবহাওয়া কেমন", "কুছ নাই", "asdf qwer"):
            m = P.parse(t)
            self.assertTrue(m is None or m.intent in ("open_unknown",), (t, m))

    def test_sensitive_needs_exactness(self):
        # similar-sounding junk must not trigger shutdown
        m = P.parse("কম্পিউটার বন্দ")
        self.assertTrue(m is None or not m.sensitive or m.score >= 0.92)

    def test_numbers(self):
        self.assertEqual(parse_number("৭"), 7)
        self.assertEqual(parse_number("সাত"), 7)
        self.assertEqual(parse_number("ষোলো"), 16)

    def test_no_duplicate_phrases_across_intents(self):
        from bvc.nlp.intents import INTENT_PHRASES
        from bvc.nlp.normalizer import canon_words, skel_words
        seen = {}
        for intent, phrases in INTENT_PHRASES.items():
            for ph in phrases:
                k = skel_words(canon_words(ph))
                if k in seen and seen[k] != intent:
                    self.fail(f"'{ph}' ({intent}) collides with {seen[k]}")
                seen[k] = intent


if __name__ == "__main__":
    unittest.main()
