"""PyInstaller entry point (keeps the package importable as `uiv_studio`)."""

import multiprocessing
import sys

from uiv_studio.app import run

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(run())
