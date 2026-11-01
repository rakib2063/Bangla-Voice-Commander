"""Type commands instead of speaking them (testing / debugging).

    python -m bvc.cli "ফেসবুক খোলো"            # parse only
    python -m bvc.cli --dry "নিচে স্ক্রল করো"   # run through the engine, actions are logged, not executed
    python -m bvc.cli --live "নতুন ট্যাব খোলো"   # really execute
"""
import argparse
import sys

from .config import Settings
from .db import Database
from .engine import CommandEngine
from .nlp.parser import Parser


class _SilentTTS:
    speaking = False
    def say(self, text): print(f"   🔊 {text}")
    def stop(self): pass


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="+")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args(argv)
    text = " ".join(args.text)
    db = Database()
    settings = Settings(db)
    if not (args.dry or args.live):
        m = Parser(settings.get("aliases")).parse(text, db.list_custom(True))
        print(m if m else "বুঝতে পারিনি (no match)")
        return 0
    settings.set("dry_run", not args.live)
    engine = CommandEngine(settings, db, _SilentTTS())
    out = engine.handle_text(text, source="text", wait=True)
    print(out)
    if not args.live:
        for c in engine.a.ctx.calls:
            print("   [dry-run]", c)
    engine.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
