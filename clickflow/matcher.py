"""Template matcher: OpenCV normalised cross-correlation with multi-scale search.

Pure function of (image, template) so it is trivial to unit test with synthetic images.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import cv2
import numpy as np

# A match at least this good (and above the threshold) ends the scale search early.
EARLY_EXIT_CONFIDENCE = 0.95
# The scale grid is geometric (each step is +10 %), so a 0.4x and a 2.0x icon are searched equally finely.
# The best coarse scale is then refined at +/-2.5 % and +/-5 %.
COARSE_FACTOR = 1.10
REFINE_FACTORS = (0.95, 0.975, 1.025, 1.05)
MIN_TEMPLATE_SIDE = 8  # a template scaled below this many pixels carries no usable detail

# Outline mode (transparent icons such as an outline heart): only the icon's stroke, grown by this many pixels, is
# compared; the see-through parts of the captured image (whatever background was behind it) are ignored.
OUTLINE_DILATE = 1
# A stroke covering less / more of the box than this is not an outline icon: outline mode falls back to plain matching.
OUTLINE_MIN_SHARE = 0.02
OUTLINE_MAX_SHARE = 0.85
# Below this stroke share a template "looks like" a transparent outline icon (used by the diagnosis to suggest the mode).
OUTLINE_SUGGEST_SHARE = 0.45


def stroke_mask(template: np.ndarray) -> Optional[np.ndarray]:
    """The icon's own pixels in ``template`` (uint8, 255 = stroke), or None if no clear stroke stands out.

    Otsu splits the template into two brightness classes. The background is the class that touches the border
    most (a captured icon is surrounded by background), so the other class is the stroke; this works for light
    and for dark outlines.
    """
    gray = Matcher._gray(template)
    if gray.size == 0 or float(gray.std()) < 1.0:
        return None
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    border = np.concatenate([bw[0, :], bw[-1, :], bw[:, 0], bw[:, -1]])
    if float((border > 0).mean()) > 0.5:
        bw = cv2.bitwise_not(bw)
    share = float((bw > 0).mean())
    if not (OUTLINE_MIN_SHARE <= share <= OUTLINE_MAX_SHARE):
        return None
    return bw


def stroke_share(template: np.ndarray) -> float:
    """Fraction of the template box covered by the icon's stroke (1.0 when no stroke stands out)."""
    m = stroke_mask(template)
    return 1.0 if m is None else float((m > 0).mean())


def outline_mask(template: np.ndarray) -> Optional[np.ndarray]:
    """The matching mask for outline mode: the stroke grown by OUTLINE_DILATE px (uint8 0/255), or None."""
    m = stroke_mask(template)
    if m is None:
        return None
    if OUTLINE_DILATE > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * OUTLINE_DILATE + 1, 2 * OUTLINE_DILATE + 1))
        m = cv2.dilate(m, k)
    gray = Matcher._gray(template)
    if float(gray[m > 0].std()) < 1.0:  # nothing varies inside the mask: correlation would be meaningless
        return None
    return m


@dataclass(frozen=True)
class MatchResult:
    found: bool
    confidence: float  # best correlation seen, 0..1 (also filled when not found)
    x: int = 0  # top-left of the match in the searched image's pixels
    y: int = 0
    w: int = 0
    h: int = 0
    scale: float = 1.0  # template scale at which the best match occurred

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.w / 2.0, self.y + self.h / 2.0)


NO_MATCH = MatchResult(False, 0.0)


def scale_list(scale_min: float, scale_max: float, first: Optional[float] = None) -> list[float]:
    """Template scales to try between ``scale_min`` and ``scale_max`` (both always included).

    Geometric grid around 1.0, nearest 1.0 first. ``first`` (e.g. the scale that worked last time)
    is tried before everything else, which makes repeat scans cheap.
    """
    scales = {1.0, round(scale_min, 4), round(scale_max, 4)}
    s = 1.0 / COARSE_FACTOR
    while s >= scale_min - 1e-9:
        scales.add(round(s, 4))
        s /= COARSE_FACTOR
    s = COARSE_FACTOR
    while s <= scale_max + 1e-9:
        scales.add(round(s, 4))
        s *= COARSE_FACTOR
    ordered = sorted((v for v in scales if v > 0), key=lambda v: (abs(np.log(v)), v))
    if first and first > 0:
        first = round(first, 4)
        ordered = [first] + [v for v in ordered if v != first]
    return ordered


class Matcher:
    def __init__(self, method: int = cv2.TM_CCOEFF_NORMED) -> None:
        self.method = method

    # ------------------------------------------------------------------ public

    def find(
        self,
        image: np.ndarray,
        template: np.ndarray,
        threshold: float = 0.85,
        *,
        scales: Optional[Sequence[float]] = None,
        region: Optional[tuple[int, int, int, int]] = None,
        grayscale: bool = True,
        refine: bool = True,
        outline: bool = False,
    ) -> MatchResult:
        """Find ``template`` in ``image``.

        ``region`` is (x0, y0, x1, y1) in image pixels; results are reported in full-image
        pixels. The returned result always carries the best confidence seen, so callers can
        report "0.62 < 0.85" for a miss. Never raises on odd inputs - returns NO_MATCH.

        ``outline``: the template is a transparent / outline icon (e.g. an outline heart). Only its stroke is
        compared (grayscale), so whatever background shows through it does not lower the score.
        """
        if image is None or template is None or image.size == 0 or template.size == 0:
            return NO_MATCH
        ox = oy = 0
        if region is not None:
            x0, y0, x1, y1 = region
            image = image[y0:y1, x0:x1]
            ox, oy = x0, y0
            if image.size == 0:
                return NO_MATCH
        if grayscale or outline:
            image, template = self._gray(image), self._gray(template)
        elif image.ndim == 2 or template.ndim == 2:
            image, template = self._gray(image), self._gray(template)

        scale_seq = list(scales) if scales else [1.0]
        best = NO_MATCH
        tried: dict[float, MatchResult] = {}

        def attempt(s: float) -> MatchResult:
            key = round(s, 4)
            if key not in tried:
                tried[key] = self._match_at(image, template, key, outline)
            return tried[key]

        for s in scale_seq:
            r = attempt(s)
            if r.confidence > best.confidence:
                best = r
            if best.confidence >= max(threshold, EARLY_EXIT_CONFIDENCE):
                break

        if refine and len(scale_seq) > 1 and best.confidence < EARLY_EXIT_CONFIDENCE and best.w:
            base_scale = best.scale  # refine around the coarse winner, not around each improvement
            for f in REFINE_FACTORS:
                r = attempt(round(base_scale * f, 4))
                if r.confidence > best.confidence:
                    best = r

        if best.w == 0:
            return NO_MATCH
        return MatchResult(
            found=best.confidence >= threshold,
            confidence=best.confidence,
            x=best.x + ox,
            y=best.y + oy,
            w=best.w,
            h=best.h,
            scale=best.scale,
        )

    # ----------------------------------------------------------------- internals

    @staticmethod
    def _gray(img: np.ndarray) -> np.ndarray:
        if img.ndim == 2:
            return img
        if img.shape[2] == 4:
            return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    def _match_at(self, image: np.ndarray, template: np.ndarray, scale: float, outline: bool = False) -> MatchResult:
        if abs(scale - 1.0) > 1e-6:
            interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
            template = cv2.resize(template, None, fx=scale, fy=scale, interpolation=interp)
        th, tw = template.shape[:2]
        ih, iw = image.shape[:2]
        if min(th, tw) < MIN_TEMPLATE_SIDE or th > ih or tw > iw:
            return MatchResult(False, 0.0, scale=scale)
        mask = outline_mask(template) if outline else None
        if mask is not None:
            # The mask is rebuilt from the scaled template (cheap: templates are tiny), so it always lines up.
            res = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED, mask=mask)
        elif float(template.std()) < 1.0:
            # Zero-variance template: correlation is undefined (OpenCV may report 1.0) and any
            # normalised measure calls every smooth patch "similar". Use an absolute score:
            # 1 - RMS pixel difference / 32.
            msd = cv2.matchTemplate(image, template, cv2.TM_SQDIFF) / float(template.size)
            res = 1.0 - np.sqrt(np.maximum(msd, 0.0)) / 32.0
        else:
            res = cv2.matchTemplate(image, template, self.method)
        # Flat (zero-variance) templates/patches produce NaN/inf in normalised methods.
        res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        conf = float(max(0.0, min(1.0, max_val)))
        return MatchResult(False, conf, max_loc[0], max_loc[1], tw, th, scale)
