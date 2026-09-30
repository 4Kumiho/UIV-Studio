"""User settings: defaults, validation, JSON persistence.

Settings are a nested dict (easy to serialize and to bind in the Settings page).
Unknown keys in the saved file are dropped; missing keys fall back to defaults,
so older settings files keep working after upgrades.
"""

import copy
import json
import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from uiv_studio.core.paths import config_dir, default_workspace

log = logging.getLogger(__name__)

HUD_CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")

DEFAULTS = {
    "general": {
        "language": "it",
        "workspace": str(default_workspace()),
        "hud_corner": "bottom-left",
        "minimize_during_sessions": True,
        "welcome_done": False,
    },
    "hotkeys": {
        # Recorder
        "recorder_menu": "ctrl+shift",
        "recorder_end_input": "f9",
        # Player
        "player_menu": "ctrl+shift",
    },
    "recording": {
        "double_click_ms": 450,
        "drag_threshold_px": 6,
        "scroll_debounce_ms": 350,
    },
    "validation": {
        # Minimum composite score to accept a match
        "threshold": 0.82,
        # Score above which the local (expected-position) match is accepted immediately
        "fast_accept": 0.93,
        # If the best two candidates differ less than this, the closer one to the expected position wins
        "ambiguity_margin": 0.03,
        "stages": 3,
        "seconds_between_stages": 2.0,
        "local_search_radius_px": 160,
        "weights_text": {"template": 0.40, "ocr": 0.35, "visual": 0.25},
        "weights_no_text": {"template": 0.60, "visual": 0.40},
    },
    "execution": {
        "delay_between_steps_s": 1.0,
        "mouse_move_ms": 250,
        "typing_interval_ms": 25,
        "record_video": True,
        "video_fps": 10,
        "stop_on_failure": True,
    },
}


def _merge(defaults: dict, data: dict) -> dict:
    out = {}
    for key, default in defaults.items():
        value = data.get(key, default) if isinstance(data, dict) else default
        if isinstance(default, dict):
            out[key] = _merge(default, value if isinstance(value, dict) else {})
        elif isinstance(default, bool):
            out[key] = bool(value) if isinstance(value, bool) else default
        elif isinstance(default, (int, float)) and not isinstance(default, bool):
            out[key] = type(default)(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default
        else:
            out[key] = value if isinstance(value, type(default)) else default
    return out


def normalize_weights(weights: dict) -> dict:
    total = sum(max(0.0, float(v)) for v in weights.values())
    if total <= 0:
        return {k: 1.0 / len(weights) for k in weights}
    return {k: max(0.0, float(v)) / total for k, v in weights.items()}


def _sanitize(s: dict) -> dict:
    v = s["validation"]
    v["threshold"] = min(max(v["threshold"], 0.3), 0.99)
    v["fast_accept"] = min(max(v["fast_accept"], v["threshold"]), 1.0)
    v["ambiguity_margin"] = min(max(v["ambiguity_margin"], 0.0), 0.2)
    v["stages"] = min(max(int(v["stages"]), 1), 20)
    v["seconds_between_stages"] = min(max(v["seconds_between_stages"], 0.0), 60.0)
    v["local_search_radius_px"] = min(max(int(v["local_search_radius_px"]), 0), 2000)
    v["weights_text"] = normalize_weights(v["weights_text"])
    v["weights_no_text"] = normalize_weights(v["weights_no_text"])
    if s["general"]["hud_corner"] not in HUD_CORNERS:
        s["general"]["hud_corner"] = DEFAULTS["general"]["hud_corner"]
    if s["general"]["language"] not in ("it", "en"):
        s["general"]["language"] = "it"
    e = s["execution"]
    e["video_fps"] = min(max(int(e["video_fps"]), 1), 30)
    return s


class Settings(QObject):
    """Application settings singleton; emits `changed` after every save."""

    changed = Signal()

    def __init__(self, path: Path | None = None):
        super().__init__()
        self.path = path or (config_dir() / "settings.json")
        self.data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self):
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self.data = _sanitize(_merge(DEFAULTS, raw))
        except Exception as exc:  # corrupted file -> defaults
            log.warning("Invalid settings file, using defaults: %s", exc)
            self.data = copy.deepcopy(DEFAULTS)

    def save(self, data: dict | None = None):
        if data is not None:
            self.data = _sanitize(_merge(DEFAULTS, data))
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        self.changed.emit()

    def snapshot(self) -> dict:
        return copy.deepcopy(self.data)

    @staticmethod
    def defaults() -> dict:
        return _sanitize(copy.deepcopy(DEFAULTS))

    def get(self, section: str, key: str):
        return self.data[section][key]

    @property
    def workspace(self) -> Path:
        p = Path(self.data["general"]["workspace"])
        (p / "recordings").mkdir(parents=True, exist_ok=True)
        (p / "runs").mkdir(parents=True, exist_ok=True)
        return p


_instance: Settings | None = None


def settings() -> Settings:
    global _instance
    if _instance is None:
        _instance = Settings()
    return _instance
