from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout

from uiv_studio.core.storage import delete_run, list_runs
from uiv_studio.ui import icons
from uiv_studio.ui.dialogs import confirm
from uiv_studio.ui.i18n import tr
from uiv_studio.ui.pages.common import Page, fmt_date, fmt_duration
from uiv_studio.ui.theme import C, STATUS_COLORS
from uiv_studio.ui.widgets import Badge, EmptyState, HoverCard, PageHeader, button, fade_in, label


class RunCard(HoverCard):
    def __init__(self, run: dict, page):
        res = run["result"] or ""
        color = STATUS_COLORS.get(res, C["text3"])
        super().__init__(clickable=True, accent=color)
        self.setFixedHeight(76)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 0, 14, 0)
        lay.setSpacing(14)
        ic = QLabel()
        ic.setPixmap(icons.pixmap({"PASSED": "check", "FAILED": "x"}.get(res, "alert"), color, 22, 2.2))
        ic.setStyleSheet("background: transparent;")
        lay.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(2)
        n = label(run["recording"])
        n.setStyleSheet("font-weight: 650; font-size: 11pt; background: transparent;")
        d = label(f"{fmt_date(run['started_at'])}   ·   {tr('rep.duration')} {fmt_duration(run['started_at'], run['ended_at'])}", "Faint")
        d.setStyleSheet("background: transparent;")
        col.addWidget(n)
        col.addWidget(d)
        lay.addLayout(col, 1)
        c = run["counts"]
        for key, col_ in (("PASSED", C["success"]), ("FAILED", C["danger"]), ("SKIPPED", C["text3"])):
            v = c.get(key, 0) + (c.get("STOPPED", 0) if key == "SKIPPED" else 0)
            lb = QLabel(f"<span style='color:{col_}; font-weight:700'>{v}</span> <span style='color:{C['text3']}'>{tr('status.' + key).lower()}</span>")
            lb.setStyleSheet("background: transparent;")
            lay.addWidget(lb)
            lay.addSpacing(6)
        lay.addWidget(Badge(tr(f"status.{res}"), color))
        rm = QToolButton()
        rm.setIcon(icons.icon("trash", C["text3"], 18))
        rm.setIconSize(QSize(18, 18))
        rm.setCursor(Qt.PointingHandCursor)
        rm.clicked.connect(lambda: page.delete(run))
        lay.addWidget(rm)
        self.clicked.connect(lambda: page.app.open_report(run["path"]))


class RunsPage(Page):
    def __init__(self, app):
        super().__init__(app)
        head = PageHeader(tr("runs.title"), tr("runs.subtitle"))
        run = button(tr("home.run"), "play", "Primary")
        run.clicked.connect(lambda: app.run_recording())
        head.actions.addWidget(run)
        self.body.addWidget(head)
        self.list = QVBoxLayout()
        self.list.setSpacing(10)
        self.body.addLayout(self.list)
        self.body.addStretch()

    def refresh(self):
        while self.list.count():
            w = self.list.takeAt(0).widget()
            if w:
                w.deleteLater()
        runs = list_runs(self.app.settings.workspace)
        if not runs:
            e = EmptyState("runs", tr("runs.empty"))
            e.setMinimumHeight(300)
            self.list.addWidget(e)
        for i, r in enumerate(runs):
            card = RunCard(r, self)
            self.list.addWidget(card)
            fade_in(card, delay=min(i, 12) * 30)

    def delete(self, run):
        if confirm(self, tr("common.confirm_delete", name=f"{run['recording']} · {fmt_date(run['started_at'])}")):
            delete_run(run["path"])
            self.refresh()
