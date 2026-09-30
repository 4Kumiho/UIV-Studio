# PyInstaller spec for UIV Studio.
#   pyinstaller packaging/uiv_studio.spec            -> dist/UIV Studio(.exe)   single file
#   UIV_ONEDIR=1 pyinstaller packaging/uiv_studio.spec -> dist/UIV Studio/       folder (payload of the single executable)
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
ONEDIR = os.environ.get("UIV_ONEDIR") == "1"
NAME = "UIV Studio"

datas = [(os.path.join(ROOT, "uiv_studio", "resources"), os.path.join("uiv_studio", "resources"))]
datas += collect_data_files("rapidocr_onnxruntime")          # PP-OCR models + config.yaml

hidden = collect_submodules("pynput") + collect_submodules("rapidocr_onnxruntime")
if sys.platform.startswith("linux"):
    hidden += collect_submodules("Xlib")

# Qt modules we never use: keeps the bundle small
excludes = [
    "tkinter", "matplotlib", "scipy", "pandas", "torch", "IPython", "PyQt5", "PyQt6",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore",
    "PySide6.Qt3DRender", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech",
    "PySide6.QtWebSockets", "PySide6.QtHttpServer", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtNetwork", "PySide6.QtVirtualKeyboard",
]

a = Analysis(
    [os.path.join(ROOT, "uiv_studio", "__main__.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=hidden,
    excludes=excludes,
    noarchive=False,
)

# Drop heavy Qt payloads that slip in through plugins
_skip = ("Qt6WebEngine", "Qt6Quick", "Qt6Qml", "Qt6Pdf", "Qt6Designer", "Qt63D", "qtwebengine", "QtWebEngineProcess",
         "opengl32sw", "Qt6Multimedia", "Qt6Charts", "Qt6Graphs", "Qt6DataVisualization", "translations",
         "Qt6Network", "QtNetwork", "Qt6VirtualKeyboard", "qtvirtualkeyboard", "plugins/tls", "plugins\tls",
         "networkinformation", "qpdf", "qtiff", "qwebp", "qicns", "qtga", "qwbmp", "qdirect2d", "qtuiotouch",
         "PIL/_avif", "PIL\_avif", "PIL/_webp", "PIL\_webp", "PIL/_imagingcms", "PIL\_imagingcms")
a.binaries = [b for b in a.binaries if not any(s in b[0] for s in _skip)]
a.datas = [d for d in a.datas if not any(s in d[0] for s in _skip)]

pyz = PYZ(a.pure)
icon = os.path.join(ROOT, "uiv_studio", "resources", "icon.ico" if sys.platform == "win32" else "icon.png")

if ONEDIR:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=False, icon=icon, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name=NAME, upx=False)
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=NAME, console=False, icon=icon, upx=False,
              runtime_tmpdir=None)
