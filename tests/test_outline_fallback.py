"""Transparent / outline icons (outline mode) and the not-found fallbacks (rescue near last, guarded blind click).

The motivating case: an outline heart drawn over a story. Its captured template is mostly the background it was
captured on, so a busy story background made plain matching miss and the like was silently skipped.
"""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from clickflow import diagnose, runner as R, storage
from clickflow.matcher import OUTLINE_SUGGEST_SHARE, Matcher, outline_mask, scale_list, stroke_mask, stroke_share
from clickflow.models import SCHEMA_VERSION, Profile, Settings, Step
from clickflow.runner import Runner
from clickflow.screen import Frame
from clickflow.storage import TemplateStore

from helpers import HEART_POS, World, make_arrow, make_background

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "instagram_story_like"

HEART_PTS = np.array([[24, 42], [6, 24], [5, 14], [10, 7], [18, 6], [24, 13], [30, 6], [38, 7], [43, 14],
                      [42, 24]], np.float32)


def heart_alpha(size: int = 48) -> np.ndarray:
    """Coverage (0..1) of a white outline heart with a 3 px stroke (anti-aliased)."""
    big = np.zeros((size * 4, size * 4), np.uint8)
    pts = (HEART_PTS * size / 48.0 * 4).astype(np.int32)
    cv2.polylines(big, [pts], True, 255, max(4, int(3 * 4 * size / 48)), cv2.LINE_AA)
    return cv2.resize(big, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0


def draw_outline_heart(bg: np.ndarray, x: int, y: int, size: int = 48, liked: bool = False) -> np.ndarray:
    """Composite the outline heart (white, with a faint shadow) - or the filled red 'liked' heart - onto ``bg``."""
    a = heart_alpha(size)
    out = bg.astype(np.float32).copy()
    roi = out[y:y + size, x:x + size]
    roi *= 1.0 - (cv2.GaussianBlur(a, (0, 0), 1.5) * 0.35)[..., None]
    if liked:
        fill = np.zeros((size, size), np.uint8)
        cv2.fillPoly(fill, [(HEART_PTS * size / 48.0).astype(np.int32)], 255)
        f = (fill.astype(np.float32) / 255.0)[..., None]
        roi[:] = roi * (1 - f) + np.array([60, 40, 235], np.float32) * f
    else:
        roi[:] = roi * (1 - a[..., None]) + 255.0 * a[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


def outline_template(size: int = 48) -> np.ndarray:
    """What a capture of the heart looks like: the outline over the (black) background it was captured on."""
    return draw_outline_heart(np.zeros((size, size, 3), np.uint8), 0, 0, size)


def busy(kind: str, w: int = 400, h: int = 300, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if kind == "noise":
        return rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
    if kind == "rects":
        b = np.full((h, w, 3), 120, np.uint8)
        for _ in range(300):
            x0, y0 = int(rng.integers(0, w)), int(rng.integers(0, h))
            cv2.rectangle(b, (x0, y0), (x0 + int(rng.integers(3, 40)), y0 + int(rng.integers(3, 40))),
                          tuple(int(c) for c in rng.integers(0, 255, 3)), -1)
        return b
    if kind == "photo":
        small = rng.integers(0, 255, (h // 6, w // 6, 3), dtype=np.uint8)
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    if kind == "bright":
        small = rng.integers(150, 255, (h // 10, w // 10, 3), dtype=np.uint8)
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    raise ValueError(kind)


KINDS = ["noise", "rects", "photo", "bright"]


# ------------------------------------------------------------------ matcher: outline mode

@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("scale", [1.0, 1.25])
def test_outline_mode_finds_a_see_through_heart_on_busy_backgrounds(kind, scale):
    tpl = outline_template(48)
    size = int(round(48 * scale))
    img = draw_outline_heart(busy(kind, seed=7), 150, 100, size)
    r = Matcher().find(img, tpl, 0.85, scales=scale_list(0.6, 1.6), outline=True)
    assert r.found, r
    assert abs(r.x - 150) <= 3 and abs(r.y - 100) <= 3


def test_plain_matching_misses_on_noise_but_outline_mode_does_not():
    """The bug itself: the template's see-through parts hold the capture background, so plain matching fails."""
    tpl = outline_template(48)
    img = draw_outline_heart(busy("noise", seed=3), 150, 100)
    m = Matcher()
    plain = m.find(img, tpl, 0.85, scales=[1.0])
    outline = m.find(img, tpl, 0.85, scales=[1.0], outline=True)
    assert not plain.found
    assert outline.found and outline.confidence > plain.confidence + 0.1


@pytest.mark.parametrize("kind", KINDS)
def test_outline_mode_does_not_take_the_liked_heart_or_an_empty_background(kind):
    tpl = outline_template(48)
    m = Matcher()
    bg = busy(kind, seed=11)
    liked = draw_outline_heart(bg, 150, 100, liked=True)
    assert m.find(liked, tpl, 0.85, scales=scale_list(0.6, 1.6), outline=True).confidence < 0.75
    assert m.find(bg, tpl, 0.85, scales=scale_list(0.6, 1.6), outline=True).confidence < 0.75


def test_stroke_mask_picks_the_icon_for_light_and_dark_outlines():
    light = outline_template(48)
    dark = 255 - light  # a dark outline on a light background
    for tpl in (light, dark):
        m = stroke_mask(tpl)
        assert m is not None
        assert 0.05 < (m > 0).mean() < 0.4  # the stroke, not the background
        assert m[0, 0] == 0 and m[-1, -1] == 0  # the border is background
    assert stroke_mask(np.full((30, 30, 3), 90, np.uint8)) is None  # flat: no stroke
    assert outline_mask(np.full((30, 30, 3), 90, np.uint8)) is None


def test_outline_mode_on_a_solid_icon_still_matches():
    """Outline mode on an icon with no see-through parts must not break it (falls back or still matches)."""
    arrow = make_arrow(40)
    img = make_background(400, 300, seed=2)
    img[120:160, 200:240] = arrow
    r = Matcher().find(img, arrow, 0.85, scales=[1.0], outline=True)
    assert r.found and (r.x, r.y) == (200, 120)


def test_example_heart_template_is_recognised_as_an_outline_icon():
    tpl = storage.read_image(EXAMPLE / "templates" / "Like_heart_-_only_if_not_yet_liked_99ca41cf.png")
    assert stroke_share(tpl) < OUTLINE_SUGGEST_SHARE
    assert stroke_share(np.full((30, 30, 3), 90, np.uint8)) == 1.0  # nothing stands out: not an outline icon


def test_diagnosis_suggests_outline_mode():
    tpl = outline_template(48)
    img = draw_outline_heart(busy("noise", seed=3), 150, 100)
    step = Step(name="heart", template="h.png", threshold=0.85, multi_scale=False)
    d = diagnose.diagnose(Frame(img), step, tpl)
    assert d.kind == "outline" and d.fix == {"ignore_background": True}
    step.ignore_background = True
    assert diagnose.diagnose(Frame(img), step, tpl).kind == "ok"


# ------------------------------------------------------------------ runner: fallbacks

LIKED = np.zeros((48, 48, 3), np.uint8)  # the "already liked" icon: a solid red block with a white dot
LIKED[:] = (40, 40, 230)
cv2.circle(LIKED, (16, 16), 6, (255, 255, 255), -1)


class StoryWorld(World):
    """Heart + arrow. After the first story the heart can turn 'invisible', degraded, or 'liked'."""

    def __init__(self, later: str = "hidden"):
        super().__init__()
        self.later = later  # what the heart looks like from the 2nd story on: hidden | degraded | liked | normal
        self.story = 1
        self.degraded = None
        self.templates["liked.png"] = LIKED

    def render(self):
        img = self.bg
        mode = "normal" if self.story == 1 else self.later
        if mode == "normal":
            img = World.render(self)
        else:
            heart, self.heart = self.heart, False
            img = World.render(self)
            self.heart = heart
            x, y = HEART_POS
            if mode == "degraded":
                img = img.copy()
                img[y:y + 48, x:x + 48] = self.degraded
            elif mode == "liked":
                img = img.copy()
                img[y:y + 48, x:x + 48] = LIKED
        return img

    def _clicked(self, a) -> None:
        super()._clicked(a)
        if self.click_log[-1] == "A":
            self.story += 1


def story_steps(**heart_kw):
    heart = dict(name="heart", template="heart.png", wait_after=0.0, timeout=0.0, multi_scale=False,
                 click_only_if_found=True)
    heart.update(heart_kw)
    arrow = dict(name="arrow", template="arrow.png", wait_after=0.0, timeout=0.0, multi_scale=False)
    return [Step(**heart), Step(**arrow)]


def make_runner(world, steps, *, dry=False, events=None, loops=4):
    s = Settings(start_delay=0.0, jitter_percent=0.0, scan_interval=0.1, speed_manual=True, loop_count=loops,
                 max_idle_loops=0).normalise()
    profile = Profile(name="t", steps=steps, settings=s)
    return Runner(profile, world.screen, world.input, clock=world.clock,
                  templates=TemplateStore(None, world.templates), dry_run=dry,
                  on_event=(events.append if events is not None else None))


def test_fallbacks_off_means_a_missed_heart_is_skipped_as_before():
    w = StoryWorld("hidden")
    assert make_runner(w, story_steps()).run().reason == R.COMPLETED
    assert w.click_log == ["H", "A", "A", "A", "A"]


def test_rescue_near_last_position_clicks_a_slightly_degraded_heart():
    w = StoryWorld("degraded")
    rng = np.random.default_rng(5)
    noisy = np.clip(w.heart_img.astype(np.int16) + rng.integers(-45, 45, w.heart_img.shape), 0, 255).astype(np.uint8)
    w.degraded = noisy
    img = w.bg.copy()
    img[HEART_POS[1]:HEART_POS[1] + 48, HEART_POS[0]:HEART_POS[0] + 48] = noisy
    conf = Matcher().find(img, w.heart_img, 0.5).confidence
    thr = min(0.99, conf + 0.05)  # the normal search misses ...
    assert conf >= max(R.RESCUE_MIN_THRESHOLD, thr - R.RESCUE_MARGIN)  # ... the relaxed rescue does not
    events = []
    r = make_runner(w, story_steps(threshold=thr, rescue_near_last=True), events=events)
    assert r.run().reason == R.COMPLETED
    assert w.click_log == ["H", "A"] * 4
    assert sum("rescued near its last position" in e.message for e in events) == 3


def test_guard_image_present_means_no_click():
    w = StoryWorld("liked")
    events = []
    steps = story_steps(rescue_near_last=True, fallback_click_last=True, guard_template="liked.png")
    assert make_runner(w, steps, events=events).run().reason == R.COMPLETED
    assert w.click_log == ["H", "A", "A", "A", "A"]  # never unliked
    assert sum("already done, skipped" in e.message for e in events) == 3


def test_blind_click_when_guard_is_absent_at_most_three_in_a_row():
    w = StoryWorld("hidden")
    events = []
    steps = story_steps(fallback_click_last=True, guard_template="liked.png")
    assert make_runner(w, steps, events=events, loops=6).run().reason == R.COMPLETED
    # story 1: real match; stories 2-4: blind clicks; stories 5-6: streak limit reached -> skipped
    assert w.click_log == ["H", "A", "H", "A", "H", "A", "H", "A", "A", "A"]
    assert sum("blind click at its last position" in e.message for e in events) == R.BLIND_MAX_STREAK
    assert any("already 3 in a row" in e.message for e in events)


def test_blind_click_needs_a_recent_real_match(monkeypatch):
    monkeypatch.setattr(R, "BLIND_MAX_STREAK", 100)
    w = StoryWorld("hidden")
    steps = story_steps(fallback_click_last=True)
    assert make_runner(w, steps, loops=9).run().reason == R.COMPLETED
    hearts = w.click_log.count("H")
    assert hearts == 1 + R.BLIND_MAX_LOOPS  # the real one, then blind clicks while it is recent enough


def test_no_blind_click_without_any_real_match_first():
    w = StoryWorld("hidden")
    w.story = 2  # the heart is never visible
    assert make_runner(w, story_steps(fallback_click_last=True)).run().reason == R.COMPLETED
    assert "H" not in w.click_log


def test_unreadable_guard_image_blocks_the_blind_click():
    w = StoryWorld("hidden")
    steps = story_steps(fallback_click_last=True, guard_template="missing.png")
    assert make_runner(w, steps).run().reason == R.COMPLETED
    assert w.click_log == ["H", "A", "A", "A", "A"]


def test_blind_click_in_dry_run_only_reports():
    w = StoryWorld("hidden")
    events = []

    def on_event(e):  # a dry run never clicks, so advance the story when the arrow *would* be clicked
        events.append(e)
        if e.kind == "click" and e.data.get("step") == "arrow":
            w.story += 1

    steps = story_steps(fallback_click_last=True)
    r = make_runner(w, steps, dry=True, loops=2)
    r.on_event = on_event
    assert r.run().reason == R.COMPLETED
    assert w.input.clicks == []
    heart_clicks = [e for e in events if e.kind == "click" and e.data.get("step") == "heart"]
    assert len(heart_clicks) == 2 and all(e.data.get("dry") for e in heart_clicks)
    assert any("blind click at its last position" in e.message for e in events)


# ------------------------------------------------------------------ model / storage

def test_old_profile_loads_with_fallbacks_off():
    data = json.loads((EXAMPLE / "profile.json").read_text(encoding="utf-8"))
    for st in data["steps"]:
        for k in ("ignore_background", "rescue_near_last", "fallback_click_last", "guard_template", "guard_threshold"):
            st.pop(k, None)
    data["version"] = 3
    prof = Profile.from_dict(data)
    assert prof.version == SCHEMA_VERSION == 4
    for st in prof.steps:
        assert not (st.ignore_background or st.rescue_near_last or st.fallback_click_last or st.guard_template)
        assert st.guard_threshold == 0.85


def test_new_fields_round_trip_and_clamp():
    st = Step(ignore_background=True, rescue_near_last=True, fallback_click_last=True, guard_template="g.png",
              guard_threshold=3.0).normalise()
    assert st.guard_threshold == 1.0
    back = Step.from_dict(st.to_dict())
    assert (back.ignore_background, back.rescue_near_last, back.fallback_click_last, back.guard_template) == \
        (True, True, True, "g.png")


def test_guard_image_is_saved_copied_and_exported(tmp_path):
    prof = storage.new_profile("g", root=tmp_path)
    st = Step(name="heart")
    prof.steps.append(st)
    rel = storage.save_guard_template(prof.directory, st, LIKED)
    assert st.guard_template == rel and (prof.directory / rel).exists()
    assert rel in storage.template_files(prof)
    dup = Step(name="heart copy")
    storage.copy_template(prof.directory, st, dup)
    assert dup.guard_template and dup.guard_template != rel and (prof.directory / dup.guard_template).exists()


def test_example_profile_uses_outline_mode_and_rescue_for_the_heart():
    prof = storage.load_profile(EXAMPLE)
    heart, arrow = prof.steps
    assert heart.ignore_background and heart.rescue_near_last
    assert not arrow.ignore_background  # a solid round button, not a see-through icon
    assert not any(st.fallback_click_last for st in prof.steps)  # needs the user's own 'liked' capture first
