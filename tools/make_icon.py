"""Render the UIV Studio icon (transparent background) -> resources/icon.png + icon.ico (multi-size)."""

import sys
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen

OUT = Path(__file__).resolve().parents[1] / "uiv_studio" / "resources"
S = 1024


def glyph() -> QImage:
    img = QImage(S, S, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    grad = QLinearGradient(QPointF(170, 150), QPointF(870, 880))
    grad.setColorAt(0.0, QColor("#B06CFF"))
    grad.setColorAt(0.5, QColor("#6C7BFF"))
    grad.setColorAt(1.0, QColor("#2FE0D4"))

    # orbit arc (open ring) around the glyph
    p.setPen(QPen(grad, 46, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(120, 120, 784, 784), 35 * 16, 290 * 16)

    # rounded play triangle
    tri = QPainterPath()
    a, b, c = QPointF(390, 300), QPointF(750, 512), QPointF(390, 724)
    tri.moveTo(a); tri.lineTo(b); tri.lineTo(c); tri.closeSubpath()
    stroker = QPen(grad, 70, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(stroker)
    p.setBrush(grad)
    p.drawPath(tri)

    # cut-out target in the triangle (transparent) + bright core
    p.setCompositionMode(QPainter.CompositionMode_Clear)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 255))
    p.drawEllipse(QPointF(505, 512), 92, 92)
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)
    p.setBrush(QColor("#FFFFFF"))
    p.drawEllipse(QPointF(505, 512), 38, 38)
    # end dot of the orbit
    p.setBrush(QColor("#2FE0D4"))
    p.drawEllipse(QPointF(512 + 392 * np.cos(np.radians(35)), 512 - 392 * np.sin(np.radians(35))), 40, 40)
    p.end()
    return img


def to_np(img: QImage) -> np.ndarray:
    img = img.convertToFormat(QImage.Format_RGBA8888)
    return np.array(img.constBits(), np.uint8).reshape(S, S, 4).copy()


def main():
    QGuiApplication(sys.argv)
    g = to_np(glyph()).astype(np.float32) / 255.0
    # soft neon glow from the glyph itself
    glow = cv2.GaussianBlur(g, (0, 0), 28)
    glow[..., 3] *= 0.55
    a_g, a_s = g[..., 3:4], glow[..., 3:4]
    a = a_g + a_s * (1 - a_g)
    rgb = (g[..., :3] * a_g + glow[..., :3] / np.maximum(glow[..., 3:4], 1e-6) * a_s * (1 - a_g)) / np.maximum(a, 1e-6)
    out = np.clip(np.concatenate([rgb, a], axis=2) * 255, 0, 255).astype(np.uint8)
    from PIL import Image
    im = Image.fromarray(out, "RGBA")
    im.resize((256, 256), Image.LANCZOS).save(OUT / "icon.png")
    im.save(OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("ok")


if __name__ == "__main__":
    main()
