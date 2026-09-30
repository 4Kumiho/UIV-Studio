# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Always-on-top session overlays: the HUD pill and the pause menu."""

import sys

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, Qt,
                            QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QPushButton, QVBoxLayout, QWidget

from uiv_studio.core.screens import Monitor
from uiv_studio.ui import icons
from uiv_studio.ui.i18n import tr
from uiv_studio.ui.theme import C

STATE_COLORS = {
    "loading": C["warning"], "ready": C["danger"], "paused": C["text3"], "finishing": C["info"],
    "running": C["success"], "searching": C["accent2"],
}


# ------------------------------------------------------------------ geometry


def qscreen_for(monitor: Monitor):
    screens = QGuiApplication.screens()
    for s in screens:
        g = s.geometry()
        if abs(g.x() - monitor.left) <= 2 and abs(g.y() - monitor.top) <= 2:
            return s
    for s in screens:
        g, d = s.geometry(), s.devicePixelRatio()
        if abs(g.x() * d - monitor.left) <= 2 and abs(g.y() * d - monitor.top) <= 2:
            return s
    return screens[min(max(monitor.index - 1, 0), len(screens) - 1)]


def physical_rect(widget: QWidget, monitor: Monitor) -> tuple:
    """Widget frame in global physical pixels (pynput / mss space)."""
    s = qscreen_for(monitor)
    g, d = s.geometry(), s.devicePixelRatio()
    fg = widget.frameGeometry()
    return (round(monitor.left + (fg.x() - g.x()) * d), round(monitor.top + (fg.y() - g.y()) * d),
            round(fg.width() * d), round(fg.height() * d))


def exclude_from_capture(widget: QWidget):
    """Windows 10 2004+: keep our overlays out of screenshots and the run video."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.user32.SetWindowDisplayAffinity(int(widget.winId()), 0x11)  # WDA_EXCLUDEFROMCAPTURE
    except Exception:
        pass


# ------------------------------------------------------------------ HUD


class Hud(QWidget):
    W, H = 300, 64

    def __init__(self, monitor: Monitor, corner: str, menu_key: str):
        flags = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
                 | Qt.WindowTransparentForInput)
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.monitor, self.corner = monitor, corner
        self.setFixedSize(self.W + 24, self.H + 24)
        self.state = "loading"
        self.title = tr("hud.loading")
        self.counter = ""
        self.sub = tr("hud.menu_hint", key=menu_key.upper())
        self._pulse = 0.0
        self._pa = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=1400, loopCount=-1)
        self._pa.valueChanged.connect(self._tick)
        self._pa.start()
        self._place()

    def _tick(self, v):
        self._pulse = float(v)
        self.update()

    def _place(self):
        g = qscreen_for(self.monitor).availableGeometry()
        m = 12
        x = g.left() + m if "left" in self.corner else g.right() - self.width() - m
        y = g.top() + m if "top" in self.corner else g.bottom() - self.height() - m
        self._home = QPoint(x, y)
        self.move(self._home)

    def appear(self):
        self.show()
        exclude_from_capture(self)
        dy = 30 if "bottom" in self.corner else -30
        a = QPropertyAnimation(self, b"pos", self, duration=450, easingCurve=QEasingCurve.OutBack)
        a.setStartValue(self._home + QPoint(0, dy))
        a.setEndValue(self._home)
        a.start()
        self._appear = a

    def set_state(self, state: str, title: str | None = None):
        self.state = state
        if title is not None:
            self.title = title
        self.update()

    def set_counter(self, text: str):
        self.counter = text
        self.update()

    def set_sub(self, text: str):
        self.sub = text
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(12, 12, self.W, self.H)
        # shadow
        for i in range(8, 0, -1):
            c = QColor(0, 0, 0, 10)
            p.setPen(Qt.NoPen); p.setBrush(c)
            p.drawRoundedRect(r.adjusted(-i, -i + 4, i, i + 4), 22 + i, 22 + i)
        p.setBrush(QColor(16, 19, 26, 240))
        p.setPen(QPen(QColor(C["border2"]), 1))
        p.drawRoundedRect(r, 20, 20)
        color = QColor(STATE_COLORS.get(self.state, C["accent"]))
        center = QPointF(r.left() + 30, r.center().y())
        if self.state in ("ready", "running", "searching", "loading"):
            halo = QColor(color); halo.setAlphaF(0.45 * (1 - self._pulse))
            p.setPen(Qt.NoPen); p.setBrush(halo)
            rad = 7 + 11 * self._pulse
            p.drawEllipse(center, rad, rad)
        p.setPen(Qt.NoPen); p.setBrush(color)
        p.drawEllipse(center, 7, 7)
        f = p.font(); f.setPointSizeF(10.5); f.setBold(True); p.setFont(f)
        p.setPen(QColor(C["text"]))
        p.drawText(QRectF(r.left() + 52, r.top() + 11, r.width() - 130, 22), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        p.setPen(QColor(C["accent2"]))
        p.drawText(QRectF(r.right() - 110, r.top() + 11, 96, 22), Qt.AlignRight | Qt.AlignVCenter, self.counter)
        f.setBold(False); f.setPointSizeF(8.5); p.setFont(f)
        p.setPen(QColor(C["text3"]))
        sub = p.fontMetrics().elidedText(self.sub, Qt.ElideRight, int(r.width() - 66))
        p.drawText(QRectF(r.left() + 52, r.top() + 33, r.width() - 66, 20), Qt.AlignLeft | Qt.AlignVCenter, sub)


# ------------------------------------------------------------------ Menu


class SessionMenu(QWidget):
    chosen = Signal(str)

    def __init__(self, monitor: Monitor, title: str, options: list[tuple[str, str, str, str]]):
        """options: (key, label, icon, style) with style in {'', 'Primary', 'Danger'}."""
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.monitor = monitor
        panel = QWidget(self)
        panel.setObjectName("MenuPanel")
        panel.setStyleSheet(f"#MenuPanel {{ background: {C['bg2']}; border: 1px solid {C['border2']}; border-radius: 18px; }}")
        sh = QGraphicsDropShadowEffect(panel, blurRadius=60, offset=QPointF(0, 16), color=QColor(0, 0, 0, 170))
        panel.setGraphicsEffect(sh)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(22, 20, 22, 22)
        lay.setSpacing(10)
        t = QLabel(title)
        t.setStyleSheet("font-size: 13pt; font-weight: 700;")
        lay.addWidget(t)
        lay.addSpacing(4)
        for key, text, icon_name, style in options:
            b = QPushButton(text)
            if style:
                b.setObjectName(style)
            color = "#FFFFFF" if style == "Primary" else C["danger"] if style == "Danger" else C["text"]
            b.setIcon(icons.icon(icon_name, color, 18))
            b.setMinimumHeight(42)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("text-align: left; padding-left: 14px;")
            b.clicked.connect(lambda _=False, k=key: self._choose(k))
            lay.addWidget(b)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 30, 30, 30)
        outer.addWidget(panel)
        self.setFixedWidth(340)
        self.adjustSize()

    def popup(self):
        g = qscreen_for(self.monitor).availableGeometry()
        end = QPoint(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)
        self.setWindowOpacity(0.0)
        self.move(end + QPoint(0, 16))
        self.show()
        self.raise_()
        self.activateWindow()
        a1 = QPropertyAnimation(self, b"windowOpacity", self, duration=200)
        a1.setStartValue(0.0); a1.setEndValue(1.0); a1.start()
        a2 = QPropertyAnimation(self, b"pos", self, duration=280, easingCurve=QEasingCurve.OutCubic)
        a2.setStartValue(end + QPoint(0, 16)); a2.setEndValue(end); a2.start()
        self._anims = (a1, a2)

    def _choose(self, key: str):
        self.close()
        self.chosen.emit(key)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._choose("resume")
        else:
            super().keyPressEvent(e)
