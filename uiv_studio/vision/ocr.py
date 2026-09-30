# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""OCR on top of RapidOCR (PP-OCRv4 models on ONNX Runtime, ~15 MB, CPU friendly).

Three speed paths:
  * single-line crops  -> recognizer only                         (~30 ms)
  * multi-line crops   -> detector capped at 960 px + recognizer  (~200 ms)
  * search whole screen for a known text -> full-res detector, then recognize
    only the boxes whose height is compatible with the expected text.
"""

import logging
import re
import threading
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class TextBox:
    text: str
    x: int
    y: int
    w: int
    h: int
    conf: float
    sim: float = 0.0

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


class OCR:
    _crop_engine = None
    _screen_engine = None
    _lock = threading.Lock()

    @classmethod
    def warmup(cls):
        cls._engines()
        cls.read(np.full((40, 160, 3), 255, np.uint8))

    @classmethod
    def _engines(cls):
        with cls._lock:
            if cls._crop_engine is None:
                from rapidocr_onnxruntime import RapidOCR
                log.info("Loading OCR models")
                cls._crop_engine = RapidOCR(det_limit_type="max", det_limit_side_len=960, use_cls=False)
                cls._screen_engine = RapidOCR(use_cls=False)
            return cls._crop_engine, cls._screen_engine

    # ------------------------------------------------------------ crops
    @classmethod
    def read(cls, img: np.ndarray, min_conf: float = 0.5) -> list[TextBox]:
        if img is None or img.size == 0 or min(img.shape[:2]) < 6:
            return []
        crop_engine, _ = cls._engines()
        h, w = img.shape[:2]
        if h <= 64 and w / max(h, 1) >= 1.2:
            text, conf = cls._recognize([img])[0]
            if text and conf >= min_conf:
                return [TextBox(text, 0, 0, w, h, conf)]
            # fall through: maybe no text, maybe an icon + text layout
        scale = 1.0
        if h < 48:
            scale = 48.0 / h
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        with cls._lock:
            result, _ = crop_engine(img)
        return cls._to_boxes(result, scale, min_conf)

    @classmethod
    def read_text(cls, img: np.ndarray) -> tuple[str, list | None]:
        """Joined text of a crop and the union box of the text ([x, y, w, h]) or None."""
        boxes = cls.read(img)
        if not boxes:
            return "", None
        boxes.sort(key=lambda b: (round(b.cy / max(8, b.h)), b.x))
        x0 = min(b.x for b in boxes)
        y0 = min(b.y for b in boxes)
        x1 = max(b.x + b.w for b in boxes)
        y1 = max(b.y + b.h for b in boxes)
        return " ".join(b.text for b in boxes), [x0, y0, x1 - x0, y1 - y0]

    # ------------------------------------------------------------ screen search
    @classmethod
    def find(cls, screen: np.ndarray, ref_text: str, height_hint: float | None = None,
             min_sim: float = 0.6) -> list[TextBox]:
        """Text boxes on the screen that match `ref_text`, best first."""
        crop_engine, screen_engine = cls._engines()
        with cls._lock:
            boxes, _ = screen_engine.text_det(screen)
        if boxes is None or len(boxes) == 0:
            return []
        rects = []
        for b in boxes:
            pts = np.asarray(b, np.float32)
            x, y = pts[:, 0].min(), pts[:, 1].min()
            rects.append((x, y, pts[:, 0].max() - x, pts[:, 1].max() - y, pts))
        if height_hint:
            lo, hi = 0.55 * height_hint, 1.8 * height_hint
            rects = [r for r in rects if lo <= r[3] <= hi]
        ref_len = len(normalize_text(ref_text))
        out = []
        for i in range(0, len(rects), 16):
            chunk = rects[i:i + 16]
            crops = [screen[int(max(0, y)):int(y + h) + 1, int(max(0, x)):int(x + w) + 1] for x, y, w, h, _ in chunk]
            for (x, y, w, h, _), (text, conf) in zip(chunk, cls._recognize(crops)):
                if not text or conf < 0.5:
                    continue
                sim = text_similarity(text, ref_text)
                nt = normalize_text(text)
                if sim < min_sim and not (ref_len >= 3 and normalize_text(ref_text) in nt):
                    continue
                out.append(TextBox(text, int(x), int(y), int(w), int(h), conf, sim if sim >= min_sim else 0.8))
        out.sort(key=lambda b: b.sim, reverse=True)
        return out

    # ------------------------------------------------------------ internals
    @classmethod
    def _recognize(cls, crops: list) -> list[tuple[str, float]]:
        crop_engine, _ = cls._engines()
        with cls._lock:
            res = crop_engine.text_rec(crops)
        rec = res[0] if isinstance(res, tuple) else res
        return [(str(r[0]).strip(), float(r[1])) for r in rec]

    @staticmethod
    def _to_boxes(result, scale, min_conf) -> list[TextBox]:
        out = []
        for box, text, conf in result or []:
            conf = float(conf)
            text = (text or "").strip()
            if not text or conf < min_conf:
                continue
            pts = np.array(box, dtype=np.float32) / scale
            x, y = pts[:, 0].min(), pts[:, 1].min()
            w, h = pts[:, 0].max() - x, pts[:, 1].max() - y
            out.append(TextBox(text, int(x), int(y), int(max(1, w)), int(max(1, h)), conf))
        return out


def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    # Characters OCR confuses most on UI fonts
    s = s.translate(str.maketrans({"0": "o", "1": "l", "|": "l", "i": "l", "5": "s"}))
    return re.sub(r"[^a-z0-9]+", "", s)


def text_similarity(a: str, b: str) -> float:
    na, nb = normalize_text(a), normalize_text(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()
