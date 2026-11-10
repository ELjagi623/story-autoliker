"""Line icons from ``assets/icons/icons.svg`` (24 px grid, 1.5 px stroke), rendered in any colour.

The sheet holds ``<symbol id="i-name">`` elements. Qt's SVG renderer wants one document per icon, so each symbol
is split out once and recoloured by rewriting ``stroke`` (cheaper and sharper than masking a bitmap).
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_symbols: Optional[dict[str, str]] = None


def _load_symbols() -> dict[str, str]:
    global _symbols
    if _symbols is None:
        _symbols = {}
        try:
            from ..app import resource_root

            text = (resource_root() / "assets" / "icons" / "icons.svg").read_text(encoding="utf-8")
            for m in re.finditer(r'<symbol id="i-([\w-]+)"[^>]*>(.*?)</symbol>', text, re.S):
                _symbols[m.group(1)] = m.group(2)
        except OSError:
            pass
    return _symbols


def has(name: str) -> bool:
    return name in _load_symbols()


@lru_cache(maxsize=512)
def pixmap(name: str, color: str = "#000000", size: int = 16, dpr: float = 1.0, stroke: float = 1.75) -> QPixmap:
    """Icon ``name`` as a crisp pixmap of ``size`` logical px in ``color``. Unknown names give a blank pixmap."""
    px = max(1, int(round(size * dpr)))
    img = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    body = _load_symbols().get(name)
    if body:
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
               f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
        r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r.render(p, QRectF(0, 0, px, px))
        p.end()
    out = QPixmap.fromImage(img)
    out.setDevicePixelRatio(dpr)
    return out


def icon(name: str, color: str = "#000000", size: int = 16, stroke: float = 1.75) -> QIcon:
    """A QIcon for buttons (rendered at 2x so it stays sharp on high-DPI screens)."""
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size, 2.0, stroke))
    return ic
