#!/usr/bin/env bash
# Build the single distributable "UIV Studio" in the project root (one executable file, like on Windows).
# For maximum compatibility build inside the old-glibc container:
#     docker build -t uiv-build -f packaging/Dockerfile.linux .
#     docker run --rm -v "$PWD":/src uiv-build
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
$PY -m venv .venv-linux
. .venv-linux/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt pyinstaller
pip uninstall -y -q opencv-python || true
pip install -q --force-reinstall --no-deps opencv-python-headless

UIV_ONEDIR=1 pyinstaller --noconfirm --distpath build/out_app --workpath build/work_app packaging/uiv_studio.spec
# Qt >= 6.5 needs libxcb-cursor, missing on many desktops: ship it inside the app
for lib in libxcb-cursor.so.0 libxcb-icccm.so.4 libxcb-keysyms.so.1 libxcb-render-util.so.0 libxcb-image.so.0 libxkbcommon-x11.so.0; do
  p=$(ldconfig -p | awk -v l="$lib" '$1==l {print $NF; exit}')
  [ -n "${p:-}" ] && cp -L "$p" "build/out_app/UIV Studio/_internal/" || echo "warning: $lib not found"
done
pyinstaller --noconfirm --distpath build/out_launcher --workpath build/work_launcher launcher/launcher.spec

python packaging/make_single_exe.py
