"""Check GitHub Releases for a newer version and replace the executable in place."""

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from uiv_studio import __version__

REPO = "4Kumiho/UIV-Studio"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
ASSET = "UIV-Studio-windows.exe" if sys.platform == "win32" else "UIV-Studio-linux"


def _parse(v: str) -> tuple:
    parts = []
    for p in v.lstrip("vV").split("-")[0].split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts + [0] * (3 - len(parts)))


def latest_release(timeout: float = 10) -> dict:
    """{'version': '1.2.0', 'newer': bool, 'url': asset download url, 'notes': str}"""
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                 headers={"User-Agent": "UIV-Studio", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    version = data.get("tag_name", "").lstrip("vV")
    url = next((a["browser_download_url"] for a in data.get("assets", []) if a["name"] == ASSET), None)
    return {"version": version, "newer": _parse(version) > _parse(__version__), "url": url,
            "notes": data.get("body") or ""}


def launcher_path() -> Path | None:
    """The single-file executable that started us (None when running from source)."""
    p = os.environ.get("UIV_LAUNCHER")
    return Path(p) if p and Path(p).is_file() else None


def download(url: str, dest: Path, progress) -> None:
    tmp = dest.with_name(dest.name + ".download")
    req = urllib.request.Request(url, headers={"User-Agent": "UIV-Studio"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 18)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            progress(done, total)
    os.replace(tmp, dest)


def install_and_restart(new_file: Path, launcher: Path):
    """Swap the executable (it is not locked: the launcher exits after starting us) and start it."""
    old = launcher.with_name(launcher.name + ".old")
    if old.exists():
        old.unlink()
    os.replace(launcher, old)
    os.replace(new_file, launcher)
    if sys.platform != "win32":
        os.chmod(launcher, 0o755)
    kwargs = {"cwd": str(launcher.parent)}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    else:
        kwargs["start_new_session"] = True
    env = {k: v for k, v in os.environ.items() if k != "UIV_LAUNCHER"}
    subprocess.Popen([str(launcher)], env=env, **kwargs)


def cleanup_old():
    lp = launcher_path()
    if lp:
        old = lp.with_name(lp.name + ".old")
        try:
            old.unlink()
        except OSError:
            pass
