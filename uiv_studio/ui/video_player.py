"""OpenCV-backed video player (codec independent) with a step-marker timeline."""

import cv2
from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from uiv_studio.ui import icons
from uiv_studio.ui.theme import C


class _Screen(QWidget):
    def __init__(self):
        super().__init__()
        self.pm = QPixmap()
        self.setMinimumHeight(200)

    def set_frame(self, pm: QPixmap):
        self.pm = pm
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#000000"))
        if self.pm.isNull():
            return
        s = self.pm.size().scaled(self.size(), Qt.KeepAspectRatio)
        x, y = (self.width() - s.width()) // 2, (self.height() - s.height()) // 2
        p.drawPixmap(x, y, s.width(), s.height(), self.pm)


class Timeline(QWidget):
    seek = Signal(float)
    marker_clicked = Signal(int)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(30)
        self.setCursor(Qt.PointingHandCursor)
        self.duration = 1.0
        self.pos_s = 0.0
        self.markers: list[tuple[float, str, int]] = []   # (time, color, idx)
        self.selected = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width() - 16
        y = self.height() / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C["surface3"]))
        p.drawRoundedRect(QRectF(8, y - 3, w, 6), 3, 3)
        frac = min(1.0, self.pos_s / max(self.duration, 1e-6))
        p.setBrush(QColor(C["accent"]))
        p.drawRoundedRect(QRectF(8, y - 3, w * frac, 6), 3, 3)
        for t, color, idx in self.markers:
            x = 8 + w * min(1.0, t / max(self.duration, 1e-6))
            big = idx == self.selected
            p.setPen(QPen(QColor(C["bg"]), 2))
            p.setBrush(QColor(color))
            r = 6 if big else 4
            p.drawEllipse(QRectF(x - r, y - r, 2 * r, 2 * r))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(8 + w * frac - 7, y - 7, 14, 14))

    def mousePressEvent(self, e):
        w = self.width() - 16
        x = e.position().x()
        for t, _, idx in self.markers:
            mx = 8 + w * t / max(self.duration, 1e-6)
            if abs(mx - x) <= 6:
                self.marker_clicked.emit(idx)
                return
        self.seek.emit(max(0.0, min(1.0, (x - 8) / w)) * self.duration)

    def mouseMoveEvent(self, e):
        w = self.width() - 16
        self.seek.emit(max(0.0, min(1.0, (e.position().x() - 8) / w)) * self.duration)


class VideoPlayer(QWidget):
    marker_clicked = Signal(int)

    def __init__(self):
        super().__init__()
        self.cap = None
        self.fps = 10.0
        self.frames = 0
        self.playing = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.screen = _Screen()
        lay.addWidget(self.screen, 1)
        ctl = QHBoxLayout()
        ctl.setSpacing(8)
        self.play_btn = QToolButton()
        self.play_btn.setIconSize(QSize(18, 18))
        self.play_btn.clicked.connect(self.toggle)
        self.timeline = Timeline()
        self.timeline.seek.connect(self.seek)
        self.timeline.marker_clicked.connect(self.marker_clicked)
        self.time = QLabel("0:00 / 0:00")
        self.time.setStyleSheet(f"color: {C['text2']}; font-family: monospace;")
        ctl.addWidget(self.play_btn)
        ctl.addWidget(self.timeline, 1)
        ctl.addWidget(self.time)
        lay.addLayout(ctl)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._next)
        self._icon()

    def load(self, path: str | None) -> bool:
        self.stop()
        if self.cap:
            self.cap.release()
            self.cap = None
        if not path:
            return False
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return False
        self.cap = cap
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 10.0
        self.frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        self.timeline.duration = self.frames / self.fps
        self.timer.setInterval(int(1000 / self.fps))
        self.seek(0.0)
        return True

    def set_markers(self, markers):
        self.timeline.markers = markers
        self.timeline.update()

    def select_marker(self, idx):
        self.timeline.selected = idx
        self.timeline.update()

    def _icon(self):
        self.play_btn.setIcon(icons.icon("pause" if self.playing else "play", C["text"], 18))

    def toggle(self):
        if not self.cap:
            return
        self.playing = not self.playing
        (self.timer.start if self.playing else self.timer.stop)()
        self._icon()

    def stop(self):
        self.playing = False
        self.timer.stop()
        self._icon()

    def seek(self, seconds: float):
        if not self.cap:
            return
        frame = int(max(0, min(self.frames - 1, seconds * self.fps)))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
        self._next(advance=False)

    def _next(self, advance=True):
        if not self.cap:
            return
        ok, img = self.cap.read()
        if not ok:
            self.stop()
            return
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        self.screen.set_frame(QPixmap.fromImage(QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()))
        pos = self.cap.get(cv2.CAP_PROP_POS_FRAMES) / self.fps
        self.timeline.pos_s = pos
        self.timeline.update()
        tot = self.timeline.duration
        self.time.setText(f"{int(pos) // 60}:{int(pos) % 60:02d} / {int(tot) // 60}:{int(tot) % 60:02d}")

    def release(self):
        self.stop()
        if self.cap:
            self.cap.release()
            self.cap = None
