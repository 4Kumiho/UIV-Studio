# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Wayland: screen frames and input injection through Mutter's D-Bus APIs.

Mutter (the GNOME Shell compositor) exposes the same services GNOME Remote Desktop
uses: org.gnome.Mutter.ScreenCast (monitor video via PipeWire) and
org.gnome.Mutter.RemoteDesktop (absolute pointer, buttons, wheel, keyboard).
One linked RemoteDesktop+ScreenCast session is kept per monitor for the whole
app lifetime; frames are pulled from PipeWire with a gst-launch subprocess.
"""

import logging
import os
import shutil
import subprocess
import threading

import numpy as np
from jeepney import DBusAddress, MatchRule, new_method_call
from jeepney.bus_messages import message_bus
from jeepney.io.blocking import open_dbus_connection

from uiv_studio.core.screens import Monitor

log = logging.getLogger(__name__)

RD = "org.gnome.Mutter.RemoteDesktop"
SC = "org.gnome.Mutter.ScreenCast"
DC = "org.gnome.Mutter.DisplayConfig"
BTN = {"left": 0x110, "right": 0x111, "middle": 0x112}   # evdev BTN_LEFT/RIGHT/MIDDLE


class GnomeError(RuntimeError):
    pass


def available(wait: float = 5.0) -> bool:
    """True when Mutter's RemoteDesktop service is on the session bus (waits a little
    right after login, when GNOME may still be registering its services)."""
    import time
    deadline = time.monotonic() + wait
    while True:
        try:
            reply = _conn().send_and_get_reply(message_bus.NameHasOwner(RD), timeout=3)
            if reply.body[0]:
                return True
        except Exception:
            return False  # no session bus at all
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.25)


_shared = None
_shared_lock = threading.Lock()


def _conn():
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = open_dbus_connection(bus="SESSION")
        return _shared


def _props(conn, path, bus_name, iface, name):
    addr = DBusAddress(path, bus_name, "org.freedesktop.DBus.Properties")
    return conn.send_and_get_reply(new_method_call(addr, "Get", "ss", (iface, name)), timeout=5).body[0][1]


# ================================================================== monitors


def list_monitors() -> list[Monitor]:
    """Monitors from org.gnome.Mutter.DisplayConfig (physical pixel size, logical position)."""
    conn = _conn()
    addr = DBusAddress("/org/gnome/Mutter/DisplayConfig", DC, DC)
    serial, monitors, logical, props = conn.send_and_get_reply(new_method_call(addr, "GetCurrentState"),
                                                               timeout=5).body
    modes = {}
    for (connector, vendor, product, mserial), mode_list, mprops in monitors:
        for mode in mode_list:
            mode_id, w, h, refresh, pref_scale, scales, mode_props = mode
            if mode_props.get("is-current", ("b", False))[1]:
                modes[connector] = (w, h)
    out = []
    for i, (x, y, scale, transform, primary, mons, lprops) in enumerate(logical, start=1):
        for connector, *_ in mons:
            w, h = modes.get(connector, (0, 0))
            m = Monitor(i, x, y, w, h, float(scale))
            m.connector = connector
            out.append(m)
    out.sort(key=lambda m: (m.left, m.top))
    for i, m in enumerate(out, start=1):
        m.index = i
    return out


# ================================================================== session


class MutterSession:
    """Linked RemoteDesktop + ScreenCast session recording one monitor."""

    _by_connector: dict = {}
    _lock = threading.Lock()

    @classmethod
    def for_monitor(cls, monitor: Monitor) -> "MutterSession":
        key = getattr(monitor, "connector", None) or f"#{monitor.index}"
        with cls._lock:
            s = cls._by_connector.get(key)
            if s is None or not s.alive:
                s = cls(monitor)
                cls._by_connector[key] = s
            return s

    def __init__(self, monitor: Monitor):
        self.monitor = monitor
        self.alive = False
        self._io = threading.Lock()
        # a private connection: signals for this session don't mix with others
        self.conn = open_dbus_connection(bus="SESSION")
        c = self.conn
        rd = DBusAddress("/org/gnome/Mutter/RemoteDesktop", RD, RD)
        self.rd_path = c.send_and_get_reply(new_method_call(rd, "CreateSession"), timeout=5).body[0]
        self.rd = DBusAddress(self.rd_path, RD, RD + ".Session")
        session_id = _props(c, self.rd_path, RD, RD + ".Session", "SessionId")
        sc = DBusAddress("/org/gnome/Mutter/ScreenCast", SC, SC)
        sc_path = c.send_and_get_reply(new_method_call(sc, "CreateSession", "a{sv}",
                                                       ({"remote-desktop-session-id": ("s", session_id)},)),
                                       timeout=5).body[0]
        self.sc = DBusAddress(sc_path, SC, SC + ".Session")
        connector = getattr(monitor, "connector", None)
        if connector is None:
            connector = list_monitors()[max(0, monitor.index - 1)].connector
        self.stream_path = c.send_and_get_reply(
            new_method_call(self.sc, "RecordMonitor", "sa{sv}", (connector, {"cursor-mode": ("u", 0)})),
            timeout=5).body[0]
        rule = MatchRule(type="signal", interface=SC + ".Stream", member="PipeWireStreamAdded",
                         path=self.stream_path)
        c.send_and_get_reply(message_bus.AddMatch(rule), timeout=5)
        with c.filter(rule) as queue:
            c.send_and_get_reply(new_method_call(self.rd, "Start"), timeout=10)
            msg = c.recv_until_filtered(queue, timeout=10)
        self.node_id = int(msg.body[0])
        params = _props(c, self.stream_path, SC, SC + ".Stream", "Parameters")
        size = params.get("size", ("(ii)", (monitor.width, monitor.height)))[1]
        self.width, self.height = int(size[0]), int(size[1])
        self.alive = True
        # Mutter creates its virtual keyboard lazily and drops that first event:
        # prime it with a neutral key so the first real character is not lost.
        for pressed in (True, False):
            self.keysym(0xFFE1, pressed)  # Shift_L
        log.info("Mutter session: monitor %s, PipeWire node %s, %sx%s", connector, self.node_id,
                 self.width, self.height)

    def pipewire_source(self):
        """(pipewiresrc properties, fds to hand to the gst process)."""
        return [f"path={self.node_id}"], ()

    # ------------------------------------------------------------ input
    def _call(self, member, sig, args):
        with self._io:
            self.conn.send_and_get_reply(new_method_call(self.rd, member, sig, args), timeout=5)

    def pointer_to(self, x: float, y: float):
        """Absolute position in stream pixels (monitor-local)."""
        x = min(max(float(x), 0.0), self.width - 1.0)
        y = min(max(float(y), 0.0), self.height - 1.0)
        self._call("NotifyPointerMotionAbsolute", "sdd", (self.stream_path, x, y))

    def button(self, name: str, pressed: bool):
        self._call("NotifyPointerButton", "ib", (BTN.get(name, BTN["left"]), pressed))

    def button_code(self, code: int, pressed: bool):
        self._call("NotifyPointerButton", "ib", (int(code), pressed))

    def wheel(self, dx: int, dy: int):
        """dy > 0 = up, like pynput (Mutter: positive steps scroll down)."""
        if dy:
            self._call("NotifyPointerAxisDiscrete", "ui", (0, -int(dy)))
        if dx:
            self._call("NotifyPointerAxisDiscrete", "ui", (1, int(dx)))

    def keysym(self, sym: int, pressed: bool):
        self._call("NotifyKeyboardKeysym", "ub", (int(sym), pressed))

    def keycode(self, code: int, pressed: bool):
        self._call("NotifyKeyboardKeycode", "ub", (int(code), pressed))

    def close(self):
        try:
            with self._io:
                self.conn.send_and_get_reply(new_method_call(self.rd, "Stop"), timeout=3)
        except Exception:
            pass
        self.alive = False
        self.conn.close()


def session_for(monitor: Monitor):
    """Input/stream session of a monitor: xdg-desktop-portal, or Mutter's own API."""
    from uiv_studio import platform as backend
    if backend.kind() == "wayland":
        from uiv_studio.platform.portal import PortalSession
        return PortalSession.for_monitor(monitor)
    return MutterSession.for_monitor(monitor)


# ================================================================== frames


class PipeWireGrabber:
    """Latest monitor frame (BGR ndarray) from the Mutter ScreenCast stream.

    A Mutter stream accepts a single consumer, so one grabber per monitor is shared by
    the recorder, the player and the video writer (use `PipeWireGrabber.shared`).
    """

    _shared: dict = {}
    _shared_lock = threading.Lock()

    @classmethod
    def shared(cls, monitor: Monitor) -> "PipeWireGrabber":
        key = getattr(monitor, "connector", None) or f"#{monitor.index}"
        with cls._shared_lock:
            g = cls._shared.get(key)
            if g is None or g._proc.poll() is not None:
                g = cls(monitor)
                cls._shared[key] = g
            return g

    def __init__(self, monitor: Monitor):
        if not shutil.which("gst-launch-1.0"):
            raise GnomeError("gst-launch-1.0 not found: install GStreamer (gstreamer1.0-tools, gstreamer1.0-pipewire)")
        self.monitor = monitor
        self.session = session_for(monitor)
        self.w, self.h = self.session.width, self.session.height
        self._frame = None
        self._cond = threading.Condition()
        src, fds = self.session.pipewire_source()
        self._proc = subprocess.Popen(
            ["gst-launch-1.0", "-q", "pipewiresrc", *src, "always-copy=true",
             "!", "videoconvert", "!", "videoscale", "!",
             f"video/x-raw,format=BGR,width={self.w},height={self.h}", "!", "fdsink", "fd=1", "sync=false"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0, pass_fds=fds)
        for fd in fds:
            os.close(fd)  # the gst process owns its copy
        self._thread = threading.Thread(target=self._pump, name="pipewire", daemon=True)
        self._thread.start()

    def _pump(self):
        size = self.w * self.h * 3
        out = self._proc.stdout
        buf = bytearray(size)
        view = memoryview(buf)
        while True:
            got = 0
            while got < size:
                n = out.readinto(view[got:])
                if not n:
                    return
                got += n
            frame = np.frombuffer(bytes(buf), np.uint8).reshape(self.h, self.w, 3)
            with self._cond:
                self._frame = frame
                self._cond.notify_all()

    def grab(self) -> np.ndarray:
        with self._cond:
            if self._frame is None:
                self._cond.wait(timeout=5)
            if self._frame is None:
                raise GnomeError("No frames from PipeWire (is gstreamer1.0-pipewire installed?)")
            return self._frame.copy()

    def close(self):
        pass  # the stream is shared; it is released when the app exits


# ================================================================== actuator


class MutterActuator:
    """Same interface as engine.actions.Actuator, driven through Mutter RemoteDesktop."""

    def __init__(self, cfg_execution: dict, monitor: Monitor):
        from uiv_studio.platform import xkb
        self.xkb = xkb
        self.cfg = cfg_execution
        self.monitor = monitor
        self.s = session_for(monitor)
        self.pos = (self.s.width / 2, self.s.height / 2)

    def _local(self, x, y):
        return x - self.monitor.left, y - self.monitor.top

    def move(self, x, y):
        import math
        import time
        tx, ty = self._local(x, y)
        sx, sy = self.pos
        duration = self.cfg["mouse_move_ms"] / 1000.0
        steps = max(1, int(duration / 0.012))
        for i in range(1, steps + 1):
            e = 0.5 - 0.5 * math.cos(math.pi * i / steps)
            self.s.pointer_to(sx + (tx - sx) * e, sy + (ty - sy) * e)
            time.sleep(duration / steps)
        self.pos = (tx, ty)
        time.sleep(0.05)

    def _mods(self, mods, pressed):
        from uiv_studio.core.keys import MODIFIERS
        for m in (mods if pressed else reversed(list(mods))):
            if m in MODIFIERS:
                self.s.keysym(self.xkb.keysym_for_name(m), pressed)

    def click(self, x, y, mods=(), button="left", count=1):
        import time
        self.move(x, y)
        self._mods(mods, True)
        try:
            for i in range(count):
                self.s.button(button, True)
                time.sleep(0.04)
                self.s.button(button, False)
                if i < count - 1:
                    time.sleep(0.07)
        finally:
            self._mods(mods, False)

    def drag(self, x1, y1, x2, y2, mods=()):
        import time
        self.move(x1, y1)
        self._mods(mods, True)
        try:
            self.s.button("left", True)
            time.sleep(0.12)
            self.move(x2, y2)
            time.sleep(0.12)
            self.s.button("left", False)
        finally:
            self._mods(mods, False)

    def scroll(self, x, y, dx, dy, mods=()):
        import time
        self.move(x, y)
        self._mods(mods, True)
        try:
            for _ in range(max(abs(dx), abs(dy), 1)):
                self.s.wheel((dx > 0) - (dx < 0) if dx else 0, (dy > 0) - (dy < 0) if dy else 0)
                time.sleep(0.03)
        finally:
            self._mods(mods, False)

    def type_text(self, text: str, enter_after: bool = False):
        import time
        interval = self.cfg["typing_interval_ms"] / 1000.0
        for ch in text:
            sym = self.xkb.keysym_for_name("enter") if ch == "\n" else self.xkb.keysym_for_char(ch)
            self.s.keysym(sym, True)
            self.s.keysym(sym, False)
            time.sleep(interval)
        if enter_after:
            sym = self.xkb.keysym_for_name("enter")
            self.s.keysym(sym, True)
            self.s.keysym(sym, False)

    def key_combo(self, combo: str):
        import time
        from uiv_studio.core.keys import MODIFIERS, parse_combo
        keys = parse_combo(combo)
        mods = [m for m in MODIFIERS if m in keys]
        self._mods(mods, True)
        try:
            for k in keys:
                if k not in MODIFIERS:
                    sym = self.xkb.keysym_for_name(k)
                    self.s.keysym(sym, True)
                    time.sleep(0.03)
                    self.s.keysym(sym, False)
        finally:
            self._mods(mods, False)
