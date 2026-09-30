# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Raw input devices (/dev/input/event*) for recording on Wayland.

Wayland never tells an application where the pointer is. While recording we
therefore *own* the pointer: mice and touchpads are grabbed (EVIOCGRAB), their
motion is integrated here and re-applied as absolute motion through Mutter
RemoteDesktop, so every click has exact coordinates. Keyboards are only read
(never grabbed) and translated with the user's XKB layout.

Requires read access to /dev/input/event* (user in the `input` group). Grabs are
released automatically by the kernel when the file descriptors close, even if
the process dies.
"""

import errno
import fcntl
import logging
import os
import select
import struct
import threading
import time

log = logging.getLogger(__name__)

EV_SYN, EV_KEY, EV_REL, EV_ABS = 0, 1, 2, 3
REL_X, REL_Y, REL_HWHEEL, REL_WHEEL = 0, 1, 6, 8
ABS_X, ABS_Y = 0, 1
BTN_LEFT, BTN_RIGHT, BTN_MIDDLE = 0x110, 0x111, 0x112
BTN_TOOL_FINGER, BTN_TOUCH, BTN_TOOL_DOUBLETAP, BTN_TOOL_TRIPLETAP = 0x145, 0x14A, 0x14D, 0x14E
KEY_A, KEY_Z, KEY_ENTER = 30, 44, 28
INPUT_PROP_DIRECT = 1

EVENT = struct.Struct("llHHi")
EVIOCGRAB = 0x40044590


def _eviocgabs(axis: int) -> int:
    return 0x80184540 + axis  # _IOR('E', 0x40 + axis, struct input_absinfo)


class NoInputAccess(PermissionError):
    pass


# ================================================================== discovery


def _bits(words: str) -> set[int]:
    out = set()
    parts = words.split()
    for i, word in enumerate(reversed(parts)):
        v = int(word, 16)
        b = 0
        while v:
            if v & 1:
                out.add(i * 64 + b)
            v >>= 1
            b += 1
    return out


def devices() -> list[dict]:
    """[{path, name, kind: mouse|touchpad|keyboard}] from /proc/bus/input/devices."""
    try:
        text = open("/proc/bus/input/devices", encoding="utf-8", errors="ignore").read()
    except OSError:
        return []
    out = []
    for block in text.strip().split("\n\n"):
        name, handler, caps = "", None, {}
        for line in block.splitlines():
            if line.startswith("N: Name="):
                name = line.split("=", 1)[1].strip('"')
            elif line.startswith("H: Handlers="):
                handler = next((h for h in line.split("=", 1)[1].split() if h.startswith("event")), None)
            elif line.startswith("B: "):
                k, _, v = line[3:].partition("=")
                caps[k] = _bits(v)
        if not handler:
            continue
        key, rel, abs_, prop = caps.get("KEY", set()), caps.get("REL", set()), caps.get("ABS", set()), caps.get("PROP", set())
        kind = None
        if {REL_X, REL_Y} <= rel and BTN_LEFT in key:
            kind = "mouse"
        elif {ABS_X, ABS_Y} <= abs_ and BTN_TOOL_FINGER in key and BTN_TOUCH in key and INPUT_PROP_DIRECT not in prop:
            kind = "touchpad"
        elif {KEY_A, KEY_Z, KEY_ENTER} <= key:
            kind = "keyboard"
        if kind:
            out.append({"path": f"/dev/input/{handler}", "name": name, "kind": kind})
    return out


def check_access(kinds=("mouse", "touchpad", "keyboard")) -> list[dict]:
    devs = [d for d in devices() if d["kind"] in kinds]
    readable = [d for d in devs if os.access(d["path"], os.R_OK)]
    if devs and not readable:
        raise NoInputAccess("no access to /dev/input")
    return readable


# ================================================================== pointer model


class PointerModel:
    """Integrates relative motion into an absolute position with a gentle acceleration curve."""

    def __init__(self, width: int, height: int):
        self.w, self.h = width, height
        self.x, self.y = width / 2.0, height / 2.0
        self._last = time.monotonic()

    def move(self, dx: float, dy: float):
        now = time.monotonic()
        dt = max(now - self._last, 0.001)
        self._last = now
        speed = (dx * dx + dy * dy) ** 0.5 / (dt * 1000.0)       # device units per ms
        gain = min(3.0, 0.9 + 0.35 * speed)
        self.x = min(max(self.x + dx * gain, 0.0), self.w - 1.0)
        self.y = min(max(self.y + dy * gain, 0.0), self.h - 1.0)


class _Touchpad:
    """Single-finger motion, two-finger scroll, tap to click (two-finger tap = right)."""

    def __init__(self, fd: int, width: int):
        self.scale = 1.0
        try:
            buf = fcntl.ioctl(fd, _eviocgabs(ABS_X), b"\0" * 24)
            _, lo, hi, _, _, res = struct.unpack("6i", buf)
            if hi > lo:
                self.scale = (width * 0.55) / (hi - lo)
        except OSError:
            pass
        self.touch = False
        self.fingers = 1
        self.last = None
        self.t0 = 0.0
        self.travel = 0.0
        self.max_fingers = 1
        self.scroll_acc = [0.0, 0.0]
        self.pending = {}

    def event(self, etype, code, value):
        if etype == EV_ABS and code in (ABS_X, ABS_Y):
            self.pending[code] = value
        elif etype == EV_KEY and code == BTN_TOUCH:
            self.touch = bool(value)
        elif etype == EV_KEY and code in (BTN_TOOL_FINGER, BTN_TOOL_DOUBLETAP, BTN_TOOL_TRIPLETAP) and value:
            self.fingers = {BTN_TOOL_FINGER: 1, BTN_TOOL_DOUBLETAP: 2, BTN_TOOL_TRIPLETAP: 3}[code]
            self.max_fingers = max(self.max_fingers, self.fingers)

    def frame(self):
        """Called on SYN_REPORT. Returns (dx, dy, scroll_dx, scroll_dy, tap_button|None)."""
        now = time.monotonic()
        dx = dy = sdx = sdy = 0
        tap = None
        if self.touch:
            x = self.pending.get(ABS_X, self.last[0] if self.last else None)
            y = self.pending.get(ABS_Y, self.last[1] if self.last else None)
            if x is not None and y is not None:
                if self.last is None:
                    self.t0, self.travel, self.max_fingers = now, 0.0, self.fingers
                else:
                    ddx, ddy = (x - self.last[0]) * self.scale, (y - self.last[1]) * self.scale
                    self.travel += abs(ddx) + abs(ddy)
                    if self.fingers >= 2:
                        self.scroll_acc[0] += ddx
                        self.scroll_acc[1] += ddy
                        step = 28.0
                        while abs(self.scroll_acc[1]) >= step:
                            s = 1 if self.scroll_acc[1] > 0 else -1
                            sdy += s          # natural scrolling: fingers up -> content up
                            self.scroll_acc[1] -= s * step
                        while abs(self.scroll_acc[0]) >= step:
                            s = 1 if self.scroll_acc[0] > 0 else -1
                            sdx -= s
                            self.scroll_acc[0] -= s * step
                    else:
                        dx, dy = ddx, ddy
                self.last = (x, y)
        elif self.last is not None:
            if now - self.t0 < 0.20 and self.travel < 12:
                tap = "right" if self.max_fingers >= 2 else "left"
            self.last = None
            self.fingers = 1
            self.scroll_acc = [0.0, 0.0]
        self.pending.clear()
        return dx, dy, sdx, sdy, tap


# ================================================================== reader


class _Reader:
    """select() loop over several evdev file descriptors."""

    def __init__(self, devs: list[dict], grab_kinds=(), on_event=None):
        self.fds = {}
        self.on_event = on_event
        for d in devs:
            try:
                fd = os.open(d["path"], os.O_RDONLY | os.O_NONBLOCK)
            except OSError as exc:
                log.warning("cannot open %s: %s", d["path"], exc)
                continue
            if d["kind"] in grab_kinds:
                try:
                    fcntl.ioctl(fd, EVIOCGRAB, 1)
                except OSError as exc:
                    log.warning("cannot grab %s: %s", d["name"], exc)
            self.fds[fd] = d
        self._stop = os.pipe()
        self._thread = threading.Thread(target=self._loop, name="evdev", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        try:
            os.write(self._stop[1], b"x")
        except OSError:
            pass
        self._thread.join(timeout=2)
        for fd in list(self.fds):
            try:
                fcntl.ioctl(fd, EVIOCGRAB, 0)
            except OSError:
                pass
            os.close(fd)
        self.fds.clear()
        for fd in self._stop:
            os.close(fd)

    def _loop(self):
        while True:
            try:
                ready, _, _ = select.select(list(self.fds) + [self._stop[0]], [], [])
            except OSError:
                return
            if self._stop[0] in ready:
                return
            for fd in ready:
                try:
                    data = os.read(fd, EVENT.size * 64)
                except OSError as exc:
                    if exc.errno == errno.ENODEV:  # device unplugged
                        self.fds.pop(fd, None)
                    continue
                for off in range(0, len(data) - EVENT.size + 1, EVENT.size):
                    _, _, etype, code, value = EVENT.unpack_from(data, off)
                    try:
                        self.on_event(self.fds[fd], fd, etype, code, value)
                    except Exception:
                        log.exception("evdev handler failed")


# ================================================================== recording source


class EvdevSource:
    """Feeds engine.capture.InputCapture on GNOME Wayland (see module docstring)."""

    def __init__(self, capture, monitor, session):
        from uiv_studio.platform.xkb import Keymap
        self.cap = capture
        self.monitor = monitor
        self.session = session
        self.keymap = Keymap()
        self.names: dict[int, str] = {}
        self.ptr = PointerModel(session.width, session.height)
        self.rel = [0, 0]
        self.touchpads: dict[int, _Touchpad] = {}
        devs = check_access()
        self.reader = _Reader(devs, grab_kinds=("mouse", "touchpad"), on_event=self._event)
        for fd, d in self.reader.fds.items():
            if d["kind"] == "touchpad":
                self.touchpads[fd] = _Touchpad(fd, session.width)

    def start(self):
        self.session.pointer_to(self.ptr.x, self.ptr.y)
        self.reader.start()

    def stop(self):
        self.reader.stop()

    def _global(self):
        return int(self.monitor.left + self.ptr.x), int(self.monitor.top + self.ptr.y)

    def _button(self, code, pressed):
        self.session.button_code(code, pressed)
        name = {BTN_LEFT: "left", BTN_RIGHT: "right"}.get(code)
        if name:
            self.cap.button(*self._global(), name, pressed)

    def _event(self, dev, fd, etype, code, value):
        kind = dev["kind"]
        if kind == "keyboard":
            if etype == EV_KEY and value in (0, 1):
                name, char = self.keymap.feed(code, bool(value))
                if value:
                    self.names[code] = name
                    if name and name != "altgr":
                        self.cap.key_press(name, char)
                else:
                    n = self.names.pop(code, None)
                    if n and n != "altgr":
                        self.cap.key_release(n)
            return
        if kind == "touchpad":
            tp = self.touchpads[fd]
            if etype == EV_KEY and code in (BTN_LEFT, BTN_RIGHT, BTN_MIDDLE):
                if code == BTN_LEFT and tp.fingers >= 2:
                    code = BTN_RIGHT  # clickpad: two-finger click = right click
                self._button(code, bool(value))
                return
            tp.event(etype, code, value)
            if etype == EV_SYN and code == 0:
                dx, dy, sdx, sdy, tap = tp.frame()
                if dx or dy:
                    self.ptr.move(dx, dy)
                    self.session.pointer_to(self.ptr.x, self.ptr.y)
                if sdx or sdy:
                    self.session.wheel(sdx, sdy)
                    self.cap.scroll(*self._global(), sdx, sdy)
                if tap:
                    btn = BTN_RIGHT if tap == "right" else BTN_LEFT
                    self._button(btn, True)
                    self._button(btn, False)
            return
        # mouse
        if etype == EV_REL:
            if code == REL_X:
                self.rel[0] += value
            elif code == REL_Y:
                self.rel[1] += value
            elif code == REL_WHEEL:
                self.session.wheel(0, value)
                self.cap.scroll(*self._global(), 0, value)
            elif code == REL_HWHEEL:
                self.session.wheel(value, 0)
                self.cap.scroll(*self._global(), value, 0)
        elif etype == EV_KEY and code in (BTN_LEFT, BTN_RIGHT, BTN_MIDDLE, 0x113, 0x114):
            self._button(code, bool(value))
        elif etype == EV_SYN and code == 0 and (self.rel[0] or self.rel[1]):
            self.ptr.move(*self.rel)
            self.rel = [0, 0]
            self.session.pointer_to(self.ptr.x, self.ptr.y)


# ================================================================== hotkeys during playback


class EvdevHotkeys:
    """Watch physical keyboards (not grabbed) for one combination while a run plays.

    Keys injected through RemoteDesktop never reach /dev/input, so the player's own
    typing cannot trigger the menu.
    """

    def __init__(self, combo: frozenset, callback):
        from uiv_studio.platform.xkb import Keymap
        self.combo = set(combo)
        self.callback = callback
        self.keymap = Keymap()
        self.pressed: set[str] = set()
        self.names: dict[int, str] = {}
        try:
            devs = [d for d in check_access(("keyboard",))]
        except NoInputAccess:
            log.warning("No /dev/input access: the run menu hotkey is disabled on Wayland")
            devs = []
        self.reader = _Reader(devs, on_event=self._event)

    def start(self):
        self.reader.start()

    def stop(self):
        self.reader.stop()

    def _event(self, dev, fd, etype, code, value):
        if etype != EV_KEY or value not in (0, 1):
            return
        name, _ = self.keymap.feed(code, bool(value))
        if value:
            self.names[code] = name
            if name:
                self.pressed.add(name)
                if self.combo and self.pressed == self.combo:
                    self.callback()
        else:
            self.pressed.discard(self.names.pop(code, None))
