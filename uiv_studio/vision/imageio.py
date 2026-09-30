"""PNG encode/decode helpers and safe cropping."""

import cv2
import numpy as np


def to_png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img, [cv2.IMWRITE_PNG_COMPRESSION, 3])
    return buf.tobytes() if ok else b""


def from_png(data: bytes) -> np.ndarray | None:
    if not data:
        return None
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)


def clamp_box(x: int, y: int, w: int, h: int, img_w: int, img_h: int) -> tuple:
    x = max(0, min(int(x), img_w - 1))
    y = max(0, min(int(y), img_h - 1))
    w = max(1, min(int(w), img_w - x))
    h = max(1, min(int(h), img_h - y))
    return x, y, w, h


def crop(img: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    x, y, w, h = clamp_box(x, y, w, h, img.shape[1], img.shape[0])
    return img[y:y + h, x:x + w]
