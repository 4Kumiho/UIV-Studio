"""Execution session: replay a recording, validate every target, record results."""

import logging
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from pynput import keyboard
from PySide6.QtCore import QObject, Signal

from uiv_studio.core.keys import parse_combo, pynput_key_name
from uiv_studio.core.models import Action, MatchInfo, RunInfo, RunStep, Status, Step, Target
from uiv_studio.core.screens import Monitor, ScreenGrabber
from uiv_studio.core.storage import VIDEO_FILE, Recording, Run
from uiv_studio.engine.actions import Actuator
from uiv_studio.engine.video import VideoRecorder
from uiv_studio.vision.embed import Embedder
from uiv_studio.vision.matcher import Geometry, Matcher
from uiv_studio.vision.ocr import OCR

log = logging.getLogger(__name__)


class _Paused(Exception):
    pass


class Player(QObject):
    state_changed = Signal(str)                 # loading | running | searching | paused | finishing
    step_started = Signal(int, int, str)        # idx, total, action
    stage_changed = Signal(int, int)            # stage, total stages
    step_done = Signal(int, str, float)         # idx, status, score
    hotkey = Signal(str)                        # "menu"
    finished = Signal(str, str)                 # run path, result
    failed = Signal(str)

    def __init__(self, recording_path: str, monitor: Monitor, settings: dict, workspace: Path):
        super().__init__()
        self.recording_path = recording_path
        self.monitor = monitor
        self.settings = settings
        self.workspace = workspace
        self._paused = threading.Event()
        self._stop = threading.Event()
        self._skip = threading.Event()
        self._menu_combo = parse_combo(settings["hotkeys"]["player_menu"])
        self._pressed: set[str] = set()
        self._kb = None
        self.run: Run | None = None

    # ------------------------------------------------------------ control
    def start(self):
        threading.Thread(target=self._main, name="player", daemon=True).start()

    def pause(self, paused: bool):
        (self._paused.set if paused else self._paused.clear)()
        self.state_changed.emit("paused" if paused else "running")

    def skip_step(self):
        self._skip.set()
        self.pause(False)

    def stop(self):
        self._stop.set()
        self._paused.clear()

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    # ------------------------------------------------------------ hotkey
    def _on_press(self, key, injected=False):
        if injected:  # our own simulated key presses must never open the menu
            return
        name = pynput_key_name(key)
        if name:
            self._pressed.add(name)
            if self._menu_combo and self._pressed == set(self._menu_combo):
                self.hotkey.emit("menu")

    def _on_release(self, key, injected=False):
        if injected:
            return
        name = pynput_key_name(key)
        if name:
            self._pressed.discard(name)

    # ------------------------------------------------------------ main loop
    def _main(self):
        rec = None
        video = None
        result, error = Status.FAILED, ""
        try:
            self.state_changed.emit("loading")
            rec = Recording(Path(self.recording_path))
            info = rec.info()
            steps = rec.steps()
            rec.close()
            rec = None
            OCR.warmup()
            Embedder.warmup()

            m = self.monitor
            self.run = Run.create(self.workspace, RunInfo(
                recording_name=info.name, recording_path=self.recording_path,
                started_at=datetime.now().isoformat(timespec="seconds"),
                screen_w=m.width, screen_h=m.height, scale=m.scale))
            geo = Geometry(info.screen_w, info.screen_h, info.scale, m.width, m.height, m.scale)
            grabber = ScreenGrabber(m)
            actuator = Actuator(self.settings["execution"])
            matcher = Matcher(grabber.grab, geo, self.settings["validation"],
                              should_abort=lambda: self._paused.is_set() or self._stop.is_set(),
                              on_stage=lambda s, n: self.stage_changed.emit(s, n))

            self._kb = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
            self._kb.start()

            if self.settings["execution"]["record_video"]:
                video = VideoRecorder(str(self.run.folder / VIDEO_FILE), m, self.settings["execution"]["video_fps"])
                video.start()
            clock = video.elapsed if video else _Clock().elapsed

            self.state_changed.emit("running")
            result = Status.PASSED
            total = len(steps)
            i = 0
            while i < total:
                step = steps[i]
                if self._stop.is_set():
                    self._mark_rest(steps[i:], Status.STOPPED)
                    result = Status.STOPPED
                    break
                self._wait_while_paused()
                if self._stop.is_set():
                    continue
                self.step_started.emit(step.idx, total, step.action)
                t0 = clock()
                try:
                    status, match, drop, err = self._execute(step, matcher, actuator)
                except _Paused:
                    continue                        # retry the same step after resume
                if self._skip.is_set():
                    self._skip.clear()
                    status, err = Status.SKIPPED, "Skipped by user"
                rs = RunStep(idx=step.idx, action=step.action, status=status, started_s=round(t0, 2),
                             duration_s=round(clock() - t0, 2), match=match, drop_match=drop,
                             error=err, testcase=step.testcase)
                self.run.add_step(rs)
                self.step_done.emit(step.idx, status, match.score if match else 1.0)
                i += 1
                if status == Status.FAILED:
                    result = Status.FAILED
                    if self.settings["execution"]["stop_on_failure"]:
                        self._mark_rest(steps[i:], Status.SKIPPED)
                        break
                if i < total:
                    self._sleep(self.settings["execution"]["delay_between_steps_s"])
        except Exception as exc:
            log.exception("Player failed")
            result, error = Status.FAILED, f"{exc}\n{traceback.format_exc()}"
        finally:
            self.state_changed.emit("finishing")
            if self._kb:
                self._kb.stop()
            if video:
                video.stop()
            if rec:
                rec.close()
            path = ""
            if self.run:
                self.run.finish(result, error, VIDEO_FILE if video and video.ok else "")
                path = str(self.run.path)
                self.run.close()
            self.finished.emit(path, result)

    def _execute(self, step: Step, matcher: Matcher, act: Actuator):
        """Returns (status, match, drop_match, error)."""
        if step.wait_s > 0 and step.action != Action.WAIT:
            self._sleep(step.wait_s)
        a = step.action
        if a == Action.WAIT:
            self._sleep(step.wait_s)
            return Status.PASSED, None, None, ""
        if a == Action.INPUT:
            act.type_text(step.text, step.enter_after)
            return Status.PASSED, None, None, ""
        if a == Action.KEY:
            act.key_combo(step.key)
            return Status.PASSED, None, None, ""
        if step.target is None:
            return Status.FAILED, None, None, "Step has no target"

        self.state_changed.emit("searching")
        match = matcher.find(step.target)
        drop = None
        if a == Action.DRAG and match.found and step.drop is not None:
            drop = matcher.find(step.drop)
        self.state_changed.emit("running")
        if self._paused.is_set() and not self._stop.is_set():
            raise _Paused()
        if self._skip.is_set() or self._stop.is_set():
            return Status.SKIPPED if self._skip.is_set() else Status.STOPPED, match, drop, ""
        if not match.found:
            return Status.FAILED, match, drop, "Element not found"
        if a == Action.DRAG and (drop is None or not drop.found):
            return Status.FAILED, match, drop, "Drop target not found"

        x, y = self._point(match, step.target)
        mods = step.modifiers
        if a == Action.CLICK:
            act.click(x, y, mods)
        elif a == Action.DOUBLE_CLICK:
            act.click(x, y, mods, count=2)
        elif a == Action.RIGHT_CLICK:
            act.click(x, y, mods, button="right")
        elif a == Action.SCROLL:
            act.scroll(x, y, step.scroll_dx, step.scroll_dy, mods)
        elif a == Action.DRAG:
            x2, y2 = self._point(drop, step.drop)
            act.drag(x, y, x2, y2, mods)
        return Status.PASSED, match, drop, ""

    def _point(self, m: MatchInfo, t: Target) -> tuple[int, int]:
        """Global physical coordinates of the click point inside the found element."""
        fx = m.w / t.w if t.w else 1.0
        fy = m.h / t.h if t.h else 1.0
        return (self.monitor.left + m.x + round(t.click_x * fx),
                self.monitor.top + m.y + round(t.click_y * fy))

    # ------------------------------------------------------------ utils
    def _mark_rest(self, steps: list[Step], status: str):
        for s in steps:
            self.run.add_step(RunStep(idx=s.idx, action=s.action, status=status, testcase=s.testcase))
            self.step_done.emit(s.idx, status, 0.0)

    def _wait_while_paused(self):
        while self._paused.is_set() and not self._stop.is_set():
            time.sleep(0.05)

    def _sleep(self, seconds: float):
        end = time.monotonic() + seconds
        while time.monotonic() < end and not self._stop.is_set():
            time.sleep(0.05)
            self._wait_while_paused()


class _Clock:
    def __init__(self):
        self.t0 = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self.t0
