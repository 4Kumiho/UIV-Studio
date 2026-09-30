"""Application entry point."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def _setup_logging():
    from uiv_studio.core.paths import log_dir
    handler = RotatingFileHandler(log_dir() / "uiv_studio.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handlers = [handler]
    if sys.stderr is not None:  # windowed (frozen) builds have no console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers)
    logging.getLogger("RapidOCR").setLevel(logging.WARNING)


def run() -> int:
    # Linux: pynput and mss need X11; force the xcb platform so Qt coordinates match them
    if sys.platform.startswith("linux") and os.environ.get("DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    if sys.platform == "win32":
        try:  # own taskbar group + icon instead of python.exe's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("UIVStudio.App")
        except Exception:
            pass

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtWidgets import QApplication

    _setup_logging()
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    from uiv_studio import APP_NAME
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)

    from uiv_studio.core.paths import resource_dir
    from uiv_studio.core.settings import settings
    from uiv_studio.ui.main_window import MainWindow
    from uiv_studio.ui.theme import apply_palette

    apply_palette(app)
    icon_path = resource_dir() / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    win = MainWindow(settings())
    win.show()
    return app.exec()
