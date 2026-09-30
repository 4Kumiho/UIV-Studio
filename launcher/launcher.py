"""UIV Studio single-file launcher.

The distributed executable is this launcher with the whole application appended
as a ZIP payload:

    [launcher exe][payload.zip][version: 32 bytes][payload size: 8 bytes][MAGIC: 8 bytes]

First run: extract the payload (with a progress window) into a hidden `.uivstudio`
folder next to the executable (fallback: the user's local app-data folder), then
start the app. Later runs: start the installed app immediately. A new executable
(different version) installs itself the same way and removes old versions.
"""

import os
import shutil
import struct
import subprocess
import sys
import threading
import zipfile
from pathlib import Path

MAGIC = b"UIVPAYLD"
TRAILER = 32 + 8 + 8
APP_NAME = "UIV Studio"
APP_EXE = "UIV Studio.exe" if sys.platform == "win32" else "UIV Studio"

TEXT = {
    "it": ("Preparazione di UIV Studio", "Installazione in corso (solo al primo avvio)…", "Avvio…",
           "Errore durante l'installazione"),
    "en": ("Preparing UIV Studio", "Installing (first launch only)…", "Starting…", "Installation error"),
}


def _lang() -> str:
    try:
        import locale
        loc = (locale.getlocale()[0] or os.environ.get("LANG", "")).lower()
    except Exception:
        loc = ""
    return "it" if loc.startswith("it") else "en"


def read_trailer(exe: Path):
    """Return (version, payload_offset, payload_size) or None."""
    with open(exe, "rb") as f:
        f.seek(-TRAILER, os.SEEK_END)
        data = f.read(TRAILER)
        if data[-8:] != MAGIC:
            return None
        version = data[:32].rstrip(b"\0").decode()
        size = struct.unpack("<Q", data[32:40])[0]
        end = f.seek(0, os.SEEK_END)
        return version, end - TRAILER - size, size


class _Slice:
    """Read-only file view on the payload region, for zipfile."""

    def __init__(self, path, offset, size):
        self.f = open(path, "rb")
        self.offset, self.size, self.pos = offset, size, 0

    def seek(self, pos, whence=0):
        self.pos = {0: pos, 1: self.pos + pos, 2: self.size + pos}[whence]
        return self.pos

    def tell(self):
        return self.pos

    def read(self, n=-1):
        if n < 0 or self.pos + n > self.size:
            n = self.size - self.pos
        self.f.seek(self.offset + self.pos)
        data = self.f.read(n)
        self.pos += len(data)
        return data

    def seekable(self):
        return True

    def close(self):
        self.f.close()


def install_root(exe: Path) -> Path:
    local = exe.parent / ".uivstudio"
    try:
        local.mkdir(exist_ok=True)
        probe = local / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(str(local), 0x02)  # FILE_ATTRIBUTE_HIDDEN
        return local
    except OSError:
        if sys.platform == "win32":
            base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        else:
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        root = base / APP_NAME / "runtime"
        root.mkdir(parents=True, exist_ok=True)
        return root


def _retry(fn, attempts=20):
    """Antivirus/indexers briefly lock freshly written files on Windows: retry."""
    import time
    for i in range(attempts):
        try:
            return fn()
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.25 * (i + 1))


def _rmtree(path: Path):
    if path.exists():
        _retry(lambda: shutil.rmtree(path))


def extract(exe: Path, offset: int, size: int, target: Path, progress):
    # Extract in place; the `.complete` marker written last guarantees integrity
    _rmtree(target)
    target.mkdir(parents=True)
    tmp = target
    src = _Slice(exe, offset, size)
    try:
        with zipfile.ZipFile(src) as z:
            items = z.infolist()
            total = sum(i.file_size for i in items) or 1
            done = 0
            for i in items:
                _retry(lambda i=i: z.extract(i, tmp))
                if not i.is_dir():
                    mode = (i.external_attr >> 16) & 0o777
                    if mode:
                        os.chmod(tmp / i.filename, mode)
                done += i.file_size
                progress(done / total)
    finally:
        src.close()
    (target / ".complete").write_text("ok")


def cleanup_old(root: Path, keep: str):
    for p in root.iterdir():
        if p.is_dir() and p.name != keep:
            shutil.rmtree(p, ignore_errors=True)   # best effort; retried at the next update


def launch(app_dir: Path, launcher: Path):
    exe = app_dir / APP_EXE
    # Tell the app which file to replace when it updates itself
    env = dict(os.environ, UIV_LAUNCHER=str(launcher))
    kwargs = {"cwd": str(app_dir), "env": env}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([str(exe), *sys.argv[1:]], **kwargs)


# ------------------------------------------------------------------ progress window


def run_with_window(work):
    import tkinter as tk

    t = TEXT[_lang()]
    bg, fg, muted, accent, track = "#0B0D12", "#E8ECF4", "#A3ACBF", "#7C6CFF", "#232938"
    root = tk.Tk()
    root.title(APP_NAME)
    root.configure(bg=bg)
    root.resizable(False, False)
    w, h = 520, 230
    root.geometry(f"{w}x{h}+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 2}")
    try:
        icon = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "icon.png"
        img = tk.PhotoImage(file=str(icon))
        root.iconphoto(True, img)
        logo = img.subsample(max(1, img.width() // 48))
        tk.Label(root, image=logo, bg=bg).place(x=28, y=28)
    except Exception:
        pass
    tk.Label(root, text=t[0], bg=bg, fg=fg, font=("Segoe UI", 14, "bold")).place(x=92, y=30)
    status = tk.Label(root, text=t[1], bg=bg, fg=muted, font=("Segoe UI", 10),
                      wraplength=w - 120, justify="left", anchor="nw")
    status.place(x=92, y=62, width=w - 120, height=80)
    cv = tk.Canvas(root, width=w - 56, height=8, bg=bg, highlightthickness=0)
    cv.place(x=28, y=160)
    cv.create_rectangle(0, 0, w - 56, 8, fill=track, outline=track)
    bar = cv.create_rectangle(0, 0, 0, 8, fill=accent, outline=accent)
    pct = tk.Label(root, text="0%", bg=bg, fg=fg, font=("Segoe UI", 10, "bold"))
    pct.place(x=28, y=180)

    state = {"p": 0.0, "done": False, "error": None}

    def progress(p):
        state["p"] = p

    def worker():
        try:
            work(progress)
        except Exception as exc:  # shown in the window
            state["error"] = exc
        state["done"] = True

    def tick():
        p = state["p"]
        cv.coords(bar, 0, 0, (w - 56) * p, 8)
        pct.configure(text=f"{p * 100:.0f}%")
        if state["error"] is not None:
            status.configure(text=f"{t[3]}: {state['error']}", fg="#F87171")
            return
        if state["done"]:
            status.configure(text=t[2])
            root.after(400, root.destroy)
            return
        root.after(50, tick)

    threading.Thread(target=worker, daemon=True).start()
    tick()
    root.mainloop()
    if state["error"] is not None:
        raise SystemExit(1)


def main():
    exe = Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0]).resolve()
    info = read_trailer(exe)
    if info is None:
        raise SystemExit("No application payload found in this executable.")
    version, offset, size = info
    root = install_root(exe)
    app_dir = root / version
    if not (app_dir / ".complete").exists():
        run_with_window(lambda progress: extract(exe, offset, size, app_dir, progress))
        cleanup_old(root, keep=version)
    launch(app_dir, exe)


if __name__ == "__main__":
    main()
