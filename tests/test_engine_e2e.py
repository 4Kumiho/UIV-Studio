"""Headless end-to-end test of Recorder -> Recording -> Player (no real input is generated)."""

import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

from uiv_studio.core.models import Action, Status
from uiv_studio.core.screens import Monitor
from uiv_studio.core.settings import Settings
from uiv_studio.core.storage import Recording, Run

W, H = 1280, 800
BUTTONS = [("Login", (200, 150)), ("Settings", (500, 150)), ("Save file", (800, 150)), ("Cancel", (1000, 600))]


def draw_ui(offset=(0, 0), scale=1.0, size=(W, H)):
    img = np.full((size[1], size[0], 3), (40, 34, 30), np.uint8)
    cv2.rectangle(img, (0, 0), (size[0], int(60 * scale)), (60, 50, 45), -1)
    cv2.putText(img, "Demo App", (int(20 * scale), int(40 * scale)), cv2.FONT_HERSHEY_SIMPLEX, 0.9 * scale, (230, 230, 230), 2)
    rects = {}
    for text, (x, y) in BUTTONS:
        x = int(x * scale) + offset[0]
        y = int(y * scale) + offset[1]
        w, h = int(170 * scale), int(52 * scale)
        cv2.rectangle(img, (x, y), (x + w, y + h), (200, 110, 90), -1)
        cv2.rectangle(img, (x, y), (x + w, y + h), (250, 170, 150), 2)
        cv2.putText(img, text, (x + int(18 * scale), y + int(35 * scale)), cv2.FONT_HERSHEY_SIMPLEX, 0.9 * scale, (255, 255, 255), 2)
        rects[text] = (x, y, w, h)
    return img, rects


class FakeActuator:
    def __init__(self, *a):
        self.calls = []

    def click(self, x, y, mods=(), button="left", count=1):
        self.calls.append(("click", x, y, button, count))

    def drag(self, x1, y1, x2, y2, mods=()):
        self.calls.append(("drag", x1, y1, x2, y2))

    def scroll(self, x, y, dx, dy, mods=()):
        self.calls.append(("scroll", x, y, dx, dy))

    def type_text(self, text, enter_after=False):
        self.calls.append(("type", text, enter_after))

    def key_combo(self, combo):
        self.calls.append(("key", combo))


def record(ws: Path, frame) -> Path:
    from uiv_studio.engine.recorder import Recorder
    from uiv_studio.vision.ocr import OCR

    mon = Monitor(1, 0, 0, W, H, 1.0)
    rec = Recording.create(ws, "demo", W, H, 1.0)
    s = Settings.defaults()
    r = Recorder(rec, mon, s)
    done = []
    from PySide6.QtCore import Qt
    r.finished.connect(lambda p: done.append(p), Qt.DirectConnection)
    OCR.warmup()
    r._worker.start()
    _, rects = draw_ui()
    cx = lambda t: rects[t][0] + rects[t][2] // 2
    cy = lambda t: rects[t][1] + rects[t][3] // 2
    ev = r._on_event
    ev("click", {"x": cx("Login"), "y": cy("Login"), "mods": [], "frame": frame})
    ev("text", {"text": "hello", "enter_after": True, "frame": frame})
    ev("double_click", {"x": cx("Settings"), "y": cy("Settings"), "mods": ["ctrl"], "frame": frame})
    ev("key", {"combo": "ctrl+s", "frame": frame})
    ev("drag", {"x": cx("Save file"), "y": cy("Save file"), "x2": cx("Cancel"), "y2": cy("Cancel"), "mods": [], "frame": frame})
    ev("scroll", {"x": cx("Cancel"), "y": cy("Cancel"), "dx": 0, "dy": -3, "mods": [], "frame": frame})
    r._queue.put(("stop", False))
    r._worker.join(timeout=60)
    r.frames.grabber.close()
    assert done and done[0], "recorder did not finish"
    return Path(done[0])


def play(ws: Path, rec_path: Path, screen, exe_w, exe_h, exe_scale=1.0):
    import uiv_studio.engine.player as player_mod

    player_mod.ScreenGrabber.grab = lambda self: screen
    fake = FakeActuator()
    player_mod.Actuator = lambda cfg: fake
    s = Settings.defaults()
    s["execution"]["record_video"] = False
    s["execution"]["delay_between_steps_s"] = 0
    s["validation"]["seconds_between_stages"] = 0.1
    p = player_mod.Player(str(rec_path), Monitor(1, 0, 0, exe_w, exe_h, exe_scale), s, ws)
    out = []
    p.finished.connect(lambda path, res: out.append((path, res)))
    p._main()
    run = Run(Path(out[0][0]))
    steps = run.steps()
    run.close()
    return out[0][1], steps, fake.calls


def main():
    t0 = time.time()
    ws = Path(tempfile.mkdtemp(prefix="uiv_e2e_"))
    frame, rects = draw_ui()
    rec_path = record(ws, frame)
    rec = Recording(rec_path)
    steps = rec.steps()
    rec.close()
    print("recorded:", [(s.idx, s.action, s.target.ocr_text if s.target else s.text or s.key) for s in steps])
    assert [s.action for s in steps] == [Action.CLICK, Action.INPUT, Action.DOUBLE_CLICK, Action.KEY, Action.DRAG, Action.SCROLL]

    # 1) identical screen
    res, rs, calls = play(ws, rec_path, frame, W, H)
    print("same screen:", res, [(r.status, round(r.match.score, 3) if r.match else None) for r in rs])
    assert res == Status.PASSED, rs

    # 2) buttons moved by (+37, +23)
    moved, mrects = draw_ui(offset=(37, 23))
    res, rs, calls = play(ws, rec_path, moved, W, H)
    click = calls[0]
    lx, ly, lw, lh = mrects["Login"]
    print("moved:", res, click, "login rect", mrects["Login"])
    assert res == Status.PASSED and lx <= click[1] <= lx + lw and ly <= click[2] <= ly + lh

    # 3) different resolution + 125% scaling
    big, brects = draw_ui(scale=1.25, size=(1600, 1000))
    res, rs, calls = play(ws, rec_path, big, 1600, 1000, 1.25)
    click = calls[0]
    bx, by, bw, bh = brects["Login"]
    print("scaled 125%:", res, click, "login rect", brects["Login"], [(r.status, r.match.method if r.match else "") for r in rs])
    assert res == Status.PASSED and bx <= click[1] <= bx + bw and by <= click[2] <= by + bh

    # 4) element missing -> must FAIL (no false positive)
    missing = frame.copy()
    x, y, w, h = rects["Login"]
    missing[y - 2:y + h + 3, x - 2:x + w + 3] = (40, 34, 30)
    res, rs, calls = play(ws, rec_path, missing, W, H)
    print("missing:", res, [(r.status, round(r.match.score, 3) if r.match else None) for r in rs][:2])
    assert res == Status.FAILED and rs[0].status == Status.FAILED

    print(f"ALL OK in {time.time() - t0:.1f}s  (workspace {ws})")


if __name__ == "__main__":
    main()
