# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

import multiprocessing
import sys

from uiv_studio.app import run

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(run())
