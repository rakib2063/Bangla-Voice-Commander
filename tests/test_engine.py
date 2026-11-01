"""Engine tests in dry-run mode (no mouse/keyboard/Windows needed)."""
import os, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["BVC_HOME"] = tempfile.mkdtemp(prefix="bvc_test_")

from bvc.config import Settings
from bvc.db import Database
from bvc.engine import CommandEngine


class FakeTTS:
    speaking = False
    def __init__(self): self.said = []
    def say(self, t): self.said.append(t)
    def stop(self): pass


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(os.path.join(os.environ["BVC_HOME"], f"t{time.time_ns()}.sqlite3"))
        self.s = Settings(self.db)
        self.s.update({"dry_run": True, "keep_history": True})
        self.tts = FakeTTS()
        self.events = []
        self.e = CommandEngine(self.s, self.db, self.tts, lambda n, **k: self.events.append((n, k)))

    def tearDown(self):
        self.e.shutdown()

    def run_cmd(self, text):
        return self.e.handle_text(text, source="text", wait=True)

    def calls(self):
        return [c[0] for c in self.e.a.ctx.calls]

    def test_basic_actions(self):
        self.assertTrue(self.run_cmd("নতুন ট্যাব খোলো").ok)
        self.assertIn("hotkey", self.calls())
        self.assertIn("নতুন ট্যাব খোলা হয়েছে।", self.tts.said)
        self.run_cmd("ফেসবুক খোলো")
        self.assertIn(("open_url", ("https://www.facebook.com",)), self.e.a.ctx.calls)
        self.assertTrue(any("ফেসবুক খুলছি" in s for s in self.tts.said))

    def test_not_understood_is_reported(self):
        out = self.run_cmd("আজকে আবহাওয়া কেমন")
        self.assertFalse(out.ok)
        self.assertIn("কমান্ডটি বুঝতে পারিনি।", self.tts.said)

    def test_continuous_scroll_and_emergency_stop(self):
        self.run_cmd("ফেসবুক স্ক্রল করতে থাকো")
        self.assertTrue(self.e.a.mouse.is_scrolling)
        time.sleep(0.4)
        self.assertGreater(self.calls().count("scroll"), 1)
        out = self.e.handle_text("থামো", wait=True)
        self.assertFalse(self.e.a.mouse.is_scrolling)
        self.assertEqual(out.intent, "stop_all")

    def test_scroll_stop_command(self):
        self.run_cmd("নিচে স্ক্রল করতে থাকো")
        self.run_cmd("স্ক্রল বন্ধ করো")
        self.assertFalse(self.e.a.mouse.is_scrolling)

    def test_shutdown_requires_confirmation(self):
        self.run_cmd("কম্পিউটার বন্ধ করো")
        self.assertNotIn("shutdown", self.calls())                      # nothing executed yet
        self.assertTrue(any(n == "confirm" for n, _ in self.events))
        out = self.run_cmd("না")
        self.assertNotIn("shutdown", self.calls())
        self.run_cmd("কম্পিউটার বন্ধ করো")
        self.run_cmd("হ্যাঁ")
        self.assertIn("shutdown", self.calls())
        # emergency stop aborts a scheduled shutdown
        self.e.handle_text("Stop", wait=True)
        self.assertIn(("shutdown", ("/a",)), self.e.a.ctx.calls)

    def test_confirmation_withdrawn_by_other_command(self):
        self.run_cmd("ডিলিট করো")
        self.run_cmd("নতুন ট্যাব খোলো")
        self.run_cmd("হ্যাঁ")                                            # nothing pending any more
        self.assertNotIn(("press", ("delete",)), self.e.a.ctx.calls)

    def test_confirm_expires(self):
        self.s.set("confirm_timeout_s", 1)
        self.run_cmd("রিস্টার্ট করো")
        time.sleep(1.4)
        self.run_cmd("হ্যাঁ")
        self.assertNotIn("shutdown", self.calls())

    def test_duplicate_click_suppressed(self):
        self.run_cmd("লাইক দাও")
        n = len(self.e.a.ctx.calls)
        self.e.handle_text("লাইক দাও", wait=True)
        self.assertEqual(len(self.e.a.ctx.calls), n)

    def test_numbered_labels(self):
        self.assertFalse(self.run_cmd("৩ নম্বরে ক্লিক করো").ok)         # no overlay yet
        self.assertTrue(self.run_cmd("নম্বর দেখাও").ok)
        self.assertFalse(self.run_cmd("৯ নম্বরে ক্লিক করো").ok)         # out of range
        self.assertTrue(self.run_cmd("২ নম্বরে ক্লিক করো").ok)
        self.assertIn("click", self.calls())

    def test_type_bangla(self):
        out = self.run_cmd("লেখো আমি ভালো আছি")
        self.assertTrue(out.ok)
        self.assertIn(("type_text", ("আমি ভালো আছি",)), self.e.a.ctx.calls)

    def test_sleep_mode(self):
        self.run_cmd("ঘুমাও")
        self.assertIsNone(self.e.handle_text("নতুন ট্যাব খোলো", wait=True))
        self.run_cmd("জাগো")
        self.assertTrue(self.run_cmd("নতুন ট্যাব খোলো").ok)

    def test_wake_word(self):
        self.s.set("require_wake_word", True)
        self.assertIsNone(self.e.handle_text("নতুন ট্যাব খোলো", wait=True))
        self.assertTrue(self.e.handle_text("কমান্ডার নতুন ট্যাব খোলো", wait=True).ok)
        self.assertEqual(self.e.handle_text("থামো", wait=True).intent, "stop_all")   # no wake word needed

    def test_custom_command(self):
        self.db.save_custom(None, "আমার কাজ", ["আমার কাজ শুরু করো"], [
            {"type": "open_app", "value": "ক্রোম"}, {"type": "open_url", "value": "facebook.com"},
            {"type": "open_url", "value": "https://youtube.com"}, {"type": "command", "value": "নতুন ট্যাব খোলো"},
            {"type": "command", "value": "কম্পিউটার বন্ধ করো"}])
        out = self.run_cmd("আমার কাজ শুরু করো")
        self.assertFalse(out.ok)                                         # shutdown step refused, others ran
        self.assertIn("needs confirmation", out.detail)
        self.assertIn(("launch", ("chrome",)), self.e.a.ctx.calls)
        self.assertIn(("open_url", ("https://facebook.com",)), self.e.a.ctx.calls)
        self.assertNotIn("shutdown", self.calls())
        self.assertIn("ধাপ 5", out.detail)

    def test_history_respects_setting(self):
        self.run_cmd("নতুন ট্যাব খোলো")
        self.assertEqual(len(self.db.recent_history()), 1)
        self.s.set("keep_history", False)
        self.run_cmd("পেছনে যাও")
        self.assertEqual(len(self.db.recent_history()), 1)

    def test_volume_set_and_not_windows_report(self):
        self.assertTrue(self.run_cmd("ভলিউম ৩০ করো").ok)
        self.assertIn(("volume", ("set", 30)), self.e.a.ctx.calls)


if __name__ == "__main__":
    unittest.main()
