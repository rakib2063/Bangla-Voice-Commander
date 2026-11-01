"""Command engine: text -> intent -> (confirmation) -> action -> spoken feedback.

Safety rules implemented here:
  * Emergency stop ("থামো"/"বন্ধ করো"/"Stop", UI button, global hotkey) runs on the caller's thread,
    never waits in the work queue, cancels scrolling / drags / queued work / pending confirmations /
    a scheduled shutdown, and silences speech.
  * Sensitive intents (shutdown, restart, delete, send) always require an explicit yes.
  * Duplicate suppression for click-like actions, honest failure reporting (ActionResult.ok).
  * The parser is deterministic; no AI model ever executes anything.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Optional

from .actions import Actions, ActionResult, KEYSPECS, foreground_info
from .actions import uia
from .actions.uia import UiItem
from .nlp import responses as R
from .nlp.intents import INTENT_META
from .nlp.normalizer import canon_words, light
from .nlp.parser import Match, Parser

log = logging.getLogger("bvc.engine")
NO_REPEAT = {"like", "click", "right_click", "double_click", "click_name", "click_number", "key_enter",
             "send_message", "delete_sel", "new_tab", "close_tab", "open_target", "video_play", "video_pause"}
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)


@dataclass
class Outcome:
    heard: str
    intent: str = ""
    ok: bool = True
    message: str = ""
    detail: str = ""
    params: Optional[dict] = None


class CommandEngine:
    def __init__(self, settings, db, tts, emit: Optional[Callable] = None, actions: Optional[Actions] = None):
        self.s, self.db, self.tts = settings, db, tts
        self.emit = emit or (lambda *a, **k: None)
        self.a = actions or Actions(settings)
        self.parser = Parser(settings.get("aliases"))
        self.mode = settings.get("mode")
        self.asleep = False
        self._gen = 0
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bvc-exec")
        self._lock = threading.RLock()
        self._pending: Optional[dict] = None
        self._recent: dict[str, float] = {}
        self._power_scheduled = False
        self._overlay: list[UiItem] = []
        self._overlay_timer: Optional[threading.Timer] = None
        settings.on_change(self._on_settings)
        if settings.get("keep_history"):
            try:
                db.purge_history_older_than(int(settings.get("history_days")))
            except Exception:
                log.exception("history purge failed")
        self._table = self._build_table()

    # ======================================================================== public API
    def handle_text(self, text: str, source: str = "voice", wait: bool = False) -> Optional[Outcome]:
        text = light(text)
        if not text:
            return None
        self.emit("heard", text=text)
        custom = self.db.list_custom(True)
        m = self.parser.parse(text, custom)

        # ---- emergency: highest priority, never queued ------------------------------------
        if m and m.intent == "stop_all":
            self.emergency_stop(announce=False)
            out = self._finish(m, text, ActionResult(True, R.OK["stop_all"], "emergency stop"))
            return out

        # ---- sleep mode: only "wake up" is accepted ---------------------------------------
        if self.asleep:
            if m and m.intent == "wake_up":
                return self._submit(m, text, wait)
            self.emit("ignored", text=text, reason="sleeping")
            return None

        # ---- optional wake word ---------------------------------------------------------------
        if self.s.get("require_wake_word") and source == "voice":
            ww = canon_words(self.s.get("wake_word"))
            toks = canon_words(text)
            answering = self._pending and m and m.intent in ("confirm_yes", "confirm_no")
            if not answering:
                if ww and toks[:len(ww)] == ww:
                    text = " ".join(light(text).split()[len(ww):])
                    m = self.parser.parse(text, custom) if text else None
                else:
                    self.emit("ignored", text=text, reason="no wake word")
                    return None

        if m is None:
            return self._finish(Match("unknown"), text, ActionResult.fail(R.NOT_UNDERSTOOD, "not understood"))

        # ---- pending confirmation --------------------------------------------------------------
        if self._pending:
            if m.intent == "confirm_yes":
                return self._confirm(True, wait)
            if m.intent == "confirm_no":
                return self._confirm(False, wait)
            self._clear_pending()                             # any other command withdraws the question
        elif m.intent in ("confirm_yes", "confirm_no"):
            return self._finish(m, text, ActionResult(True, R.NOTHING_PENDING, "nothing pending"))

        if m.sensitive:
            return self._ask_confirmation(m, text)
        return self._submit(m, text, wait)

    def confirm(self, yes: bool) -> None:
        """Called by the UI buttons."""
        if self._pending:
            self._confirm(yes, wait=False)

    def emergency_stop(self, announce: bool = True) -> None:
        with self._lock:
            self._gen += 1
        self.a.mouse.stop_scrolling()
        self.a.mouse.release_all()
        self.tts.stop()
        self._clear_pending(silent=True)
        self._hide_overlay()
        if self._power_scheduled:
            try:
                self.a.system.cancel_power()
            except Exception:
                log.exception("could not cancel shutdown")
            self._power_scheduled = False
        self.emit("emergency")
        if announce:
            self.tts.say(R.OK["stop_all"])

    def shutdown(self) -> None:
        self.emergency_stop(announce=False)
        self._pool.shutdown(wait=False, cancel_futures=True)

    def current_app(self) -> str:
        title, proc = foreground_info()
        return f"{proc}  —  {title}"[:120] if proc or title else ""

    # ======================================================================== internals
    def _on_settings(self, changes: dict) -> None:
        if "aliases" in changes:
            self.parser = Parser(self.s.get("aliases"))

    def _submit(self, m: Match, heard: str, wait: bool) -> Optional[Outcome]:
        key = m.intent + str(sorted(m.params.items())) if m.params else m.intent
        if m.intent in NO_REPEAT:
            now = time.time()
            if now - self._recent.get(key, 0) < 1.5:
                self.emit("ignored", text=heard, reason="duplicate")
                return None
            self._recent[key] = now
        gen = self._gen
        fut: Future = self._pool.submit(self._execute, m, heard, gen)
        return fut.result(timeout=120) if wait else None

    def _execute(self, m: Match, heard: str, gen: int) -> Outcome:
        if gen != self._gen:
            return Outcome(heard, m.intent, False, "cancelled", "cancelled by emergency stop")
        try:
            res = self._dispatch(m, gen)
        except Exception as e:
            if type(e).__name__ == "FailSafeException":
                self.emergency_stop()
                res = ActionResult.fail("মাউস স্ক্রিনের কোণায় যাওয়ায় সব থামানো হয়েছে।", "pyautogui fail-safe")
            else:
                log.exception("action failed")
                res = ActionResult.fail("কাজটি করতে গিয়ে সমস্যা হয়েছে।", f"{type(e).__name__}: {e}")
        return self._finish(m, heard, res)

    def _finish(self, m: Match, heard: str, res: ActionResult) -> Outcome:
        if res.skipped:
            self.emit("ignored", text=heard, reason=res.detail)
            return Outcome(heard, m.intent, True, "", res.detail, m.params)
        if res.speak is not None:
            msg = res.speak
        elif res.ok:
            msg = R.OK.get(m.intent, "ঠিক আছে।")
        else:
            msg = "কাজটি করা যায়নি।"
        if msg:
            self.tts.say(msg)
        out = Outcome(heard, m.intent, res.ok, msg, res.detail, m.params)
        if self.s.get("keep_history"):
            try:
                self.db.add_history(heard, m.intent, m.params, res.ok, res.detail or msg)
            except Exception:
                log.exception("history write failed")
        self.emit("result", heard=heard, intent=m.intent, ok=res.ok, message=msg, detail=res.detail,
                  label=INTENT_META.get(m.intent, ("", m.intent))[1], ts=time.time())
        return out

    # ---- confirmation ------------------------------------------------------------------------
    def _ask_confirmation(self, m: Match, heard: str) -> Optional[Outcome]:
        timeout = int(self.s.get("confirm_timeout_s"))
        token = object()
        prompt = R.CONFIRM_PROMPTS.get(m.intent, "নিশ্চিত করতে হ্যাঁ বলুন।")
        timer = threading.Timer(timeout, self._expire, args=(token,))
        timer.daemon = True
        self._pending = {"match": m, "heard": heard, "token": token, "timer": timer}
        timer.start()
        self.tts.say(prompt)
        label = INTENT_META.get(m.intent, ("", m.intent))[1]
        self.emit("confirm", prompt=prompt, label=label, heard=heard, timeout=timeout)
        return Outcome(heard, m.intent, True, prompt, "waiting for confirmation", m.params)

    def _expire(self, token) -> None:
        p = self._pending
        if p and p["token"] is token:
            self._pending = None
            self.tts.say(R.EXPIRED)
            self.emit("confirm_done", confirmed=False, expired=True)

    def _clear_pending(self, silent: bool = False) -> None:
        p, self._pending = self._pending, None
        if p:
            p["timer"].cancel()
            if not silent:
                self.emit("confirm_done", confirmed=False, expired=False)

    def _confirm(self, yes: bool, wait: bool) -> Optional[Outcome]:
        p, self._pending = self._pending, None
        if not p:
            return None
        p["timer"].cancel()
        self.emit("confirm_done", confirmed=yes, expired=False)
        m, heard = p["match"], p["heard"]
        if not yes:
            return self._finish(m, heard, ActionResult(True, R.CANCELLED, "user declined"))
        gen = self._gen
        fut = self._pool.submit(self._execute, m, heard, gen)
        return fut.result(timeout=120) if wait else None

    # ---- overlay (numbered labels) -------------------------------------------------------------
    def _hide_overlay(self) -> None:
        if self._overlay_timer:
            self._overlay_timer.cancel()
            self._overlay_timer = None
        if self._overlay:
            self._overlay = []
        self.emit("overlay_hide")

    # ---- dispatch --------------------------------------------------------------------------------
    def _build_table(self) -> dict[str, Callable[[Match], ActionResult]]:
        a = self.a
        mouse, kb, br, fb, sy = a.mouse, a.keyboard, a.browser, a.facebook, a.system
        t: dict[str, Callable[[Match], ActionResult]] = {
            # scrolling
            "scroll_down": lambda m: mouse.start_scrolling("down") if self.mode == "continuous" else mouse.scroll_step("down"),
            "scroll_up": lambda m: mouse.start_scrolling("up") if self.mode == "continuous" else mouse.scroll_step("up"),
            "scroll_top": lambda m: kb.hotkey("ctrl", "home"),
            "scroll_bottom": lambda m: kb.hotkey("ctrl", "end"),
            "page_down": lambda m: kb.press("pagedown"),
            "page_up": lambda m: kb.press("pageup"),
            "scroll_auto_down": lambda m: mouse.start_scrolling("down"),
            "scroll_auto_up": lambda m: mouse.start_scrolling("up"),
            "scroll_stop": lambda m: ActionResult(True, None if mouse.stop_scrolling() else "স্ক্রল চলছিল না।"),
            "scroll_faster": lambda m: mouse.change_speed(1.5),
            "scroll_slower": lambda m: mouse.change_speed(1 / 1.5),
            # facebook / video
            "next_post": lambda m: fb.next_post(), "prev_post": lambda m: fb.prev_post(),
            "like": lambda m: fb.like(), "unlike": lambda m: fb.unlike(),
            "comments_open": lambda m: fb.comments_open(), "comments_close": lambda m: fb.comments_close(),
            "video_play": lambda m: fb.video("play"), "video_pause": lambda m: fb.video("pause"),
            "video_mute": lambda m: fb.video("mute"), "video_unmute": lambda m: fb.video("unmute"),
            "video_fullscreen": lambda m: kb.press("f"),
            "fb_profile": lambda m: fb.open_profile(), "fb_home": lambda m: fb.open_home(),
            # mouse
            "click": lambda m: mouse.click(), "right_click": lambda m: mouse.click("right"),
            "double_click": lambda m: mouse.click("left", 2),
            "drag_start": lambda m: mouse.drag_start(), "drag_drop": lambda m: mouse.drag_drop(),
            "mouse_up": lambda m: mouse.move("up"), "mouse_down": lambda m: mouse.move("down"),
            "mouse_left": lambda m: mouse.move("left"), "mouse_right": lambda m: mouse.move("right"),
            "mouse_center": lambda m: mouse.center(),
            "show_numbers": self._show_numbers, "hide_numbers": self._do_hide_numbers,
            "click_number": self._click_number,
            "click_name": lambda m: br.click_name(m.params["name"]),
            # browser
            "new_tab": lambda m: br.new_tab(), "close_tab": lambda m: br.close_tab(),
            "next_tab": lambda m: br.next_tab(), "prev_tab": lambda m: br.prev_tab(),
            "reopen_tab": lambda m: br.reopen_tab(), "refresh": lambda m: br.refresh(),
            "back": lambda m: br.back(), "forward": lambda m: br.forward(),
            "zoom_in": lambda m: br.zoom_in(), "zoom_out": lambda m: br.zoom_out(),
            "address_bar": lambda m: br.address_bar(),
            "find_text": lambda m: br.find_text(m.params["query"]),
            "search_google": lambda m: self._with_speech(br.search_google(m.params["query"]), f"{m.params['query']} গুগলে খোঁজা হচ্ছে।"),
            "search_youtube": lambda m: self._with_speech(br.search_youtube(m.params["query"]), f"{m.params['query']} ইউটিউবে খোঁজা হচ্ছে।"),
            "type_text": lambda m: self._with_speech(kb.type_text(m.params["text"]), "লেখা হয়েছে।"),
            # system
            "open_target": self._open_target, "open_unknown": lambda m: sy.open_by_name(m.params["name"]),
            "close_app": lambda m: sy.close_app(m.params["procs"], m.params["label"]),
            "vol_up": lambda m: sy.volume("up"), "vol_down": lambda m: sy.volume("down"),
            "vol_mute": lambda m: sy.volume("mute"), "vol_unmute": lambda m: sy.volume("unmute"),
            "vol_set": lambda m: sy.volume("set", m.params["level"]),
            "bright_up": lambda m: sy.brightness("up"), "bright_down": lambda m: sy.brightness("down"),
            "bright_set": lambda m: sy.brightness("set", m.params["level"]),
            "minimize": lambda m: sy.minimize(), "maximize": lambda m: sy.maximize(),
            "restore_window": lambda m: sy.restore(), "show_desktop": lambda m: sy.show_desktop(),
            "close_window": lambda m: sy.close_window(), "lock": lambda m: sy.lock(),
            "screenshot": lambda m: sy.screenshot(),
            "shutdown": lambda m: self._power("shutdown"), "restart": lambda m: self._power("restart"),
            "cancel_shutdown": self._cancel_power,
            # modes
            "mode_command": lambda m: self._set_mode("command"),
            "mode_continuous": lambda m: self._set_mode("continuous"),
            "sleep_mode": self._sleep, "wake_up": self._wake,
            "listen_stop": lambda m: (self.emit("request_stop_listening"), ActionResult())[1],
            "custom": lambda m: self._run_custom(m.params["id"], self._gen),
        }
        for intent in KEYSPECS:
            t[intent] = (lambda i: lambda m: kb.run_spec(i))(intent)
        return t

    def _dispatch(self, m: Match, gen: Optional[int] = None) -> ActionResult:
        fn = self._table.get(m.intent)
        if fn is None:
            return ActionResult.fail(R.NOT_UNDERSTOOD, f"no handler for {m.intent}")
        return fn(m)

    @staticmethod
    def _with_speech(res: ActionResult, msg: str) -> ActionResult:
        if res.ok and res.speak is None:
            res.speak = msg
        return res

    # ---- individual handlers ----------------------------------------------------------------------
    def _open_target(self, m: Match) -> ActionResult:
        kind, value, label = m.params["kind"], m.params["value"], m.params["label"]
        res = self.a.browser.open_url(value) if kind == "url" else self.a.system.launch(value, label)
        if res.ok and res.speak is None:
            res.speak = f"{label} খুলছি।"
        return res

    def _set_mode(self, mode: str) -> ActionResult:
        self.mode = mode
        self.s.set("mode", mode)
        if mode == "command":
            self.a.mouse.stop_scrolling()
        self.emit("mode", mode=mode)
        return ActionResult()

    def set_mode(self, mode: str) -> None:
        self._set_mode(mode)

    def _sleep(self, m: Match) -> ActionResult:
        self.asleep = True
        self.a.mouse.stop_scrolling()
        self.emit("sleep", asleep=True)
        return ActionResult()

    def _wake(self, m: Match) -> ActionResult:
        self.asleep = False
        self.emit("sleep", asleep=False)
        return ActionResult()

    def _power(self, kind: str) -> ActionResult:
        res = self.a.system.power(kind)
        if res.ok:
            self._power_scheduled = True
        return res

    def _cancel_power(self, m: Match) -> ActionResult:
        res = self.a.system.cancel_power()
        if res.ok:
            self._power_scheduled = False
        return res

    def _show_numbers(self, m: Match) -> ActionResult:
        if self.a.ctx.dry:
            items = [UiItem("Demo button", "ButtonControl", (100, 100, 220, 140)),
                     UiItem("Demo link", "HyperlinkControl", (300, 200, 420, 230))]
        else:
            bad = self.a.ctx.need_windows()
            if bad:
                return bad
            if not uia.available():
                return ActionResult.fail("UI Automation পাওয়া যায়নি (uiautomation ইনস্টল করুন)।", "uiautomation missing")
            items = uia.numbered_items()
        if not items:
            return ActionResult.fail("ক্লিক করার মতো কিছু খুঁজে পাইনি।", "no clickable controls found")
        self._overlay = items
        self.emit("overlay", items=[(i + 1, it.rect, it.name) for i, it in enumerate(items)])
        if self._overlay_timer:
            self._overlay_timer.cancel()
        self._overlay_timer = threading.Timer(45.0, self._hide_overlay)
        self._overlay_timer.daemon = True
        self._overlay_timer.start()
        return ActionResult(detail=f"{len(items)} labels")

    def _do_hide_numbers(self, m: Match) -> ActionResult:
        self._hide_overlay()
        return ActionResult()

    def _click_number(self, m: Match) -> ActionResult:
        n = m.params["n"]
        if not self._overlay:
            return ActionResult.fail("আগে বলুন, নম্বর দেখাও।", "no overlay active")
        if not 1 <= n <= len(self._overlay):
            return ActionResult.fail(f"{n} নম্বর নেই। ১ থেকে {len(self._overlay)} এর মধ্যে বলুন।", "label out of range")
        it = self._overlay[n - 1]
        self._hide_overlay()
        time.sleep(0.15)                                   # let the overlay disappear first
        res = self.a.mouse.click_at(*it.center)
        res.detail = f"label {n} '{it.name}' -> {res.detail}"
        return res

    # ---- custom commands ---------------------------------------------------------------------------
    def _open_named(self, v: str) -> ActionResult:
        if re.search(r"[\\/]|\.(exe|lnk|bat|cmd)$", v, re.I) and not _SCHEME.match(v):
            return self.a.system.launch(v, v)
        if _SCHEME.match(v):
            return self.a.browser.open_url(v)
        t = self.parser.lexicon.resolve(canon_words(v))
        if t:
            return self.a.browser.open_url(t.value) if t.kind == "url" else self.a.system.launch(t.value, t.label)
        if re.match(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}", v, re.I):
            return self.a.browser.open_url("https://" + v)
        return self.a.system.open_by_name(v)

    def _sleep_cancellable(self, secs: float, gen: int) -> bool:
        end = time.time() + secs
        while time.time() < end:
            if gen != self._gen:
                return False
            time.sleep(0 if self.a.ctx.dry else 0.1)
            if self.a.ctx.dry:
                break
        return True

    def _run_custom(self, cid: int, gen: int) -> ActionResult:
        cmd = next((c for c in self.db.list_custom() if c["id"] == cid), None)
        if not cmd:
            return ActionResult.fail("কাস্টম কমান্ডটি পাওয়া যায়নি।", "custom command missing")
        failures: list[str] = []
        for i, st in enumerate(cmd["steps"], 1):
            if gen != self._gen:
                return ActionResult.fail("থামানো হয়েছে।", f"stopped at step {i}")
            kind, v = st.get("type", ""), str(st.get("value", "")).strip()
            if kind == "open_app":
                r = self._open_named(v)
                self._sleep_cancellable(0.8, gen)
            elif kind == "open_url":
                r = self.a.browser.open_url(v if _SCHEME.match(v) else "https://" + v)
                self._sleep_cancellable(0.8, gen)
            elif kind == "hotkey":
                r = self.a.keyboard.hotkey(*[k.strip().lower() for k in v.split("+") if k.strip()])
            elif kind == "type":
                r = self.a.keyboard.type_text(v)
            elif kind == "wait":
                try:
                    secs = max(0.0, min(60.0, float(v)))
                except ValueError:
                    secs = 1.0
                r = ActionResult() if self._sleep_cancellable(secs, gen) else ActionResult.fail("থামানো হয়েছে।")
            elif kind == "say":
                self.tts.say(v)
                r = ActionResult()
            elif kind == "command":
                m2 = self.parser.parse(v)
                if not m2 or m2.intent == "custom":
                    r = ActionResult.fail("ধাপের কমান্ড বুঝতে পারিনি।", f"unknown command '{v}'")
                elif m2.sensitive or m2.intent in ("stop_all", "confirm_yes", "confirm_no"):
                    r = ActionResult.fail("নিরাপত্তার জন্য এই কমান্ড কাস্টম কমান্ডে চালানো যায় না।",
                                          f"'{v}' needs confirmation - not allowed inside macros")
                else:
                    r = self._dispatch(m2, gen)
            else:
                r = ActionResult.fail("অজানা ধাপ।", f"unknown step type '{kind}'")
            if not r.ok:
                failures.append(f"ধাপ {i} ({kind}): {r.detail or r.speak}")
        if failures:
            return ActionResult(False, "কিছু ধাপ ব্যর্থ হয়েছে।", "; ".join(failures))
        return ActionResult(True, f"{cmd['name']} সম্পন্ন হয়েছে।", f"{len(cmd['steps'])} steps done")
