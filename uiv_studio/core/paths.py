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
