# Small installer executable placed in the repository root ("Installa UIV Studio.exe")
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
res = os.path.join(ROOT, "uiv_studio", "resources")

a = Analysis([os.path.join(SPECPATH, "installer.py")], datas=[(os.path.join(res, "icon.png"), ".")],
             excludes=["numpy", "PySide6", "cv2", "onnxruntime", "unittest", "pydoc"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="Installa UIV Studio", console=False, upx=False,
          icon=os.path.join(res, "icon.ico" if sys.platform == "win32" else "icon.png"))
