# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Native Wayland Qt app used as the system under test. Logs every interaction."""

import json
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QGridLayout, QLabel, QLineEdit, QPushButton, QWidget

LOG = "/tmp/target.log"


def log(msg):
    with open(LOG, "a") as f:
        f.write(msg + "\n")


class Target(QWidget):
    def __init__(self, offset=0):
        super().__init__()
        self.setStyleSheet("QWidget { background: #1e1e2e; color: white; font-size: 22px; }"
                           "QPushButton { background: #5b5bd6; border: 2px solid #9a9aff; padding: 14px; }"
                           "QLineEdit { background: white; color: black; padding: 8px; }")
        g = QGridLayout(self)
        g.setContentsMargins(60 + offset, 60 + offset, 60, 60)
        g.addWidget(QLabel("Demo App"), 0, 0)
        self.buttons = {}
        for i, name in enumerate(("Login", "Settings", "Save file")):
            b = QPushButton(name)
            b.setMinimumSize(220, 70)
            b.clicked.connect(lambda _=False, n=name: log(f"click {n}"))
            g.addWidget(b, 1, i)
            self.buttons[name] = b
        self.edit = QLineEdit()
        self.edit.setMinimumHeight(60)
        self.edit.textChanged.connect(lambda t: log(f"text {t}"))
        self.edit.returnPressed.connect(lambda: log("enter"))
        g.addWidget(self.edit, 2, 0, 1, 3)
        g.setRowStretch(3, 1)

    def dump(self):
        geo = {n: [b.mapTo(self, b.rect().topLeft()).x(), b.mapTo(self, b.rect().topLeft()).y(), b.width(), b.height()]
               for n, b in self.buttons.items()}
        e = self.edit
        geo["edit"] = [e.mapTo(self, e.rect().topLeft()).x(), e.mapTo(self, e.rect().topLeft()).y(), e.width(), e.height()]
        with open("/tmp/target_geometry.json", "w") as f:
            json.dump(geo, f)
        log("ready")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Target(offset=int(sys.argv[1]) if len(sys.argv) > 1 else 0)
    w.showFullScreen()
    QTimer.singleShot(1500, w.dump)
    app.exec()
