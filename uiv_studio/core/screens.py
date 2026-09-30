"""Monitor enumeration and screen capture (physical pixels, BGR numpy arrays)."""

import sys
import threading
from dataclasses import asdict, dataclass

import numpy as np


@dataclass
class Monitor:
    index: int          # 1-based, as in mss
    left: int
    top: int
    width: int
    height: int
    scale: float        # OS display scaling (1.0 = 100 %)

    @property
    def label(self) -> str:
        return f"#{self.index}  {self.width}×{self.height}  @ {round(self.scale * 100)}%"

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.left + self.width and self.top <= y < self.top + self.height

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Monitor":
        return cls(**{k: d[k] for k in ("index", "left", "top", "width", "height", "scale")})

    def mss_region(self) -> dict:
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}


def _windows_scale(left: int, top: int, width: int, height: int) -> float:
    try:
        import ctypes
        from ctypes import wintypes

        pt = wintypes.POINT(left + width // 2, top + height // 2)
        hmon = ctypes.windll.user32.MonitorFromPoint(pt, 2)  # MONITOR_DEFAULTTONEAREST
        dpi_x, dpi_y = ctypes.c_uint(), ctypes.c_uint()
        ctypes.windll.shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
        return round(dpi_x.value / 96.0, 2) or 1.0
    except Exception:
        return 1.0


def _qt_scale(width: int, height: int, index: int) -> float:
    try:
        from PySide6.QtGui import QGuiApplication

        screens = QGuiApplication.screens()
        for s in screens:
            dpr = s.devicePixelRatio()
            g = s.geometry()
            if round(g.width() * dpr) == width and round(g.height() * dpr) == height:
                return round(dpr, 2)
        if 0 <= index - 1 < len(screens):
            return round(screens[index - 1].devicePixelRatio(), 2)
    except Exception:
        pass
    return 1.0


def list_monitors() -> list[Monitor]:
    import mss

    with mss.mss() as sct:
        mons = sct.monitors[1:]
    out = []
    for i, m in enumerate(mons, start=1):
        if sys.platform == "win32":
            scale = _windows_scale(m["left"], m["top"], m["width"], m["height"])
        else:
            scale = _qt_scale(m["width"], m["height"], i)
        out.append(Monitor(i, m["left"], m["top"], m["width"], m["height"], scale))
    return out


class ScreenGrabber:
    """Thread-safe grabber. mss handles are per-thread, so we keep one per thread."""

    def __init__(self, monitor: Monitor):
        self.monitor = monitor
        self._local = threading.local()

    def _sct(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            import mss
            sct = mss.mss()
            self._local.sct = sct
        return sct

    def grab(self) -> np.ndarray:
        shot = self._sct().grab(self.monitor.mss_region())
        img = np.frombuffer(shot.bgra, dtype=np.uint8).reshape(shot.height, shot.width, 4)
        return np.ascontiguousarray(img[:, :, :3])

    def close(self):
        sct = getattr(self._local, "sct", None)
        if sct is not None:
            sct.close()
            self._local.sct = None


def wayland_session() -> bool:
    import os
    # Under Wayland (even with XWayland) global input hooks and screen capture of
    # other applications are blocked by the compositor.
    return sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
