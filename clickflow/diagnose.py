"""Explain *why* a step is not found, and propose a concrete fix.

Used by "Test this step": when the configured search misses, the same screenshot is searched again
with the restrictions removed one at a time, which tells the causes apart:

* ``scale``     - the icon is on screen but at a size outside the configured scale range
                  (or multi-scale is off): fix = widen the scale range around the size that matched.
* ``region``    - the icon is on screen but outside the search box: fix = a box around where it is.
* ``threshold`` - something similar is there but the confidence is a bit too low: fix = lower threshold.
* ``absent``    - nothing resembling the template: re-capture it while the icon is visible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from .matcher import MatchResult, Matcher, scale_list
from .models import Preset, Step
from .presets import resolve_region
from .screen import Frame, Rect

WIDE_MIN, WIDE_MAX = 0.2, 3.0
NEAR_MISS_MARGIN = 0.30  # confidence this close to the threshold (and >= 0.5) counts as "similar, but too strict"


@dataclass
class Diagnosis:
    kind: str  # ok | scale | region | threshold | absent
    title: str
    lines: list[str] = field(default_factory=list)
    # Proposed settings change. Keys: scale_min, scale_max, multi_scale, threshold, region (global box).
    fix: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    rect: Optional[Rect] = None  # where the best match was, in screen coordinates
    scale: float = 1.0

    @property
    def text(self) -> str:
        return "\n".join([self.title] + [f"- {ln}" for ln in self.lines])


def _screen_rect(frame: Frame, r: MatchResult) -> Optional[Rect]:
    return frame.rect_to_screen(r.x, r.y, r.w, r.h) if r.w else None


def diagnose(frame: Frame, step: Step, template: np.ndarray, preset: Optional[Preset] = None,
             matcher: Optional[Matcher] = None) -> Diagnosis:
    matcher = matcher or Matcher()
    thr = step.threshold
    box = resolve_region(step, preset, frame)
    img_region = frame.region_to_image(box) if box else None
    use_box = img_region is not None
    configured = scale_list(step.scale_min, step.scale_max) if step.multi_scale else [1.0]

    r0 = matcher.find(frame.image, template, thr, scales=configured, region=img_region, grayscale=step.grayscale)
    where0 = _screen_rect(frame, r0)
    if r0.found:
        return Diagnosis("ok", f"FOUND with confidence {r0.confidence:.2f} (threshold {thr:.2f}): a run WOULD click.",
                         confidence=r0.confidence, rect=where0, scale=r0.scale)

    # 1) same area, but any size
    rw = matcher.find(frame.image, template, thr, scales=scale_list(WIDE_MIN, WIDE_MAX), region=img_region,
                      grayscale=step.grayscale)
    where_w = _screen_rect(frame, rw)
    if rw.found:
        smaller = rw.scale < 1.0
        factor = (1.0 / rw.scale) if smaller else rw.scale
        why = ("multi-scale search is switched off" if not step.multi_scale
               else f"the scale range {step.scale_min:.2f}-{step.scale_max:.2f} does not reach it")
        return Diagnosis(
            "scale",
            f"The icon IS on screen (confidence {rw.confidence:.2f} at scale {rw.scale:.2f}) but it is "
            f"{factor:.1f}x {'smaller' if smaller else 'larger'} than your captured template, and {why}.",
            [f"Found at ({where_w.left:.0f},{where_w.top:.0f}), size {where_w.width:.0f}x{where_w.height:.0f}; "
             f"your template is {template.shape[1]}x{template.shape[0]} px.",
             "Typical causes: browser zoom, window size or display scaling changed since the template was captured.",
             "Fix: widen the scale range (one click below), or re-capture the template at today's size."],
            fix={"multi_scale": True, "scale_min": min(1.0, round(rw.scale * 0.8, 2)),
                 "scale_max": max(1.0, round(rw.scale * 1.25, 2))},
            confidence=rw.confidence, rect=where_w, scale=rw.scale,
        )

    # 2) any size, whole screen: is it outside the search box?
    rr: Optional[MatchResult] = None
    if use_box:
        rr = matcher.find(frame.image, template, thr, scales=scale_list(WIDE_MIN, WIDE_MAX), region=None,
                          grayscale=step.grayscale)
        if rr.found:
            w = _screen_rect(frame, rr)
            pad = int(max(40, w.width, w.height))
            new_box = (int(w.left - pad), int(w.top - pad), int(w.width + 2 * pad), int(w.height + 2 * pad))
            return Diagnosis(
                "region",
                f"The icon is on screen (confidence {rr.confidence:.2f}) but OUTSIDE the search box.",
                [f"Found at ({w.left:.0f},{w.top:.0f}), size {w.width:.0f}x{w.height:.0f}; "
                 f"the search box is x={box[0]} y={box[1]} w={box[2]} h={box[3]}.",
                 "Fix: redraw the search box around where the icon really is (one click below)."],
                fix={"region": new_box}, confidence=rr.confidence, rect=w, scale=rr.scale,
            )

    best = max((r for r in (r0, rw, rr) if r is not None), key=lambda r: r.confidence)
    where = _screen_rect(frame, best)
    if best.confidence >= max(0.5, thr - NEAR_MISS_MARGIN):
        suggested = max(0.5, round(best.confidence - 0.05, 2))
        return Diagnosis(
            "threshold",
            f"Something similar is there, but confidence {best.confidence:.2f} is below the threshold {thr:.2f}.",
            ["The best candidate is at "
             f"({where.left:.0f},{where.top:.0f}). If that is the icon, lower the threshold a little "
             f"(suggested {suggested:.2f}) or re-capture a tighter template.",
             "Icons drawn over changing backgrounds (video, photos) match worse: crop tightly around the icon only."],
            fix={"threshold": suggested}, confidence=best.confidence, rect=where, scale=best.scale,
        )

    return Diagnosis(
        "absent",
        f"No match: the best confidence anywhere is only {best.confidence:.2f} (threshold {thr:.2f}).",
        ["Is the icon visible right now (not covered, not hidden by a hover/pause state, right page open)?",
         "Re-capture the template while the icon is on screen; the capture hides ClickFlow first.",
         "If the icon looks different (theme, selected/hover state, filled vs outline), it needs its own template."],
        confidence=best.confidence, rect=where, scale=best.scale,
    )
