# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QMenu, QToolButton, QVBoxLayout

from uiv_studio.core.storage import delete_recording, duplicate_recording, list_recordings
from uiv_studio.ui import icons
from uiv_studio.ui.dialogs import ask_text, confirm, error_box
from uiv_studio.ui.i18n import tr
from uiv_studio.ui.pages.common import FlowGrid, Page, fmt_date
from uiv_studio.ui.theme import C
from uiv_studio.ui.widgets import EmptyState, HoverCard, IconBadge, PageHeader, button, fade_in, label


class RecordingCard(HoverCard):
    def __init__(self, rec: dict, page):
        super().__init__(clickable=True)
        self.rec, self.page = rec, page
        self.setMinimumHeight(168)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 14, 14)
        lay.setSpacing(6)
        top = QHBoxLayout()
        top.addWidget(IconBadge("layers", (C["accent"], C["cyan"]), 36))
        top.addStretch()
        more = QToolButton()
        more.setIcon(icons.icon("more", C["text2"], 18))
        more.setIconSize(QSize(18, 18))
        more.setCursor(Qt.PointingHandCursor)
        more.clicked.connect(self._menu)
        self.more = more
        top.addWidget(more)
        lay.addLayout(top)
        n = label(rec["name"])
        n.setStyleSheet("font-size: 11.5pt; font-weight: 650; background: transparent;")
        lay.addWidget(n)
        if rec["description"]:
            d = label(rec["description"], "Muted")
            d.setStyleSheet("background: transparent;")
            lay.addWidget(d)
        meta = label(f"{rec['steps']} {tr('common.steps')}  ·  {rec['screen']}  ·  {fmt_date(rec['created_at'])}", "Faint")
        meta.setStyleSheet("background: transparent;")
        lay.addWidget(meta)
        lay.addStretch()
        row = QHBoxLayout()
        row.setSpacing(8)
        e = button(tr("rec.edit"), "edit")
        r = button(tr("rec.run"), "play", "Primary")
        e.clicked.connect(lambda: page.app.open_editor(rec["path"]))
        r.clicked.connect(lambda: page.app.run_recording(rec["path"]))
        row.addWidget(e)
        row.addWidget(r)
        row.addStretch()
        lay.addLayout(row)
        self.clicked.connect(lambda: page.app.open_editor(rec["path"]))

    def _menu(self):
        m = QMenu(self)
        m.addAction(icons.icon("copy", C["text"]), tr("common.duplicate"), self._duplicate)
        m.addSeparator()
        m.addAction(icons.icon("trash", C["danger"]), tr("common.delete"), self._delete)
        m.exec(self.more.mapToGlobal(self.more.rect().bottomLeft()))

    def _duplicate(self):
        name = ask_text(self, tr("common.duplicate"), tr("rec.dup_name"), f"{self.rec['name']} (2)")
        if name:
            try:
                duplicate_recording(self.rec["path"], name)
                self.page.refresh()
            except FileExistsError:
                error_box(self, tr("rec.exists"))

    def _delete(self):
        if confirm(self, tr("common.confirm_delete", name=self.rec["name"])):
            delete_recording(self.rec["path"])
            self.page.refresh()


class RecordingsPage(Page):
    def __init__(self, app):
        super().__init__(app)
        head = PageHeader(tr("rec.title"), tr("rec.subtitle"))
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("common.search"))
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(260)
        self.search.addAction(icons.icon("search", C["text3"], 16), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self._populate)
        new = button(tr("rec.new"), "plus", "Primary")
        new.clicked.connect(app.new_recording)
        head.actions.addWidget(self.search)
        head.actions.addWidget(new)
        self.body.addWidget(head)
        self.grid = FlowGrid(320)
        self.body.addWidget(self.grid)
        self.empty = EmptyState("layers", tr("rec.empty"))
        self.empty.setMinimumHeight(300)
        self.body.addWidget(self.empty)
        self.body.addStretch()
        self.recs = []

    def refresh(self):
        self.recs = list_recordings(self.app.settings.workspace)
        self._populate()

    def _populate(self):
        q = self.search.text().strip().lower()
        recs = [r for r in self.recs if not q or q in r["name"].lower() or q in r["description"].lower()]
        cards = [RecordingCard(r, self) for r in recs]
        self.grid.set_items(cards)
        for i, c in enumerate(cards):
            fade_in(c, delay=min(i, 12) * 35)
        self.empty.setVisible(not recs)
