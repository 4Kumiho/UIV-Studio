# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""End-to-end test on a real GNOME Wayland compositor (headless mutter).

1. start the native Wayland target app
2. RECORD a flow: frames come from Mutter ScreenCast/PipeWire; input either from
   virtual evdev devices (uinput, the real recording path) or, if /dev/uinput is
   not available, injected into the recorder's event handlers
3. PLAY it back with the real Player (Mutter RemoteDesktop) on a *moved* layout
4. check the target app's log: every click and the typed text must arrive
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt

from uiv_studio import platform as backend
from uiv_studio.core.models import Action, Status
from uiv_studio.core.settings import Settings
from uiv_studio.core.storage import Recording, Run

LOG = Path("/tmp/target.log")


def start_target(offset=0):
    LOG.unlink(missing_ok=True)
    env = dict(os.environ, QT_QPA_PLATFORM="wayland")
    p = subprocess.Popen([sys.executable, "tests/wayland/target_app.py", str(offset)], env=env)
    for _ in range(100):
        if LOG.exists() and "ready" in LOG.read_text():
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("target app did not start")
    time.sleep(0.5)
    return p, json.load(open("/tmp/target_geometry.json"))


def center(r):
    return r[0] + r[2] // 2, r[1] + r[3] // 2


def record(ws: Path, monitor, geo) -> Path:
    from uiv_studio.engine.recorder import Recorder
    rec = Recording.create(ws, "wayland-demo", monitor.width, monitor.height, monitor.scale)
    s = Settings.defaults()
    r = Recorder(rec, monitor, s)
    done = []
    r.finished.connect(lambda p: done.append(p), Qt.DirectConnection)
    r._boot_sync = True
    from uiv_studio.vision.ocr import OCR
    OCR.warmup()
    r.frames.start()
    r._worker.start()
    r.capture.set_enabled(True)
    time.sleep(0.8)
    cap = r.capture
    uinput = _uinput_available()
    print("recording input path:", "uinput -> evdev (real)" if uinput else "direct handler injection")
    if uinput:
        from tests.wayland.vinput import VirtualInput
        with VirtualInput() as vi:
            r.capture.start(backend.make_input_source(r.capture, monitor))
            time.sleep(1.0)
            src = r.capture.source
            for name in ("Login", "Settings"):
                vi.move_to(src, *center(geo[name]))
                vi.click()
                time.sleep(0.9)
            vi.move_to(src, *center(geo["edit"]))
            vi.click()
            time.sleep(0.9)
            vi.type("hello wayland\n")
            time.sleep(1.0)
    else:
        for name in ("Login", "Settings"):
            x, y = center(geo[name])
            cap.button(x, y, "left", True); cap.button(x, y, "left", False)
            time.sleep(0.9)
        x, y = center(geo["edit"])
        cap.button(x, y, "left", True); cap.button(x, y, "left", False)
        time.sleep(0.9)
        for ch in "hello wayland":
            cap.key_press("space" if ch == " " else ch, ch); cap.key_release("space" if ch == " " else ch)
        cap.key_press("enter", None); cap.key_release("enter")
        time.sleep(0.5)
    r.stop()
    for _ in range(300):
        if done:
            break
        QCoreApplication.processEvents()
        time.sleep(0.1)
    assert done and done[0], "recorder did not finish"
    return Path(done[0])


def _uinput_available() -> bool:
    return os.access("/dev/uinput", os.W_OK)


def play(ws: Path, rec_path: Path, monitor):
    from uiv_studio.engine.player import Player
    s = Settings.defaults()
    s["execution"]["record_video"] = True
    s["execution"]["delay_between_steps_s"] = 0.3
    s["validation"]["seconds_between_stages"] = 0.5
    p = Player(str(rec_path), monitor, s, ws)
    out = []
    p.finished.connect(lambda path, res: out.append((path, res)), Qt.DirectConnection)
    p._main()
    run = Run(Path(out[0][0]))
    steps = run.steps()
    info = run.info()
    run.close()
    return out[0][1], steps, info, Path(out[0][0]).parent


def main():
    app = QCoreApplication(sys.argv)
    t0 = time.time()
    from uiv_studio.platform import gnome
    gnome.available(wait=30)          # slow CI machines: give mutter time to register its services
    backend.kind.cache_clear()
    print("backend:", backend.kind())
    if not backend.needs_input_group():
        for f in ("/tmp/mutter.log", "/tmp/pipewire.log", "/tmp/wireplumber.log"):
            print(f"----- {f}"); print(open(f).read()[-2500:])
        print(subprocess.run("pgrep -a 'pipewire|wireplumber|mutter'; dbus-send --session --print-reply "
                             "--dest=org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus.ListNames",
                             shell=True, capture_output=True, text=True).stdout[-2500:])
    assert backend.needs_input_group(), backend.kind()
    monitor = backend.list_monitors()[0]
    ws = Path(tempfile.mkdtemp(prefix="uiv_wl_"))

    target, geo = start_target(0)
    rec_path = record(ws, monitor, geo)
    target.terminate(); target.wait()
    rec = Recording(rec_path)
    steps = rec.steps()
    rec.close()
    print("recorded:", [(s.action, s.target.ocr_text if s.target else (s.text or s.key)) for s in steps])
    actions = [s.action for s in steps]
    assert actions[:3] == [Action.CLICK, Action.CLICK, Action.CLICK], actions
    assert Action.INPUT in actions, actions

    # play on a MOVED layout: the matcher must find the elements again
    target, geo2 = start_target(offset=45)
    result, rsteps, info, folder = play(ws, rec_path, monitor)
    time.sleep(0.8)
    target.terminate(); target.wait()
    log = LOG.read_text()
    print("run:", result, [(r.action, r.status, round(r.match.score, 3) if r.match else None) for r in rsteps])
    print("target log:", [l for l in log.splitlines() if l != "ready"][-6:])
    assert result == Status.PASSED, result
    assert "click Login" in log and "click Settings" in log, log
    assert "text hello wayland" in log and "enter" in log, log
    video = folder / "video.mp4"
    print("video:", video.exists() and video.stat().st_size > 10_000)
    print(f"WAYLAND E2E OK in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
