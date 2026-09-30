"""Main window: sidebar navigation, page stack and session orchestration."""

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QMessageBox, QWidget

from uiv_studio import APP_NAME, __version__
from uiv_studio.core.settings import Settings
from uiv_studio.core.storage import Recording
from uiv_studio.ui.dialogs import NewRecordingDialog, RunDialog, WelcomeDialog, error_box
from uiv_studio.ui.i18n import set_language, tr
from uiv_studio.ui.pages.editor import EditorPage
from uiv_studio.ui.pages.home import HomePage
from uiv_studio.ui.pages.recordings import RecordingsPage
from uiv_studio.ui.pages.report import ReportPage
from uiv_studio.ui.pages.runs import RunsPage
from uiv_studio.ui.pages.settings_page import SettingsPage
from uiv_studio.ui.session import PlaybackSession, RecordingSession
from uiv_studio.ui.theme import C
from uiv_studio.ui.widgets import AnimatedStack, Sidebar, Toast, label

log = logging.getLogger(__name__)

HOME, RECORDINGS, RUNS, SETTINGS, EDITOR, REPORT = range(6)


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.session = None
        self.setWindowTitle(APP_NAME)
        self.resize(1360, 860)
        self.setMinimumSize(1080, 680)
        self._build()
        threading.Thread(target=self._warmup, daemon=True).start()

    # ------------------------------------------------------------------ build
    def _build(self):
        set_language(self.settings.data["general"]["language"])
        root = QWidget()
        root.setObjectName("Root")
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.sidebar = Sidebar([("home", tr("nav.home")), ("layers", tr("nav.recordings")),
                                ("runs", tr("nav.runs")), ("settings", tr("nav.settings"))])
        from uiv_studio.ui.widgets import button
        guide = button(tr("welcome.help"), "sparkles", "Ghost")
        guide.clicked.connect(self.show_welcome)
        self.sidebar.footer.addWidget(guide)
        ver = label(f"v{__version__}", "Faint")
        self.sidebar.footer.addWidget(ver)
        lay.addWidget(self.sidebar)
        self.stack = AnimatedStack()
        self.pages = [HomePage(self), RecordingsPage(self), RunsPage(self), SettingsPage(self),
                      EditorPage(self), ReportPage(self)]
        for p in self.pages:
            self.stack.addWidget(p)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.sidebar.changed.connect(self._on_nav)
        self.sidebar.select(HOME, animate=False)

    def rebuild(self):
        """Recreate the UI (after a language change)."""
        current = min(self.stack.currentIndex(), SETTINGS)
        self.pages[EDITOR].close_recording()
        self.pages[REPORT].release()
        old = self.centralWidget()
        self._build()
        old.deleteLater()
        self.navigate(current)

    def _warmup(self):
        try:
            from uiv_studio.vision.embed import Embedder
            from uiv_studio.vision.ocr import OCR
            OCR.warmup()
            Embedder.warmup()
        except Exception:
            log.exception("Model warmup failed")

    # ------------------------------------------------------------------ navigation
    def _on_nav(self, i: int):
        self._leave_detail_pages()
        self._show(i)

    def _show(self, i: int):
        page = self.pages[i]
        page.refresh() if hasattr(page, "refresh") else None
        self.stack.slide_to(i)

    def navigate(self, i: int):
        self.sidebar.select(i, emit=False)
        self._leave_detail_pages()
        self._show(i)

    def _leave_detail_pages(self):
        cur = self.stack.currentIndex()
        if cur == EDITOR:
            self.pages[EDITOR].close_recording()
        elif cur == REPORT:
            self.pages[REPORT].release()

    def open_editor(self, path):
        self._leave_detail_pages()
        try:
            self.pages[EDITOR].load(Path(path))
        except Exception as exc:
            log.exception("Cannot open recording")
            error_box(self, str(exc))
            return
        self.sidebar.select(RECORDINGS, emit=False)
        self.stack.slide_to(EDITOR)

    def open_report(self, path):
        self._leave_detail_pages()
        try:
            self.pages[REPORT].load(Path(path))
        except Exception as exc:
            log.exception("Cannot open run")
            error_box(self, str(exc))
            return
        self.sidebar.select(RUNS, emit=False)
        self.stack.slide_to(REPORT)

    def toast(self, text: str, kind: str = "info"):
        Toast(self.centralWidget(), text, kind)

    # ------------------------------------------------------------------ sessions
    def _hide_for_session(self):
        if self.settings.data["general"]["minimize_during_sessions"]:
            self.showMinimized()

    def _restore(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def new_recording(self):
        if self.session:
            return
        d = NewRecordingDialog(self.settings.data, self)
        if d.exec() != NewRecordingDialog.Accepted:
            return
        name, desc, monitor = d.values()
        try:
            rec = Recording.create(self.settings.workspace, name, monitor.width, monitor.height, monitor.scale, desc)
        except FileExistsError:
            error_box(self, tr("rec.exists"))
            return
        self.session = RecordingSession(rec, monitor, self.settings.snapshot())
        self.session.done.connect(self._recording_done)
        self._hide_for_session()
        QTimer.singleShot(350, self.session.start)

    def _recording_done(self, path: str, steps: int):
        self.session = None
        self._restore()
        if path:
            self.toast(tr("toast.recording_saved", n=steps), "success")
            self.open_editor(path)
        else:
            self.toast(tr("toast.recording_discarded"), "warning")
            self.navigate(RECORDINGS)

    def run_recording(self, path=None):
        if self.session:
            return
        if self.stack.currentIndex() == EDITOR:
            self.pages[EDITOR].maybe_save()
        d = RunDialog(self.settings.workspace, str(path) if path else None, self)
        if d.exec() != RunDialog.Accepted:
            return
        rec_path, monitor = d.values()
        if not rec_path or monitor is None:
            return
        self.session = PlaybackSession(rec_path, monitor, self.settings.snapshot(), self.settings.workspace)
        self.session.done.connect(self._run_done)
        self._hide_for_session()
        QTimer.singleShot(350, self.session.start)

    def _run_done(self, path: str, result: str):
        self.session = None
        self._restore()
        self.toast(tr("toast.run_done", result=tr(f"status.{result}")),
                   "success" if result == "PASSED" else "error" if result == "FAILED" else "warning")
        if path:
            self.open_report(path)

    # ------------------------------------------------------------------ window
    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_shown", False):
            self._shown = True
            self.setWindowOpacity(0.0)
            a = QPropertyAnimation(self, b"windowOpacity", self, duration=350, easingCurve=QEasingCurve.OutCubic)
            a.setStartValue(0.0)
            a.setEndValue(1.0)
            a.start()
            self._intro = a
            if not self.settings.data["general"]["welcome_done"]:
                QTimer.singleShot(500, self._first_welcome)

    def _first_welcome(self):
        self.show_welcome()
        d = self.settings.snapshot()
        d["general"]["welcome_done"] = True
        self.settings.save(d)

    def show_welcome(self):
        WelcomeDialog(self.settings.data, self).exec()

    def closeEvent(self, e):
        if self.session:
            e.ignore()
            return
        self.pages[EDITOR].close_recording()
        self.pages[REPORT].release()
        super().closeEvent(e)
