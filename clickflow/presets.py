"""Display presets: pick the right preset *and* the right monitor from the detected screen resolutions.

Selection rules (``choose``):

1. A preset is a candidate for every monitor whose resolution equals ``preset.resolution``.
2. No candidate  -> no preset (the default step settings are used).
3. One candidate -> that one.
4. Several (two monitors share a resolution, or two presets fit) -> each is probed: the monitor is
   captured and the first few enabled steps are searched with the preset's own boxes/templates; the
   best confidence wins. Ties fall back to a fixed priority (preset's preferred monitor, primary
   monitor, preset order).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from .matcher import Matcher, scale_list
from .models import Preset, Profile, Step, effective_region, effective_template
from .screen import Frame, MonitorInfo, ScreenProvider

PROBE_STEPS = 3


@dataclass
class Selection:
    preset: Optional[Preset]
    monitor: Optional[MonitorInfo]
    reason: str
    scores: list[tuple[str, float]] = field(default_factory=list)


def resolve_region(step: Step, preset: Optional[Preset], frame: Frame) -> Optional[tuple[int, int, int, int]]:
    """The step's search box in *global* screen coordinates for the frame being searched.

    Preset boxes are stored relative to the monitor, so the frame's origin is added back.
    The default (no preset) box is already in global coordinates.
    """
    r = effective_region(step, preset)
    if not r:
        return None
    if preset is None:
        return r
    return (int(r[0] + frame.left), int(r[1] + frame.top), r[2], r[3])


def candidates(presets: list[Preset], monitors: list[MonitorInfo]) -> list[tuple[Preset, MonitorInfo]]:
    """(preset, monitor) pairs whose resolution matches, best priority first."""
    pairs = []
    for order, p in enumerate(presets):
        for m in monitors:
            if p.resolution == m.resolution:
                hinted = 0 if p.monitor == m.index else 1
                pairs.append(((hinted, 0 if m.primary else 1, order, m.index), p, m))
    pairs.sort(key=lambda t: t[0])
    return [(p, m) for _, p, m in pairs]


def describe_monitors(monitors: list[MonitorInfo]) -> str:
    return ", ".join(m.label for m in monitors) or "none detected"


def resolve_explicit(preset: Preset, monitors: list[MonitorInfo]) -> Selection:
    """A preset the user picked by hand: find its monitor (same resolution, preferred index first)."""
    cands = [(p, m) for p, m in candidates([preset], monitors)]
    if cands:
        p, m = cands[0]
        return Selection(p, m, f"preset '{p.name}' on {m.label}")
    hint = next((m for m in monitors if m.index == preset.monitor), None)
    return Selection(
        preset, hint,
        f"preset '{preset.name}' expects {preset.resolution[0]}x{preset.resolution[1]} but the displays are: "
        f"{describe_monitors(monitors)} - using it anyway",
    )


def probe_score(
    preset: Preset, frame: Frame, steps: list[Step], load_template: Callable[[str], np.ndarray], matcher: Matcher
) -> float:
    """Best match confidence of the probe steps on this frame (0 if nothing could be searched)."""
    best = 0.0
    for step in steps:
        rel = effective_template(step, preset)
        if not rel:
            continue
        try:
            tpl = load_template(rel)
            region = resolve_region(step, preset, frame)
            img_region = frame.region_to_image(region) if region else None
            if region and img_region is None:
                continue
            scales = scale_list(step.scale_min, step.scale_max) if step.multi_scale else [1.0]
            r = matcher.find(frame.image, tpl, step.threshold, scales=scales, region=img_region,
                             grayscale=step.grayscale)
            best = max(best, r.confidence)
        except Exception:
            continue
    return best


def choose(
    profile: Profile,
    screen: ScreenProvider,
    load_template: Callable[[str], np.ndarray],
    matcher: Optional[Matcher] = None,
) -> Selection:
    matcher = matcher or Matcher()
    monitors = screen.monitors()
    cands = candidates(profile.presets, monitors)
    if not cands:
        return Selection(None, None, f"no preset matches the detected displays ({describe_monitors(monitors)})")
    if len(cands) == 1:
        p, m = cands[0]
        return Selection(p, m, f"preset '{p.name}' matches {m.label}")

    steps = [s for s in profile.steps if s.enabled][:PROBE_STEPS]
    scores: list[tuple[str, float]] = []
    best: Optional[tuple[Preset, MonitorInfo]] = None
    best_score = -1.0
    for p, m in cands:
        screen.set_monitor(m.index)
        try:
            score = probe_score(p, screen.grab(), steps, load_template, matcher)
        except Exception:
            score = 0.0
        scores.append((f"'{p.name}' on monitor {m.index}", score))
        if score > best_score + 1e-9:
            best, best_score = (p, m), score
    assert best is not None
    p, m = best
    detail = ", ".join(f"{label}: {sc:.2f}" for label, sc in scores)
    if best_score <= 0.0:
        why = f"icons not visible on any matching display, using priority order ({detail})"
    else:
        why = f"best icon match ({detail})"
    return Selection(p, m, f"preset '{p.name}' on {m.label} - {why}", scores)
