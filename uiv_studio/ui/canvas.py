# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Screenshot canvas with editable target boxes (bbox + click point), smooth zoom and focus."""

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QGraphicsObject, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView

from uiv_studio.ui.theme import C

HANDLE = 9  # handle size in view pixels


class TargetItem(QGraphicsObject):
    """Bounding box with 8 resize handles and a draggable click crosshair."""

    changed = Signal()

    def __init__(self, rect: QRectF, click: QPointF, color: str, label: str, bounds: QRectF):
        super().__init__()
        self.r = QRectF(rect)
        self.click = QPointF(click)   # relative to r.topLeft()
        self.color = QColor(color)
        self.label = label
        self.bounds = bounds
        self._mode = None
        self._press = None
        self._orig = None
        self.setAcceptHoverEvents(True)
        self.setZValue(10)

    # ---------------------------------------------------------------- geometry
    def _scale(self) -> float:
        views = self.scene().views() if self.scene() else []
        return views[0].transform().m11() if views else 1.0

    def _hs(self) -> float:
        return HANDLE / max(self._scale(), 1e-3)

    def boundingRect(self) -> QRectF:
        m = self._hs() * 2 + 30 / max(self._scale(), 1e-3)
        return self.r.adjusted(-m, -m, m, m)

    def _handles(self) -> dict:
        r, h = self.r, self._hs()
        pts = {
            "tl": r.topLeft(), "t": QPointF(r.center().x(), r.top()), "tr": r.topRight(),
            "l": QPointF(r.left(), r.center().y()), "r": QPointF(r.right(), r.center().y()),
            "bl": r.bottomLeft(), "b": QPointF(r.center().x(), r.bottom()), "br": r.bottomRight(),
        }
        return {k: QRectF(p.x() - h / 2, p.y() - h / 2, h, h) for k, p in pts.items()}

    def _click_abs(self) -> QPointF:
        return self.r.topLeft() + self.click

    def _hit(self, pos: QPointF) -> str | None:
        cp = self._click_abs()
        if (pos - cp).manhattanLength() <= self._hs() * 1.6:
            return "click"
        for k, hr in self._handles().items():
            if hr.adjusted(-2, -2, 2, 2).contains(pos):
                return k
        if self.r.contains(pos):
            return "move"
        return None

    # ---------------------------------------------------------------- paint
    def paint(self, p: QPainter, opt, widget=None):
        s = max(self._scale(), 1e-3)
        fill = QColor(self.color); fill.setAlpha(28)
        p.setBrush(fill)
        p.setPen(QPen(self.color, 2 / s))
        p.drawRect(self.r)
        # label chip
        f = p.font(); f.setPointSizeF(9 / s if s < 1 else 9 / s); f.setBold(True); p.setFont(f)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(self.label) + 12 / s
        chip = QRectF(self.r.left(), self.r.top() - 20 / s, tw, 18 / s)
        p.setPen(Qt.NoPen); p.setBrush(self.color)
        p.drawRoundedRect(chip, 4 / s, 4 / s)
        p.setPen(QColor("white"))
        p.drawText(chip, Qt.AlignCenter, self.label)
        # handles
        p.setPen(QPen(self.color, 1.5 / s)); p.setBrush(QColor("white"))
        for hr in self._handles().values():
            p.drawRoundedRect(hr, 2 / s, 2 / s)
        # click crosshair
        cp = self._click_abs()
        r1, r2 = 7 / s, 13 / s
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 160), 4 / s))
        p.drawEllipse(cp, r1, r1)
        p.setPen(QPen(QColor(C["warning"]), 2 / s))
        p.drawEllipse(cp, r1, r1)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            p.drawLine(cp + QPointF(dx * r1, dy * r1), cp + QPointF(dx * r2, dy * r2))

    # ---------------------------------------------------------------- interaction
    def hoverMoveEvent(self, e):
        m = self._hit(e.pos())
        cursors = {"click": Qt.CrossCursor, "move": Qt.SizeAllCursor, "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
                   "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor, "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
                   "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor}
        self.setCursor(cursors.get(m, Qt.ArrowCursor))

    def mousePressEvent(self, e):
        self._mode = self._hit(e.pos())
        if self._mode is None:
            e.ignore()
            return
        self._press = e.pos()
        self._orig = (QRectF(self.r), QPointF(self.click))
        e.accept()

    def mouseMoveEvent(self, e):
        if not self._mode:
            return
        self.prepareGeometryChange()
        d = e.pos() - self._press
        r0, c0 = self._orig
        r = QRectF(r0)
        m = self._mode
        if m == "click":
            p = c0 + d
            self.click = QPointF(min(max(p.x(), 0), r.width() - 1), min(max(p.y(), 0), r.height() - 1))
        elif m == "move":
            r.translate(d)
            r.moveLeft(min(max(r.left(), self.bounds.left()), self.bounds.right() - r.width()))
            r.moveTop(min(max(r.top(), self.bounds.top()), self.bounds.bottom() - r.height()))
            self.r = r
        else:
            if "l" in m:
                r.setLeft(min(r.left() + d.x(), r.right() - 8))
            if "r" in m:
                r.setRight(max(r.right() + d.x(), r.left() + 8))
            if "t" in m:
                r.setTop(min(r.top() + d.y(), r.bottom() - 8))
            if "b" in m:
                r.setBottom(max(r.bottom() + d.y(), r.top() + 8))
            r = r.intersected(self.bounds)
            # keep the click point at the same absolute position when possible
            abs_click = r0.topLeft() + c0
            self.click = QPointF(min(max(abs_click.x() - r.left(), 0), r.width() - 1),
                                 min(max(abs_click.y() - r.top(), 0), r.height() - 1))
            self.r = r
        self.update()
        self.scene().update()

    def mouseReleaseEvent(self, e):
        if self._mode:
            self._mode = None
            r = self.r
            self.r = QRectF(round(r.left()), round(r.top()), round(r.width()), round(r.height()))
            self.click = QPointF(round(self.click.x()), round(self.click.y()))
            self.update()
            self.changed.emit()

    def values(self) -> tuple[tuple, tuple]:
        r = self.r
        return (int(r.left()), int(r.top()), int(r.width()), int(r.height())), (int(self.click.x()), int(self.click.y()))


class Canvas(QGraphicsView):
    targetChanged = Signal(str)   # 'main' | 'drop'

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setBackgroundBrush(QColor(C["bg"]))
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.pix: QGraphicsPixmapItem | None = None
        self.items_: dict[str, TargetItem] = {}
        self._anim = QVariantAnimation(self, duration=420, easingCurve=QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._anim_step)
        self._from = self._to = None

    # ---------------------------------------------------------------- content
    def set_image(self, pm: QPixmap):
        self.scene().clear()
        self.items_.clear()
        self.pix = self.scene().addPixmap(pm)
        self.pix.setTransformationMode(Qt.SmoothTransformation)
        self.pix.setZValue(0)
        self.scene().setSceneRect(QRectF(pm.rect()).adjusted(-200, -200, 200, 200))

    def set_target(self, role: str, rect: tuple | None, click: tuple = (0, 0), color: str = C["accent"], text: str = ""):
        old = self.items_.pop(role, None)
        if old:
            self.scene().removeItem(old)
        if rect is None or self.pix is None:
            self.viewport().update()
            return
        it = TargetItem(QRectF(*rect), QPointF(*click), color, text, QRectF(self.pix.pixmap().rect()))
        it.changed.connect(lambda r=role: self.targetChanged.emit(r))
        self.scene().addItem(it)
        self.items_[role] = it

    def target_values(self, role: str):
        it = self.items_.get(role)
        return it.values() if it else None

    # ---------------------------------------------------------------- view
    def _fit_scale(self, rect: QRectF) -> float:
        vw, vh = self.viewport().width() - 40, self.viewport().height() - 40
        return max(0.05, min(vw / max(rect.width(), 1), vh / max(rect.height(), 1)))

    def focus(self, rect: QRectF | None = None, animate: bool = True):
        """Zoom to `rect` (with context) or to the whole image."""
        if self.pix is None:
            return
        full = QRectF(self.pix.pixmap().rect())
        if rect is None:
            target = full
        else:
            ctx = QRectF(rect)
            grow_w = max(ctx.width() * 3, 700)
            grow_h = max(ctx.height() * 3, 420)
            ctx = QRectF(ctx.center().x() - grow_w / 2, ctx.center().y() - grow_h / 2, grow_w, grow_h)
            target = ctx
        s1 = min(self._fit_scale(target), 3.0)
        s1 = max(s1, self._fit_scale(full))
        c1 = target.center()
        s0 = self.transform().m11()
        c0 = self.mapToScene(self.viewport().rect().center())
        if not animate or s0 == 0:
            self._apply(s1, c1)
            return
        self._from, self._to = (s0, c0), (s1, c1)
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def _anim_step(self, t):
        (s0, c0), (s1, c1) = self._from, self._to
        t = float(t)
        # interpolate zoom geometrically for a natural feel
        s = s0 * (s1 / s0) ** t
        c = c0 + (c1 - c0) * t
        self._apply(s, c)

    def _apply(self, s: float, c: QPointF):
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setTransform(QTransform.fromScale(s, s))
        self.centerOn(c)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

    def wheelEvent(self, e):
        self._anim.stop()
        f = 1.0015 ** e.angleDelta().y()
        s = self.transform().m11() * f
        if 0.05 <= s <= 12:
            self.scale(f, f)

    def mouseDoubleClickEvent(self, e):
        if self.itemAt(e.position().toPoint()) in (None, self.pix):
            self.focus(None)
        super().mouseDoubleClickEvent(e)

    def drawForeground(self, p: QPainter, rect: QRectF):
        """Dim everything outside the targets to draw attention to them."""
        if self.pix is None or not self.items_:
            return
        path = QPainterPath()
        path.addRect(QRectF(self.pix.pixmap().rect()))
        for it in self.items_.values():
            hole = QPainterPath()
            hole.addRect(it.r)
            path = path.subtracted(hole)
        p.fillPath(path, QBrush(QColor(5, 7, 12, 105)))
