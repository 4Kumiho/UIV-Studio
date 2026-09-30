"""Screen recording to MP4 in a background thread, kept in sync with wall time."""

import logging
import threading
import time

import cv2

from uiv_studio.core.screens import Monitor, ScreenGrabber

log = logging.getLogger(__name__)

MAX_WIDTH = 1600


class VideoRecorder:
    def __init__(self, path: str, monitor: Monitor, fps: int = 10):
        self.path = path
        self.monitor = monitor
        self.fps = fps
        self._stop = threading.Event()
        self._thread = None
        self.t0 = None
        self.ok = False

    def start(self):
        self.t0 = time.monotonic()
        self._thread = threading.Thread(target=self._loop, name="video", daemon=True)
        self._thread.start()

    def elapsed(self) -> float:
        return 0.0 if self.t0 is None else time.monotonic() - self.t0

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        grabber = ScreenGrabber(self.monitor)
        w, h = self.monitor.width, self.monitor.height
        scale = min(1.0, MAX_WIDTH / w)
        size = (int(w * scale) // 2 * 2, int(h * scale) // 2 * 2)
        writer = cv2.VideoWriter(self.path, cv2.VideoWriter_fourcc(*"mp4v"), self.fps, size)
        if not writer.isOpened():
            log.warning("Video writer unavailable; execution continues without video")
            grabber.close()
            return
        self.ok = True
        written = 0
        last = None
        try:
            while not self._stop.is_set():
                frame = cv2.resize(grabber.grab(), size, interpolation=cv2.INTER_AREA)
                # Write as many frames as wall time requires -> timestamps stay exact
                due = int(self.elapsed() * self.fps) + 1
                while written < due:
                    writer.write(frame if last is None or written == due - 1 else last)
                    written += 1
                last = frame
                sleep = (written / self.fps) - self.elapsed()
                if sleep > 0:
                    self._stop.wait(sleep)
        except Exception:
            log.exception("Video recording error")
        finally:
            writer.release()
            grabber.close()
