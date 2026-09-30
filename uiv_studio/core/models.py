# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Plain data objects for recordings and runs."""

from dataclasses import dataclass, field


class Action:
    CLICK = "CLICK"
    DOUBLE_CLICK = "DOUBLE_CLICK"
    RIGHT_CLICK = "RIGHT_CLICK"
    DRAG = "DRAG"
    SCROLL = "SCROLL"
    INPUT = "INPUT"
    KEY = "KEY"
    WAIT = "WAIT"

    ALL = (CLICK, DOUBLE_CLICK, RIGHT_CLICK, DRAG, SCROLL, INPUT, KEY, WAIT)
    NEEDS_TARGET = (CLICK, DOUBLE_CLICK, RIGHT_CLICK, DRAG, SCROLL)


class Status:
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"


@dataclass
class Target:
    """A UI element on the recorded screenshot, in monitor-relative physical pixels."""
    x: int
    y: int
    w: int
    h: int
    click_x: int = 0            # click point relative to bbox origin
    click_y: int = 0
    ocr_text: str = ""
    ocr_box: list | None = None  # [x, y, w, h] of the text, relative to bbox origin
    template: bytes = b""        # PNG crop
    embedding: bytes = b""       # float32 vector

    @property
    def bbox(self) -> tuple:
        return self.x, self.y, self.w, self.h

    def meta(self) -> dict:
        return {
            "x": self.x, "y": self.y, "w": self.w, "h": self.h,
            "click_x": self.click_x, "click_y": self.click_y,
            "ocr_text": self.ocr_text, "ocr_box": self.ocr_box,
        }


@dataclass
class Step:
    action: str
    idx: int = 0
    id: int | None = None
    screenshot: bytes = b""          # PNG of the screen before the action
    target: Target | None = None
    drop: Target | None = None       # DRAG destination
    modifiers: list = field(default_factory=list)
    text: str = ""                   # INPUT text
    enter_after: bool = False
    key: str = ""                    # KEY combo, e.g. "ctrl+s"
    scroll_dx: int = 0
    scroll_dy: int = 0
    wait_s: float = 0.0              # extra wait before the step (WAIT: the duration)
    testcase: str = ""
    note: str = ""


@dataclass
class RecordingInfo:
    name: str
    created_at: str
    screen_w: int
    screen_h: int
    scale: float
    app_version: str = ""
    description: str = ""


@dataclass
class MatchInfo:
    found: bool = False
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    score: float = 0.0
    template: float = 0.0
    ocr: float | None = None
    visual: float = 0.0
    stage: int = 0
    method: str = ""                 # "local" | "global" | "text"
    ocr_text: str = ""
    crop: bytes = b""

    def meta(self) -> dict:
        return {k: getattr(self, k) for k in
                ("found", "x", "y", "w", "h", "score", "template", "ocr", "visual", "stage", "method", "ocr_text")}


@dataclass
class RunStep:
    idx: int
    action: str
    status: str
    started_s: float = 0.0           # seconds since run start (video timestamp)
    duration_s: float = 0.0
    match: MatchInfo | None = None
    drop_match: MatchInfo | None = None
    error: str = ""
    testcase: str = ""
    id: int | None = None


@dataclass
class RunInfo:
    recording_name: str
    recording_path: str
    started_at: str
    ended_at: str = ""
    result: str = ""
    error: str = ""
    screen_w: int = 0
    screen_h: int = 0
    scale: float = 1.0
    video: str = ""
