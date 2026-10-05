# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""libxkbcommon via ctypes: evdev keycode -> (canonical name, typed char), char -> keysym.

The keymap follows the user's GNOME input source (gsettings), so an Italian
keyboard records "@" (AltGr+ò) correctly.
"""

import ast
import ctypes
import ctypes.util
import os
import subprocess

_lib = None


def lib():
    global _lib
    if _lib is None:
        name = ctypes.util.find_library("xkbcommon") or "libxkbcommon.so.0"
        _lib = ctypes.CDLL(name)
        _lib.xkb_context_new.restype = ctypes.c_void_p
        _lib.xkb_context_new.argtypes = [ctypes.c_int]
        _lib.xkb_keymap_new_from_names.restype = ctypes.c_void_p
        _lib.xkb_keymap_new_from_names.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        _lib.xkb_state_new.restype = ctypes.c_void_p
        _lib.xkb_state_new.argtypes = [ctypes.c_void_p]
        _lib.xkb_state_update_key.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int]
        _lib.xkb_state_key_get_one_sym.restype = ctypes.c_uint32
        _lib.xkb_state_key_get_one_sym.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        _lib.xkb_state_key_get_utf8.restype = ctypes.c_int
        _lib.xkb_state_key_get_utf8.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_size_t]
        _lib.xkb_keysym_get_name.restype = ctypes.c_int
        _lib.xkb_keysym_get_name.argtypes = [ctypes.c_uint32, ctypes.c_char_p, ctypes.c_size_t]
        _lib.xkb_keysym_from_name.restype = ctypes.c_uint32
        _lib.xkb_keysym_from_name.argtypes = [ctypes.c_char_p, ctypes.c_int]
        _lib.xkb_utf32_to_keysym.restype = ctypes.c_uint32
        _lib.xkb_utf32_to_keysym.argtypes = [ctypes.c_uint32]
    return _lib


class _RuleNames(ctypes.Structure):
    _fields_ = [(n, ctypes.c_char_p) for n in ("rules", "model", "layout", "variant", "options")]


def gnome_layout() -> tuple[str, str]:
    """(layout, variant) of the first GNOME input source, e.g. ('it', '')."""
    env = os.environ.get("XKB_DEFAULT_LAYOUT")
    if env:
        return env, os.environ.get("XKB_DEFAULT_VARIANT", "")
    try:
        from uiv_studio.core.paths import system_env
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.input-sources", "sources"],
                             capture_output=True, text=True, timeout=3, env=system_env()).stdout.strip()
        out = out.replace("@a(ss)", "").strip()
        for kind, value in ast.literal_eval(out or "[]"):
            if kind == "xkb":
                layout, _, variant = value.partition("+")
                return layout, variant
    except Exception:
        pass
    return "us", ""


# keysym name -> canonical name used across UIV Studio (see core/keys.py)
_SYM_TO_NAME = {
    "Control_L": "ctrl", "Control_R": "ctrl", "Shift_L": "shift", "Shift_R": "shift",
    "Alt_L": "alt", "Alt_R": "alt", "Meta_L": "alt", "Super_L": "cmd", "Super_R": "cmd",
    "Return": "enter", "KP_Enter": "enter", "Tab": "tab", "ISO_Left_Tab": "tab", "Escape": "esc",
    "space": "space", "BackSpace": "backspace", "Delete": "delete", "Insert": "insert",
    "Home": "home", "End": "end", "Prior": "page_up", "Next": "page_down",
    "Up": "up", "Down": "down", "Left": "left", "Right": "right",
    **{f"F{i}": f"f{i}" for i in range(1, 13)},
}
_NAME_TO_SYM = {v: k for k, v in reversed(list(_SYM_TO_NAME.items()))}
_NAME_TO_SYM.update({"ctrl": "Control_L", "shift": "Shift_L", "alt": "Alt_L", "cmd": "Super_L"})


class Keymap:
    def __init__(self, layout: str | None = None, variant: str | None = None):
        L = lib()
        if layout is None:
            layout, variant = gnome_layout()
        self.ctx = L.xkb_context_new(0)
        names = _RuleNames(b"evdev", b"pc105", layout.encode(), (variant or "").encode(), None)
        self.keymap = L.xkb_keymap_new_from_names(self.ctx, ctypes.byref(names), 0)
        if not self.keymap:  # unknown layout -> US
            names = _RuleNames(b"evdev", b"pc105", b"us", b"", None)
            self.keymap = L.xkb_keymap_new_from_names(self.ctx, ctypes.byref(names), 0)
        self.state = L.xkb_state_new(self.keymap)

    def feed(self, evdev_code: int, pressed: bool) -> tuple[str | None, str | None]:
        """Update the state with a key event; return (canonical name, typed char) for presses."""
        L = lib()
        kc = evdev_code + 8
        name = char = None
        if pressed:
            sym = L.xkb_state_key_get_one_sym(self.state, kc)
            buf = ctypes.create_string_buffer(64)
            L.xkb_keysym_get_name(sym, buf, 64)
            symname = buf.value.decode(errors="ignore")
            L.xkb_state_key_get_utf8(self.state, kc, buf, 64)
            text = buf.value.decode(errors="ignore")
            name = _SYM_TO_NAME.get(symname)
            if symname == "ISO_Level3_Shift":
                name = "altgr"
            elif name is None and len(text) == 1:
                name = text.lower()
            if len(text) == 1 and text.isprintable() and symname not in ("Return", "Tab", "KP_Enter"):
                char = text
        L.xkb_state_update_key(self.state, kc, 0 if pressed else 1)  # XKB_KEY_DOWN=0, UP=1
        return name, char


def keysym_for_name(name: str) -> int:
    """Canonical key name ('enter', 'f5', 'a', ...) -> X keysym."""
    L = lib()
    sym_name = _NAME_TO_SYM.get(name)
    if sym_name:
        return L.xkb_keysym_from_name(sym_name.encode(), 0)
    if len(name) == 1:
        return L.xkb_utf32_to_keysym(ord(name))
    return L.xkb_keysym_from_name(name.encode(), 1)  # XKB_KEYSYM_CASE_INSENSITIVE


def keysym_for_char(ch: str) -> int:
    return lib().xkb_utf32_to_keysym(ord(ch))
