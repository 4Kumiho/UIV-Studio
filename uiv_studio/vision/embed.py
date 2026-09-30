"""Visual descriptor for element crops.

If `resources/models/embedder.onnx` exists (see tools/export_embedder.py, a
MobileNetV3-Small ~6 MB) it is used; otherwise a fast hand-crafted descriptor
(HOG on grayscale + HSV color histogram). Both return an L2-normalized float32
vector; `similarity()` maps cosine similarity to a calibrated 0..1 score.
"""

import logging
import threading

import cv2
import numpy as np

from uiv_studio.core.paths import resource_dir

log = logging.getLogger(__name__)

def _gradient_histograms(gray: np.ndarray, cell: int = 8, bins: int = 9) -> np.ndarray:
    """HOG-like descriptor: per-cell histograms of unsigned gradient orientation."""
    g = gray.astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=1)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=1)
    mag = np.hypot(gx, gy)
    ang = (np.degrees(np.arctan2(gy, gx)) % 180.0) * (bins / 180.0)
    b = np.minimum(ang.astype(np.int32), bins - 1)
    h, w = g.shape
    cy, cx = h // cell, w // cell
    idx = ((np.arange(h)[:, None] // cell) * cx + (np.arange(w)[None, :] // cell)) * bins + b
    hist = np.bincount(idx.ravel(), weights=mag.ravel(), minlength=cy * cx * bins).astype(np.float32)
    hist = hist.reshape(cy * cx, bins)
    hist /= (np.linalg.norm(hist, axis=1, keepdims=True) + 1e-3)   # per-cell contrast normalization
    hist = hist.reshape(-1)
    return hist / (np.linalg.norm(hist) + 1e-6)


_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_STD = np.array([0.229, 0.224, 0.225], np.float32)


class Embedder:
    _session = None
    _input = None
    _tried = False
    _lock = threading.Lock()

    @classmethod
    def _onnx(cls):
        with cls._lock:
            if not cls._tried:
                cls._tried = True
                path = resource_dir() / "models" / "embedder.onnx"
                if path.is_file():
                    try:
                        import onnxruntime as ort
                        opts = ort.SessionOptions()
                        opts.intra_op_num_threads = 2
                        cls._session = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])
                        cls._input = cls._session.get_inputs()[0].name
                        log.info("Visual embedder: ONNX (%s)", path.name)
                    except Exception as exc:
                        log.warning("ONNX embedder unavailable (%s), using hand-crafted descriptor", exc)
                else:
                    log.info("Visual embedder: hand-crafted descriptor")
            return cls._session

    @classmethod
    def kind(cls) -> str:
        return "cnn" if cls._onnx() is not None else "hog"

    @classmethod
    def warmup(cls):
        cls.embed(np.zeros((32, 32, 3), np.uint8))

    @classmethod
    def embed(cls, img: np.ndarray) -> np.ndarray:
        sess = cls._onnx()
        vec = cls._embed_cnn(sess, img) if sess is not None else cls._embed_hog(img)
        n = np.linalg.norm(vec)
        return (vec / n if n > 0 else vec).astype(np.float32)

    @classmethod
    def embed_bytes(cls, img: np.ndarray) -> bytes:
        return cls.embed(img).tobytes()

    @classmethod
    def _embed_cnn(cls, sess, img) -> np.ndarray:
        x = cv2.resize(img, (128, 128), interpolation=cv2.INTER_AREA)
        x = cv2.cvtColor(x, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        x = ((x - _MEAN) / _STD).transpose(2, 0, 1)[None]
        with cls._lock:
            out = sess.run(None, {cls._input: x})[0]
        return out.reshape(-1).astype(np.float32)

    @classmethod
    def _embed_hog(cls, img) -> np.ndarray:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        g = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA)
        hog = _gradient_histograms(g)
        hsv = cv2.cvtColor(cv2.resize(img, (32, 32), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 4, 4], [0, 180, 0, 256, 0, 256]).reshape(-1)
        hist /= (np.linalg.norm(hist) + 1e-6)
        # Aspect ratio matters for UI elements (a button vs. a field)
        ar = np.array([np.log(max(img.shape[1], 1) / max(img.shape[0], 1))], np.float32)
        return np.concatenate([hog, 0.6 * hist, 0.5 * ar]).astype(np.float32)

    @classmethod
    def similarity(cls, ref: bytes | np.ndarray, img: np.ndarray) -> tuple[float, np.ndarray]:
        """Calibrated 0..1 similarity between a stored vector and a new crop."""
        v = cls.embed(img)
        r = np.frombuffer(ref, np.float32) if isinstance(ref, (bytes, bytearray)) else ref
        if r is None or r.size != v.size:
            return 0.0, v
        cos = float(np.dot(r, v))
        floor = 0.55 if cls._session is not None else 0.40  # typical cosine of unrelated UI crops
        return float(np.clip((cos - floor) / (1.0 - floor), 0.0, 1.0)), v
