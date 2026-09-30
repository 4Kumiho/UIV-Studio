# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Locate a recorded element on the live screen.

Per stage (a fresh screenshot each time):
  1. LOCAL  - normalized template matching in a window around the expected position.
              Accepted immediately if the composite score >= `fast_accept`.
  2. GLOBAL - multi-scale template matching on the whole screen (top-K peaks, NMS)
              plus, when the element has text, OCR text boxes whose text matches.
  3. Every candidate gets a composite score:
        template (color NCC) + OCR similarity (if text) + visual embedding
     weighted by the user's settings. Near-ties are resolved by distance to the
     expected position, so identical buttons elsewhere don't steal the match.
Stages repeat (waiting `seconds_between_stages`) to let the UI settle.
"""

import logging
import time
from dataclasses import dataclass

import cv2
import numpy as np

from uiv_studio.core.models import MatchInfo, Target
from uiv_studio.vision.embed import Embedder
from uiv_studio.vision.imageio import from_png, to_png
from uiv_studio.vision.ocr import OCR, normalize_text, text_similarity

log = logging.getLogger(__name__)


@dataclass
class Candidate:
    x: int
    y: int
    w: int
    h: int
    method: str
    template: float = 0.0
    visual: float = 0.0
    ocr: float | None = None
    ocr_text: str = ""
    score: float = 0.0
    dist: float = 0.0


class Geometry:
    """Mapping between the recording screen and the execution screen."""

    def __init__(self, rec_w, rec_h, rec_scale, exe_w, exe_h, exe_scale):
        self.rx = exe_w / rec_w if rec_w else 1.0
        self.ry = exe_h / rec_h if rec_h else 1.0
        self.dpi = (exe_scale or 1.0) / (rec_scale or 1.0)
        self.identical = abs(self.rx - 1) < 1e-3 and abs(self.ry - 1) < 1e-3 and abs(self.dpi - 1) < 1e-3

    def template_scales(self) -> list[float]:
        if self.identical:
            return [1.0]
        base = {round(self.dpi, 3)}
        r = (self.rx + self.ry) / 2
        if abs(r - 1) > 0.02:
            base.add(round(self.dpi * r, 3))
        out = set()
        for b in base:
            out.update({round(b * 0.93, 3), b, round(b * 1.07, 3)})
        return sorted(s for s in out if 0.3 <= s <= 3.0)

    def expected(self, t: Target) -> tuple[float, float]:
        return t.x * self.rx, t.y * self.ry


def _top_peaks(res: np.ndarray, k: int, tw: int, th: int, min_score: float) -> list[tuple]:
    """Up to k (score, x, y) maxima separated by at least half the template size."""
    res = res.copy()
    peaks = []
    rx, ry = max(1, tw // 2), max(1, th // 2)
    for _ in range(k):
        _, max_val, _, (px, py) = cv2.minMaxLoc(res)
        if not np.isfinite(max_val) or max_val < min_score:
            break
        peaks.append((float(max_val), px, py))
        res[max(0, py - ry):py + ry + 1, max(0, px - rx):px + rx + 1] = -1.0
    return peaks


def _is_flat(img: np.ndarray) -> bool:
    return float(img.std()) < 3.0


def template_score(crop: np.ndarray, tpl: np.ndarray) -> float:
    """Same-size color similarity in 0..1."""
    if crop.shape[:2] != tpl.shape[:2]:
        crop = cv2.resize(crop, (tpl.shape[1], tpl.shape[0]), interpolation=cv2.INTER_AREA)
    if _is_flat(tpl) or _is_flat(crop):
        diff = np.abs(crop.astype(np.int16) - tpl.astype(np.int16)).mean() / 255.0
        return float(max(0.0, 1.0 - 4.0 * diff))
    v = float(cv2.matchTemplate(crop, tpl, cv2.TM_CCOEFF_NORMED)[0, 0])
    return max(0.0, v) if np.isfinite(v) else 0.0


class Matcher:
    def __init__(self, grab, geometry: Geometry, cfg: dict, should_abort=lambda: False, on_stage=None):
        self.grab = grab                    # callable -> BGR screenshot
        self.geo = geometry
        self.cfg = cfg                      # settings["validation"]
        self.should_abort = should_abort
        self.on_stage = on_stage or (lambda stage, total: None)

    # ------------------------------------------------------------------ public
    def find(self, target: Target) -> MatchInfo:
        tpl0 = from_png(target.template)
        if tpl0 is None:
            return MatchInfo(found=False)
        has_text = bool(normalize_text(target.ocr_text))
        weights = self.cfg["weights_text"] if has_text else self.cfg["weights_no_text"]
        ref_vec = Embedder.embed(tpl0)
        scales = self.geo.template_scales()
        templates = {s: tpl0 if s == 1.0 else cv2.resize(
            tpl0, (max(4, round(tpl0.shape[1] * s)), max(4, round(tpl0.shape[0] * s))),
            interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC) for s in scales}
        ex, ey = self.geo.expected(target)
        stages = int(self.cfg["stages"])
        best_seen: Candidate | None = None
        best_shot = None

        for stage in range(1, stages + 1):
            if self.should_abort():
                break
            self.on_stage(stage, stages)
            shot = self.grab()
            ctx = _Ctx(shot, templates, tpl0, ref_vec, target, has_text, weights, ex, ey)

            local = self._local(ctx)
            if local and local.score >= self.cfg["fast_accept"]:
                return self._result(True, local, shot, stage)

            cands = ([local] if local else []) + self._global(ctx)
            best = self._pick(cands)
            if best and best.score < self.cfg["threshold"] and has_text:
                cands += self._text_candidates(ctx)
                best = self._pick(cands)
            if best and (best_seen is None or best.score > best_seen.score):
                best_seen, best_shot = best, shot
            if best and best.score >= self.cfg["threshold"]:
                return self._result(True, best, shot, stage)
            if stage < stages and self._sleep(self.cfg["seconds_between_stages"]):
                break

        if best_seen is None:
            return MatchInfo(found=False, stage=stages)
        return self._result(False, best_seen, best_shot, stages)

    # ------------------------------------------------------------------ search
    def _local(self, ctx: "_Ctx") -> Candidate | None:
        radius = int(self.cfg["local_search_radius_px"])
        H, W = ctx.shot.shape[:2]
        found = []
        for s, tpl in ctx.templates.items():
            th, tw = tpl.shape[:2]
            x0 = int(max(0, ctx.ex - radius)); y0 = int(max(0, ctx.ey - radius))
            x1 = int(min(W, ctx.ex + tw + radius)); y1 = int(min(H, ctx.ey + th + radius))
            if x1 - x0 < tw or y1 - y0 < th:
                continue
            region = ctx.shot[y0:y1, x0:x1]
            for score, px, py in self._peaks(region, tpl, 3, 0.3):
                found.append(Candidate(x0 + px, y0 + py, tw, th, "local", template=score))
        return self._pick([self._score(ctx, c) for c in found]) if found else None

    def _global(self, ctx: "_Ctx") -> list[Candidate]:
        found = []
        for s, tpl in ctx.templates.items():
            th, tw = tpl.shape[:2]
            if tw >= ctx.shot.shape[1] or th >= ctx.shot.shape[0]:
                continue
            for score, px, py in self._peaks(ctx.shot, tpl, 6, 0.35):
                found.append(Candidate(px, py, tw, th, "global", template=score))
        found.sort(key=lambda c: c.template, reverse=True)
        return [self._score(ctx, c) for c in found[:8]]

    def _text_candidates(self, ctx: "_Ctx") -> list[Candidate]:
        t = ctx.target
        s = 1.0 if self.geo.identical else self.geo.dpi
        tpl_h, tpl_w = ctx.base_template.shape[:2]
        w, h = max(4, round(tpl_w * s)), max(4, round(tpl_h * s))
        ob = t.ocr_box or [0, 0, tpl_w, tpl_h]
        out = []
        for b in OCR.find(ctx.shot, t.ocr_text, height_hint=ob[3] * s)[:6]:
            # Align the recorded text box inside the element with the one found now
            x = round(b.x - ob[0] * s)
            y = round(b.cy - (ob[1] + ob[3] / 2) * s)
            out.append(self._score(ctx, Candidate(x, y, w, h, "text")))
        return out

    @staticmethod
    def _peaks(img, tpl, k, min_score):
        th, tw = tpl.shape[:2]
        if _is_flat(tpl):
            res = 1.0 - cv2.matchTemplate(img, tpl, cv2.TM_SQDIFF_NORMED)
        else:
            res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
        res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
        return _top_peaks(res, k, tw, th, min_score)

    # ------------------------------------------------------------------ scoring
    def _score(self, ctx: "_Ctx", c: Candidate) -> Candidate:
        H, W = ctx.shot.shape[:2]
        x0, y0 = max(0, c.x), max(0, c.y)
        x1, y1 = min(W, c.x + c.w), min(H, c.y + c.h)
        if x1 - x0 < 4 or y1 - y0 < 4:
            c.score = 0.0
            return c
        crop = ctx.shot[y0:y1, x0:x1]
        tpl = ctx.base_template
        c.template = template_score(crop, tpl)
        c.visual, _ = Embedder.similarity(ctx.ref_vec, crop)
        w = ctx.weights
        if ctx.has_text:
            # OCR only on promising candidates: it is the most expensive signal
            prelim = (w["template"] * c.template + w["visual"] * c.visual) / max(1e-6, w["template"] + w["visual"])
            if prelim >= 0.45 or c.method == "text":
                # Same crop geometry as at record time -> consistent OCR output
                if crop.shape[:2] != tpl.shape[:2]:
                    crop_n = cv2.resize(crop, (tpl.shape[1], tpl.shape[0]), interpolation=cv2.INTER_AREA)
                else:
                    crop_n = crop
                text, _ = OCR.read_text(crop_n)
                c.ocr_text = text
                c.ocr = text_similarity(text, ctx.target.ocr_text)
            else:
                c.ocr = 0.0
            c.score = w["template"] * c.template + w["ocr"] * c.ocr + w["visual"] * c.visual
        else:
            c.score = w["template"] * c.template + w["visual"] * c.visual
        c.dist = float(np.hypot(c.x - ctx.ex, c.y - ctx.ey))
        return c

    def _pick(self, cands: list[Candidate]) -> Candidate | None:
        cands = [c for c in cands if c is not None]
        if not cands:
            return None
        cands.sort(key=lambda c: c.score, reverse=True)
        best = cands[0]
        margin = self.cfg["ambiguity_margin"]
        for c in cands[1:]:
            if best.score - c.score > margin:
                break
            if c.dist + 8 < best.dist:
                best = c
        return best

    # ------------------------------------------------------------------ utils
    def _result(self, found: bool, c: Candidate, shot, stage: int) -> MatchInfo:
        H, W = shot.shape[:2]
        x0, y0 = max(0, c.x), max(0, c.y)
        crop = shot[y0:min(H, c.y + c.h), x0:min(W, c.x + c.w)]
        return MatchInfo(
            found=found, x=int(c.x), y=int(c.y), w=int(c.w), h=int(c.h),
            score=round(float(c.score), 4), template=round(float(c.template), 4),
            ocr=None if c.ocr is None else round(float(c.ocr), 4), visual=round(float(c.visual), 4),
            stage=stage, method=c.method, ocr_text=c.ocr_text, crop=to_png(crop) if crop.size else b"",
        )

    def _sleep(self, seconds: float) -> bool:
        """Abortable sleep; returns True if aborted."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.should_abort():
                return True
            time.sleep(0.05)
        return False


@dataclass
class _Ctx:
    shot: np.ndarray
    templates: dict
    base_template: np.ndarray
    ref_vec: np.ndarray
    target: Target
    has_text: bool
    weights: dict
    ex: float
    ey: float
