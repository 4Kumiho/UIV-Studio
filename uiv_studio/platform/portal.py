# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Any Wayland desktop: screen frames and input injection through xdg-desktop-portal.

The portal (org.freedesktop.portal.Desktop) is the standard D-Bus service every
Wayland desktop provides (GNOME, KDE Plasma, ...). One linked
RemoteDesktop + ScreenCast session is opened for the whole app lifetime:

    CreateSession -> SelectDevices (keyboard+pointer, persist) -> SelectSources (monitors)
    -> Start (the desktop asks the user for consent) -> OpenPipeWireRemote (fd)

The desktop shows its consent dialog the first time only: the restore token it
returns is saved and reused, so later sessions start silently. Pixels come from
the PipeWire file descriptor (pipewiresrc fd=… path=node), input is injected with
the RemoteDesktop Notify* methods.
"""

import json
import logging
import secrets
import threading

from jeepney import DBusAddress, MatchRule, new_method_call
from jeepney.bus_messages import message_bus
from jeepney.io.blocking import open_dbus_connection

from uiv_studio.core.screens import Monitor

log = logging.getLogger(__name__)

BUS = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"
RD = "org.freedesktop.portal.RemoteDesktop"
SC = "org.freedesktop.portal.ScreenCast"
BTN = {"left": 0x110, "right": 0x111, "middle": 0x112}   # evdev BTN_LEFT/RIGHT/MIDDLE
KEYBOARD, POINTER = 1, 2
CONSENT_TIMEOUT = 300    # seconds the user has to answer the desktop's dialog


class PortalError(RuntimeError):
    pass


def available() -> bool:
    """True when the desktop's portal offers RemoteDesktop (and so ScreenCast too)."""
    try:
        conn = open_dbus_connection(bus="SESSION")
    except Exception:
        return False
    try:
        addr = DBusAddress(PATH, BUS, "org.freedesktop.DBus.Properties")
        conn.send_and_get_reply(new_method_call(addr, "Get", "ss", (RD, "AvailableDeviceTypes")), timeout=5)
        return True
    except Exception:
        return False
    finally:
        conn.close()


def _token_file():
    from uiv_studio.core.paths import config_dir
    return config_dir() / "portal.json"


def _load_token() -> str:
    try:
        return json.loads(_token_file().read_text()).get("restore_token", "")
    except Exception:
        return ""


def _save_token(token: str):
    try:
        _token_file().write_text(json.dumps({"restore_token": token}))
    except Exception:
        log.exception("cannot save portal restore token")


# ================================================================== monitors


def list_monitors() -> list[Monitor]:
    """Monitors as Qt sees them (logical position, physical pixel size)."""
    from PySide6.QtGui import QGuiApplication
    out = []
    for i, s in enumerate(QGuiApplication.screens(), start=1):
        g, dpr = s.geometry(), s.devicePixelRatio()
        m = Monitor(i, g.x(), g.y(), round(g.width() * dpr), round(g.height() * dpr), float(dpr))
        m.connector = s.name()
        out.append(m)
    out.sort(key=lambda m: (m.left, m.top))
    for i, m in enumerate(out, start=1):
        m.index = i
    return out


# ================================================================== session


class _Portal:
    """The single portal session shared by every monitor."""

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> "_Portal":
        with cls._lock:
            if cls._instance is None or not cls._instance.alive:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self.alive = False
        self._io = threading.Lock()
        # a private connection: the session lives as long as this connection
        self.conn = open_dbus_connection(bus="SESSION", enable_fds=True)
        self.sender = self.conn.unique_name[1:].replace(".", "_")
        self.rd = DBusAddress(PATH, BUS, RD)
        self.sc = DBusAddress(PATH, BUS, SC)

        res = self._request(self.rd, "CreateSession", "a{sv}",
                            lambda t: ({"handle_token": ("s", t), "session_handle_token": ("s", "uiv" + t)},))
        self.session = res["session_handle"][1]
        opts = {"types": ("u", KEYBOARD | POINTER), "persist_mode": ("u", 2)}
        token = _load_token()
        if token:
            opts["restore_token"] = ("s", token)
        self._request(self.rd, "SelectDevices", "oa{sv}", lambda t: (self.session, {**opts, "handle_token": ("s", t)}))
        self._request(self.sc, "SelectSources", "oa{sv}", lambda t: (self.session, {
            "types": ("u", 1), "multiple": ("b", True), "cursor_mode": ("u", 1), "handle_token": ("s", t)}))
        res = self._request(self.rd, "Start", "osa{sv}", lambda t: (self.session, "", {"handle_token": ("s", t)}),
                            timeout=CONSENT_TIMEOUT)
        if res.get("restore_token"):
            _save_token(res["restore_token"][1])
        self.streams = []    # (node_id, (x, y) logical position or None, (w, h) logical size or None)
        for node, props in res.get("streams", ("", []))[1]:
            pos = props.get("position", (None, None))[1]
            size = props.get("size", (None, None))[1]
            self.streams.append((int(node), tuple(pos) if pos else None, tuple(size) if size else None))
        if not self.streams:
            raise PortalError("the desktop shared no screen")
        self.alive = True
        # GNOME creates its virtual keyboard lazily and drops that first event:
        # prime it with a neutral key so the first real character is not lost.
        for pressed in (1, 0):
            self.notify("NotifyKeyboardKeysym", "iu", (0xFFE1, pressed))  # Shift_L
        log.info("portal session %s: streams %s", self.session, self.streams)

    def _request(self, addr, member, sig, make_args, timeout=60):
        """Call a portal method and wait for its Request::Response signal."""
        token = "uiv" + secrets.token_hex(6)
        path = f"/org/freedesktop/portal/desktop/request/{self.sender}/{token}"
        rule = MatchRule(type="signal", interface="org.freedesktop.portal.Request", member="Response", path=path)
        c = self.conn
        c.send_and_get_reply(message_bus.AddMatch(rule), timeout=5)
        with c.filter(rule) as queue:
            c.send_and_get_reply(new_method_call(addr, member, sig, make_args(token)), timeout=10)
            msg = c.recv_until_filtered(queue, timeout=timeout)
        code, results = msg.body
        if code != 0:
            raise PortalError(f"{member}: " + ("denied by the user" if code == 1 else f"failed ({code})"))
        return results

    def stream_for(self, monitor: Monitor):
        if len(self.streams) == 1:
            return self.streams[0]
        for s in self.streams:
            if s[1] == (monitor.left, monitor.top):
                return s
        return self.streams[min(monitor.index, len(self.streams)) - 1]

    def open_fd(self) -> int:
        """A new PipeWire remote fd (one per consumer process)."""
        with self._io:
            reply = self.conn.send_and_get_reply(
                new_method_call(self.sc, "OpenPipeWireRemote", "oa{sv}", (self.session, {})), timeout=10)
        return reply.body[0].to_raw_fd()

    def notify(self, member, sig, args):
        with self._io:
            self.conn.send_and_get_reply(new_method_call(self.rd, member, "oa{sv}" + sig, (self.session, {}, *args)),
                                         timeout=5)


class PortalSession:
    """One monitor of the portal session, same interface as gnome.MutterSession."""

    _by_monitor: dict = {}
    _lock = threading.Lock()

    @classmethod
    def for_monitor(cls, monitor: Monitor) -> "PortalSession":
        key = getattr(monitor, "connector", None) or f"#{monitor.index}"
        with cls._lock:
            s = cls._by_monitor.get(key)
            if s is None or not s.alive:
                s = cls(monitor)
                cls._by_monitor[key] = s
            return s

    def __init__(self, monitor: Monitor):
        self.portal = _Portal.get()
        self.monitor = monitor
        self.node_id, _, size = self.portal.stream_for(monitor)
        self.width, self.height = monitor.width, monitor.height          # frame pixels
        lw, lh = size or (monitor.width / monitor.scale, monitor.height / monitor.scale)
        self._sx, self._sy = lw / self.width, lh / self.height             # pixels -> stream logical units

    @property
    def alive(self):
        return self.portal.alive

    def pipewire_source(self):
        """(pipewiresrc properties, fds to hand to the gst process)."""
        fd = self.portal.open_fd()
        return [f"fd={fd}", f"path={self.node_id}"], (fd,)

    # ------------------------------------------------------------ input
    def pointer_to(self, x: float, y: float):
        """Absolute position in frame pixels (monitor-local)."""
        x = min(max(float(x), 0.0), self.width - 1.0) * self._sx
        y = min(max(float(y), 0.0), self.height - 1.0) * self._sy
        self.portal.notify("NotifyPointerMotionAbsolute", "udd", (self.node_id, x, y))

    def button(self, name: str, pressed: bool):
        self.button_code(BTN.get(name, BTN["left"]), pressed)

    def button_code(self, code: int, pressed: bool):
        self.portal.notify("NotifyPointerButton", "iu", (int(code), int(pressed)))

    def wheel(self, dx: int, dy: int):
        """dy > 0 = up, like pynput (portal: positive steps scroll down)."""
        if dy:
            self.portal.notify("NotifyPointerAxisDiscrete", "ui", (0, -int(dy)))
        if dx:
            self.portal.notify("NotifyPointerAxisDiscrete", "ui", (1, int(dx)))

    def keysym(self, sym: int, pressed: bool):
        self.portal.notify("NotifyKeyboardKeysym", "iu", (int(sym), int(pressed)))

    def keycode(self, code: int, pressed: bool):
        self.portal.notify("NotifyKeyboardKeycode", "iu", (int(code), int(pressed)))
