# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Filesystem locations: bundled resources, per-user config, default workspace."""

import os
import sys
from pathlib import Path

from uiv_studio import APP_ID, APP_NAME


def resource_dir() -> Path:
    """Folder holding bundled read-only resources (works frozen and from source)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "uiv_studio" / "resources"
    return Path(__file__).resolve().parent.parent / "resources"


def system_env() -> dict:
    """Environment for running a tool that belongs to the system, not to us.

    A frozen build runs with LD_LIBRARY_PATH pointing at its own bundled
    libraries, so a system binary started from here loads our older glib and
    dies on an undefined symbol: gst-launch then never produces a frame and
    recording shows a blank screen. PyInstaller keeps the caller's original
    value in <VAR>_ORIG.
    """
    env = dict(os.environ)
    for var in ("LD_LIBRARY_PATH", "LD_PRELOAD", "LIBPATH", "DYLD_LIBRARY_PATH"):
        original = env.pop(var + "_ORIG", None)
        if original is not None:
            env[var] = original
        elif getattr(sys, "frozen", False):
            env.pop(var, None)
    return env


def config_dir() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_ID
    root.mkdir(parents=True, exist_ok=True)
    return root


def log_dir() -> Path:
    d = config_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_workspace() -> Path:
    docs = Path.home() / "Documents"
    return (docs if docs.is_dir() else Path.home()) / APP_NAME
