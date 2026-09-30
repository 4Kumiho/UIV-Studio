# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Glue the launcher and the zipped application into the single distributable executable.

Inputs : build/out_launcher/UIV Studio(.exe)   (launcher, PyInstaller onefile)
         build/out_app/UIV Studio/             (application, PyInstaller onedir)
Output : UIV Studio(.exe) in the project root
"""

import hashlib
import os
import shutil
import struct
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uiv_studio import __version__  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXT = ".exe" if sys.platform == "win32" else ""
LAUNCHER = ROOT / "build" / "out_launcher" / f"UIV Studio{EXT}"
APP = ROOT / "build" / "out_app" / "UIV Studio"
OUT = ROOT / f"UIV Studio{EXT}"
PAYLOAD = ROOT / "build" / "payload.zip"
MAGIC = b"UIVPAYLD"


def main():
    PAYLOAD.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(PAYLOAD, "w", zipfile.ZIP_LZMA) as z:
        for p in sorted(APP.rglob("*")):
            arc = p.relative_to(APP).as_posix()
            if p.is_dir():
                continue
            info = zipfile.ZipInfo.from_file(p, arc)
            info.compress_type = zipfile.ZIP_LZMA  # much smaller than deflate: keeps the exe under GitHub's 100 MB limit
            with open(p, "rb") as f:
                z.writestr(info, f.read())
    digest = hashlib.sha256(PAYLOAD.read_bytes()).hexdigest()[:12]
    version = f"{__version__}-{digest}".encode()
    size = PAYLOAD.stat().st_size
    shutil.copyfile(LAUNCHER, OUT)
    with open(OUT, "ab") as out, open(PAYLOAD, "rb") as src:
        shutil.copyfileobj(src, out, 1 << 20)
        out.write(version.ljust(32, b"\0") + struct.pack("<Q", size) + MAGIC)
    if not sys.platform == "win32":
        os.chmod(OUT, 0o755)
    print(f"Built {OUT}  ({OUT.stat().st_size / 1e6:.0f} MB, version {version.decode()})")


if __name__ == "__main__":
    main()
