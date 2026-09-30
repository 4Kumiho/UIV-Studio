# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Canonical key names shared by recorder, player, hotkeys and the Settings UI.

A hotkey is stored as a '+'-joined, order-independent set of canonical names,
e.g. "ctrl+shift" or "ctrl+alt+f9".
"""

MODIFIERS = ("ctrl", "shift", "alt", "cmd")

SPECIAL_KEYS = (
    "enter", "tab", "esc", "space", "backspace", "delete", "insert",
    "home", "end", "page_up", "page_down", "up", "down", "left", "right",
    *[f"f{i}" for i in range(1, 13)],
)

_ALIASES = {
    "control": "ctrl", "ctl": "ctrl", "ctrl_l": "ctrl", "ctrl_r": "ctrl",
    "shift_l": "shift", "shift_r": "shift",
    "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt", "option": "alt",
    "win": "cmd", "super": "cmd", "meta": "cmd", "cmd_l": "cmd", "cmd_r": "cmd",
    "escape": "esc", "return": "enter", "del": "delete", "ins": "insert",
    "pgup": "page_up", "pageup": "page_up", "pgdown": "page_down", "pagedown": "page_down",
}


def canonical(name: str) -> str:
    n = name.strip().lower()
    return _ALIASES.get(n, n)


def parse_combo(text: str) -> frozenset:
    if not text:
        return frozenset()
    return frozenset(canonical(p) for p in text.split("+") if p.strip())


def format_combo(keys) -> str:
    keys = set(keys)
    mods = [m for m in MODIFIERS if m in keys]
    rest = sorted(k for k in keys if k not in MODIFIERS)
    return "+".join(mods + rest)


def display_combo(text: str) -> str:
    """Human readable, e.g. 'Ctrl + Shift + F9'."""
    parts = format_combo(parse_combo(text)).split("+")
    return " + ".join(p.replace("_", " ").title() if len(p) > 1 else p.upper() for p in parts if p)


# ---------------------------------------------------------------- pynput glue

def pynput_key_name(key) -> str | None:
    """Map a pynput key event to a canonical name (None for unknown keys)."""
    from pynput import keyboard

    if isinstance(key, keyboard.Key):
        return canonical(key.name)
    if isinstance(key, keyboard.KeyCode):
        if key.char is not None:
            ch = key.char
            # With ctrl held, Windows reports control characters (\x01 == ctrl+a)
            if len(ch) == 1 and 1 <= ord(ch) <= 26:
                return chr(ord("a") + ord(ch) - 1)
            return ch.lower()
        if key.vk is not None:
            vk = key.vk
            if 0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39:  # A-Z / 0-9 virtual keys
                return chr(vk).lower()
    return None


def pynput_key(name: str):
    """Map a canonical name back to something pynput's Controller can press."""
    from pynput import keyboard

    name = canonical(name)
    table = {
        "ctrl": keyboard.Key.ctrl, "shift": keyboard.Key.shift, "alt": keyboard.Key.alt,
        "cmd": keyboard.Key.cmd,
    }
    if name in table:
        return table[name]
    if hasattr(keyboard.Key, name):
        return getattr(keyboard.Key, name)
    if len(name) == 1:
        return keyboard.KeyCode.from_char(name)
    raise ValueError(f"Unknown key: {name}")


# ---------------------------------------------------------------- Qt glue

def qt_key_name(qt_key: int, text: str = "") -> str | None:
    from PySide6.QtCore import Qt

    table = {
        Qt.Key_Control: "ctrl", Qt.Key_Shift: "shift", Qt.Key_Alt: "alt", Qt.Key_AltGr: "alt",
        Qt.Key_Meta: "cmd", Qt.Key_Super_L: "cmd", Qt.Key_Super_R: "cmd",
        Qt.Key_Return: "enter", Qt.Key_Enter: "enter", Qt.Key_Tab: "tab", Qt.Key_Backtab: "tab",
        Qt.Key_Escape: "esc", Qt.Key_Space: "space", Qt.Key_Backspace: "backspace",
        Qt.Key_Delete: "delete", Qt.Key_Insert: "insert", Qt.Key_Home: "home", Qt.Key_End: "end",
        Qt.Key_PageUp: "page_up", Qt.Key_PageDown: "page_down",
        Qt.Key_Up: "up", Qt.Key_Down: "down", Qt.Key_Left: "left", Qt.Key_Right: "right",
    }
    if qt_key in table:
        return table[qt_key]
    if Qt.Key_F1 <= qt_key <= Qt.Key_F12:
        return f"f{qt_key - Qt.Key_F1 + 1}"
    if Qt.Key_A <= qt_key <= Qt.Key_Z:
        return chr(ord("a") + qt_key - Qt.Key_A)
    if Qt.Key_0 <= qt_key <= Qt.Key_9:
        return chr(ord("0") + qt_key - Qt.Key_0)
    return None
