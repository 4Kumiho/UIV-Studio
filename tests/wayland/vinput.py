# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Virtual mouse + keyboard through /dev/uinput (pure Python), for tests only."""

import fcntl
import os
import struct
import time

EV_SYN, EV_KEY, EV_REL = 0, 1, 2
REL_X, REL_Y, REL_WHEEL = 0, 1, 8
BTN_LEFT, BTN_RIGHT = 0x110, 0x111
UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_RELBIT = 0x40045564, 0x40045565, 0x40045566
UI_DEV_CREATE, UI_DEV_DESTROY = 0x5501, 0x5502
KEY_LEFTSHIFT, KEY_SPACE, KEY_ENTER = 42, 57, 28

_ROWS = {"qwertyuiop": 16, "asdfghjkl": 30, "zxcvbnm": 44, "1234567890": 2}
KEYCODES = {ch: base + i for row, base in _ROWS.items() for i, ch in enumerate(row)}


class _Dev:
    def __init__(self, name: str, evbits, keybits=(), relbits=()):
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        for b in evbits:
            fcntl.ioctl(self.fd, UI_SET_EVBIT, b)
        for b in keybits:
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, b)
        for b in relbits:
            fcntl.ioctl(self.fd, UI_SET_RELBIT, b)
        user_dev = name.encode()[:79].ljust(80, b"\0") + struct.pack("HHHHi", 3, 0x1234, 0x5678, 1, 0) + b"\0" * (64 * 4 * 4)
        os.write(self.fd, user_dev)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)

    def emit(self, etype, code, value):
        now = time.time()
        os.write(self.fd, struct.pack("llHHi", int(now), int((now % 1) * 1e6), etype, code, value))

    def syn(self):
        self.emit(EV_SYN, 0, 0)

    def close(self):
        fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        os.close(self.fd)


def _make_device_nodes():
    import stat
    os.makedirs("/dev/input", exist_ok=True)
    for name in os.listdir("/sys/class/input"):
        if not name.startswith("event"):
            continue
        node = f"/dev/input/{name}"
        if os.path.exists(node):
            continue
        major, minor = open(f"/sys/class/input/{name}/dev").read().strip().split(":")
        os.mknod(node, 0o660 | stat.S_IFCHR, os.makedev(int(major), int(minor)))


class VirtualInput:
    def __enter__(self):
        self.mouse = _Dev("UIV test mouse", (EV_SYN, EV_KEY, EV_REL), (BTN_LEFT, BTN_RIGHT), (REL_X, REL_Y, REL_WHEEL))
        keys = list(KEYCODES.values()) + [KEY_LEFTSHIFT, KEY_SPACE, KEY_ENTER] + list(range(1, 120))
        self.kbd = _Dev("UIV test keyboard", (EV_SYN, EV_KEY), sorted(set(keys)))
        time.sleep(0.5)
        _make_device_nodes()  # containers have no udev
        return self

    def __exit__(self, *exc):
        self.mouse.close()
        self.kbd.close()

    def move_to(self, source, x: int, y: int, tol: float = 0.9):
        """Drive the recorder's pointer model to (x, y) with relative motion, like a real mouse."""
        for _ in range(400):
            dx, dy = x - source.ptr.x, y - source.ptr.y
            if abs(dx) <= tol and abs(dy) <= tol:
                return
            sx = int(max(-40, min(40, dx / 2))) or (1 if dx > 0 else -1 if dx < 0 else 0)
            sy = int(max(-40, min(40, dy / 2))) or (1 if dy > 0 else -1 if dy < 0 else 0)
            if sx:
                self.mouse.emit(EV_REL, REL_X, sx)
            if sy:
                self.mouse.emit(EV_REL, REL_Y, sy)
            self.mouse.syn()
            time.sleep(0.012)
        raise RuntimeError(f"pointer did not reach {(x, y)}: {(source.ptr.x, source.ptr.y)}")

    def click(self, button=BTN_LEFT):
        for v in (1, 0):
            self.mouse.emit(EV_KEY, button, v)
            self.mouse.syn()
            time.sleep(0.05)

    def _tap(self, code, shift=False):
        if shift:
            self.kbd.emit(EV_KEY, KEY_LEFTSHIFT, 1); self.kbd.syn()
        self.kbd.emit(EV_KEY, code, 1); self.kbd.syn()
        self.kbd.emit(EV_KEY, code, 0); self.kbd.syn()
        if shift:
            self.kbd.emit(EV_KEY, KEY_LEFTSHIFT, 0); self.kbd.syn()
        time.sleep(0.03)

    def type(self, text: str):
        for ch in text:
            if ch == " ":
                self._tap(KEY_SPACE)
            elif ch == "\n":
                self._tap(KEY_ENTER)
            else:
                self._tap(KEYCODES[ch.lower()], shift=ch.isupper())
