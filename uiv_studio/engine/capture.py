"""Global mouse/keyboard capture -> high-level user actions.

Runs pynput listeners and turns raw events into:
    ("click", {...}) ("double_click") ("right_click") ("drag") ("scroll")
    ("text", {text, enter_after}) ("key", {combo})
    ("hotkey", {name})
Each mouse action carries the screen frame captured *before* the action.
"""

import logging
import threading
import time
from collections import deque

from pynput import keyboard, mouse

from uiv_studio.core.keys import MODIFIERS, format_combo, parse_combo, pynput_key_name

log = logging.getLogger(__name__)


class FrameBuffer:
    """Continuously grabs the screen so every action has a 'before' frame."""

    def __init__(self, grabber, interval: float = 0.12):
        self.grabber = grabber
        self.interval = interval
        self.frames = deque(maxlen=12)
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="frame-buffer", daemon=True)
        self._lock = threading.Lock()

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)
        self.grabber.close()

    def pause(self, paused: bool):
        (self._paused.set if paused else self._paused.clear)()

    def _loop(self):
        while not self._stop.is_set():
            if not self._paused.is_set():
                try:
                    frame = self.grabber.grab()
                    with self._lock:
                        self.frames.append((time.monotonic(), frame))
                except Exception as exc:
                    log.warning("Screen grab failed: %s", exc)
            time.sleep(self.interval)

    def before(self, t: float):
        """Latest frame captured before time `t` (falls back to the oldest)."""
        with self._lock:
            frames = list(self.frames)
        if not frames:
            return self.grabber.grab()
        for ts, frame in reversed(frames):
            if ts <= t - 0.03:
                return frame
        return frames[0][1]

    def latest(self):
        with self._lock:
            return self.frames[-1][1] if self.frames else self.grabber.grab()


class InputCapture:
    def __init__(self, cfg_recording: dict, hotkeys: dict, frames: FrameBuffer, emit,
                 accept_point=lambda x, y: True):
        """
        cfg_recording: settings["recording"]
        hotkeys: {name: combo string} checked on key press (swallowed, never recorded)
        emit(kind, payload): called from listener/timer threads
        accept_point(x, y): False for points on our own windows / other monitors
        """
        self.cfg = cfg_recording
        self.hotkeys = {name: parse_combo(combo) for name, combo in hotkeys.items() if combo}
        self.frames = frames
        self.emit = emit
        self.accept_point = accept_point

        self.enabled = False
        self.pressed: set[str] = set()
        self.text = ""
        self._lock = threading.RLock()
        self._press = None                 # (x, y, t, frame, mods) of left button down
        self._pending_click = None
        self._click_timer = None
        self._scroll = None
        self._scroll_timer = None
        self._swallow: set[str] = set()     # keys belonging to a hotkey, until released
        self._mouse = mouse.Listener(on_click=self._on_click, on_scroll=self._on_scroll)
        self._keys = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)

    # ------------------------------------------------------------ lifecycle
    def start(self):
        self._mouse.start()
        self._keys.start()

    def stop(self):
        self.flush()
        for t in (self._click_timer, self._scroll_timer):
            if t:
                t.cancel()
        for listener in (self._mouse, self._keys):
            if listener.is_alive():
                listener.stop()

    def set_enabled(self, enabled: bool):
        with self._lock:
            self.enabled = enabled
            if not enabled:
                self._press = None

    def flush(self):
        """Emit pending click/scroll/text now."""
        with self._lock:
            if self._click_timer:
                self._click_timer.cancel()
            self._emit_pending_click()
            if self._scroll_timer:
                self._scroll_timer.cancel()
            self._emit_scroll()
            self.flush_text()

    def flush_text(self, enter_after: bool = False):
        with self._lock:
            if self.text.strip() or (self.text and enter_after):
                self.emit("text", {"text": self.text, "enter_after": enter_after,
                                   "frame": self.frames.latest(), "t": time.monotonic()})
            self.text = ""
            self.emit("buffer", {"text": ""})

    def discard_text(self):
        with self._lock:
            self.text = ""
            self.emit("buffer", {"text": ""})

    def _mods(self) -> list:
        return [m for m in MODIFIERS if m in self.pressed]

    # ------------------------------------------------------------ mouse
    def _on_click(self, x, y, button, pressed, injected=False):
        if injected:
            return
        with self._lock:
            if not self.enabled:
                return
            if not self.accept_point(x, y):
                self._press = None
                return
            now = time.monotonic()
            if button == mouse.Button.left:
                if pressed:
                    self._press = (x, y, now, self.frames.before(now), self._mods())
                    return
                if self._press is None:
                    return
                px, py, pt, frame, mods = self._press
                self._press = None
                if ((x - px) ** 2 + (y - py) ** 2) ** 0.5 >= self.cfg["drag_threshold_px"]:
                    self._before_mouse_action()
                    self.emit("drag", {"x": px, "y": py, "x2": x, "y2": y, "mods": mods, "frame": frame, "t": pt})
                else:
                    self._handle_left_click(px, py, pt, frame, mods)
            elif button == mouse.Button.right and pressed:
                self._before_mouse_action()
                self.emit("right_click", {"x": x, "y": y, "mods": self._mods(),
                                          "frame": self.frames.before(now), "t": now})

    def _before_mouse_action(self):
        """Text typed so far belongs to the previous element: close it first."""
        if self._click_timer:
            self._click_timer.cancel()
        self._emit_pending_click()
        if self._scroll_timer:
            self._scroll_timer.cancel()
        self._emit_scroll()
        self.flush_text()

    def _handle_left_click(self, x, y, t, frame, mods):
        limit = self.cfg["double_click_ms"] / 1000.0
        pc = self._pending_click
        if pc and t - pc["t"] < limit and abs(x - pc["x"]) < 8 and abs(y - pc["y"]) < 8:
            if self._click_timer:
                self._click_timer.cancel()
            self._pending_click = None
            self.emit("double_click", {**pc, "mods": pc["mods"] or mods})
            return
        self._before_mouse_action()
        self._pending_click = {"x": x, "y": y, "t": t, "frame": frame, "mods": mods}
        self._click_timer = threading.Timer(limit, self._timer_click)
        self._click_timer.daemon = True
        self._click_timer.start()

    def _timer_click(self):
        with self._lock:
            self._emit_pending_click()

    def _emit_pending_click(self):
        if self._pending_click:
            pc, self._pending_click = self._pending_click, None
            self.emit("click", pc)

    def _on_scroll(self, x, y, dx, dy, injected=False):
        if injected:
            return
        with self._lock:
            if not self.enabled or not self.accept_point(x, y):
                return
            now = time.monotonic()
            if self._scroll is None:
                if self._click_timer:
                    self._click_timer.cancel()
                self._emit_pending_click()
                self.flush_text()
                self._scroll = {"x": x, "y": y, "dx": 0, "dy": 0, "mods": self._mods(),
                                "frame": self.frames.before(now), "t": now}
            self._scroll["dx"] += dx
            self._scroll["dy"] += dy
            if self._scroll_timer:
                self._scroll_timer.cancel()
            self._scroll_timer = threading.Timer(self.cfg["scroll_debounce_ms"] / 1000.0, self._timer_scroll)
            self._scroll_timer.daemon = True
            self._scroll_timer.start()

    def _timer_scroll(self):
        with self._lock:
            self._emit_scroll()

    def _emit_scroll(self):
        if self._scroll:
            s, self._scroll = self._scroll, None
            if s["dx"] or s["dy"]:
                self.emit("scroll", s)

    # ------------------------------------------------------------ keyboard
    def _on_press(self, key, injected=False):
        if injected:
            return
        name = pynput_key_name(key)
        if name is None:
            return
        with self._lock:
            self.pressed.add(name)
            for hk_name, combo in self.hotkeys.items():
                if combo and self.pressed == set(combo):
                    self._swallow |= set(combo)
                    self.emit("hotkey", {"name": hk_name})
                    return
            if not self.enabled or name in MODIFIERS or name in self._swallow:
                return
            char = getattr(key, "char", None)
            chord = [m for m in self._mods() if m != "shift"]
            altgr = set(chord) == {"ctrl", "alt"}  # AltGr on Windows = ctrl+alt (e.g. '@' on IT layout)
            if char and len(char) == 1 and char.isprintable() and (not chord or altgr):
                self.text += char
                self.emit("buffer", {"text": self.text})
            elif name == "space" and not chord:
                self.text += " "
                self.emit("buffer", {"text": self.text})
            elif name == "backspace" and self.text and not chord:
                self.text = self.text[:-1]
                self.emit("buffer", {"text": self.text})
            elif name == "enter" and self.text and not chord:
                self.flush_text(enter_after=True)
            else:
                if self._click_timer:
                    self._click_timer.cancel()
                self._emit_pending_click()
                self.flush_text()
                combo = format_combo(set(self._mods()) | {name})
                self.emit("key", {"combo": combo, "frame": self.frames.latest(), "t": time.monotonic()})

    def _on_release(self, key, injected=False):
        if injected:
            return
        name = pynput_key_name(key)
        if name is None:
            return
        with self._lock:
            self.pressed.discard(name)
            self._swallow.discard(name)
