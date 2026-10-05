# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.
"""Start the real UIV Studio UI inside the Wayland session and screenshot it through PipeWire."""
import faulthandler, os, subprocess, sys, time

# Nothing here should take more than a few seconds; say where we are stuck instead
# of letting the CI job sit on a dead step until its own timeout.
faulthandler.dump_traceback_later(120, exit=True)

mode = sys.argv[1]            # "wayland" | "xcb"
out = sys.argv[2]
# Built before UIV_BACKEND is touched: the app under test keeps the session's own backend.
env = dict(os.environ, QT_QPA_PLATFORM=mode)
env.pop("UIV_BACKEND", None)
if mode == "wayland":
    env.pop("DISPLAY", None)

# Our own screenshot goes through Mutter. The portal would ask the desktop to
# confirm screen sharing and then wait CONSENT_TIMEOUT for an answer that nobody
# can give in a headless session.
os.environ["UIV_BACKEND"] = "gnome-wayland"
import cv2
from uiv_studio import platform as backend

app = subprocess.Popen([sys.executable, "-m", "uiv_studio"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
time.sleep(9)
alive = app.poll() is None
g = backend.make_grabber(backend.list_monitors()[0])
cv2.imwrite(out, g.grab())
app.terminate()
print(mode, "app alive:", alive)
if not alive:
    print(app.stdout.read()[-1500:])
    sys.exit(1)
