"""Small numpy <-> Qt image helpers."""
from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage, QPixmap


def bgr_to_qimage(img: np.ndarray) -> QImage:
    img = np.ascontiguousarray(img)
    h, w = img.shape[:2]
    qi = QImage(img.data, w, h, img.strides[0], QImage.Format.Format_BGR888)
    return qi.copy()  # detach from the numpy buffer


def bgr_to_pixmap(img: np.ndarray) -> QPixmap:
    return QPixmap.fromImage(bgr_to_qimage(img))


def qimage_to_bgr(qi: QImage) -> np.ndarray:
    qi = qi.convertToFormat(QImage.Format.Format_RGB888)
    w, h = qi.width(), qi.height()
    buf = np.frombuffer(qi.constBits(), dtype=np.uint8)
    arr = buf.reshape(h, qi.bytesPerLine())[:, : w * 3].reshape(h, w, 3)
    return np.ascontiguousarray(arr[:, :, ::-1])
