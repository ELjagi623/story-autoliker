"""Speed slider: one control for "how long from one click to the next"."""
import threading
import time

import pytest

from clickflow import runner as R
from clickflow.clock import Clock
from clickflow.fakes import FakeInput
from clickflow.models import (FAST_INTERVAL, FAST_WAIT, SLOW_INTERVAL, Profile, Settings, Step, click_interval,
                              display_interval)
from clickflow.runner import Runner
from clickflow.storage import TemplateStore

from helpers import World
from test_runner import arrow_step, heart_step, make_runner


def slider_runner(w, speed, steps=None, events=None, **settings):
    steps = steps or [heart_step(), arrow_step()]
    r = make_runner(w, steps, events=events, speed_manual=False, speed=speed, **settings)
    r._overhead = 0.0  # a fake clock has no scan/click cost; start from zero instead of the 0.2 s default
    return r


def gaps(w):
    t = [a.t for a in w.input.clicks]
    return [b - a for a, b in zip(t, t[1:])]


# ------------------------------------------------------------------ mapping

def test_interval_mapping_endpoints_and_shape():
    assert click_interval(100) == 0.0  # fastest: no added delay at all
    assert click_interval(0) == pytest.approx(SLOW_INTERVAL) == pytest.approx(1.5)
    assert display_interval(100) == FAST_INTERVAL  # shown as what a scan + click physically take
    vals = [click_interval(s) for s in range(0, 100)]
    assert all(a > b for a, b in zip(vals, vals[1:]))  # strictly faster as the slider moves right
    assert vals[-1] == pytest.approx(FAST_INTERVAL, rel=0.03)  # continuous with the fastest end
    ratios = {round(click_interval(s) / click_interval(s + 10), 4) for s in range(0, 90, 10)}
    assert len(ratios) == 1  # geometric: every notch is the same relative change
    assert click_interval(-50) == click_interval(0) and click_interval(500) == 0.0  # clamped


def test_speed_is_clamped_and_round_trips():
    assert Settings(speed=250).normalise().speed == 100 and Settings(speed=-4).normalise().speed == 0
    s = Settings(speed=37, speed_manual=True)
    s2 = Settings.from_dict(s.to_dict())
    assert (s2.speed, s2.speed_manual) == (37, True)


# ------------------------------------------------------------------ pacing

@pytest.mark.parametrize("speed", [0, 25, 50, 75])
def test_click_to_click_spacing_matches_the_slider(speed):
    w = World()
    slider_runner(w, speed, loop_count=8).run()
    target = click_interval(speed)
    g = gaps(w)
    assert len(g) == 15
    assert all(x == pytest.approx(target, abs=0.03) for x in g[2:]), (speed, target, g)


def test_slowest_setting_is_one_and_a_half_seconds_between_clicks():
    w = World()
    slider_runner(w, 0, loop_count=5).run()
    assert all(x == pytest.approx(1.5, abs=0.03) for x in gaps(w)[1:])


def test_fastest_setting_adds_no_delay_beyond_the_small_fixed_waits():
    w = World()
    slider_runner(w, 100, loop_count=6).run()
    # each gap = wait after (0.05) + next wait before (0.05); nothing else is added
    assert all(x == pytest.approx(2 * FAST_WAIT, abs=0.06) for x in gaps(w))


def test_scan_and_click_time_is_compensated_not_added():
    """Real scans + clicks take time. Pacing must aim for the chosen interval, not interval + that time."""
    w = World()
    real_grab = w.screen.grab

    def slow_grab():  # every screenshot costs 0.15 s (bounds() for the corner check stays free, like in reality)
        w.clock.sleep(0.15)
        return real_grab()

    w.screen.grab = slow_grab
    r = make_runner(w, [heart_step(), arrow_step()], speed_manual=False, speed=25, loop_count=10)
    r.run()
    target = click_interval(25)
    assert all(x == pytest.approx(target, abs=0.06) for x in gaps(w)[4:]), (target, gaps(w))


def test_a_skipped_optional_step_does_not_add_delay():
    w = World(heart=False)  # the heart is never there (e.g. already liked): only the arrow is clicked
    steps = [heart_step(click_only_if_found=True), arrow_step()]
    slider_runner(w, 25, steps, loop_count=8).run()
    assert all(x == pytest.approx(click_interval(25), abs=0.06) for x in gaps(w)[2:])


def test_jitter_varies_the_spacing_within_bounds():
    w = World()
    slider_runner(w, 0, loop_count=30, jitter_percent=25.0).run()
    g = gaps(w)[2:]
    assert all(1.5 * 0.75 - 0.08 <= x <= 1.5 * 1.25 + 0.08 for x in g), g
    assert max(g) - min(g) > 0.2


def test_manual_mode_ignores_the_slider_and_uses_each_steps_waits():
    w = World()
    steps = [heart_step(wait_before=0.0, wait_after=0.3), arrow_step(wait_before=0.0, wait_after=0.3)]
    make_runner(w, steps, speed_manual=True, speed=0, loop_count=5).run()  # slider says "slowest" - must not matter
    assert all(x == pytest.approx(0.3, abs=0.06) for x in gaps(w))


def test_per_step_waits_are_not_used_in_slider_mode():
    w = World()
    steps = [heart_step(wait_before=5.0, wait_after=5.0), arrow_step(wait_before=5.0, wait_after=5.0)]
    slider_runner(w, 100, steps, loop_count=3).run()
    assert w.clock.now() < 3.0  # 5 s waits would have taken 30 s


def test_dry_run_is_paced_like_a_real_run():
    w = World()
    r = make_runner(w, [heart_step(), arrow_step()], dry=True, speed_manual=False, speed=0, loop_count=3)
    r._overhead = 0.0
    r.run()
    assert w.clock.now() >= 1.4 * 5 - 0.2  # 6 dry clicks, 5 gaps of ~1.5 s


def test_first_click_is_not_delayed():
    w = World()
    slider_runner(w, 0, loop_count=2).run()
    assert w.input.clicks[0].t < 0.3


def test_stop_interrupts_a_pacing_wait_immediately():
    w = World()
    profile = Profile(steps=[heart_step(), arrow_step()],
                      settings=Settings(start_delay=0, jitter_percent=0, infinite_loop=True, speed=0,
                                        speed_manual=False).normalise())
    r = Runner(profile, w.screen, FakeInput(Clock(), position=(500, 500)), clock=Clock(),
               templates=TemplateStore(None, w.templates))
    out = {}
    th = threading.Thread(target=lambda: out.update(res=r.run()))
    th.start()
    time.sleep(0.6)  # first click done, now inside the ~1.5 s pacing wait
    t0 = time.monotonic()
    r.request_stop()
    th.join(3)
    assert not th.is_alive() and out["res"].reason == R.USER
    assert time.monotonic() - t0 < 0.5


def test_run_log_states_the_speed_and_effective_waits():
    w = World()
    events = []
    slider_runner(w, 0, events=events, loop_count=1).run()
    msgs = [e.message for e in events]
    assert any("speed: 0%" in m and "1.50 s between clicks" in m for m in msgs)
    assert any("step 1:" in m and "wait 0.05s before / 0.05s after" in m for m in msgs)
    events.clear()
    make_runner(World(), [heart_step(wait_before=0.4, wait_after=0.7)], speed_manual=True, events=events).run()
    assert any("speed: MANUAL" in e.message for e in events)
    assert any("wait 0.4s before / 0.7s after" in e.message for e in events)


# ------------------------------------------------------------------ old profiles keep their timing

def test_legacy_profile_with_tiny_uniform_waits_opens_at_fastest():
    """The user's own profile: both steps wait 0.05 s before and after."""
    data = {"version": 2, "steps": [{"name": "heart", "wait_before": 0.05, "wait_after": 0.05},
                                    {"name": "next", "wait_before": 0.05, "wait_after": 0.05}],
            "settings": {"jitter_percent": 30.0}}
    p = Profile.from_dict(data)
    assert p.settings.speed_manual is False and p.settings.speed == 100 and p.version == 3


@pytest.mark.parametrize("steps", [
    [{"wait_before": 0.5, "wait_after": 2.0}],  # the bundled example: non-uniform, long waits
    [{"wait_before": 0.0, "wait_after": 1.0}, {"wait_before": 0.0, "wait_after": 1.0}],
    [{"wait_before": 0.05, "wait_after": 0.05}, {"wait_before": 0.3, "wait_after": 0.3}],
    [{"wait_before": 0.0, "wait_after": 0.05}],  # before != after
])
def test_legacy_profile_with_other_waits_stays_manual_so_timing_never_changes(steps):
    p = Profile.from_dict({"version": 2, "steps": [dict(name="s", **d) for d in steps], "settings": {}})
    assert p.settings.speed_manual is True
    assert [(s.wait_before, s.wait_after) for s in p.steps] == [(d["wait_before"], d["wait_after"]) for d in steps]


def test_explicit_speed_settings_are_respected_on_load():
    data = {"version": 3, "steps": [{"name": "s", "wait_before": 0.05, "wait_after": 0.05}],
            "settings": {"speed": 20, "speed_manual": False}}
    p = Profile.from_dict(data)
    assert (p.settings.speed, p.settings.speed_manual) == (20, False)
    data["settings"]["speed_manual"] = True
    assert Profile.from_dict(data).settings.speed_manual is True


def test_new_profiles_default_to_the_slider():
    s = Settings()
    assert s.speed_manual is False and s.speed == 50
