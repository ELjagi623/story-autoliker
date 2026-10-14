"""Regression: "Test this step shows the right place but nothing is clicked".

Root cause found in a user's log: the icons on screen were ~0.5x the size of the captured templates, outside the old
0.7-1.4 scale range. The best match then sat at the range edge with a low confidence (0.29 / 0.68 vs thresholds
0.88 / 0.85) at nearly the right position, so the step was "not found" and nothing was clicked.
"""
import cv2
import numpy as np
import pytest

from clickflow import diagnose as D
from clickflow import runner as R
from clickflow.clock import FakeClock
from clickflow.fakes import FakeInput, FakeScreen
from clickflow.matcher import Matcher, scale_list
from clickflow.models import Profile, Settings, Step
from clickflow.runner import Runner
from clickflow.screen import Frame
from clickflow.storage import TemplateStore

from helpers import make_arrow, make_background, make_heart, paste


def dark_ui(w=400, h=300, seed=0):
    rng = np.random.default_rng(seed)
    return np.clip(27 + rng.normal(0, 2, (h, w, 3)), 0, 255).astype(np.uint8)


def low_contrast_arrow(size=68):
    """Like the user's real 'next story' icon: a dim grey disc with a dark chevron on a near-black background."""
    img = np.full((size, size, 3), 27, np.uint8)
    cv2.circle(img, (size // 2, size // 2), int(size * 0.42), (68, 68, 68), -1)
    cv2.polylines(img, [np.array([[size * 0.42, size * 0.3], [size * 0.62, size * 0.5], [size * 0.42, size * 0.7]],
                                 np.int32)], False, (27, 27, 27), max(2, size // 12))
    return img


def shrink(img, f):
    return cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC)


# ------------------------------------------------------------------ the matcher

OLD_RANGE = scale_list(0.7, 1.4)
NEW_RANGE = scale_list(0.35, 2.5)


@pytest.mark.parametrize("make", [lambda: make_heart(50), low_contrast_arrow])
@pytest.mark.parametrize("on_screen", [0.5, 0.42, 0.4, 2.0, 2.3])
def test_default_range_finds_icons_much_smaller_or_larger_than_the_template(make, on_screen):
    tpl = make()
    bg = dark_ui()
    icon = shrink(tpl, on_screen)
    shot = paste(bg, icon, 150, 120)
    r = Matcher().find(shot, tpl, 0.85, scales=NEW_RANGE)
    assert r.found and r.confidence > 0.9, (on_screen, r)
    assert abs(r.scale - on_screen) / on_screen < 0.08
    cx, cy = r.x + r.w / 2, r.y + r.h / 2
    assert abs(cx - (150 + icon.shape[1] / 2)) <= 2 and abs(cy - (120 + icon.shape[0] / 2)) <= 2


def test_old_narrow_range_reproduces_the_reported_symptom():
    """Right place, low confidence, best scale stuck at the edge of the range: exactly the user's log."""
    tpl = make_heart(50)
    shot = paste(dark_ui(), shrink(tpl, 0.5), 150, 120)
    r = Matcher().find(shot, tpl, 0.88, scales=OLD_RANGE)
    assert not r.found and r.confidence < 0.88  # below the threshold (0.29 for the user's thinner real heart)
    assert r.scale <= 0.7 * 1.08  # at the lower edge
    assert abs(r.x + r.w / 2 - (150 + 12.5)) <= 6  # ...yet the position is about right, so it LOOKS accurate


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("make", [lambda: make_heart(50), low_contrast_arrow, lambda: make_arrow(40)])
def test_wide_range_does_not_invent_matches_on_other_content(seed, make):
    tpl = make()
    for bg in (dark_ui(seed=seed), make_background(400, 300, seed=seed)):
        r = Matcher().find(bg, tpl, 0.85, scales=NEW_RANGE)
        assert not r.found, r


def test_scale_list_tries_the_remembered_scale_first_and_is_geometric():
    s = scale_list(0.35, 2.5, first=0.5)
    assert s[0] == 0.5 and 1.0 in s and min(s) == 0.35 and max(s) == 2.5
    ratios = [b / a for a, b in zip(sorted(s), sorted(s)[1:])]
    assert max(ratios) <= 1.2  # no coarse jumps, even at small scales
    assert scale_list(0.7, 1.4)[0] == 1.0


# ------------------------------------------------------------------ the runner

def make_runner(img, step, **settings):
    clock = FakeClock()
    inputs = FakeInput(clock, position=(5000, 5000))
    s = dict(start_delay=0, jitter_percent=0, scan_interval=0.1, loop_count=2, speed_manual=True)
    s.update(settings)
    prof = Profile(steps=[step], settings=Settings(**s).normalise())
    events = []
    matcher_calls = []

    class SpyMatcher(Matcher):
        def find(self, image, template, threshold=0.85, **kw):
            matcher_calls.append(kw.get("scales"))
            return super().find(image, template, threshold, **kw)

    r = Runner(prof, FakeScreen(img), inputs, clock=clock, templates=TemplateStore(None, {"t.png": TPL}),
               on_event=events.append, matcher=SpyMatcher())
    return r, inputs, events, matcher_calls


TPL = make_heart(50)


def test_runner_clicks_an_icon_half_the_template_size_with_default_settings():
    shot = paste(dark_ui(), shrink(TPL, 0.5), 150, 120)
    r, inp, events, _ = make_runner(shot, Step(name="heart", template="t.png", timeout=0, wait_after=0))
    res = r.run()
    assert res.reason == R.COMPLETED and res.clicks == 2
    assert inp.clicks[0].x == pytest.approx(150 + 12.5, abs=2) and inp.clicks[0].y == pytest.approx(120 + 13, abs=2)


def test_runner_remembers_the_matching_scale_for_the_next_scan():
    shot = paste(dark_ui(), shrink(TPL, 0.5), 150, 120)
    r, _, _, calls = make_runner(shot, Step(name="heart", template="t.png", timeout=0, wait_after=0))
    r.run()
    assert calls[0][0] == 1.0  # first scan: nearest to 1.0 first
    assert calls[1][0] == pytest.approx(0.5, abs=0.05)  # second scan starts with the scale that worked


def test_not_found_log_warns_when_the_best_match_sits_at_the_scale_range_edge():
    shot = paste(dark_ui(), shrink(TPL, 0.2), 150, 120)  # far below even the new range
    st = Step(name="heart", template="t.png", timeout=0, wait_after=0, not_found_action="skip")
    r, _, events, _ = make_runner(shot, st, loop_count=1)
    r.run()
    assert any("EDGE of the scale range" in e.message for e in events)
    st2 = Step(name="heart", template="t.png", timeout=0, wait_after=0, multi_scale=False)
    r2, _, events2, _ = make_runner(paste(dark_ui(), shrink(TPL, 0.5), 150, 120), st2, loop_count=1)
    r2.run()
    assert any("multi-scale is OFF" in e.message for e in events2)


# ------------------------------------------------------------------ diagnosis

def frame_of(img, left=0, top=0):
    return Frame(img, float(left), float(top))


def test_diagnose_ok_when_found():
    shot = paste(dark_ui(), TPL, 100, 100)
    d = D.diagnose(frame_of(shot), Step(name="h", template="t.png"), TPL)
    assert d.kind == "ok" and "WOULD click" in d.title


def test_diagnose_size_outside_the_range_proposes_a_wider_range():
    shot = paste(dark_ui(), shrink(TPL, 0.25), 150, 120)  # 4x smaller than the template
    d = D.diagnose(frame_of(shot), Step(name="h", template="t.png", scale_min=0.7, scale_max=1.4), TPL)
    assert d.kind == "scale" and "4.0x smaller" in d.title
    assert d.fix["multi_scale"] is True and d.fix["scale_min"] <= 0.25 * 1.01 and d.fix["scale_max"] >= 1.0
    # applying the fix makes the step found
    st = Step(name="h", template="t.png", scale_min=0.7, scale_max=1.4)
    for k, v in d.fix.items():
        setattr(st, k, v)
    assert D.diagnose(frame_of(shot), st.normalise(), TPL).kind == "ok"


def test_diagnose_multi_scale_switched_off():
    shot = paste(dark_ui(), shrink(TPL, 0.5), 150, 120)
    d = D.diagnose(frame_of(shot), Step(name="h", template="t.png", multi_scale=False), TPL)
    assert d.kind == "scale" and "switched off" in d.title and d.fix["multi_scale"] is True


def test_diagnose_icon_outside_the_search_box():
    shot = paste(dark_ui(), TPL, 280, 200)
    st = Step(name="h", template="t.png", region=(20, 20, 100, 100))
    d = D.diagnose(frame_of(shot), st, TPL)
    assert d.kind == "region" and "OUTSIDE the search box" in d.title
    l, t, w, h = d.fix["region"]
    assert l <= 280 and t <= 200 and l + w >= 330 and t + h >= 250  # the proposed box contains the icon


def test_diagnose_near_miss_proposes_a_lower_threshold():
    rng = np.random.default_rng(5)
    noisy = np.clip(paste(dark_ui(), TPL, 100, 100).astype(np.float32) + rng.normal(0, 38, (300, 400, 3)), 0, 255)
    shot = noisy.astype(np.uint8)
    conf = Matcher().find(shot, TPL, 0.5, scales=NEW_RANGE).confidence
    assert 0.5 < conf < 0.95, conf
    st = Step(name="h", template="t.png", threshold=min(1.0, conf + 0.1))
    d = D.diagnose(frame_of(shot), st, TPL)
    assert d.kind == "threshold" and d.fix["threshold"] < st.threshold and d.fix["threshold"] >= 0.5


def test_diagnose_absent_when_nothing_resembles_it():
    d = D.diagnose(frame_of(dark_ui()), Step(name="h", template="t.png"), TPL)
    assert d.kind == "absent" and not d.fix and "re-capture" in d.text.lower()


def test_diagnose_respects_preset_regions_relative_to_the_monitor():
    from clickflow.models import Preset

    shot = paste(dark_ui(), TPL, 280, 200)
    st = Step(name="h", template="t.png")
    pre = Preset(name="P", resolution=(400, 300), regions={st.id: (20, 20, 100, 100)})  # local to the monitor
    d = D.diagnose(frame_of(shot, left=1000, top=0), st, TPL, pre)
    assert d.kind == "region"


def test_runner_diagnose_wraps_the_module():
    shot = paste(dark_ui(), shrink(TPL, 0.5), 150, 120)
    r, *_ = make_runner(shot, Step(name="h", template="t.png", multi_scale=False))
    assert r.diagnose(r.profile.steps[0]).kind == "scale"
    assert r.diagnose(Step(name="none")).kind == "absent"
