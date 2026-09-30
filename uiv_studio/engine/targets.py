# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Build a Target (bbox + template + OCR + embedding) from a screenshot."""

import numpy as np

from uiv_studio.core.models import Target
from uiv_studio.vision.bbox import smart_bbox
from uiv_studio.vision.embed import Embedder
from uiv_studio.vision.imageio import clamp_box, crop, to_png
from uiv_studio.vision.ocr import OCR


def build_target(frame: np.ndarray, cx: int, cy: int, bbox: tuple | None = None) -> Target:
    """`cx, cy` is the action point (monitor-relative). If `bbox` is None it is detected."""
    H, W = frame.shape[:2]
    if bbox is None:
        x, y, w, h = smart_bbox(frame, cx, cy)
    else:
        x, y, w, h = clamp_box(*bbox, W, H)
    img = crop(frame, x, y, w, h)
    text, box = OCR.read_text(img)
    return Target(
        x=x, y=y, w=w, h=h,
        click_x=int(min(max(cx - x, 0), w - 1)), click_y=int(min(max(cy - y, 0), h - 1)),
        ocr_text=text, ocr_box=box, template=to_png(img), embedding=Embedder.embed_bytes(img),
    )


def rebuild_target(frame: np.ndarray, t: Target) -> Target:
    """Recompute crop-derived data after the user edited bbox / click point."""
    nt = build_target(frame, t.x + t.click_x, t.y + t.click_y, (t.x, t.y, t.w, t.h))
    nt.click_x = min(max(t.click_x, 0), nt.w - 1)
    nt.click_y = min(max(t.click_y, 0), nt.h - 1)
    return nt
