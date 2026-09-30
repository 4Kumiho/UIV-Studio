# Build the single distributable "dist\UIV Studio.exe". Run from the project root:
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv")) { python -m venv .venv }
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install -q -r requirements.txt pyinstaller
# rapidocr pulls opencv-python (GUI build) as a dependency: keep only the headless one
& $py -m pip uninstall -y -q opencv-python
& $py -m pip install -q --force-reinstall --no-deps opencv-python-headless

$env:UIV_ONEDIR = "1"
& $py -m PyInstaller --noconfirm --distpath build\out_app --workpath build\work_app packaging\uiv_studio.spec
Remove-Item Env:\UIV_ONEDIR
& $py -m PyInstaller --noconfirm --distpath build\out_launcher --workpath build\work_launcher launcher\launcher.spec
& $py packaging\make_single_exe.py
