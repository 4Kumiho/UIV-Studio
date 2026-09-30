# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from uiv_studio.core.screens import wayland_session
from uiv_studio.core.storage import list_recordings, list_runs
from uiv_studio.ui import icons
from uiv_studio.ui.i18n import tr
from uiv_studio.ui.pages.common import GradientTitle, Page, fmt_date
from uiv_studio.ui.theme import C, STATUS_COLORS
from uiv_studio.ui.widgets import ActionTile, Badge, EmptyState, HoverCard, StatCard, fade_in, label


class RunRow(HoverCard):
    def __init__(self, run: dict, on_open):
        super().__init__(clickable=True)
        self.setFixedHeight(62)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(12)
        res = run["result"] or ""
        color = STATUS_COLORS.get(res, C["text3"])
        dot = QLabel()
        dot.setPixmap(icons.pixmap("dot", color, 14))
        dot.setStyleSheet("background: transparent;")
        lay.addWidget(dot)
        col = QVBoxLayout()
        col.setSpacing(0)
        n = label(run["recording"])
        n.setStyleSheet("font-weight: 600; background: transparent;")
        d = label(fmt_date(run["started_at"]), "Faint")
        d.setStyleSheet("background: transparent;")
        col.addWidget(n)
        col.addWidget(d)
        lay.addLayout(col, 1)
        c = run["counts"]
        stats = label(f"✓ {c.get('PASSED', 0)}    ✗ {c.get('FAILED', 0)}    ⤼ {c.get('SKIPPED', 0) + c.get('STOPPED', 0)}", "Muted")
        stats.setStyleSheet("background: transparent;")
        lay.addWidget(stats)
        lay.addSpacing(10)
        lay.addWidget(Badge(tr(f"status.{res}"), color))
        self.clicked.connect(lambda: on_open(run["path"]))


class HomePage(Page):
    def __init__(self, app):
        super().__init__(app)
        b = self.body
        b.setSpacing(22)

        if wayland_session():
            warn = label("⚠  " + tr("home.wayland"), wrap=True)
            warn.setStyleSheet(f"background: {C['warning_dim']}; color: {C['warning']}; border-radius: 10px; padding: 12px 14px;")
            b.addWidget(warn)

        hero = QVBoxLayout()
        hero.setSpacing(6)
        hero.addWidget(label(tr("home.eyebrow"), "Eyebrow"))
        hero.addWidget(GradientTitle(tr("home.title"), (C["text"], C["accent2"], C["cyan"]), 28))
        hero.addWidget(label(tr("home.subtitle"), "Muted"))
        b.addLayout(hero)

        tiles = QHBoxLayout()
        tiles.setSpacing(16)
        t1 = ActionTile("record", tr("home.new_recording"), tr("home.new_recording_sub"), ("#F472B6", "#7C6CFF"))
        t2 = ActionTile("play", tr("home.run"), tr("home.run_sub"), ("#7C6CFF", "#3DD6D0"))
        t3 = ActionTile("library", tr("home.library"), tr("home.library_sub"), ("#3DD6D0", "#60A5FA"))
        t1.clicked.connect(app.new_recording)
        t2.clicked.connect(lambda: app.run_recording())
        t3.clicked.connect(lambda: app.navigate(1))
        self._animated = [t1, t2, t3]
        for t in (t1, t2, t3):
            tiles.addWidget(t)
        b.addLayout(tiles)

        stats = QHBoxLayout()
        stats.setSpacing(16)
        self.s_rec = StatCard("layers", tr("home.stat_recordings"), C["accent"])
        self.s_runs = StatCard("runs", tr("home.stat_runs"), C["cyan"])
        self.s_pass = StatCard("shield", tr("home.stat_pass"), C["success"])
        for s in (self.s_rec, self.s_runs, self.s_pass):
            stats.addWidget(s)
            self._animated.append(s)
        b.addLayout(stats)

        b.addWidget(label(tr("home.recent_runs"), "H3"))
        self.recent = QVBoxLayout()
        self.recent.setSpacing(8)
        b.addLayout(self.recent)
        b.addStretch()

    def refresh(self):
        ws = self.app.settings.workspace
        recs = list_recordings(ws)
        runs = list_runs(ws)
        self.s_rec.set_value(len(recs))
        self.s_runs.set_value(len(runs))
        done = [r for r in runs if r["result"] in ("PASSED", "FAILED")]
        rate = round(100 * sum(r["result"] == "PASSED" for r in done) / len(done)) if done else 0
        self.s_pass.set_value(rate, "%")
        while self.recent.count():
            w = self.recent.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not runs:
            e = EmptyState("runs", tr("home.no_runs"))
            e.setMinimumHeight(140)
            self.recent.addWidget(e)
        for i, r in enumerate(runs[:6]):
            row = RunRow(r, self.app.open_report)
            self.recent.addWidget(row)
            fade_in(row, delay=40 * i)
        for i, w in enumerate(self._animated):
            fade_in(w, delay=30 * i)
