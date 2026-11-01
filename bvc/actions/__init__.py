from .base import ActionResult, Ctx
from .browser import Browser
from .facebook import Facebook
from .keyboard import KEYSPECS, Keyboard
from .mouse import Mouse
from .system import System, foreground_info


class Actions:
    """All action modules sharing one context."""

    def __init__(self, settings, dry_run=None):
        self.ctx = Ctx(settings, dry_run)
        self.mouse = Mouse(self.ctx)
        self.keyboard = Keyboard(self.ctx)
        self.system = System(self.ctx)
        self.browser = Browser(self.ctx, self.keyboard, self.mouse)
        self.facebook = Facebook(self.ctx, self.keyboard, self.mouse, self.browser)
