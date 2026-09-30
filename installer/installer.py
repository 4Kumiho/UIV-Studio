# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""UIV Studio installer: downloads the latest application executable from the
GitHub Release into the folder where this installer lives, then starts it.

Run it again at any time to update UIV Studio to the latest version.
"""

import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

REPO = "4Kumiho/UIV-Studio"
if sys.platform == "win32":
    ASSET, TARGET = "UIV-Studio-windows.exe", "UIV Studio.exe"
else:
    ASSET, TARGET = "UIV-Studio-linux", "UIV Studio"
URL = f"https://github.com/{REPO}/releases/latest/download/{ASSET}"

TEXT = {
    "it": ("Installazione di UIV Studio", "Download dell'ultima versione…", "Avvio di UIV Studio…",
           "Download non riuscito", "Controlla la connessione a internet e riprova."),
    "en": ("Installing UIV Studio", "Downloading the latest version…", "Starting UIV Studio…",
           "Download failed", "Check your internet connection and try again."),
}


def _lang() -> str:
    try:
        import locale
        loc = (locale.getlocale()[0] or os.environ.get("LANG", "")).lower()
    except Exception:
        loc = ""
    return "it" if loc.startswith("it") else "en"


def here() -> Path:
    exe = sys.executable if getattr(sys, "frozen", False) else __file__
    return Path(exe).resolve().parent


def download(dest: Path, progress):
    tmp = dest.with_name(dest.name + ".download")
    req = urllib.request.Request(URL, headers={"User-Agent": "UIV-Studio-Installer"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done, t0 = 0, time.monotonic()
        while True:
            chunk = r.read(1 << 18)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            progress(done, total, done / max(time.monotonic() - t0, 1e-3))
    if dest.exists():
        dest.unlink()
    tmp.rename(dest)
    if sys.platform != "win32":
        os.chmod(dest, 0o755)


def launch(exe: Path):
    kwargs = {"cwd": str(exe.parent)}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([str(exe)], **kwargs)


def main():
    import tkinter as tk

    t = TEXT[_lang()]
    dest = here() / TARGET
    bg, fg, muted, accent, track = "#0B0D12", "#E8ECF4", "#A3ACBF", "#7C6CFF", "#232938"
    root = tk.Tk()
    root.title("UIV Studio")
    root.configure(bg=bg)
    root.resizable(False, False)
    w, h = 520, 230
    root.geometry(f"{w}x{h}+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 2}")
    try:
        img = tk.PhotoImage(file=str(Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "icon.png"))
        root.iconphoto(True, img)
        logo = img.subsample(max(1, img.width() // 48))
        tk.Label(root, image=logo, bg=bg).place(x=28, y=28)
    except Exception:
        pass
    tk.Label(root, text=t[0], bg=bg, fg=fg, font=("Segoe UI", 14, "bold")).place(x=92, y=30)
    status = tk.Label(root, text=t[1], bg=bg, fg=muted, font=("Segoe UI", 10), wraplength=w - 120,
                      justify="left", anchor="nw")
    status.place(x=92, y=62, width=w - 120, height=80)
    cv = tk.Canvas(root, width=w - 56, height=8, bg=bg, highlightthickness=0)
    cv.place(x=28, y=160)
    cv.create_rectangle(0, 0, w - 56, 8, fill=track, outline=track)
    bar = cv.create_rectangle(0, 0, 0, 8, fill=accent, outline=accent)
    info = tk.Label(root, text="", bg=bg, fg=fg, font=("Segoe UI", 10, "bold"))
    info.place(x=28, y=180)

    state = {"done": 0, "total": 0, "speed": 0.0, "finished": False, "error": None}

    def progress(done, total, speed):
        state.update(done=done, total=total, speed=speed)

    def worker():
        try:
            download(dest, progress)
        except Exception as exc:
            state["error"] = exc
        state["finished"] = True

    def tick():
        done, total = state["done"], state["total"]
        frac = done / total if total else 0.0
        cv.coords(bar, 0, 0, (w - 56) * frac, 8)
        mb = f"{done / 1e6:.0f} / {total / 1e6:.0f} MB" if total else f"{done / 1e6:.0f} MB"
        info.configure(text=f"{frac * 100:.0f}%   ·   {mb}   ·   {state['speed'] / 1e6:.1f} MB/s")
        if state["error"] is not None:
            status.configure(text=f"{t[3]}: {state['error']}\n{t[4]}", fg="#F87171")
            return
        if state["finished"]:
            status.configure(text=t[2])
            launch(dest)
            root.after(800, root.destroy)
            return
        root.after(80, tick)

    threading.Thread(target=worker, daemon=True).start()
    tick()
    root.mainloop()


if __name__ == "__main__":
    main()
