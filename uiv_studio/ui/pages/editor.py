"""Recording editor: step list, screenshot canvas with editable targets, properties."""

import copy
import time
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                               QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMenu, QPlainTextEdit, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QVBoxLayout,
                               QWidget)

from uiv_studio.core.keys import MODIFIERS
from uiv_studio.core.models import Action, Step, Target
from uiv_studio.core.screens import ScreenGrabber, list_monitors
from uiv_studio.core.storage import Recording, list_recordings
from uiv_studio.engine.targets import rebuild_target
from uiv_studio.ui import icons
from uiv_studio.ui.dialogs import BaseDialog, ask_text, confirm, error_box
from uiv_studio.ui.i18n import tr
from uiv_studio.ui.canvas import Canvas
from uiv_studio.ui.theme import ACTION_COLORS, C
from uiv_studio.ui.icons import ACTION_ICONS
from uiv_studio.ui.widgets import Badge, EmptyState, HotkeyEdit, Spinner, button, label
from uiv_studio.vision.imageio import from_png, to_png


def png_pixmap(data: bytes) -> QPixmap:
    pm = QPixmap()
    if data:
        pm.loadFromData(data, "PNG")
    return pm


def step_summary(s: Step) -> str:
    if s.action == Action.INPUT:
        return f"“{s.text}”" + ("  ⏎" if s.enter_after else "")
    if s.action == Action.KEY:
        return s.key.replace("+", " + ").upper()
    if s.action == Action.WAIT:
        return f"{s.wait_s:g} s"
    t = s.target
    txt = (t.ocr_text if t and t.ocr_text else "")
    if s.action == Action.SCROLL:
        txt = f"{txt}  ↕ {s.scroll_dy}" if txt else f"↕ {s.scroll_dy}  ↔ {s.scroll_dx}"
    mods = " + ".join(m.upper() for m in s.modifiers)
    return f"{mods} · {txt}" if mods and txt else mods or txt or "—"


class StepRow(QWidget):
    def __init__(self, s: Step):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)
        color = ACTION_COLORS.get(s.action, C["accent"])
        self.num = QLabel(str(s.idx))
        self.num.setFixedSize(26, 26)
        self.num.setAlignment(Qt.AlignCenter)
        self.num.setStyleSheet(f"background: {C['surface3']}; border-radius: 13px; font-weight: 700; font-size: 8.5pt; color: {C['text2']};")
        lay.addWidget(self.num)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(ACTION_ICONS.get(s.action, "pointer"), color, 18))
        lay.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(0)
        t = QLabel(tr(f"action.{s.action}"))
        t.setStyleSheet("font-weight: 650;")
        sub = QLabel(step_summary(s))
        sub.setStyleSheet(f"color: {C['text3']}; font-size: 8.5pt;")
        sub.setMaximumWidth(170)
        col.addWidget(t)
        col.addWidget(sub)
        lay.addLayout(col, 1)
        if s.target and s.target.template:
            th = QLabel()
            pm = png_pixmap(s.target.template)
            if not pm.isNull():
                th.setPixmap(pm.scaled(64, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            th.setStyleSheet(f"border: 1px solid {C['border']}; border-radius: 4px;")
            lay.addWidget(th)


class StepList(QListWidget):
    moved = Signal(int, int)  # step id, new 1-based index

    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSpacing(2)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setStyleSheet(f"""
            QListWidget::item {{ border: 1px solid transparent; border-radius: 10px; margin: 1px 4px; }}
            QListWidget::item:hover {{ background: {C['surface2']}; }}
            QListWidget::item:selected {{ background: {C['accent_dim']}; border: 1px solid {C['accent']}; }}
        """)

    def dropEvent(self, e):
        item = self.currentItem()
        super().dropEvent(e)
        if item is not None:
            self.moved.emit(item.data(Qt.UserRole), self.row(item) + 1)


class EditorPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.rec: Recording | None = None
        self.steps: list[Step] = []
        self.cur: Step | None = None
        self.dirty = False
        self.geom_dirty: set[str] = set()
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ------------------------------------------------------------ toolbar
        bar = QFrame()
        bar.setStyleSheet(f"QFrame {{ background: {C['bg2']}; border-bottom: 1px solid {C['border']}; }}")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 10, 16, 10)
        bl.setSpacing(8)
        back = button("", "back", "Ghost")
        back.setToolTip(tr("common.back"))
        back.clicked.connect(self._back)
        bl.addWidget(back)
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        bl.addWidget(self.title)
        rename = button("", "edit", "Ghost")
        rename.setToolTip(tr("ed.rename"))
        rename.clicked.connect(self._rename)
        bl.addWidget(rename)
        self.meta = label("", "Faint")
        bl.addWidget(self.meta)
        self.dirty_badge = Badge(tr("ed.unsaved"), C["warning"])
        self.dirty_badge.hide()
        bl.addWidget(self.dirty_badge)
        bl.addStretch()
        self.spinner = Spinner(20)
        self.spinner.hide()
        bl.addWidget(self.spinner)
        add = button(tr("ed.add"), "plus")
        add.clicked.connect(lambda: self._add_menu(add))
        dup = button("", "copy")
        dup.setToolTip(tr("common.duplicate"))
        dup.clicked.connect(self._duplicate)
        rm = button("", "trash")
        rm.setToolTip(tr("common.delete"))
        rm.clicked.connect(self._delete)
        cap = button(tr("ed.recapture"), "camera")
        cap.setToolTip(tr("ed.recapture_tip"))
        cap.clicked.connect(self._recapture)
        merge = button("", "merge")
        merge.setToolTip(tr("ed.append_tip"))
        merge.clicked.connect(self._merge)
        self.save_btn = button(tr("common.save"), "save")
        self.save_btn.clicked.connect(self.save)
        run = button(tr("rec.run"), "play", "Primary")
        run.clicked.connect(self._run)
        for w in (add, dup, rm, cap, merge, self.save_btn, run):
            bl.addWidget(w)
        root.addWidget(bar)

        # ------------------------------------------------------------ body
        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(1)
        root.addWidget(split, 1)

        left = QWidget()
        left.setMinimumWidth(300)
        left.setMaximumWidth(380)
        left.setObjectName("SidePanel")
        left.setStyleSheet(f"#SidePanel {{ background: {C['bg2']}; }}")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 12, 8, 8)
        ll.addWidget(label(f"  {tr('ed.steps')}", "Eyebrow"))
        self.list = StepList()
        self.list.currentRowChanged.connect(self._select_row)
        self.list.moved.connect(self._moved)
        ll.addWidget(self.list, 1)
        split.addWidget(left)

        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        self.canvas = Canvas()
        self.canvas.targetChanged.connect(self._geometry_changed)
        cl.addWidget(self.canvas, 1)
        hint = label(tr("ed.hint"), "Faint", wrap=True)
        hint.setStyleSheet(f"background: {C['bg2']}; padding: 6px 10px; border-top: 1px solid {C['border']};")
        cl.addWidget(hint)
        self.empty = EmptyState("layers", tr("ed.no_steps"))
        self.empty.hide()
        cl.addWidget(self.empty)
        split.addWidget(center)

        right = QScrollArea()
        right.setWidgetResizable(True)
        right.setMinimumWidth(310)
        right.setMaximumWidth(380)
        right.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right.setStyleSheet(f"QScrollArea {{ background: {C['bg2']}; border-left: 1px solid {C['border']}; }}")
        props = QWidget()
        props.setObjectName("PropsPanel")
        props.setStyleSheet(f"#PropsPanel {{ background: {C['bg2']}; }}")
        self.props = QVBoxLayout(props)
        self.props.setContentsMargins(18, 16, 18, 16)
        self.props.setSpacing(10)
        right.setWidget(props)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        self._build_props()

        QShortcut(QKeySequence.Save, self, activated=self.save)
        QShortcut(QKeySequence.Delete, self.list, activated=self._delete)

    # ================================================================ props
    def _build_props(self):
        p = self.props
        p.addWidget(label(tr("ed.properties"), "Eyebrow"))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setVerticalSpacing(10)
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        self.f_action = QComboBox()
        for a in Action.ALL:
            self.f_action.addItem(icons.icon(ACTION_ICONS[a], ACTION_COLORS[a]), tr(f"action.{a}"), a)
        self.f_action.currentIndexChanged.connect(self._action_changed)
        form.addRow(tr("ed.action"), self.f_action)

        self.w_mods = QWidget()
        ml = QHBoxLayout(self.w_mods)
        ml.setContentsMargins(0, 0, 0, 0)
        self.f_mods = {}
        for m in MODIFIERS:
            cb = QCheckBox(m.capitalize())
            cb.toggled.connect(self._mark)
            ml.addWidget(cb)
            self.f_mods[m] = cb
        ml.addStretch()
        self.r_mods = self._row(form, tr("ed.modifiers"), self.w_mods)

        self.f_text = QPlainTextEdit()
        self.f_text.setFixedHeight(80)
        self.f_text.textChanged.connect(self._mark)
        self.r_text = self._row(form, tr("ed.text"), self.f_text)
        self.f_enter = QCheckBox(tr("ed.enter_after"))
        self.f_enter.toggled.connect(self._mark)
        self.r_enter = self._row(form, "", self.f_enter)

        self.f_key = HotkeyEdit()
        self.f_key.setMinimumWidth(0)
        self.f_key.changed.connect(self._mark)
        self.r_key = self._row(form, tr("ed.key"), self.f_key)

        sw = QWidget()
        sl = QHBoxLayout(sw)
        sl.setContentsMargins(0, 0, 0, 0)
        self.f_sdx, self.f_sdy = QSpinBox(), QSpinBox()
        for sb in (self.f_sdx, self.f_sdy):
            sb.setRange(-100, 100)
            sb.valueChanged.connect(self._mark)
            sl.addWidget(sb)
        self.r_scroll = self._row(form, tr("ed.scroll"), sw)

        self.f_wait = QDoubleSpinBox()
        self.f_wait.setRange(0, 3600)
        self.f_wait.setDecimals(1)
        self.f_wait.setSingleStep(0.5)
        self.f_wait.valueChanged.connect(self._mark)
        self.r_wait_label = QLabel(tr("ed.wait"))
        form.addRow(self.r_wait_label, self.f_wait)

        self.f_tc = QLineEdit()
        self.f_tc.textChanged.connect(self._mark)
        form.addRow(tr("ed.testcase"), self.f_tc)
        self.f_note = QLineEdit()
        self.f_note.textChanged.connect(self._mark)
        form.addRow(tr("ed.note"), self.f_note)
        p.addLayout(form)

        self.target_box = QWidget()
        tl = QVBoxLayout(self.target_box)
        tl.setContentsMargins(0, 8, 0, 0)
        tl.setSpacing(8)
        tl.addWidget(label(tr("ed.target"), "Eyebrow"))
        self.t_preview = QLabel()
        self.t_preview.setAlignment(Qt.AlignCenter)
        self.t_preview.setMinimumHeight(70)
        self.t_preview.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.t_preview.setStyleSheet(f"background: {C['bg']}; border: 1px solid {C['border']}; border-radius: 8px; padding: 6px;")
        tl.addWidget(self.t_preview)
        self.t_ocr = label("", "Muted", wrap=True)
        tl.addWidget(self.t_ocr)
        self.t_geom = label("", "Faint")
        tl.addWidget(self.t_geom)
        self.drop_preview = QLabel()
        self.drop_preview.setAlignment(Qt.AlignCenter)
        self.drop_preview.setStyleSheet(self.t_preview.styleSheet())
        self.drop_preview.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.drop_label = label(tr("ed.drop"), "Eyebrow")
        tl.addWidget(self.drop_label)
        tl.addWidget(self.drop_preview)
        p.addWidget(self.target_box)
        self.no_target = label(tr("ed.no_target"), "Faint", wrap=True)
        p.addWidget(self.no_target)
        p.addStretch()

    def _row(self, form: QFormLayout, title: str, w: QWidget):
        lab = QLabel(title)
        form.addRow(lab, w)
        return lab, w

    @staticmethod
    def _show_row(row, visible: bool):
        for w in row:
            w.setVisible(visible)

    # ================================================================ load
    def load(self, path: Path):
        if self.rec:
            self.rec.close()
        self.rec = Recording(Path(path))
        self.info = self.rec.info()
        self.title.setText(self.info.name)
        self.meta.setText(f"{self.info.screen_w}×{self.info.screen_h} @ {round(self.info.scale * 100)}%")
        self.steps = self.rec.steps()
        self.cur = None
        self._set_dirty(False)
        self._fill_list(0)

    def _fill_list(self, select: int):
        self.list.blockSignals(True)
        self.list.clear()
        for s in self.steps:
            it = QListWidgetItem()
            it.setData(Qt.UserRole, s.id)
            row = StepRow(s)
            it.setSizeHint(QSize(260, 56))
            self.list.addItem(it)
            self.list.setItemWidget(it, row)
        self.list.blockSignals(False)
        has = bool(self.steps)
        self.canvas.setVisible(has)
        self.empty.setVisible(not has)
        if has:
            self.list.setCurrentRow(min(max(select, 0), len(self.steps) - 1))
            self._select_row(self.list.currentRow())

    def _refresh_row(self, s: Step):
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(Qt.UserRole) == s.id:
                self.list.setItemWidget(it, StepRow(s))

    def _select_row(self, row: int):
        if row < 0 or row >= len(self.steps):
            return
        new = next((s for s in self.steps if s.id == self.list.item(row).data(Qt.UserRole)), None)
        if new is None or new is self.cur:
            return
        if self.cur is not None and self.dirty:
            self._commit_current()
        self.cur = new
        self._show_step(new, animate=True)

    def _show_step(self, s: Step, animate: bool):
        self._loading = True
        pm = png_pixmap(s.screenshot)
        self.canvas.set_image(pm)
        self._place_targets(s)
        self.f_action.setCurrentIndex(self.f_action.findData(s.action))
        for m, cb in self.f_mods.items():
            cb.setChecked(m in s.modifiers)
        self.f_text.setPlainText(s.text)
        self.f_enter.setChecked(s.enter_after)
        self.f_key.set_combo(s.key)
        self.f_sdx.setValue(s.scroll_dx)
        self.f_sdy.setValue(s.scroll_dy)
        self.f_wait.setValue(s.wait_s)
        self.f_tc.setText(s.testcase)
        self.f_note.setText(s.note)
        self._update_visibility()
        self._update_target_info()
        self._loading = False
        QTimer.singleShot(0, lambda: self.canvas.focus(
            QRectF(s.target.x, s.target.y, s.target.w, s.target.h) if s.target else None, animate))

    def _place_targets(self, s: Step):
        t, d = s.target, s.drop
        self.canvas.set_target("main", (t.x, t.y, t.w, t.h) if t else None, (t.click_x, t.click_y) if t else (0, 0),
                               ACTION_COLORS.get(s.action, C["accent"]), f"{s.idx} · {tr('action.' + s.action)}")
        self.canvas.set_target("drop", (d.x, d.y, d.w, d.h) if (d and s.action == Action.DRAG) else None,
                               (d.click_x, d.click_y) if d else (0, 0), C["cyan"], tr("ed.drop"))

    def _update_visibility(self):
        a = self.f_action.currentData()
        self._show_row(self.r_mods, a in Action.NEEDS_TARGET)
        self._show_row(self.r_text, a == Action.INPUT)
        self._show_row(self.r_enter, a == Action.INPUT)
        self._show_row(self.r_key, a == Action.KEY)
        self._show_row(self.r_scroll, a == Action.SCROLL)
        self.r_wait_label.setText(tr("ed.wait_duration") if a == Action.WAIT else tr("ed.wait"))
        has_target = a in Action.NEEDS_TARGET
        self.target_box.setVisible(has_target)
        self.no_target.setVisible(not has_target)
        is_drag = a == Action.DRAG
        self.drop_label.setVisible(is_drag)
        self.drop_preview.setVisible(is_drag)

    def _update_target_info(self):
        s = self.cur
        if not s or not s.target:
            self.t_preview.clear()
            return
        t = s.target
        pm = png_pixmap(t.template)
        if not pm.isNull():
            self.t_preview.setPixmap(pm.scaled(280, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.t_ocr.setText(f"{tr('ed.ocr')}: <b>{t.ocr_text or '—'}</b>")
        self.t_geom.setText(f"x {t.x}  y {t.y}  ·  {t.w}×{t.h}  ·  click ({t.click_x}, {t.click_y})")
        if s.drop:
            dp = png_pixmap(s.drop.template)
            if not dp.isNull():
                self.drop_preview.setPixmap(dp.scaled(280, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # ================================================================ editing
    def _mark(self, *_):
        if not self._loading:
            self._set_dirty(True)

    def _set_dirty(self, d: bool):
        self.dirty = d
        self.dirty_badge.setVisible(d)
        self.save_btn.setObjectName("Primary" if d else "")
        self.save_btn.setIcon(icons.icon("save", "#FFFFFF" if d else C["text"], 18))
        self.save_btn.style().unpolish(self.save_btn)
        self.save_btn.style().polish(self.save_btn)

    def _action_changed(self):
        if self._loading or not self.cur:
            return
        a = self.f_action.currentData()
        s = self.cur
        frame = from_png(s.screenshot)
        if a in Action.NEEDS_TARGET and s.target is None and frame is not None:
            h, w = frame.shape[:2]
            s.target = Target(w // 2 - 60, h // 2 - 20, 120, 40, 60, 20)
            self.geom_dirty.add("main")
        if a == Action.DRAG and s.drop is None and s.target is not None and frame is not None:
            t = s.target
            s.drop = Target(min(t.x + t.w + 80, frame.shape[1] - t.w), t.y, t.w, t.h, t.click_x, t.click_y)
            self.geom_dirty.add("drop")
        s.action = a
        self._place_targets(s)
        self._update_visibility()
        self._mark()

    def _geometry_changed(self, role: str):
        self.geom_dirty.add(role)
        vals = self.canvas.target_values(role)
        t = self.cur.target if role == "main" else self.cur.drop
        if vals and t:
            (t.x, t.y, t.w, t.h), (t.click_x, t.click_y) = vals
            self.t_geom.setText(f"x {t.x}  y {t.y}  ·  {t.w}×{t.h}  ·  click ({t.click_x}, {t.click_y})")
        self._mark()

    def _commit_current(self):
        """Write the property panel + geometry back into the current step and persist it."""
        s = self.cur
        if s is None:
            return
        s.action = self.f_action.currentData()
        s.modifiers = [m for m, cb in self.f_mods.items() if cb.isChecked()] if s.action in Action.NEEDS_TARGET else []
        s.text = self.f_text.toPlainText()
        s.enter_after = self.f_enter.isChecked()
        s.key = self.f_key.combo
        s.scroll_dx, s.scroll_dy = self.f_sdx.value(), self.f_sdy.value()
        s.wait_s = self.f_wait.value()
        s.testcase = self.f_tc.text().strip()
        s.note = self.f_note.text().strip()
        if s.action not in Action.NEEDS_TARGET:
            s.target = None
        if s.action != Action.DRAG:
            s.drop = None
        if self.geom_dirty:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.spinner.show()
            QApplication.processEvents()
            try:
                frame = from_png(s.screenshot)
                if frame is not None:
                    if s.target is not None and "main" in self.geom_dirty:
                        s.target = rebuild_target(frame, s.target)
                    if s.drop is not None and "drop" in self.geom_dirty:
                        s.drop = rebuild_target(frame, s.drop)
            finally:
                self.spinner.hide()
                QApplication.restoreOverrideCursor()
        self.rec.update_step(s)
        self.geom_dirty.clear()
        self._refresh_row(s)
        self._set_dirty(False)

    def save(self):
        if self.cur is not None and self.dirty:
            self._commit_current()
            self._update_target_info()
            self.app.toast(tr("common.saved"), "success")

    def maybe_save(self) -> bool:
        """Before leaving: persist pending edits (True = ok to leave)."""
        if self.dirty and self.cur is not None:
            self._commit_current()
        return True

    # ================================================================ structure
    def _current_index(self) -> int:
        return self.list.currentRow()

    def _reload(self, select: int):
        self.cur = None
        self.steps = self.rec.steps()
        self._fill_list(select)

    def _add_menu(self, anchor):
        m = QMenu(self)
        for a in Action.ALL:
            m.addAction(icons.icon(ACTION_ICONS[a], ACTION_COLORS[a]), tr(f"action.{a}"), lambda a=a: self._add(a))
        m.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _add(self, action: str):
        self.maybe_save()
        base = self.cur or (self.steps[-1] if self.steps else None)
        shot = base.screenshot if base else b""
        if not shot:
            frame = self._grab_frame()
            shot = to_png(frame) if frame is not None else b""
        s = Step(action=action, screenshot=shot, wait_s=1.0 if action == Action.WAIT else 0.0)
        frame = from_png(shot)
        if action in Action.NEEDS_TARGET and frame is not None:
            h, w = frame.shape[:2]
            base_t = base.target if base and base.target else Target(w // 2 - 60, h // 2 - 20, 120, 40, 60, 20)
            s.target = rebuild_target(frame, copy.copy(base_t))
            if action == Action.DRAG:
                t = s.target
                s.drop = rebuild_target(frame, Target(min(t.x + t.w + 80, w - t.w), t.y, t.w, t.h, t.click_x, t.click_y))
        idx = self._current_index() + 2 if self.steps else 1
        self.rec.add_step(s, index=idx)
        self._reload(idx - 1)

    def _duplicate(self):
        if not self.cur:
            return
        self.maybe_save()
        s = copy.deepcopy(self.cur)
        s.id = None
        idx = self._current_index() + 2
        self.rec.add_step(s, index=idx)
        self._reload(idx - 1)

    def _delete(self):
        if not self.cur:
            return
        row = self._current_index()
        self.rec.delete_step(self.cur.id)
        self._set_dirty(False)
        self._reload(row)

    def _moved(self, step_id: int, new_index: int):
        self.maybe_save()
        self.rec.move_step(step_id, new_index)
        self._reload(new_index - 1)

    def _rename(self):
        name = ask_text(self, tr("ed.rename"), tr("common.name"), self.info.name)
        if name:
            self.rec.update_info(name=name)
            self.info.name = name
            self.title.setText(name)

    # ================================================================ capture / merge / run
    def _pick_monitor(self):
        mons = list_monitors()
        for m in mons:
            if m.width == self.info.screen_w and m.height == self.info.screen_h:
                return m
        return mons[0]

    def _grab_frame(self):
        try:
            g = ScreenGrabber(self._pick_monitor())
            f = g.grab()
            g.close()
            return f
        except Exception:
            return None

    def _recapture(self):
        if not self.cur:
            return
        win = self.window()
        win.showMinimized()
        QTimer.singleShot(3000, self._finish_recapture)

    def _finish_recapture(self):
        frame = self._grab_frame()
        win = self.window()
        win.showNormal()
        win.activateWindow()
        if frame is None or not self.cur:
            return
        self.cur.screenshot = to_png(frame)
        self.geom_dirty |= {"main", "drop"}
        self._set_dirty(True)
        self._commit_current()
        self._show_step(self.cur, animate=False)

    def _merge(self):
        recs = [r for r in list_recordings(self.app.settings.workspace) if Path(r["path"]) != self.rec.path]
        if not recs:
            return
        d = BaseDialog(tr("ed.append"), self)
        d.setMinimumWidth(460)
        d.root.addWidget(label(tr("ed.append_pick")))
        combo = QComboBox()
        for r in recs:
            combo.addItem(f"{r['name']}  ·  {r['steps']} {tr('common.steps')}  ·  {r['screen']}", str(r["path"]))
        d.root.addWidget(combo)
        warn = label("", wrap=True)
        warn.setStyleSheet(f"color: {C['warning']};")
        d.root.addWidget(warn)
        mine = f"{self.info.screen_w}×{self.info.screen_h} @ {round(self.info.scale * 100)}%"

        def check():
            warn.setText("" if recs[combo.currentIndex()]["screen"] == mine else tr("ed.append_diff"))
        combo.currentIndexChanged.connect(check)
        check()
        d.footer(tr("ed.append"), "merge")
        if d.exec() != QDialog.Accepted:
            return
        self.maybe_save()
        other = Recording(Path(combo.currentData()))
        try:
            self.rec.append_from(other)
        finally:
            other.close()
        self._reload(len(self.steps))

    def _run(self):
        self.maybe_save()
        self.app.run_recording(self.rec.path)

    def _back(self):
        self.maybe_save()
        self.app.navigate(1)

    def close_recording(self):
        if self.rec:
            self.maybe_save()
            self.rec.close()
            self.rec = None
