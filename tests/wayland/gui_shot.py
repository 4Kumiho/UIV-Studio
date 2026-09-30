# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.
"""Start the real UIV Studio UI inside the Wayland session and screenshot it through PipeWire."""
import os, subprocess, sys, time
import cv2
from uiv_studio import platform as backend

mode = sys.argv[1]            # "wayland" | "xcb"
out = sys.argv[2]
env = dict(os.environ, QT_QPA_PLATFORM=mode)
if mode == "wayland":
    env.pop("DISPLAY", None)
app = subprocess.Popen([sys.executable, "-m", "uiv_studio"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
time.sleep(9)
alive = app.poll() is None
g = backend.make_grabber(backend.list_monitors()[0])
cv2.imwrite(out, g.grab())
app.terminate()
print(mode, "app alive:", alive)
if not alive:
    print(app.stdout.read()[-1500:])
