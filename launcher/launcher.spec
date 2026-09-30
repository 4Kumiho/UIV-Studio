# Small single-file launcher (the payload is appended afterwards by packaging/make_single_exe.py)
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
icon_png = os.path.join(ROOT, "uiv_studio", "resources", "icon.png")

a = Analysis([os.path.join(SPECPATH, "launcher.py")], datas=[(icon_png, ".")],
             excludes=["numpy", "PySide6", "cv2", "onnxruntime", "unittest", "pydoc", "email", "http", "xml"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="UIV Studio", console=False, upx=False,
          icon=os.path.join(ROOT, "uiv_studio", "resources", "icon.ico" if sys.platform == "win32" else "icon.png"))
