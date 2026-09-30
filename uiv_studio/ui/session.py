"""Glue between engine sessions (Recorder / Player) and on-screen overlays."""

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from uiv_studio.core.keys import display_combo
from uiv_studio.core.screens import Monitor
from uiv_studio.core.storage import Recording
from uiv_studio.engine.player import Player
from uiv_studio.engine.recorder import Recorder
from uiv_studio.ui.i18n import tr
from uiv_studio.ui.overlays import Hud, SessionMenu, physical_rect


class RecordingSession(QObject):
    done = Signal(str, int)          # recording path ('' if discarded), steps

    def __init__(self, recording: Recording, monitor: Monitor, settings: dict):
        super().__init__()
        self.settings = settings
        self.monitor = monitor
        self.menu: SessionMenu | None = None
        hk = settings["hotkeys"]
        self.hud = Hud(monitor, settings["general"]["hud_corner"], display_combo(hk["recorder_menu"]))
        self.recorder = Recorder(recording, monitor, settings, own_windows=self._own_windows)
        self.steps = recording.step_count()
        r = self.recorder
        r.state_changed.connect(self._on_state)
        r.step_saved.connect(self._on_step)
        r.pending_changed.connect(self._on_pending)
        r.buffer_changed.connect(self._on_buffer)
        r.hotkey.connect(self._on_hotkey)
        r.finished.connect(self._on_finished)
        r.failed.connect(lambda msg: self._on_finished(""))
        self._menu_rect = None
        self._menu_hint = tr("hud.menu_hint", key=display_combo(hk["recorder_menu"]))

    def start(self):
        self.hud.set_counter(tr("hud.step", n=self.steps + 1))
        self.hud.appear()
        self.recorder.start()

    def _own_windows(self):
        return [self._menu_rect] if self._menu_rect else []

    # ------------------------------------------------------------ signals
    def _on_state(self, s: str):
        self.hud.set_state(s, tr(f"hud.{s}"))

    def _on_step(self, n: int, action: str):
        self.steps = n
        self.hud.set_counter(tr("hud.step", n=n + 1))
        if action != "UNDO":
            self.hud.set_sub(f"✓ {tr('action.' + action)}")
            QTimer.singleShot(1500, lambda: self.hud.set_sub(self._menu_hint))

    def _on_pending(self, n: int):
        if n > 0:
            self.hud.set_sub(tr("hud.pending", n=n))

    def _on_buffer(self, text: str):
        self.hud.set_sub(f"✎ {text}" if text else self._menu_hint)

    def _on_hotkey(self, name: str):
        if name == "menu":
            if self.menu and self.menu.isVisible():
                self._menu_choice("resume")
            else:
                self._open_menu()
        elif name == "end_input":
            self.recorder.end_input()

    def _open_menu(self):
        self.recorder.pause(True)
        opts = [
            ("resume", tr("menu.resume"), "play", "Primary"),
            ("end_input", tr("menu.end_input"), "type", ""),
            ("undo", tr("menu.undo"), "undo", ""),
            ("finish", tr("menu.finish"), "save", ""),
            ("discard", tr("menu.discard"), "trash", "Danger"),
        ]
        self.menu = SessionMenu(self.monitor, tr("menu.recorder"), opts)
        self.menu.chosen.connect(self._menu_choice)
        self.menu.popup()
        self._menu_rect = physical_rect(self.menu, self.monitor)

    def _menu_choice(self, key: str):
        if self.menu:
            self.menu.close()
            self.menu = None
        # keep ignoring clicks on the (fading) menu area for a moment
        QTimer.singleShot(300, lambda: setattr(self, "_menu_rect", None))
        if key == "resume":
            self.recorder.pause(False)
        elif key == "end_input":
            self.recorder.end_input()
            self.recorder.pause(False)
        elif key == "undo":
            self.recorder.undo_last()
            self.recorder.pause(False)
        elif key == "finish":
            self.recorder.stop()
        elif key == "discard":
            self.recorder.stop(discard=True)

    def _on_finished(self, path: str):
        self.hud.close()
        if self.menu:
            self.menu.close()
        self.done.emit(path, self.steps)


class PlaybackSession(QObject):
    done = Signal(str, str)          # run path, result

    def __init__(self, recording_path: str, monitor: Monitor, settings: dict, workspace: Path):
        super().__init__()
        self.monitor = monitor
        self.menu: SessionMenu | None = None
        hk = settings["hotkeys"]["player_menu"]
        self.hud = Hud(monitor, settings["general"]["hud_corner"], display_combo(hk))
        self.player = Player(recording_path, monitor, settings, workspace)
        self._hint = tr("hud.menu_hint", key=display_combo(hk))
        p = self.player
        p.state_changed.connect(lambda s: self.hud.set_state(s, tr(f"hud.{s}")))
        p.step_started.connect(self._on_step)
        p.stage_changed.connect(lambda s, n: self.hud.set_sub(f"{tr('hud.searching')} · {tr('rep.stage', n=s)}/{n}"))
        p.step_done.connect(self._on_step_done)
        p.hotkey.connect(self._on_hotkey)
        p.finished.connect(self._on_finished)

    def start(self):
        self.hud.appear()
        self.player.start()

    def _on_step(self, idx: int, total: int, action: str):
        self.hud.set_counter(tr("hud.step_of", n=idx, total=total))
        self.hud.set_sub(f"{tr('action.' + action)} · {self._hint}")

    def _on_step_done(self, idx: int, status: str, score: float):
        mark = {"PASSED": "✓", "FAILED": "✗"}.get(status, "•")
        self.hud.set_sub(f"{mark} {tr('status.' + status)}  {score * 100:.0f}%")

    def _on_hotkey(self, name: str):
        if self.menu and self.menu.isVisible():
            self._choice("resume")
            return
        self.player.pause(True)
        opts = [
            ("resume", tr("menu.resume"), "play", "Primary"),
            ("skip", tr("menu.skip"), "skip", ""),
            ("stop", tr("menu.stop"), "stop", "Danger"),
        ]
        self.menu = SessionMenu(self.monitor, tr("menu.player"), opts)
        self.menu.chosen.connect(self._choice)
        self.menu.popup()

    def _choice(self, key: str):
        if self.menu:
            self.menu.close()
            self.menu = None
        if key == "resume":
            self.player.pause(False)
        elif key == "skip":
            self.player.skip_step()
        elif key == "stop":
            self.player.stop()

    def _on_finished(self, path: str, result: str):
        self.hud.close()
        if self.menu:
            self.menu.close()
        self.done.emit(path, result)
