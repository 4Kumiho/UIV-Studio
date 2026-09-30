"""Page scaffolding shared by all pages."""

from datetime import datetime

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter
from PySide6.QtWidgets import QFrame, QGridLayout, QScrollArea, QVBoxLayout, QWidget


class Page(QWidget):
    """Scrollable page with standard margins. Subclasses fill `self.body`."""

    def __init__(self, app, scroll: bool = True):
        super().__init__()
        self.app = app
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(36, 30, 36, 30)
        self.body.setSpacing(18)
        if scroll:
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.NoFrame)
            area.setWidget(content)
            outer.addWidget(area)
        else:
            outer.addWidget(content)

    def refresh(self):
        pass


class FlowGrid(QWidget):
    """Responsive grid: number of columns follows the available width."""

    def __init__(self, min_w: int = 300, spacing: int = 14):
        super().__init__()
        self.min_w = min_w
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(spacing)
        self.items: list[QWidget] = []
        self._cols = 0

    def set_items(self, widgets: list[QWidget]):
        for w in self.items:
            self.grid.removeWidget(w)
            w.deleteLater()
        self.items = list(widgets)
        self._cols = 0
        self._relayout()

    def _relayout(self):
        cols = max(1, self.width() // self.min_w) if self.width() > 0 else 3
        if cols == self._cols:
            return
        self._cols = cols
        for w in self.items:
            self.grid.removeWidget(w)
        for i, w in enumerate(self.items):
            self.grid.addWidget(w, i // cols, i % cols)
        for c in range(8):
            self.grid.setColumnStretch(c, 1 if c < cols else 0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._relayout)


class GradientTitle(QWidget):
    """Large headline rendered with a gradient fill."""

    def __init__(self, text: str, colors: tuple[str, str, str], size: float = 30):
        super().__init__()
        self.text, self.colors = text, colors
        self.font = QFont()
        self.font.setPointSizeF(size)
        self.font.setWeight(QFont.Bold)
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self.font)
        self.setMinimumHeight(fm.height() + 6)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(self.font)
        w = p.fontMetrics().horizontalAdvance(self.text)
        g = QLinearGradient(0, 0, max(w, 1), 0)
        for i, c in enumerate(self.colors):
            g.setColorAt(i / (len(self.colors) - 1), QColor(c))
        from PySide6.QtGui import QPen, QBrush
        p.setPen(QPen(QBrush(g), 1))
        p.drawText(QRectF(self.rect()), Qt.AlignLeft | Qt.AlignVCenter, self.text)


def fmt_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso or ""


def fmt_duration(a: str, b: str) -> str:
    try:
        s = int((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds())
        return f"{s // 60}m {s % 60:02d}s" if s >= 60 else f"{s}s"
    except Exception:
        return "—"
