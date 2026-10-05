# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""Element bounding box around a click point.

Strategy: build an edge/structure map, find contours, keep the ones containing the
click, and pick the smallest *plausible* control (not a 3px glyph, not a whole panel).
Small results (icons, single letters) are padded so the template stays distinctive.
"""

import cv2
import numpy as np

MIN_SIDE = 14         # below this a crop is not distinctive enough
MAX_FRACTION = 0.45   # a candidate larger than this share of the screen is a container
DEFAULT_HALF = 40     # fallback half-size
WINDOWS = (400, 1000, 2400)   # growing search half-sizes (wide elements, HiDPI frames)
RECT_FILL = 0.90      # how much of its box a contour must enclose to count as a control


def _structure_map(gray: np.ndarray) -> np.ndarray:
    edges = cv2.Canny(gray, 40, 120)
    grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    _, grad = cv2.threshold(grad, 18, 255, cv2.THRESH_BINARY)
    combined = cv2.bitwise_or(edges, grad)
    return cv2.morphologyEx(combined, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))


def _best_in_window(screen, cx, cy, win, W, H):
    """Smallest plausible control containing the click, searched in a +/-win box.

    Returns (rect, has_rect, clipped): rect is (x, y, w, h, area) in full-frame
    coordinates, has_rect says a real rectangular control was seen (not just a
    glyph blob), clipped says the winner touches the window border. Either of the
    last two means a wider search may still find the real element.
    """
    x0, y0 = max(0, cx - win), max(0, cy - win)
    x1, y1 = min(W, cx + win), min(H, cy + win)
    roi = screen[y0:y1, x0:x1]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    struct = _structure_map(gray)

    contours, _ = cv2.findContours(struct, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    lx, ly = cx - x0, cy - y0
    rw, rh = x1 - x0, y1 - y0
    max_area = MAX_FRACTION * W * H
    best_rect = None   # smallest rectangle-like control (button, field, tab, icon frame)
    best_any = None    # smallest plausible blob (fallback: glyph clusters, irregular shapes)
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if not (x <= lx < x + w and y <= ly < y + h):
            continue
        if w < MIN_SIDE or h < MIN_SIDE or w * h > max_area:
            continue
        # Thin separator lines, but not a wide flat control: a full-width text
        # field is just as elongated, and twice as tall again on a HiDPI frame.
        if w > 12 * h and h < max(16, 0.015 * H):
            continue
        area = w * h
        if best_any is None or area < best_any[4]:
            best_any = (x, y, w, h, area)
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.03 * peri, True)
        # A control's outline encloses its whole box; a cluster of letters does
        # not. On a HiDPI frame the glyphs of a centred label are big enough to
        # pass every size filter, so this fill ratio is what keeps them from
        # beating the button they sit on (button ~0.99, text ~0.45-0.80).
        rect_like = 4 <= len(approx) <= 8 and cv2.contourArea(c) >= RECT_FILL * area
        if rect_like and w >= 24 and h >= 16 and (best_rect is None or area < best_rect[4]):
            best_rect = (x, y, w, h, area)

    best = best_rect or best_any
    if best is None:
        # nothing at all: a wider window may still contain the element's borders
        return None, False, (rw < W or rh < H)
    x, y, w, h = best[:4]
    touches = (x <= 1 and x0 > 0) or (y <= 1 and y0 > 0) or (x + w >= rw - 1 and x1 < W) or (y + h >= rh - 1 and y1 < H)
    return (x + x0, y + y0, w, h, best[4]), best_rect is not None, touches


def smart_bbox(screen: np.ndarray, cx: int, cy: int) -> tuple:
    """Return (x, y, w, h) of the element under (cx, cy)."""
    H, W = screen.shape[:2]
    cx = max(0, min(int(cx), W - 1))
    cy = max(0, min(int(cy), H - 1))

    # Start on a window around the click: faster and avoids giant containers. A
    # wide element (a full-width field, any button on a HiDPI screen, where
    # physical pixels are 2x the logical ones) overflows it, so widen until the
    # winner no longer runs into the border.
    best = None
    for win in WINDOWS:
        found, has_rect, clipped = _best_in_window(screen, cx, cy, win, W, H)
        if found is not None and (best is None or has_rect):
            best = found          # keep the first hit as the fallback for icons
        if found is not None and has_rect and not clipped:
            break
        if 2 * win >= max(W, H):
            break

    if best is None:
        x, y, w, h = cx - DEFAULT_HALF, cy - DEFAULT_HALF // 2, DEFAULT_HALF * 2, DEFAULT_HALF
    else:
        x, y, w, h = best[0], best[1], best[2], best[3]

    x, y, w, h = _ensure_distinctive(x, y, w, h, cx, cy)
    return _clamp(x, y, w, h, W, H)


def _ensure_distinctive(x, y, w, h, cx, cy) -> tuple:
    """Pad tiny boxes so the template carries enough context to be unique."""
    min_w, min_h = 36, 24
    if w < min_w:
        pad = (min_w - w) // 2 + 1
        x, w = x - pad, w + 2 * pad
    if h < min_h:
        pad = (min_h - h) // 2 + 1
        y, h = y - pad, h + 2 * pad
    # A 4px margin makes matching tolerant to 1-2px rendering shifts
    return x - 4, y - 4, w + 8, h + 8


def _clamp(x, y, w, h, W, H) -> tuple:
    x, y = max(0, x), max(0, y)
    w, h = min(w, W - x), min(h, H - y)
    return int(x), int(y), int(max(1, w)), int(max(1, h))
