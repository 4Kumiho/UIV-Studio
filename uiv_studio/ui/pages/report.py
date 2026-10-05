# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Run report: step results, expected vs found, scores, synced video, HTML export."""

import base64
import html
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QScrollArea, QSplitter, QVBoxLayout, QWidget)

from uiv_studio.core.models import Action
from uiv_studio.core.storage import Recording, Run
from uiv_studio.ui import icons
from uiv_studio.ui.i18n import tr
from uiv_studio.ui.icons import ACTION_ICONS
from uiv_studio.ui.pages.common import fmt_date, fmt_duration
from uiv_studio.ui.theme import ACTION_COLORS, C, STATUS_COLORS
from uiv_studio.ui.video_player import VideoPlayer
from uiv_studio.ui.widgets import Badge, ScoreBar, button, fade_in, label


def _pm(data: bytes) -> QPixmap:
    pm = QPixmap()
    if data:
        pm.loadFromData(data, "PNG")
    return pm


class ResultRow(QWidget):
    def __init__(self, rs, ref_step):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 12, 6)
        lay.setSpacing(10)
        color = STATUS_COLORS.get(rs.status, C["text3"])
        st = QLabel()
        st.setPixmap(icons.pixmap({"PASSED": "check", "FAILED": "x"}.get(rs.status, "skip"), color, 16, 2.4))
        lay.addWidget(st)
        num = QLabel(str(rs.idx))
        num.setFixedWidth(22)
        num.setStyleSheet(f"color: {C['text3']}; font-weight: 700;")
        lay.addWidget(num)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(ACTION_ICONS.get(rs.action, "pointer"), ACTION_COLORS.get(rs.action, C["accent"]), 16))
        lay.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(0)
        t = QLabel(tr(f"action.{rs.action}"))
        t.setStyleSheet("font-weight: 600;")
        col.addWidget(t)
        sub = ""
        if ref_step is not None and ref_step.target is not None and ref_step.target.ocr_text:
            sub = ref_step.target.ocr_text
        elif ref_step is not None and ref_step.action == Action.INPUT:
            sub = f"“{ref_step.text}”"
        if sub:
            s = QLabel(sub)
            s.setStyleSheet(f"color: {C['text3']}; font-size: 8.5pt;")
            s.setMaximumWidth(170)
            col.addWidget(s)
        lay.addLayout(col, 1)
        if rs.match is not None:
            sc = QLabel(f"{rs.match.score * 100:.0f}%")
            sc.setStyleSheet(f"color: {color}; font-weight: 700;")
            lay.addWidget(sc)


class ReportPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.run_path = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QFrame()
        bar.setStyleSheet(f"QFrame {{ background: {C['bg2']}; border-bottom: 1px solid {C['border']}; }}")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 10, 16, 10)
        bl.setSpacing(10)
        back = button("", "back", "Ghost")
        back.clicked.connect(lambda: app.navigate(2))
        bl.addWidget(back)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        self.sub = label("", "Faint")
        col.addWidget(self.title)
        col.addWidget(self.sub)
        bl.addLayout(col)
        self.badge = Badge("", C["text3"])
        bl.addWidget(self.badge)
        bl.addSpacing(12)
        self.stats = QLabel()
        bl.addWidget(self.stats)
        bl.addStretch()
        folder = button(tr("rep.open_folder"), "folder")
        folder.clicked.connect(self._open_folder)
        export = button(tr("rep.export"), "file")
        export.clicked.connect(self._export)
        rerun = button(tr("rep.rerun"), "play", "Primary")
        rerun.clicked.connect(self._rerun)
        for w in (folder, export, rerun):
            bl.addWidget(w)
        root.addWidget(bar)

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(1)
        root.addWidget(split, 1)
        left = QWidget()
        left.setMinimumWidth(290)
        left.setMaximumWidth(360)
        left.setObjectName("SidePanel")
        left.setStyleSheet(f"#SidePanel {{ background: {C['bg2']}; }}")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 12, 8, 8)
        ll.addWidget(label(f"  {tr('ed.steps')}", "Eyebrow"))
        self.list = QListWidget()
        self.list.setStyleSheet(f"""
            QListWidget::item {{ border: 1px solid transparent; border-radius: 10px; margin: 1px 4px; }}
            QListWidget::item:hover {{ background: {C['surface2']}; }}
            QListWidget::item:selected {{ background: {C['accent_dim']}; border: 1px solid {C['accent']}; }}""")
        self.list.currentRowChanged.connect(self._select)
        ll.addWidget(self.list, 1)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(18, 16, 18, 16)
        rl.setSpacing(14)
        vsplit = QSplitter(Qt.Vertical)
        vsplit.setHandleWidth(8)
        vsplit.setStyleSheet("QSplitter::handle { background: transparent; }")
        self.player = VideoPlayer()
        self.player.marker_clicked.connect(self._marker)
        self.novideo = label(tr("rep.no_video"), "Muted")
        self.novideo.setAlignment(Qt.AlignCenter)
        vwrap = QWidget()
        vl = QVBoxLayout(vwrap)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.addWidget(self.player)
        vl.addWidget(self.novideo)
        vsplit.addWidget(vwrap)
        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        self.detail = QWidget()
        self.dl = QVBoxLayout(self.detail)
        self.dl.setContentsMargins(0, 0, 0, 0)
        self.dl.setSpacing(12)
        detail_scroll.setWidget(self.detail)
        vsplit.addWidget(detail_scroll)
        vsplit.setSizes([420, 360])
        rl.addWidget(vsplit)
        split.addWidget(right)
        split.setStretchFactor(1, 1)

    # ------------------------------------------------------------------
    def load(self, path):
        self.run_path = Path(path)
        run = Run(self.run_path)
        try:
            self.info = run.info()
            self.results = run.steps()
        finally:
            run.close()
        self.ref = {}
        try:
            rec = Recording(Path(self.info.recording_path))
            self.ref = {s.idx: s for s in rec.steps()}
            rec.close()
        except Exception:
            pass
        i = self.info
        self.title.setText(i.recording_name)
        self.sub.setText(f"{fmt_date(i.started_at)} · {tr('rep.duration')} {fmt_duration(i.started_at, i.ended_at)} · "
                         f"{i.screen_w}×{i.screen_h} @ {round(i.scale * 100)}%")
        color = STATUS_COLORS.get(i.result, C["text3"])
        self.badge.set(tr(f"status.{i.result}"), color)
        cnt = {s: sum(r.status == s for r in self.results) for s in ("PASSED", "FAILED", "SKIPPED", "STOPPED")}
        self.stats.setText(
            f"<span style='color:{C['success']};font-weight:700'>{cnt['PASSED']}</span> {tr('rep.passed').lower()} &nbsp; "
            f"<span style='color:{C['danger']};font-weight:700'>{cnt['FAILED']}</span> {tr('rep.failed').lower()} &nbsp; "
            f"<span style='color:{C['text2']};font-weight:700'>{cnt['SKIPPED'] + cnt['STOPPED']}</span> {tr('rep.skipped').lower()}")
        self.list.clear()
        for r in self.results:
            it = QListWidgetItem()
            it.setSizeHint(QSize(250, 50))
            self.list.addItem(it)
            self.list.setItemWidget(it, ResultRow(r, self.ref.get(r.idx)))
        video = str(self.run_path.parent / i.video) if i.video else None
        has_video = self.player.load(video) if video and os.path.exists(video) else False
        self.player.setVisible(has_video)
        self.novideo.setVisible(not has_video)
        self.player.set_markers([(r.started_s, STATUS_COLORS.get(r.status, C["text3"]), r.idx)
                                 for r in self.results if r.status in ("PASSED", "FAILED")])
        first_fail = next((k for k, r in enumerate(self.results) if r.status == "FAILED"), 0)
        if self.results:
            self.list.setCurrentRow(first_fail)

    def _marker(self, idx):
        for k, r in enumerate(self.results):
            if r.idx == idx:
                self.list.setCurrentRow(k)
                return

    def _select(self, row):
        if row < 0 or row >= len(self.results):
            return
        r = self.results[row]
        self.player.select_marker(r.idx)
        if r.status in ("PASSED", "FAILED"):
            self.player.seek(r.started_s)
        while self.dl.count():
            it = self.dl.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        ref = self.ref.get(r.idx)
        head = QHBoxLayout()
        t = label(f"{tr('hud.step', n=r.idx)} · {tr('action.' + r.action)}", "H2")
        head.addWidget(t)
        head.addWidget(Badge(tr(f"status.{r.status}"), STATUS_COLORS.get(r.status, C["text3"])))
        head.addStretch()
        if r.duration_s:
            head.addWidget(label(f"{r.duration_s:.1f} s", "Faint"))
        hw = QWidget()
        hw.setLayout(head)
        self.dl.addWidget(hw)
        if r.error:
            e = label(r.error.splitlines()[0], wrap=True)
            e.setStyleSheet(f"color: {C['danger']}; background: {C['danger_dim']}; border-radius: 8px; padding: 8px 10px;")
            self.dl.addWidget(e)
        if r.match is None:
            self.dl.addWidget(label(tr("rep.no_match_data"), "Muted"))
        else:
            self.dl.addWidget(self._match_card(r.match, ref.target if ref else None, None))
            if r.action == Action.DRAG:
                self.dl.addWidget(label(tr("rep.drop"), "H3"))
                self.dl.addWidget(self._match_card(r.drop_match, ref.drop if ref else None, None))
        self.dl.addStretch()
        fade_in(self.detail, 220, dy=0)

    def _match_card(self, m, target, _):
        card = QFrame()
        card.setObjectName("Card")
        g = QGridLayout(card)
        g.setContentsMargins(16, 14, 16, 16)
        g.setHorizontalSpacing(18)
        g.setVerticalSpacing(8)
        g.addWidget(label(tr("rep.expected"), "Eyebrow"), 0, 0)
        g.addWidget(label(tr("rep.found"), "Eyebrow"), 0, 1)
        for col, data in ((0, target.template if target else b""), (1, m.crop if m else b"")):
            img = QLabel()
            img.setAlignment(Qt.AlignCenter)
            img.setMinimumHeight(90)
            img.setStyleSheet(f"background: {C['bg']}; border: 1px solid {C['border']}; border-radius: 8px; padding: 6px;")
            pm = _pm(data)
            if pm.isNull():
                img.setText(tr("rep.not_found") if col == 1 else "—")
            else:
                img.setPixmap(pm.scaled(360, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            g.addWidget(img, 1, col)
        if target is not None:
            g.addWidget(label(f"OCR: {target.ocr_text or '—'}", "Faint"), 2, 0)
        if m is not None:
            g.addWidget(label(f"OCR: {m.ocr_text or '—'}", "Faint"), 2, 1)
        if m is None:
            return card
        thr = self.app.settings.data["validation"]["threshold"]
        bars = QVBoxLayout()
        bars.setSpacing(4)
        bars.addWidget(ScoreBar(tr("rep.score"), m.score, thr))
        bars.addWidget(ScoreBar(tr("rep.template"), m.template))
        if m.ocr is not None:
            bars.addWidget(ScoreBar(tr("rep.ocr"), m.ocr))
        bars.addWidget(ScoreBar(tr("rep.visual"), m.visual))
        bw = QWidget()
        bw.setLayout(bars)
        g.addWidget(bw, 3, 0, 1, 2)
        method = tr(f"rep.method.{m.method}") if m.method else "—"
        g.addWidget(label(f"{tr('rep.stage', n=m.stage)} · {method} · x {m.x}  y {m.y}  ·  {m.w}×{m.h}", "Faint"), 4, 0, 1, 2)
        return card

    # ------------------------------------------------------------------
    def _open_folder(self):
        folder = str(self.run_path.parent)
        if sys.platform == "win32":
            os.startfile(folder)
        else:
            from uiv_studio.core.paths import system_env
            subprocess.Popen(["xdg-open", folder], env=system_env())

    def _rerun(self):
        self.app.run_recording(self.info.recording_path)

    def _export(self):
        default = str(self.run_path.parent / "report.html")
        path, _ = QFileDialog.getSaveFileName(self, tr("rep.export"), default, "HTML (*.html)")
        if not path:
            return
        Path(path).write_text(build_html_report(self.info, self.results, self.ref), encoding="utf-8")
        self.app.toast(tr("rep.exported"), "success")

    def release(self):
        self.player.release()


def build_html_report(info, results, ref) -> str:
    def img(data):
        return f"<img src='data:image/png;base64,{base64.b64encode(data).decode()}'>" if data else "<span class='na'>—</span>"

    rows = []
    for r in results:
        st = ref.get(r.idx)
        m = r.match
        color = STATUS_COLORS.get(r.status, "#888")
        parts = ""
        if m:
            ocr = "—" if m.ocr is None else f"{m.ocr * 100:.0f}"
            parts = f"{m.template * 100:.0f} / {ocr} / {m.visual * 100:.0f}"
        score = f"{m.score * 100:.1f}%" if m else ""
        err = html.escape(r.error.splitlines()[0]) if r.error else ""
        rows.append(
            f"<tr><td>{r.idx}</td><td>{html.escape(tr('action.' + r.action))}</td>"
            f"<td><span class='b' style='color:{color};border-color:{color}'>{html.escape(tr('status.' + r.status))}</span></td>"
            f"<td>{img(st.target.template) if st and st.target else ''}</td>"
            f"<td>{img(m.crop) if m else ''}</td>"
            f"<td>{score}</td><td>{parts}</td>"
            f"<td>{r.duration_s:.1f}s</td><td class='err'>{err}</td></tr>")
    color = STATUS_COLORS.get(info.result, "#888")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>UIV Studio — {html.escape(info.recording_name)}</title>
<style>
body{{background:#0B0D12;color:#E8ECF4;font-family:Inter,Segoe UI,system-ui,sans-serif;margin:32px}}
h1{{margin:0 0 4px}} .muted{{color:#A3ACBF}} table{{border-collapse:collapse;width:100%;margin-top:24px}}
th,td{{padding:10px;border-bottom:1px solid #262D3B;text-align:left;vertical-align:middle}}
th{{color:#A3ACBF;font-size:12px;text-transform:uppercase;letter-spacing:1px}}
img{{max-width:260px;max-height:90px;border:1px solid #262D3B;border-radius:6px}}
.b{{border:1px solid;border-radius:9px;padding:2px 9px;font-size:12px;font-weight:700}} .err{{color:#F87171}} .na{{color:#6B7489}}
</style></head><body>
<h1>{html.escape(info.recording_name)} <span class='b' style='color:{color};border-color:{color}'>{html.escape(tr('status.' + info.result))}</span></h1>
<div class='muted'>{fmt_date(info.started_at)} · {tr('rep.duration')} {fmt_duration(info.started_at, info.ended_at)} · {info.screen_w}×{info.screen_h} @ {round(info.scale * 100)}%</div>
<table><tr><th>#</th><th>{tr('ed.action')}</th><th>Status</th><th>{tr('rep.expected')}</th><th>{tr('rep.found')}</th>
<th>{tr('rep.score')}</th><th>{tr('rep.template')} / OCR / {tr('rep.visual')}</th><th>{tr('rep.duration')}</th><th></th></tr>
{''.join(rows)}</table><p class='muted'>UIV Studio</p></body></html>"""
