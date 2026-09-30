# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Modal dialogs: new recording, run, simple prompts."""

import cv2
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QVBoxLayout,
                               QWidget)

from uiv_studio.core.keys import display_combo
from uiv_studio.core.screens import Monitor, ScreenGrabber, list_monitors
from uiv_studio.core.storage import list_recordings
from uiv_studio.ui import icons
from uiv_studio.ui.i18n import tr
from uiv_studio.ui.theme import C
from uiv_studio.ui.widgets import HoverCard, button, label, lerp_color


def bgr_to_pixmap(img, max_w: int | None = None) -> QPixmap:
    if max_w and img.shape[1] > max_w:
        f = max_w / img.shape[1]
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QPixmap.fromImage(QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy())


class MonitorCard(HoverCard):
    def __init__(self, monitor: Monitor, parent=None):
        super().__init__(clickable=True, parent=parent)
        self.monitor = monitor
        self.selected = False
        self.setFixedSize(236, 178)
        try:
            g = ScreenGrabber(monitor)
            self.thumb = bgr_to_pixmap(g.grab(), 440)
            g.close()
        except Exception:
            self.thumb = QPixmap()

    def set_selected(self, s: bool):
        self.selected = s
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(12, 12, self.width() - 24, 118)
        path = QPainterPath()
        path.addRoundedRect(r, 8, 8)
        p.setClipPath(path)
        if not self.thumb.isNull():
            pm = self.thumb.scaled(r.size().toSize(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.drawPixmap(r.topLeft(), pm, QRectF(0, 0, r.width() * pm.devicePixelRatio(), r.height() * pm.devicePixelRatio()))
        else:
            p.fillRect(r, QColor(C["surface3"]))
        p.setClipping(False)
        p.setPen(QColor(C["text"]))
        f = p.font(); f.setBold(True); p.setFont(f)
        p.drawText(QRectF(14, 136, self.width() - 28, 18), Qt.AlignLeft, f"{tr('common.monitor')} {self.monitor.index}")
        f.setBold(False); p.setFont(f)
        p.setPen(QColor(C["text2"]))
        p.drawText(QRectF(14, 154, self.width() - 28, 18), Qt.AlignLeft,
                   f"{self.monitor.width}×{self.monitor.height} · {round(self.monitor.scale * 100)}%")
        if self.selected:
            p.setPen(QPen(QColor(C["accent"]), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 14, 14)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C["accent"]))
            p.drawEllipse(QRectF(self.width() - 34, 20, 18, 18))
            p.drawPixmap(self.width() - 32, 22, icons.pixmap("check", "#FFFFFF", 14, 2.6))


class MonitorPicker(QWidget):
    changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.cards = []
        for m in list_monitors():
            c = MonitorCard(m)
            c.clicked.connect(lambda c=c: self.select(c))
            lay.addWidget(c)
            self.cards.append(c)
        lay.addStretch()
        if self.cards:
            self.select(self.cards[0])

    def select(self, card):
        for c in self.cards:
            c.set_selected(c is card)
        self.changed.emit(card.monitor)

    def monitor(self) -> Monitor | None:
        for c in self.cards:
            if c.selected:
                return c.monitor
        return None


class BaseDialog(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(28, 24, 28, 22)
        self.root.setSpacing(14)
        self.root.addWidget(label(title, "H2"))

    def footer(self, ok_text: str, ok_icon: str = "check"):
        row = QHBoxLayout()
        row.addStretch()
        cancel = button(tr("common.cancel"), obj="Ghost")
        cancel.clicked.connect(self.reject)
        self.ok = button(ok_text, ok_icon, "Primary")
        self.ok.setMinimumHeight(40)
        self.ok.clicked.connect(self._accept)
        row.addWidget(cancel)
        row.addWidget(self.ok)
        self.root.addSpacing(6)
        self.root.addLayout(row)

    def _accept(self):
        self.accept()

    def showEvent(self, e):
        super().showEvent(e)
        self.setWindowOpacity(0.0)
        a = QPropertyAnimation(self, b"windowOpacity", self, duration=180, easingCurve=QEasingCurve.OutCubic)
        a.setStartValue(0.0); a.setEndValue(1.0); a.start()
        self._fade = a


class NewRecordingDialog(BaseDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(tr("newrec.title"), parent)
        self.setMinimumWidth(620)
        self.root.addWidget(label(tr("common.name")))
        self.name = QLineEdit()
        self.name.setPlaceholderText(tr("newrec.name_ph"))
        self.root.addWidget(self.name)
        self.root.addWidget(label(f"{tr('common.description')} ({tr('common.optional')})"))
        self.desc = QLineEdit()
        self.root.addWidget(self.desc)
        self.root.addSpacing(4)
        self.root.addWidget(label(tr("newrec.pick_monitor"), "H3"))
        self.picker = MonitorPicker()
        self.root.addWidget(self.picker)
        hk = settings["hotkeys"]
        tip = label(tr("newrec.tips", menu=display_combo(hk["recorder_menu"]),
                       end_input=display_combo(hk["recorder_end_input"])), "Faint", wrap=True)
        tip.setStyleSheet(f"background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 10px; "
                          f"padding: 10px 12px; color: {C['text2']};")
        self.root.addWidget(tip)
        self.error = label("", wrap=True)
        self.error.setStyleSheet(f"color: {C['danger']};")
        self.root.addWidget(self.error)
        self.footer(tr("newrec.start"), "record")
        self.name.setFocus()

    def _accept(self):
        if not self.name.text().strip():
            self.error.setText(tr("newrec.name_required"))
            self.name.setFocus()
            return
        self.accept()

    def values(self) -> tuple[str, str, Monitor]:
        return self.name.text().strip(), self.desc.text().strip(), self.picker.monitor()


class RunDialog(BaseDialog):
    def __init__(self, workspace, preselect: str | None = None, parent=None):
        super().__init__(tr("run.title"), parent)
        self.setMinimumWidth(620)
        self.recs = list_recordings(workspace)
        self.root.addWidget(label(tr("run.recording")))
        self.combo = QComboBox()
        for r in self.recs:
            self.combo.addItem(f"{r['name']}   ·   {r['steps']} {tr('common.steps')}   ·   {r['screen']}", str(r["path"]))
        if preselect:
            i = self.combo.findData(str(preselect))
            if i >= 0:
                self.combo.setCurrentIndex(i)
        self.root.addWidget(self.combo)
        self.root.addSpacing(4)
        self.root.addWidget(label(tr("run.pick_monitor"), "H3"))
        self.picker = MonitorPicker()
        self.root.addWidget(self.picker)
        self.info = label("", wrap=True)
        self.root.addWidget(self.info)
        self.footer(tr("run.start"), "play")
        self.picker.changed.connect(self._update_info)
        self.combo.currentIndexChanged.connect(lambda _: self._update_info(self.picker.monitor()))
        self._update_info(self.picker.monitor())
        if not self.recs:
            self.info.setText(tr("run.no_recordings"))
            self.ok.setEnabled(False)

    def _update_info(self, m: Monitor | None):
        if not self.recs or m is None:
            return
        r = self.recs[self.combo.currentIndex()]
        exe = f"{m.width}×{m.height} @ {round(m.scale * 100)}%"
        same = r["screen"] == exe
        color = C["success"] if same else C["warning"]
        text = tr("run.geometry_same") if same else tr("run.geometry_diff", rec=r["screen"], exe=exe)
        self.info.setText(text)
        self.info.setStyleSheet(f"color: {color}; background: {lerp_color(QColor(color), QColor(C['bg2']), 0.88).name()}; "
                                f"border-radius: 10px; padding: 10px 12px;")

    def values(self) -> tuple[str, Monitor]:
        return self.combo.currentData(), self.picker.monitor()


def ask_text(parent, title: str, prompt: str, text: str = "") -> str | None:
    d = BaseDialog(title, parent)
    d.setMinimumWidth(420)
    d.root.addWidget(label(prompt))
    e = QLineEdit(text)
    e.selectAll()
    d.root.addWidget(e)
    d.footer(tr("common.save"))
    e.returnPressed.connect(d.accept)
    return e.text().strip() if d.exec() == QDialog.Accepted and e.text().strip() else None


def confirm(parent, text: str, danger: bool = True) -> bool:
    d = BaseDialog(tr("common.delete") if danger else "UIV Studio", parent)
    d.setMinimumWidth(420)
    d.root.addWidget(label(text, wrap=True))
    d.footer(tr("common.delete") if danger else tr("common.yes"), "trash" if danger else "check")
    if danger:
        d.ok.setObjectName("Danger")
        d.ok.setIcon(icons.icon("trash", C["danger"], 18))
        d.ok.style().unpolish(d.ok); d.ok.style().polish(d.ok)
    return d.exec() == QDialog.Accepted


def error_box(parent, text: str):
    QMessageBox.critical(parent, tr("common.error"), text)


class WelcomeDialog(BaseDialog):
    """First-launch guide (also reachable from the sidebar)."""

    def __init__(self, settings: dict, parent=None):
        super().__init__(tr("welcome.title"), parent)
        self.setMinimumWidth(760)
        self.root.addWidget(label(tr("welcome.sub"), "Muted"))
        row = QHBoxLayout()
        row.setSpacing(14)
        from uiv_studio.ui.widgets import IconBadge
        menu = display_combo(settings["hotkeys"]["recorder_menu"])
        for icon_name, colors, t, d in (
                ("record", ("#F472B6", "#7C6CFF"), "welcome.s1", tr("welcome.s1d", menu=menu)),
                ("edit", ("#7C6CFF", "#3DD6D0"), "welcome.s2", tr("welcome.s2d")),
                ("play", ("#3DD6D0", "#60A5FA"), "welcome.s3", tr("welcome.s3d"))):
            card = HoverCard(accent=colors[0])
            cl = QVBoxLayout(card)
            cl.setContentsMargins(18, 18, 18, 18)
            cl.setSpacing(8)
            cl.addWidget(IconBadge(icon_name, colors, 40))
            h = label(tr(t), "H3")
            h.setStyleSheet("background: transparent; font-size: 12pt; font-weight: 650;")
            cl.addWidget(h)
            dl = label(d, "Muted", wrap=True)
            dl.setStyleSheet("background: transparent;")
            cl.addWidget(dl)
            cl.addStretch()
            row.addWidget(card, 1)
        self.root.addLayout(row)
        r = QHBoxLayout()
        r.addStretch()
        ok = button(tr("welcome.start"), "zap", "Primary")
        ok.setMinimumHeight(40)
        ok.clicked.connect(self.accept)
        r.addWidget(ok)
        self.root.addSpacing(6)
        self.root.addLayout(r)



class UpdateDialog(BaseDialog):
    """Check GitHub Releases; download and install a newer version in place."""

    _progress = Signal(int, int)
    _checked = Signal(object)
    _downloaded = Signal(object)

    def __init__(self, parent=None, prefetched: dict | None = None):
        super().__init__(tr("upd.title"), parent)
        from PySide6.QtWidgets import QProgressBar
        from uiv_studio import __version__
        from uiv_studio.ui.widgets import Spinner
        self.setMinimumWidth(480)
        self.info = None
        self.root.addWidget(label(tr("upd.current", v=__version__), "Faint"))
        row = QHBoxLayout()
        self.spinner = Spinner(22)
        self.msg = label(tr("upd.checking"), wrap=True)
        row.addWidget(self.spinner)
        row.addWidget(self.msg, 1)
        self.root.addLayout(row)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setStyleSheet(
            f"QProgressBar {{ background: {C['surface3']}; border: none; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {C['accent']}, "
            f"stop:1 {C['cyan']}); border-radius: 4px; }}")
        self.bar.hide()
        self.root.addWidget(self.bar)
        foot = QHBoxLayout()
        foot.addStretch()
        self.close_btn = button(tr("common.close"), obj="Ghost")
        self.close_btn.clicked.connect(self.reject)
        self.go = button(tr("upd.install"), "refresh", "Primary")
        self.go.setMinimumHeight(40)
        self.go.hide()
        self.go.clicked.connect(self._install)
        foot.addWidget(self.close_btn)
        foot.addWidget(self.go)
        self.root.addSpacing(6)
        self.root.addLayout(foot)
        self._progress.connect(self._on_progress)
        self._checked.connect(self._on_checked)
        self._downloaded.connect(self._on_downloaded)
        if prefetched is not None:
            self._on_checked(prefetched)
        else:
            import threading
            threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        from uiv_studio.core.updates import latest_release
        try:
            self._checked.emit(latest_release())
        except Exception as exc:
            self._checked.emit(exc)

    def _error(self, exc):
        self.spinner.hide()
        self.msg.setText(tr("upd.error", e=exc))
        self.msg.setStyleSheet(f"color: {C['danger']};")

    def _on_checked(self, res):
        self.spinner.hide()
        if isinstance(res, Exception):
            return self._error(res)
        self.info = res
        if not res["newer"]:
            self.msg.setText("✓  " + tr("upd.latest"))
            self.msg.setStyleSheet(f"color: {C['success']};")
            return
        self.msg.setText(tr("upd.available", v=res["version"]))
        self.msg.setStyleSheet(f"color: {C['accent2']}; font-weight: 600;")
        self.go.show()

    def _install(self):
        from uiv_studio.core.updates import RELEASES_PAGE, launcher_path
        launcher = launcher_path()
        if launcher is None or not self.info.get("url"):
            # Running from source: open the release page instead
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(RELEASES_PAGE))
            return
        self.go.setEnabled(False)
        self.close_btn.setEnabled(False)
        self.bar.show()
        self.msg.setText(tr("upd.downloading"))
        self.msg.setStyleSheet("")
        import threading

        def work():
            from uiv_studio.core.updates import download
            dest = launcher.with_name(launcher.name + ".new")
            try:
                download(self.info["url"], dest, lambda d, t: self._progress.emit(d, t))
                self._downloaded.emit((dest, launcher))
            except Exception as exc:
                self._downloaded.emit(exc)
        threading.Thread(target=work, daemon=True).start()

    def _on_progress(self, done, total):
        self.bar.setMaximum(max(total, 1))
        self.bar.setValue(done)
        if total:
            self.msg.setText(f"{tr('upd.downloading')}  {done / 1e6:.0f} / {total / 1e6:.0f} MB")

    def _on_downloaded(self, res):
        if isinstance(res, Exception):
            self._error(res)
            self.close_btn.setEnabled(True)
            self.go.setEnabled(True)
            return
        from PySide6.QtWidgets import QApplication
        from uiv_studio.core.updates import install_and_restart
        self.msg.setText(tr("upd.restarting"))
        try:
            install_and_restart(*res)
        except Exception as exc:
            return self._on_downloaded(exc)
        QApplication.quit()
