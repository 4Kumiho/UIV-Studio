# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLineEdit,
                               QVBoxLayout, QWidget)

from uiv_studio import __version__
from uiv_studio.core.settings import HUD_CORNERS, Settings, normalize_weights
from uiv_studio.ui import icons
from uiv_studio.ui.i18n import tr
from uiv_studio.ui.pages.common import Page
from uiv_studio.ui.theme import C
from uiv_studio.ui.widgets import (HotkeyEdit, HoverCard, IconBadge, PageHeader, SliderRow, Toggle, button,
                                   fade_in, label)


class Section(HoverCard):
    def __init__(self, icon_name: str, title: str, subtitle: str = "", color: str = C["accent"]):
        super().__init__(accent=color)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(22, 18, 22, 20)
        self.lay.setSpacing(12)
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(IconBadge(icon_name, (color, C["surface3"]), 34))
        col = QVBoxLayout()
        col.setSpacing(0)
        t = label(title, "H3")
        t.setStyleSheet("background: transparent; font-size: 12pt; font-weight: 650;")
        col.addWidget(t)
        if subtitle:
            s = label(subtitle, "Faint")
            s.setStyleSheet("background: transparent;")
            col.addWidget(s)
        head.addLayout(col)
        head.addStretch()
        self.lay.addLayout(head)

    def row(self, title: str, widget: QWidget, tip: str = ""):
        r = QHBoxLayout()
        t = label(title)
        t.setStyleSheet("background: transparent;")
        if tip:
            t.setToolTip(tip)
        r.addWidget(t)
        r.addStretch()
        r.addWidget(widget)
        self.lay.addLayout(r)
        return widget


class SettingsPage(Page):
    def __init__(self, app):
        super().__init__(app)
        self.s = app.settings
        head = PageHeader(tr("set.title"), tr("set.subtitle"))
        self.reset_btn = button(tr("common.reset"), "refresh", "Ghost")
        self.save_btn = button(tr("common.save"), "save", "Primary")
        self.reset_btn.clicked.connect(self._reset)
        self.save_btn.clicked.connect(self._save)
        head.actions.addWidget(self.reset_btn)
        head.actions.addWidget(self.save_btn)
        self.body.addWidget(head)

        grid = QGridLayout()
        grid.setSpacing(16)
        self.body.addLayout(grid)

        # ---------------------------------------------------------- hotkeys
        hk = Section("keyboard", tr("set.hotkeys"), tr("set.hotkeys_sub"), C["accent"])
        self.hk = {}
        for key in ("recorder_menu", "recorder_end_input", "player_menu"):
            w = HotkeyEdit()
            w.changed.connect(self._check_conflicts)
            self.hk[key] = hk.row(tr(f"set.hk.{key}"), w)
        self.conflict = label("", wrap=True)
        self.conflict.setStyleSheet(f"color: {C['danger']}; background: transparent;")
        hk.lay.addWidget(self.conflict)

        # ---------------------------------------------------------- validation
        va = Section("target", tr("set.validation"), tr("set.validation_sub"), C["cyan"])
        self.threshold = SliderRow(tr("set.threshold"), 0.5, 0.99, 0.8, 2, percent=True, tip=tr("set.threshold_tip"))
        self.fast = SliderRow(tr("set.fast_accept"), 0.6, 1.0, 0.9, 2, percent=True, tip=tr("set.fast_accept_tip"))
        self.margin = SliderRow(tr("set.ambiguity"), 0.0, 0.15, 0.03, 2, percent=True, tip=tr("set.ambiguity_tip"))
        self.stages = SliderRow(tr("set.stages"), 1, 10, 3, 0)
        self.stage_wait = SliderRow(tr("set.stage_wait"), 0, 15, 2, 1, suffix=" s")
        self.radius = SliderRow(tr("set.radius"), 0, 800, 160, 0, suffix=" px")
        for w in (self.threshold, self.fast, self.margin, self.stages, self.stage_wait, self.radius):
            va.lay.addWidget(w)
        self.threshold.valueChanged.connect(lambda v: self.fast.value() < v and self.fast.set_value(v))

        # ---------------------------------------------------------- weights
        we = Section("sliders", tr("set.weights_text"), tr("set.weights_sub"), "#F472B6")
        self.w_text = {k: SliderRow(tr(f"set.w.{k}"), 0, 1, 0.33, 2, percent=True) for k in ("template", "ocr", "visual")}
        for w in self.w_text.values():
            we.lay.addWidget(w)
        self.w_text_sum = label("", "Faint")
        we.lay.addWidget(self.w_text_sum)
        we.lay.addSpacing(8)
        t2 = label(tr("set.weights_no_text"), "H3")
        t2.setStyleSheet("background: transparent;")
        we.lay.addWidget(t2)
        self.w_notext = {k: SliderRow(tr(f"set.w.{k}"), 0, 1, 0.5, 2, percent=True) for k in ("template", "visual")}
        for w in self.w_notext.values():
            we.lay.addWidget(w)
        self.w_notext_sum = label("", "Faint")
        we.lay.addWidget(self.w_notext_sum)
        for w in list(self.w_text.values()) + list(self.w_notext.values()):
            w.valueChanged.connect(self._update_sums)

        # ---------------------------------------------------------- execution
        ex = Section("play", tr("set.execution"), "", C["success"])
        self.delay = SliderRow(tr("set.delay_steps"), 0, 10, 1, 1, suffix=" s")
        self.mouse_ms = SliderRow(tr("set.mouse_ms"), 0, 1500, 250, 0, suffix=" ms")
        self.typing_ms = SliderRow(tr("set.typing_ms"), 0, 300, 25, 0, suffix=" ms")
        self.fps = SliderRow(tr("set.video_fps"), 1, 30, 10, 0)
        for w in (self.delay, self.mouse_ms, self.typing_ms, self.fps):
            ex.lay.addWidget(w)
        self.video = ex.row(tr("set.record_video"), Toggle())
        self.stop_fail = ex.row(tr("set.stop_on_failure"), Toggle())

        # ---------------------------------------------------------- recording
        rc = Section("record", tr("set.recording"), "", "#FB923C")
        self.dbl = SliderRow(tr("set.double_click"), 200, 900, 450, 0, suffix=" ms")
        self.drag = SliderRow(tr("set.drag_px"), 2, 40, 6, 0, suffix=" px")
        self.scroll = SliderRow(tr("set.scroll_ms"), 100, 1500, 350, 0, suffix=" ms")
        for w in (self.dbl, self.drag, self.scroll):
            rc.lay.addWidget(w)

        # ---------------------------------------------------------- general
        ge = Section("globe", tr("set.general"), "", C["info"])
        self.lang = QComboBox()
        self.lang.addItem("Italiano", "it")
        self.lang.addItem("English", "en")
        ge.row(tr("set.language"), self.lang)
        self.corner = QComboBox()
        for c in HUD_CORNERS:
            self.corner.addItem(tr(f"corner.{c}"), c)
        ge.row(tr("set.hud_corner"), self.corner)
        self.minimize = ge.row(tr("set.minimize"), Toggle())
        ws_row = QHBoxLayout()
        self.ws = QLineEdit()
        browse = button(tr("common.browse"), "folder")
        browse.clicked.connect(self._browse)
        ws_row.addWidget(self.ws, 1)
        ws_row.addWidget(browse)
        wl = label(tr("set.workspace"))
        wl.setStyleSheet("background: transparent;")
        ge.lay.addWidget(wl)
        ge.lay.addLayout(ws_row)
        from uiv_studio.vision.embed import Embedder
        about = label(f"UIV Studio {__version__}  ·  © 2026 4Kumiho  ·  " + tr("set.models", kind="CNN" if Embedder.kind() == "cnn" else "HOG+color"), "Faint")
        about.setStyleSheet("background: transparent;")
        ge.lay.addWidget(about)

        grid.addWidget(hk, 0, 0)
        grid.addWidget(ge, 0, 1)
        grid.addWidget(va, 1, 0)
        grid.addWidget(we, 1, 1)
        grid.addWidget(ex, 2, 0)
        grid.addWidget(rc, 2, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.sections = [hk, ge, va, we, ex, rc]
        self.body.addStretch()
        self._load(self.s.snapshot())

    # ------------------------------------------------------------------
    def refresh(self):
        self._load(self.s.snapshot())
        for i, sec in enumerate(self.sections):
            fade_in(sec, delay=i * 40)

    def _load(self, d: dict):
        for k, w in self.hk.items():
            w.set_combo(d["hotkeys"][k])
        v = d["validation"]
        self.threshold.set_value(v["threshold"])
        self.fast.set_value(v["fast_accept"])
        self.margin.set_value(v["ambiguity_margin"])
        self.stages.set_value(v["stages"])
        self.stage_wait.set_value(v["seconds_between_stages"])
        self.radius.set_value(v["local_search_radius_px"])
        for k, w in self.w_text.items():
            w.set_value(v["weights_text"][k])
        for k, w in self.w_notext.items():
            w.set_value(v["weights_no_text"][k])
        e = d["execution"]
        self.delay.set_value(e["delay_between_steps_s"])
        self.mouse_ms.set_value(e["mouse_move_ms"])
        self.typing_ms.set_value(e["typing_interval_ms"])
        self.fps.set_value(e["video_fps"])
        self.video.setChecked(e["record_video"])
        self.stop_fail.setChecked(e["stop_on_failure"])
        r = d["recording"]
        self.dbl.set_value(r["double_click_ms"])
        self.drag.set_value(r["drag_threshold_px"])
        self.scroll.set_value(r["scroll_debounce_ms"])
        g = d["general"]
        self.lang.setCurrentIndex(max(0, self.lang.findData(g["language"])))
        self.corner.setCurrentIndex(max(0, self.corner.findData(g["hud_corner"])))
        self.minimize.setChecked(g["minimize_during_sessions"])
        self.ws.setText(g["workspace"])
        self._update_sums()
        self._check_conflicts()

    def _collect(self) -> dict:
        d = self.s.snapshot()
        for k, w in self.hk.items():
            d["hotkeys"][k] = w.combo
        v = d["validation"]
        v["threshold"] = self.threshold.value()
        v["fast_accept"] = self.fast.value()
        v["ambiguity_margin"] = self.margin.value()
        v["stages"] = int(self.stages.value())
        v["seconds_between_stages"] = self.stage_wait.value()
        v["local_search_radius_px"] = int(self.radius.value())
        v["weights_text"] = {k: w.value() for k, w in self.w_text.items()}
        v["weights_no_text"] = {k: w.value() for k, w in self.w_notext.items()}
        e = d["execution"]
        e["delay_between_steps_s"] = self.delay.value()
        e["mouse_move_ms"] = int(self.mouse_ms.value())
        e["typing_interval_ms"] = int(self.typing_ms.value())
        e["video_fps"] = int(self.fps.value())
        e["record_video"] = self.video.isChecked()
        e["stop_on_failure"] = self.stop_fail.isChecked()
        r = d["recording"]
        r["double_click_ms"] = int(self.dbl.value())
        r["drag_threshold_px"] = int(self.drag.value())
        r["scroll_debounce_ms"] = int(self.scroll.value())
        g = d["general"]
        g["language"] = self.lang.currentData()
        g["hud_corner"] = self.corner.currentData()
        g["minimize_during_sessions"] = self.minimize.isChecked()
        g["workspace"] = self.ws.text().strip() or g["workspace"]
        return d

    def _update_sums(self, *_):
        for rows, lab in ((self.w_text, self.w_text_sum), (self.w_notext, self.w_notext_sum)):
            n = normalize_weights({k: w.value() for k, w in rows.items()})
            lab.setText("  ·  ".join(f"{tr('set.w.' + k)} {v * 100:.0f}%" for k, v in n.items()))

    def _check_conflicts(self, *_) -> bool:
        # The recorder and the player never run together, so only same-session keys may clash
        a, b = self.hk["recorder_menu"].combo, self.hk["recorder_end_input"].combo
        if a and a == b:
            self.conflict.setText(tr("set.hk.conflict", a=tr("set.hk.recorder_menu"), b=tr("set.hk.recorder_end_input")))
            self.save_btn.setEnabled(False)
            return False
        self.conflict.setText("")
        self.save_btn.setEnabled(True)
        return True

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, tr("set.workspace"), self.ws.text())
        if d:
            self.ws.setText(d)

    def _reset(self):
        self._load(Settings.defaults())

    def _save(self):
        if not self._check_conflicts():
            return
        old_lang = self.s.data["general"]["language"]
        self.s.save(self._collect())
        self.app.toast(tr("set.saved"), "success")
        if self.s.data["general"]["language"] != old_lang:
            QTimer.singleShot(150, self.app.rebuild)
