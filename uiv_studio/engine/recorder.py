# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Recording session: capture user actions and turn them into steps.

Capture never blocks: events go to a queue and a worker thread does the heavy
part (bbox, OCR, embedding, DB write), so the user can keep working naturally.
"""

import logging
import queue
import threading

from PySide6.QtCore import QObject, Signal

from uiv_studio.core.models import Action, Step
from uiv_studio.core.screens import Monitor, ScreenGrabber
from uiv_studio.core.storage import Recording
from uiv_studio.engine.capture import FrameBuffer, InputCapture
from uiv_studio.engine.targets import build_target
from uiv_studio.vision.embed import Embedder
from uiv_studio.vision.imageio import to_png
from uiv_studio.vision.ocr import OCR

log = logging.getLogger(__name__)

_MOUSE_ACTIONS = {
    "click": Action.CLICK, "double_click": Action.DOUBLE_CLICK,
    "right_click": Action.RIGHT_CLICK, "drag": Action.DRAG, "scroll": Action.SCROLL,
}


class Recorder(QObject):
    state_changed = Signal(str)          # loading | ready | paused | finishing
    step_saved = Signal(int, str)        # total steps, action
    pending_changed = Signal(int)        # events waiting to be processed
    buffer_changed = Signal(str)         # text being typed
    hotkey = Signal(str)                 # hotkey name (menu, end_input)
    finished = Signal(str)               # recording path
    failed = Signal(str)

    def __init__(self, recording: Recording, monitor: Monitor, settings: dict, own_windows=lambda: []):
        super().__init__()
        self.recording = recording
        self.monitor = monitor
        self.settings = settings
        self.own_windows = own_windows    # callable -> list of (x, y, w, h) global physical rects
        self.frames = FrameBuffer(ScreenGrabber(monitor))
        hk = settings["hotkeys"]
        self.capture = InputCapture(
            settings["recording"],
            {"menu": hk["recorder_menu"], "end_input": hk["recorder_end_input"]},
            self.frames, self._on_event, accept_point=self._accept_point,
        )
        self._queue: queue.Queue = queue.Queue()
        self._worker = threading.Thread(target=self._work, name="recorder", daemon=True)
        self._pending = 0
        self._stopping = False
        self.state = "loading"

    # ------------------------------------------------------------ control
    def start(self):
        self._set_state("loading")
        threading.Thread(target=self._boot, name="recorder-boot", daemon=True).start()

    def _boot(self):
        try:
            OCR.warmup()
            Embedder.warmup()
            self.frames.start()
            self.capture.start()
            self._worker.start()
            self.capture.set_enabled(True)
            self._set_state("ready")
        except Exception as exc:
            log.exception("Recorder boot failed")
            self.failed.emit(str(exc))

    def pause(self, paused: bool):
        self.capture.set_enabled(not paused)
        self._set_state("paused" if paused else "ready")

    def end_input(self):
        self.capture.flush_text()

    def undo_last(self):
        self._queue.put(("undo", None))

    def stop(self, discard: bool = False):
        if self._stopping:
            return
        self._stopping = True
        self._set_state("finishing")
        self.capture.set_enabled(False)
        if not discard:
            self.capture.flush()
        else:
            self.capture.discard_text()
        self._queue.put(("stop", discard))

    # ------------------------------------------------------------ events
    def _accept_point(self, x, y) -> bool:
        if not self.monitor.contains(x, y):
            return False
        for (wx, wy, ww, wh) in self.own_windows():
            if wx <= x < wx + ww and wy <= y < wy + wh:
                return False
        return True

    def _on_event(self, kind: str, data: dict):
        if kind == "hotkey":
            self.hotkey.emit(data["name"])
            return
        if kind == "buffer":
            self.buffer_changed.emit(data["text"])
            return
        if self._stopping and kind not in ("text", "click", "scroll"):
            return
        self._pending += 1
        self.pending_changed.emit(self._pending)
        self._queue.put((kind, data))

    def _work(self):
        while True:
            kind, data = self._queue.get()
            if kind == "stop":
                self._finish(discard=data)
                return
            if kind == "undo":
                steps = self.recording.steps(with_screens=False)
                if steps:
                    self.recording.delete_step(steps[-1].id)
                    self.step_saved.emit(len(steps) - 1, "UNDO")
                continue
            try:
                step = self._build_step(kind, data)
                if step is not None:
                    self.recording.add_step(step)
                    self.step_saved.emit(step.idx, step.action)
            except Exception:
                log.exception("Failed to process %s", kind)
            finally:
                self._pending = max(0, self._pending - 1)
                self.pending_changed.emit(self._pending)

    def _local(self, x, y) -> tuple[int, int]:
        return int(x - self.monitor.left), int(y - self.monitor.top)

    def _build_step(self, kind: str, d: dict) -> Step | None:
        frame = d.get("frame")
        shot = to_png(frame) if frame is not None else b""
        if kind in _MOUSE_ACTIONS:
            action = _MOUSE_ACTIONS[kind]
            x, y = self._local(d["x"], d["y"])
            step = Step(action=action, screenshot=shot, modifiers=d.get("mods", []),
                        target=build_target(frame, x, y))
            if action == Action.DRAG:
                x2, y2 = self._local(d["x2"], d["y2"])
                step.drop = build_target(frame, x2, y2)
            elif action == Action.SCROLL:
                step.scroll_dx, step.scroll_dy = int(d["dx"]), int(d["dy"])
            return step
        if kind == "text":
            return Step(action=Action.INPUT, screenshot=shot, text=d["text"], enter_after=d["enter_after"])
        if kind == "key":
            return Step(action=Action.KEY, screenshot=shot, key=d["combo"])
        return None

    def _finish(self, discard: bool):
        try:
            self.capture.stop()
        except Exception:
            pass
        self.frames.stop()
        path = str(self.recording.path)
        self.recording.close()
        if discard:
            from uiv_studio.core.storage import delete_recording
            delete_recording(path)
            path = ""
        self.finished.emit(path)

    def _set_state(self, s: str):
        self.state = s
        self.state_changed.emit(s)
