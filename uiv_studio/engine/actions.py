"""Perform recorded actions with pynput (global physical coordinates)."""

import math
import time
from contextlib import contextmanager

from pynput import keyboard, mouse

from uiv_studio.core.keys import MODIFIERS, parse_combo, pynput_key


class Actuator:
    def __init__(self, cfg_execution: dict):
        self.cfg = cfg_execution
        self.mouse = mouse.Controller()
        self.kb = keyboard.Controller()

    # ------------------------------------------------------------ helpers
    def move(self, x: int, y: int):
        """Eased movement: looks natural and triggers hover states like a human."""
        duration = self.cfg["mouse_move_ms"] / 1000.0
        sx, sy = self.mouse.position
        steps = max(1, int(duration / 0.012))
        for i in range(1, steps + 1):
            t = i / steps
            e = 0.5 - 0.5 * math.cos(math.pi * t)
            self.mouse.position = (round(sx + (x - sx) * e), round(sy + (y - sy) * e))
            time.sleep(duration / steps)
        self.mouse.position = (x, y)
        time.sleep(0.05)

    @contextmanager
    def held(self, mods: list):
        keys = [pynput_key(m) for m in mods if m in MODIFIERS]
        for k in keys:
            self.kb.press(k)
        if keys:
            time.sleep(0.08)  # let the target app register modifiers (important on X11)
        try:
            yield
        finally:
            for k in reversed(keys):
                self.kb.release(k)

    def _press_release(self, button, count=1):
        for i in range(count):
            self.mouse.press(button)
            time.sleep(0.04)
            self.mouse.release(button)
            if i < count - 1:
                time.sleep(0.07)

    # ------------------------------------------------------------ actions
    def click(self, x, y, mods=(), button="left", count=1):
        self.move(x, y)
        with self.held(list(mods)):
            self._press_release(mouse.Button.right if button == "right" else mouse.Button.left, count)

    def drag(self, x1, y1, x2, y2, mods=()):
        self.move(x1, y1)
        with self.held(list(mods)):
            self.mouse.press(mouse.Button.left)
            time.sleep(0.12)
            steps = 40
            for i in range(1, steps + 1):
                t = i / steps
                e = 0.5 - 0.5 * math.cos(math.pi * t)
                self.mouse.position = (round(x1 + (x2 - x1) * e), round(y1 + (y2 - y1) * e))
                time.sleep(0.015)
            time.sleep(0.12)
            self.mouse.release(mouse.Button.left)

    def scroll(self, x, y, dx, dy, mods=()):
        self.move(x, y)
        with self.held(list(mods)):
            # Emit notch by notch: many apps ignore large single deltas
            n = max(abs(dx), abs(dy), 1)
            sx = (dx > 0) - (dx < 0)
            sy = (dy > 0) - (dy < 0)
            for i in range(n):
                self.mouse.scroll(sx if i < abs(dx) else 0, sy if i < abs(dy) else 0)
                time.sleep(0.03)

    def type_text(self, text: str, enter_after: bool = False):
        interval = self.cfg["typing_interval_ms"] / 1000.0
        for ch in text:
            if ch == "\n":
                self.kb.press(keyboard.Key.enter)
                self.kb.release(keyboard.Key.enter)
            else:
                self.kb.type(ch)
            time.sleep(interval)
        if enter_after:
            time.sleep(0.05)
            self.kb.press(keyboard.Key.enter)
            self.kb.release(keyboard.Key.enter)

    def key_combo(self, combo: str):
        keys = parse_combo(combo)
        mods = [m for m in MODIFIERS if m in keys]
        rest = [k for k in keys if k not in MODIFIERS]
        with self.held(mods):
            for k in rest:
                pk = pynput_key(k)
                self.kb.press(pk)
                time.sleep(0.03)
                self.kb.release(pk)
