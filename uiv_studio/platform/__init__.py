# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Platform backends: the single place that knows how to see the screen, move the
mouse and listen to the user on each system.

    windows        mss + pynput
    x11            mss + pynput (Xlib)                    no WAYLAND_DISPLAY
    wayland        xdg-desktop-portal ScreenCast (PipeWire fd) + RemoteDesktop + /dev/input
    gnome-wayland  fallback without a portal: Mutter's own ScreenCast/RemoteDesktop + /dev/input
    wayland-unsupported  neither available (clear message in the UI)
"""

import os
import sys
from functools import lru_cache


@lru_cache(maxsize=1)
def kind() -> str:
    forced = os.environ.get("UIV_BACKEND")
    if forced:
        return forced
    if sys.platform == "win32":
        return "windows"
    if os.environ.get("WAYLAND_DISPLAY"):
        from uiv_studio.platform import gnome, portal
        if portal.available():
            return "wayland"
        return "gnome-wayland" if gnome.available() else "wayland-unsupported"
    return "x11"


def is_wayland() -> bool:
    return kind() in ("wayland", "gnome-wayland", "wayland-unsupported")


def supported() -> bool:
    return kind() != "wayland-unsupported"


def needs_input_group() -> bool:
    """Recording reads /dev/input (Wayland never reveals global input to apps)."""
    return kind() in ("wayland", "gnome-wayland")


def list_monitors():
    if kind() == "wayland":
        from uiv_studio.platform import portal
        return portal.list_monitors()
    if kind() == "gnome-wayland":
        from uiv_studio.platform import gnome
        return gnome.list_monitors()
    from uiv_studio.core.screens import list_monitors as mss_monitors
    return mss_monitors()


def make_grabber(monitor):
    """Object with grab() -> BGR ndarray of the monitor, and close()."""
    if needs_input_group():
        from uiv_studio.platform.gnome import PipeWireGrabber
        return PipeWireGrabber.shared(monitor)
    from uiv_studio.core.screens import ScreenGrabber
    return ScreenGrabber(monitor)


def make_actuator(cfg_execution: dict, monitor):
    if needs_input_group():
        from uiv_studio.platform.gnome import MutterActuator
        return MutterActuator(cfg_execution, monitor)
    from uiv_studio.engine.actions import Actuator
    return Actuator(cfg_execution)


def make_input_source(capture, monitor):
    """Raw input feeding engine.capture.InputCapture while recording (None = default pynput)."""
    if needs_input_group():
        from uiv_studio.platform.evdev import EvdevSource
        from uiv_studio.platform.gnome import session_for
        return EvdevSource(capture, monitor, session_for(monitor, input_only=True))
    return None


def make_hotkey_listener(combo: frozenset, callback):
    """Global hotkey watcher used during runs: object with start()/stop()."""
    if needs_input_group():
        from uiv_studio.platform.evdev import EvdevHotkeys
        return EvdevHotkeys(combo, callback)
    return _PynputHotkeys(combo, callback)


class _PynputHotkeys:
    def __init__(self, combo, callback):
        from pynput import keyboard
        from uiv_studio.core.keys import pynput_key_name
        self.combo, self.callback, self.name = set(combo), callback, pynput_key_name
        self.pressed: set[str] = set()
        self.listener = keyboard.Listener(on_press=self._press, on_release=self._release)

    def start(self):
        self.listener.start()

    def stop(self):
        self.listener.stop()

    def _press(self, key, injected=False):
        if injected:  # our own simulated key presses must never open the menu
            return
        n = self.name(key)
        if n:
            self.pressed.add(n)
            if self.combo and self.pressed == self.combo:
                self.callback()

    def _release(self, key, injected=False):
        if not injected:
            self.pressed.discard(self.name(key))
