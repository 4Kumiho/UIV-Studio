# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.
"""Smoke test of the GNOME Wayland backend inside the headless test session."""
import time
import cv2
from uiv_studio import platform as backend

print("backend:", backend.kind())
mons = backend.list_monitors()
print("monitors:", [(m.index, m.width, m.height, m.scale, getattr(m, "connector", "")) for m in mons])
g = backend.make_grabber(mons[0])
t = time.time(); f = g.grab(); print("frame:", f.shape, f.dtype, f"{(time.time()-t)*1000:.0f} ms first")
t = time.time(); f = g.grab(); print(f"grab: {(time.time()-t)*1000:.1f} ms")
cv2.imwrite("/src/build/wayland_probe.png", f)
from uiv_studio.core.settings import Settings
act = backend.make_actuator(Settings.defaults()["execution"], mons[0])
act.move(400, 300); act.click(400, 300); act.type_text("ciao @ è"); act.key_combo("ctrl+s")
print("input injection: OK")
