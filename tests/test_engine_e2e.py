# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

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
        self.moves = []

    def move(self, x, y):
        self.moves.append((x, y))

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
    """`screen` is a frame, or a callable(cursor moves) -> frame for UIs that react to the cursor."""
    import uiv_studio.engine.player as player_mod

    import uiv_studio.platform as backend

    class _Grab:
        def grab(self):
            return screen(fake.moves) if callable(screen) else screen

        def close(self):
            pass

    class _NoHotkeys:
        def start(self):
            pass

        def stop(self):
            pass

    backend.make_grabber = lambda monitor: _Grab()
    backend.make_hotkey_listener = lambda combo, cb: _NoHotkeys()
    fake = FakeActuator()
    backend.make_actuator = lambda cfg, monitor: fake
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


MENU = ["Open", "Rename", "Copy path", "Delete"]


# Menu themes (BGR): desktop, menu, border, text
THEMES = {
    "light": ((235, 235, 235), (250, 250, 250), (170, 170, 170), (40, 40, 40)),
    "dark": ((30, 30, 30), (45, 43, 43), (80, 80, 80), (225, 225, 225)),
}
# Hover styles: fill (None = outline only), outline, text color (None = unchanged)
HOVERS = {
    "blue/white text": ((215, 120, 0), None, (255, 255, 255)),
    "light grey": ((222, 222, 222), None, (30, 30, 30)),
    "dark/white text": ((70, 60, 60), None, (255, 255, 255)),
    "soft green": ((205, 240, 205), None, (20, 90, 20)),
    "orange outline": (None, (0, 140, 255), None),
    "rounded accent": ((180, 105, 255), None, (255, 255, 255)),
}


def draw_menu(hovered: str | None, origin=(420, 260), theme="light", hover="blue/white text"):
    """Desktop-like context menu with one entry (optionally) in its hover state."""
    desk, menu, border, text_color = THEMES[theme]
    img = np.full((H, W, 3), desk, np.uint8)
    ox, oy = origin
    cv2.rectangle(img, (ox, oy), (ox + 220, oy + 30 * len(MENU) + 8), menu, -1)
    cv2.rectangle(img, (ox, oy), (ox + 220, oy + 30 * len(MENU) + 8), border, 1)
    rects = {}
    for i, text in enumerate(MENU):
        x, y, w, h = ox + 4, oy + 4 + 30 * i, 212, 30
        color = text_color
        if text == hovered:
            fill, outline, hover_text = HOVERS[hover]
            if fill is not None and hover == "rounded accent":
                cv2.rectangle(img, (x + 6, y), (x + w - 6, y + h), fill, -1)
                cv2.rectangle(img, (x, y + 6), (x + w, y + h - 6), fill, -1)
                for cx in (x + 6, x + w - 6):
                    for cy in (y + 6, y + h - 6):
                        cv2.circle(img, (cx, cy), 6, fill, -1, cv2.LINE_AA)
            elif fill is not None:
                cv2.rectangle(img, (x, y), (x + w, y + h), fill, -1)
            if outline is not None:
                cv2.rectangle(img, (x, y), (x + w, y + h), outline, 2)
            color = hover_text or color
        cv2.putText(img, text, (x + 14, y + 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1, cv2.LINE_AA)
        rects[text] = (x, y, w, h)
    return img, rects


def record_menu(ws: Path, theme: str, hover: str) -> Path:
    """Right-click menu recorded the way it really happens: the clicked entry is hovered."""
    from uiv_studio.engine.recorder import Recorder
    from PySide6.QtCore import Qt

    hovered, rects = draw_menu("Rename", theme=theme, hover=hover)
    rec = Recording.create(ws, f"menu {theme} {hover}".replace("/", "-"), W, H, 1.0)
    r = Recorder(rec, Monitor(1, 0, 0, W, H, 1.0), Settings.defaults())
    done = []
    r.finished.connect(lambda p: done.append(p), Qt.DirectConnection)
    r._worker.start()
    x, y, w, h = rects["Rename"]
    r._on_event("click", {"x": x + 40, "y": y + h // 2, "mods": [], "frame": hovered})
    r._queue.put(("stop", False))
    r._worker.join(timeout=60)
    r.frames.grabber.close()
    return Path(done[0])


def live_menu(theme: str, hover: str, origin=(420, 260)):
    """Screen that highlights the entry under the (fake) cursor, like a real menu."""
    _, rects = draw_menu(None, origin, theme, hover)

    def screen(moves):
        under = None
        if moves:
            mx, my = moves[-1]
            under = next((t for t, (x, y, w, h) in rects.items() if x <= mx < x + w and y <= my < y + h), None)
        return draw_menu(under, origin, theme, hover)[0]
    return screen, rects


def check_click(name, res, rs, calls, rects):
    bx, by, bw, bh = rects["Rename"]
    clicks = [c for c in calls if c[0] == "click"]
    m = rs[0].match
    print(f"  {name:34} {res:7} score={m.score:.3f} tpl={m.template:.2f} vis={m.visual:.2f} "
          f"stage={m.stage} {m.method:6} click={clicks[0][1:3] if clicks else None}")
    assert res == Status.PASSED, (name, rs)
    assert bx <= clicks[0][1] < bx + bw and by <= clicks[0][2] < by + bh, (name, clicks, rects["Rename"])


def hover_cases(ws: Path):
    """Menu entries recorded while hovered, replayed in every hover style and theme."""
    for theme in THEMES:
        for hover in HOVERS:
            print(f"menu [{theme}] hover '{hover}':")
            rec_path = record_menu(ws, theme, hover)
            outline_only = HOVERS[hover][0] is None

            # Screen that ignores the cursor: only the vision must cope with the
            # missing highlight. An outline-only hover adds a stroke the plain entry
            # lacks; that case is covered by the live screen below.
            if not outline_only:
                screen, rects = draw_menu(None, theme=theme, hover=hover)
                check_click("no hover", *play(ws, rec_path, screen, W, H), rects)
                screen, rects = draw_menu("Copy path", theme=theme, hover=hover)
                check_click("another entry hovered", *play(ws, rec_path, screen, W, H), rects)

            # Real menu: the matcher moves the cursor, the entry lights up as recorded
            screen, rects = live_menu(theme, hover)
            check_click("live (reacts to the cursor)", *play(ws, rec_path, screen, W, H), rects)
            screen, rects = live_menu(theme, hover, origin=(560, 330))
            check_click("live, menu opened elsewhere", *play(ws, rec_path, screen, W, H), rects)

            # Entry gone -> must still FAIL (no false positive on a sibling entry)
            screen, rects = draw_menu(None, theme=theme, hover=hover)
            x, y, w, h = rects["Rename"]
            screen[y:y + h, x:x + w] = THEMES[theme][1]
            res, rs, _ = play(ws, rec_path, screen, W, H)
            print(f"  {'entry missing':34} {res:7} score={rs[0].match.score:.3f}")
            assert res == Status.FAILED, (theme, hover, rs)


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

    # 5) context menu: entry recorded while hovered (highlighted), replayed without hover
    hover_cases(ws)

    print(f"ALL OK in {time.time() - t0:.1f}s  (workspace {ws})")


if __name__ == "__main__":
    main()
