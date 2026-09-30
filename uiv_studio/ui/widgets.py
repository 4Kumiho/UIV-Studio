# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Reusable animated widgets."""

from PySide6.QtCore import (QEasingCurve, QParallelAnimationGroup, QPoint, QPointF, QPropertyAnimation,
                            QRect, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal, Property)
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
                               QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSlider, QStackedWidget,
                               QVBoxLayout, QWidget)

from uiv_studio.core.keys import MODIFIERS, display_combo, format_combo, qt_key_name
from uiv_studio.ui import icons
from uiv_studio.ui.i18n import tr
from uiv_studio.ui.theme import C

EASE = QEasingCurve.OutCubic


def lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t), round(a.alpha() + (b.alpha() - a.alpha()) * t))


def label(text: str = "", obj: str | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    lb.setWordWrap(wrap)
    return lb


def button(text: str, icon_name: str | None = None, obj: str | None = None, icon_color: str | None = None) -> QPushButton:
    b = QPushButton(text)
    if obj:
        b.setObjectName(obj)
    if icon_name:
        color = icon_color or ("#FFFFFF" if obj == "Primary" else C["danger"] if obj == "Danger" else C["text"])
        b.setIcon(icons.icon(icon_name, color, 18))
        b.setIconSize(QSize(16, 16))
    b.setCursor(Qt.PointingHandCursor)
    return b


def hline() -> QFrame:
    f = QFrame()
    f.setObjectName("Divider")
    return f


def fade_in(widget: QWidget, duration: int = 280, delay: int = 0, dy: int = 10):
    """Fade + slide a widget in (used for staggered list/card entrance)."""
    eff = QGraphicsOpacityEffect(widget)
    eff.setOpacity(0.0)
    widget.setGraphicsEffect(eff)

    def run():
        anim = QPropertyAnimation(eff, b"opacity", widget)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(EASE)
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    QTimer.singleShot(delay, run)


# ====================================================================== stack


class AnimatedStack(QStackedWidget):
    """Page container with a slide + fade transition."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._group = None

    def slide_to(self, index: int):
        if index == self.currentIndex() or index < 0:
            return
        forward = index > self.currentIndex()
        if self._group:
            self._group.stop()
        self.setCurrentIndex(index)
        w = self.widget(index)
        eff = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(eff)
        end = w.pos()
        start = end + QPoint(0, 18 if forward else -18)
        g = QParallelAnimationGroup(self)
        a1 = QPropertyAnimation(eff, b"opacity")
        a1.setDuration(260)
        a1.setStartValue(0.0)
        a1.setEndValue(1.0)
        a1.setEasingCurve(EASE)
        a2 = QPropertyAnimation(w, b"pos")
        a2.setDuration(320)
        a2.setStartValue(start)
        a2.setEndValue(end)
        a2.setEasingCurve(QEasingCurve.OutQuart)
        g.addAnimation(a1)
        g.addAnimation(a2)
        g.finished.connect(lambda: w.setGraphicsEffect(None))
        g.start()
        self._group = g

    def slide_to_widget(self, w: QWidget):
        self.slide_to(self.indexOf(w))


# ====================================================================== sidebar


class NavButton(QAbstractButton):
    def __init__(self, icon_name: str, text: str, parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(42)
        self._hover = 0.0
        self._anim = QVariantAnimation(self, duration=160, easingCurve=EASE)
        self._anim.valueChanged.connect(self._set_hover)

    def _set_hover(self, v):
        self._hover = float(v)
        self.update()

    def enterEvent(self, e):
        self._anim.stop(); self._anim.setStartValue(self._hover); self._anim.setEndValue(1.0); self._anim.start()

    def leaveEvent(self, e):
        self._anim.stop(); self._anim.setStartValue(self._hover); self._anim.setEndValue(0.0); self._anim.start()

    def sizeHint(self):
        return QSize(200, 42)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(8, 2, -8, -2)
        if self._hover > 0 and not self.isChecked():
            c = QColor(C["surface2"]); c.setAlphaF(self._hover)
            p.setPen(Qt.NoPen); p.setBrush(c); p.drawRoundedRect(r, 9, 9)
        color = C["text"] if self.isChecked() else lerp_color(QColor(C["text2"]), QColor(C["text"]), self._hover).name()
        p.drawPixmap(r.left() + 12, r.center().y() - 9, icons.pixmap(self.icon_name, C["accent2"] if self.isChecked() else color, 18))
        f = self.font(); f.setWeight(QFont.DemiBold if self.isChecked() else QFont.Medium); p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(r.adjusted(42, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, self.text())


class Sidebar(QFrame):
    changed = Signal(int)

    def __init__(self, items: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(224)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 18, 0, 16)
        lay.setSpacing(2)

        brand = QWidget()
        bl = QHBoxLayout(brand)
        bl.setContentsMargins(20, 0, 16, 18)
        logo = Logo(30)
        bl.addWidget(logo)
        name = QLabel("UIV <span style='color:%s'>Studio</span>" % C["accent2"])
        name.setStyleSheet("font-size: 13.5pt; font-weight: 700;")
        bl.addWidget(name)
        bl.addStretch()
        lay.addWidget(brand)

        self.indicator = QFrame(self)
        self.indicator.setStyleSheet(f"background: {C['surface2']}; border-radius: 9px; border: 1px solid {C['border']};")
        self.bar = QFrame(self)
        self.bar.setStyleSheet(f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {C['accent']}, stop:1 {C['cyan']}); border-radius: 2px;")
        self.buttons: list[NavButton] = []
        for i, (ic, text) in enumerate(items):
            b = NavButton(ic, text)
            b.clicked.connect(lambda _=False, i=i: self.select(i))
            lay.addWidget(b)
            self.buttons.append(b)
        lay.addStretch()
        self.footer = QVBoxLayout()
        self.footer.setContentsMargins(16, 0, 16, 0)
        lay.addLayout(self.footer)
        self.indicator.lower()
        self._anim = QPropertyAnimation(self.indicator, b"geometry", self, duration=300, easingCurve=QEasingCurve.OutQuart)
        self._anim_bar = QPropertyAnimation(self.bar, b"geometry", self, duration=300, easingCurve=QEasingCurve.OutQuart)
        self.current = -1

    def select(self, i: int, animate: bool = True, emit: bool = True):
        for j, b in enumerate(self.buttons):
            b.setChecked(i == j)
        self.current = i
        self._move_indicator(animate)
        if emit:
            self.changed.emit(i)

    def _target_rects(self):
        b = self.buttons[self.current]
        g = b.geometry().adjusted(8, 2, -8, -2)
        return g, QRect(g.left() + 1, g.top() + 10, 3, g.height() - 20)

    def _move_indicator(self, animate: bool):
        if self.current < 0:
            return
        g, bar = self._target_rects()
        if not animate or self.indicator.geometry().isEmpty():
            self.indicator.setGeometry(g)
            self.bar.setGeometry(bar)
            return
        for a, target, w in ((self._anim, g, self.indicator), (self._anim_bar, bar, self.bar)):
            a.stop(); a.setStartValue(w.geometry()); a.setEndValue(target); a.start()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, lambda: self._move_indicator(False))


class Logo(QWidget):
    """Brand mark (the application icon)."""

    def __init__(self, size=30, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        from PySide6.QtGui import QPixmap
        from uiv_studio.core.paths import resource_dir
        self.pm = QPixmap(str(resource_dir() / "icon.png"))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawPixmap(self.rect(), self.pm)


# ====================================================================== cards


class HoverCard(QFrame):
    """Rounded card with animated hover highlight and shadow; optional click."""

    clicked = Signal()

    def __init__(self, clickable: bool = False, accent: str | None = None, parent=None):
        super().__init__(parent)
        self.clickable = clickable
        self.accent = QColor(accent or C["accent"])
        self._h = 0.0
        self.setAttribute(Qt.WA_StyledBackground, False)
        if clickable:
            self.setCursor(Qt.PointingHandCursor)
        self._shadow = QGraphicsDropShadowEffect(self, blurRadius=0, offset=QPointF(0, 6), color=QColor(0, 0, 0, 0))
        self.setGraphicsEffect(self._shadow)
        self._anim = QVariantAnimation(self, duration=200, easingCurve=EASE)
        self._anim.valueChanged.connect(self._set)

    def _set(self, v):
        self._h = float(v)
        eff = self.graphicsEffect()
        if not isinstance(eff, QGraphicsDropShadowEffect):
            # a transient effect (e.g. fade_in) replaced and deleted our shadow: recreate it
            if eff is not None:
                self.update()
                return
            self._shadow = QGraphicsDropShadowEffect(self, blurRadius=0, offset=QPointF(0, 6), color=QColor(0, 0, 0, 0))
            self.setGraphicsEffect(self._shadow)
        self._shadow.setBlurRadius(28 * self._h)
        c = QColor(self.accent); c.setAlpha(int(70 * self._h))
        self._shadow.setColor(c)
        self.update()

    def _go(self, end):
        self._anim.stop(); self._anim.setStartValue(self._h); self._anim.setEndValue(end); self._anim.start()

    def enterEvent(self, e):
        self._go(1.0)

    def leaveEvent(self, e):
        self._go(0.0)

    def mouseReleaseEvent(self, e):
        if self.clickable and e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        bg = lerp_color(QColor(C["surface"]), QColor(C["surface2"]), self._h * 0.8)
        border = lerp_color(QColor(C["border"]), self.accent, self._h * (0.7 if self.clickable else 0.25))
        p.setPen(QPen(border, 1))
        p.setBrush(bg)
        p.drawRoundedRect(r, 14, 14)


class ActionTile(HoverCard):
    """Big call-to-action card for the home page."""

    def __init__(self, icon_name: str, title: str, subtitle: str, colors: tuple[str, str], parent=None):
        super().__init__(clickable=True, accent=colors[0], parent=parent)
        self.colors = colors
        self.setMinimumHeight(150)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 22, 22, 20)
        lay.setSpacing(6)
        badge = IconBadge(icon_name, colors, 46)
        lay.addWidget(badge)
        lay.addStretch()
        t = label(title, "H3")
        t.setStyleSheet("font-size: 12.5pt; font-weight: 650; background: transparent;")
        s = label(subtitle, "Muted", wrap=True)
        s.setStyleSheet("background: transparent;")
        lay.addWidget(t)
        lay.addWidget(s)

    def paintEvent(self, e):
        super().paintEvent(e)
        # soft colored glow in the corner, stronger on hover
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        from PySide6.QtGui import QRadialGradient
        r = QRectF(self.rect())
        g = QRadialGradient(r.topRight() + QPointF(-30, 30), r.width() * 0.7)
        c = QColor(self.colors[0]); c.setAlpha(int(26 + 40 * self._h))
        g.setColorAt(0, c)
        g.setColorAt(1, QColor(0, 0, 0, 0))
        path = QPainterPath(); path.addRoundedRect(r.adjusted(1, 1, -1, -1), 14, 14)
        p.setClipPath(path)
        p.fillRect(r, g)


class IconBadge(QWidget):
    def __init__(self, icon_name: str, colors: tuple[str, str], size: int = 40, parent=None):
        super().__init__(parent)
        self.icon_name, self.colors = icon_name, colors
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor(self.colors[0]))
        g.setColorAt(1, QColor(self.colors[1]))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(r, r.width() * 0.3, r.width() * 0.3)
        s = int(r.width() * 0.5)
        p.drawPixmap(int((r.width() - s) / 2), int((r.height() - s) / 2), icons.pixmap(self.icon_name, "#FFFFFF", s, 2.0))


class StatCard(HoverCard):
    def __init__(self, icon_name: str, title: str, color: str, parent=None):
        super().__init__(accent=color, parent=parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(14)
        lay.addWidget(IconBadge(icon_name, (color, C["surface3"]), 42))
        col = QVBoxLayout()
        col.setSpacing(0)
        self.value = QLabel("0")
        self.value.setStyleSheet("font-size: 19pt; font-weight: 700; background: transparent;")
        t = label(title, "Muted")
        t.setStyleSheet("background: transparent;")
        col.addWidget(self.value)
        col.addWidget(t)
        lay.addLayout(col)
        lay.addStretch()
        self._anim = QVariantAnimation(self, duration=900, easingCurve=QEasingCurve.OutExpo)
        self._suffix = ""
        self._target = 0
        self._anim.valueChanged.connect(self._show)
        self._anim.finished.connect(lambda: self._show(self._target))

    def _show(self, v):
        if v is None:
            return
        self.value.setText(f"{int(v)}{self._suffix}")
        # The card's graphics effect caches its rendering: repaint the whole card, not just the label
        self.update()

    def set_value(self, n: int, suffix: str = ""):
        self._suffix = suffix
        self._target = int(n)
        self._show(0)
        self._anim.stop()
        self._anim.setStartValue(0)
        self._anim.setEndValue(int(n))
        self._anim.start()


# ====================================================================== inputs


class Toggle(QAbstractButton):
    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(44, 24)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self, duration=180, easingCurve=EASE)
        self._anim.valueChanged.connect(self._set)
        self.toggled.connect(self._animate)

    def _set(self, v):
        self._pos = float(v)
        self.update()

    def _animate(self, on):
        self._anim.stop(); self._anim.setStartValue(self._pos); self._anim.setEndValue(1.0 if on else 0.0); self._anim.start()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        track = lerp_color(QColor(C["surface3"]), QColor(C["accent"]), self._pos)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * self._pos
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))


class SliderRow(QWidget):
    """Label + slider + live value. Works on floats via a fixed decimal scale."""

    valueChanged = Signal(float)

    def __init__(self, title: str, lo: float, hi: float, value: float, decimals: int = 2,
                 suffix: str = "", percent: bool = False, tip: str = "", parent=None):
        super().__init__(parent)
        self.k = 10 ** decimals
        self.decimals, self.suffix, self.percent = decimals, suffix, percent
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(14)
        t = label(title)
        t.setMinimumWidth(220)
        if tip:
            t.setToolTip(tip)
            self.setToolTip(tip)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(round(lo * self.k), round(hi * self.k))
        self.slider.setCursor(Qt.PointingHandCursor)
        self.val = QLabel()
        self.val.setFixedWidth(64)
        self.val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.val.setStyleSheet(f"font-weight: 700; color: {C['accent2']};")
        lay.addWidget(t)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.val)
        self.slider.valueChanged.connect(self._changed)
        self.set_value(value)

    def _fmt(self, v: float) -> str:
        if self.percent:
            return f"{v * 100:.0f}%"
        return f"{v:.{self.decimals}f}{self.suffix}" if self.decimals else f"{int(v)}{self.suffix}"

    def _changed(self, raw):
        v = raw / self.k
        self.val.setText(self._fmt(v))
        self.valueChanged.emit(v)

    def set_value(self, v: float):
        self.slider.setValue(round(v * self.k))
        self.val.setText(self._fmt(self.value()))

    def value(self) -> float:
        v = self.slider.value() / self.k
        return v if self.decimals else float(int(v))


class HotkeyEdit(QPushButton):
    """Click, then press a combination. Esc cancels, Backspace clears."""

    changed = Signal(str)

    def __init__(self, combo: str = "", parent=None):
        super().__init__(parent)
        self.combo = combo
        self._recording = False
        self._seen: set[str] = set()
        self._down: set[str] = set()
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(220)
        self.setFocusPolicy(Qt.StrongFocus)
        self.clicked.connect(self._start)
        self._refresh()

    def _refresh(self):
        if self._recording:
            text = display_combo(format_combo(self._seen)) if self._seen else tr("set.hk.press")
            self.setStyleSheet(f"QPushButton {{ border: 1px solid {C['accent']}; background: {C['accent_dim']}; "
                               f"color: {C['text']}; font-family: monospace; }}")
        else:
            text = display_combo(self.combo) if self.combo else "—"
            self.setStyleSheet("QPushButton { font-family: monospace; }")
        self.setText(text)

    def _start(self):
        self._recording = True
        self._seen.clear()
        self._down.clear()
        self.grabKeyboard()
        self._refresh()

    def _finish(self, commit: bool):
        self.releaseKeyboard()
        self._recording = False
        if commit and self._seen:
            self.combo = format_combo(self._seen)
            self.changed.emit(self.combo)
        self._refresh()

    def set_combo(self, combo: str):
        self.combo = combo
        self._refresh()

    def keyPressEvent(self, e):
        if not self._recording:
            return super().keyPressEvent(e)
        if e.isAutoRepeat():
            return
        name = qt_key_name(e.key())
        if name == "esc" and not self._down:
            return self._finish(False)
        if name == "backspace" and not self._down:
            self.combo = ""
            self.changed.emit("")
            return self._finish(False)
        if name:
            self._down.add(name)
            self._seen.add(name)
            self._refresh()

    def keyReleaseEvent(self, e):
        if not self._recording:
            return super().keyReleaseEvent(e)
        if e.isAutoRepeat():
            return
        name = qt_key_name(e.key())
        self._down.discard(name)
        # The combination is complete once every key has been released
        if not self._down:
            self._finish(True)

    def focusOutEvent(self, e):
        if self._recording:
            self._finish(False)
        super().focusOutEvent(e)


# ====================================================================== feedback


class Spinner(QWidget):
    def __init__(self, size=22, color=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.color = QColor(color or C["accent2"])
        self._angle = 0
        self._timer = QTimer(self, interval=16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        self._angle = (self._angle + 7) % 360
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(2.5, 2.5, -2.5, -2.5)
        track = QColor(self.color); track.setAlpha(45)
        p.setPen(QPen(track, 3))
        p.drawEllipse(r)
        p.setPen(QPen(self.color, 3, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, -self._angle * 16, 100 * 16)


class Badge(QLabel):
    def __init__(self, text: str, color: str, parent=None):
        super().__init__(text, parent)
        self.set(text, color)

    def set(self, text: str, color: str):
        c = QColor(color)
        self.setText(text)
        self.setStyleSheet(
            f"background: rgba({c.red()},{c.green()},{c.blue()},0.14); color: {color}; border: 1px solid "
            f"rgba({c.red()},{c.green()},{c.blue()},0.35); border-radius: 9px; padding: 2px 9px; "
            f"font-size: 8.5pt; font-weight: 700;")
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)


class ScoreBar(QWidget):
    """Horizontal score bar with a threshold marker; value animates in."""

    def __init__(self, title: str, value: float | None, threshold: float | None = None, parent=None):
        super().__init__(parent)
        self.title = title
        self.target = value
        self.threshold = threshold
        self._v = 0.0
        self.setFixedHeight(34)
        self._anim = QVariantAnimation(self, duration=700, easingCurve=QEasingCurve.OutExpo)
        self._anim.valueChanged.connect(self._set)
        if value is not None:
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(float(value))
            QTimer.singleShot(60, self._anim.start)

    def _set(self, v):
        self._v = float(v)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        p.setPen(QColor(C["text2"]))
        p.drawText(QRect(0, 0, w, 16), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        txt = "—" if self.target is None else f"{self._v * 100:.1f}%"
        p.setPen(QColor(C["text"]))
        f = p.font(); f.setBold(True); p.setFont(f)
        p.drawText(QRect(0, 0, w, 16), Qt.AlignRight | Qt.AlignVCenter, txt)
        track = QRectF(0, 22, w, 7)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C["surface3"]))
        p.drawRoundedRect(track, 3.5, 3.5)
        if self.target is not None:
            ok = self.threshold is None or self.target >= self.threshold
            g = QLinearGradient(track.topLeft(), track.topRight())
            g.setColorAt(0, QColor(C["accent"] if ok else C["danger"]))
            g.setColorAt(1, QColor(C["cyan"] if ok else C["warning"]))
            p.setBrush(g)
            p.drawRoundedRect(QRectF(0, 22, max(7.0, w * self._v), 7), 3.5, 3.5)
        if self.threshold is not None:
            x = w * self.threshold
            p.setPen(QPen(QColor(C["text"]), 2))
            p.drawLine(QPointF(x, 19), QPointF(x, 32))


class Toast(QFrame):
    """Transient notification that slides in at the top-right of its parent."""

    def __init__(self, parent: QWidget, text: str, kind: str = "info"):
        super().__init__(parent)
        color = {"info": C["accent2"], "success": C["success"], "error": C["danger"], "warning": C["warning"]}[kind]
        icon_name = {"info": "zap", "success": "check", "error": "alert", "warning": "alert"}[kind]
        self.setStyleSheet(f"QFrame {{ background: {C['surface2']}; border: 1px solid {C['border2']}; border-radius: 12px; }}"
                           f"QLabel {{ border: none; background: transparent; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 18, 12)
        lay.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, color, 18))
        lay.addWidget(ic)
        t = QLabel(text)
        t.setWordWrap(True)
        t.setMaximumWidth(360)
        lay.addWidget(t)
        sh = QGraphicsDropShadowEffect(self, blurRadius=30, offset=QPointF(0, 8), color=QColor(0, 0, 0, 140))
        self.setGraphicsEffect(sh)
        self.adjustSize()
        pw = parent.width()
        end = QPoint(pw - self.width() - 24, 20 + 70 * len([c for c in parent.children() if isinstance(c, Toast) and c is not self]))
        self.move(end + QPoint(40, 0))
        self.show()
        self.raise_()
        self._a = QPropertyAnimation(self, b"pos", self, duration=380, easingCurve=QEasingCurve.OutBack)
        self._a.setStartValue(end + QPoint(self.width() + 40, 0))
        self._a.setEndValue(end)
        self._a.start()
        QTimer.singleShot(3200, self._leave)

    def _leave(self):
        a = QPropertyAnimation(self, b"pos", self, duration=260, easingCurve=QEasingCurve.InCubic)
        a.setStartValue(self.pos())
        a.setEndValue(self.pos() + QPoint(self.width() + 40, 0))
        a.finished.connect(self.deleteLater)
        a.start()
        self._a = a


class EmptyState(QWidget):
    def __init__(self, icon_name: str, text: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(12)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, C["text3"], 44, 1.4))
        ic.setAlignment(Qt.AlignCenter)
        t = label(text, "Muted", wrap=True)
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(ic)
        lay.addWidget(t)


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(label(title, "H1"))
        if subtitle:
            col.addWidget(label(subtitle, "Muted"))
        lay.addLayout(col)
        lay.addStretch()
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        lay.addLayout(self.actions)
