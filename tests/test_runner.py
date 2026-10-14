import threading
import time

import pytest

from clickflow import runner as R
from clickflow.clock import Clock
from clickflow.fakes import FakeInput, FakeScreen
from clickflow.models import Profile, Settings, Step
from clickflow.runner import Runner
from clickflow.storage import TemplateStore

from helpers import ARROW_POS, HEART_POS, World, make_background


def heart_step(**kw):
    d = dict(name="heart", template="heart.png", wait_after=0.0, timeout=0.0, multi_scale=False)
    d.update(kw)
    return Step(**d)


def arrow_step(**kw):
    d = dict(name="arrow", template="arrow.png", wait_after=0.0, timeout=0.0, multi_scale=False)
    d.update(kw)
    return Step(**d)


def make_runner(world, steps, *, end=None, dry=False, events=None, **settings):
    base = dict(start_delay=0.0, jitter_percent=0.0, scan_interval=0.1, corner_abort=True, speed_manual=True)
    base.update(settings)
    profile = Profile(name="t", steps=steps, settings=Settings(**base).normalise(), end_condition=end)
    return Runner(
        profile, world.screen, world.input,
        clock=world.clock, templates=TemplateStore(None, world.templates), dry_run=dry,
        on_event=(events.append if events is not None else None),
    )


# ------------------------------------------------------------------ order / positions

def test_steps_run_in_order_and_click_centres():
    w = World()
    r = make_runner(w, [heart_step(), arrow_step()], loop_count=3)
    res = r.run()
    assert res.reason == R.COMPLETED and res.loops == 3 and res.clicks == 6
    assert w.click_log == ["H", "A"] * 3
    hx, hy = w.center(HEART_POS, w.heart_img)
    ax, ay = w.center(ARROW_POS, w.arrow_img)
    c = w.input.clicks
    assert (c[0].x, c[0].y) == pytest.approx((hx, hy), abs=1.0)
    assert (c[1].x, c[1].y) == pytest.approx((ax, ay), abs=1.0)


def test_disabled_steps_are_skipped():
    w = World()
    r = make_runner(w, [heart_step(enabled=False), arrow_step()])
    assert r.run().reason == R.COMPLETED
    assert w.click_log == ["A"]


def test_offset_and_click_types():
    w = World()
    r = make_runner(w, [heart_step(offset_x=10, offset_y=-5, click_type="right"),
                        arrow_step(click_type="double")])
    r.run()
    hx, hy = w.center(HEART_POS, w.heart_img)
    a0, a1 = w.input.clicks
    assert (a0.x, a0.y) == pytest.approx((hx + 10, hy - 5), abs=1.0)
    assert a0.button == "right" and a0.clicks == 1
    assert a1.button == "left" and a1.clicks == 2


def test_region_restricts_search():
    w = World()
    ok = make_runner(w, [heart_step(region=(HEART_POS[0] - 20, HEART_POS[1] - 20, 100, 100))])
    assert ok.run().clicks == 1
    w2 = World()
    far = make_runner(w2, [heart_step(region=(400, 450, 100, 100))])  # heart is not there
    assert far.run().clicks == 0


def test_hidpi_scale_and_origin_convert_to_click_coordinates():
    """Retina-style: image pixels are 2x the clickable units and the screen starts at (100, 50)."""
    w = World(scale=2.0, left=100.0, top=50.0)
    r = make_runner(w, [heart_step()])
    r.run()
    c = w.input.clicks[0]
    hx, hy = w.center(HEART_POS, w.heart_img)
    assert (c.x, c.y) == pytest.approx((hx, hy), abs=1.0)
    assert w.click_log == ["H"]


# ------------------------------------------------------------------ waits

def test_waits_are_honoured_exactly_without_jitter():
    w = World()
    steps = [heart_step(wait_before=1.0, wait_after=2.0), arrow_step(wait_before=0.5, wait_after=0.25)]
    r = make_runner(w, steps, loop_count=2, start_delay=0.0)
    r.run()
    t = [a.t for a in w.input.clicks]
    assert t[0] == pytest.approx(1.0, abs=0.06)
    assert t[1] - t[0] == pytest.approx(2.0 + 0.5, abs=0.06)
    assert t[2] - t[1] == pytest.approx(0.25 + 1.0, abs=0.06)
    assert t[3] - t[2] == pytest.approx(2.0 + 0.5, abs=0.06)


def test_start_delay():
    w = World()
    r = make_runner(w, [heart_step()], start_delay=3.0)
    r.run()
    assert w.input.clicks[0].t == pytest.approx(3.0, abs=0.06)


def test_jitter_stays_in_bounds_and_varies():
    w = World()
    r = make_runner(w, [heart_step(wait_after=2.0)], loop_count=40, jitter_percent=25.0)
    r.run()
    t = [a.t for a in w.input.clicks]
    gaps = [b - a for a, b in zip(t, t[1:])]
    assert all(2.0 * 0.75 - 0.06 <= g <= 2.0 * 1.25 + 0.06 for g in gaps)
    assert max(gaps) - min(gaps) > 0.3  # randomised, not constant


# ------------------------------------------------------------------ not found handling

def test_not_found_skip_continues_with_next_step():
    w = World(heart=False)
    r = make_runner(w, [heart_step(not_found_action="skip"), arrow_step()])
    res = r.run()
    assert res.reason == R.COMPLETED
    assert w.click_log == ["A"]


def test_not_found_stop_ends_run():
    w = World(heart=False)
    r = make_runner(w, [heart_step(not_found_action="stop"), arrow_step()], loop_count=5)
    res = r.run()
    assert res.reason == R.STEP_FAILED and res.clicks == 0 and w.click_log == []


def test_retry_succeeds_when_icon_appears_late():
    w = World(heart=False)
    w.on_grab = lambda n: setattr(w, "heart", n >= 3)  # visible from the 3rd screenshot on
    r = make_runner(w, [heart_step(not_found_action="retry", retries=4)])
    res = r.run()
    assert res.reason == R.COMPLETED and w.click_log == ["H"]
    assert w.screen.grab_count == 3


def test_retry_exhausted_then_stop_or_skip():
    w = World(heart=False)
    r = make_runner(w, [heart_step(not_found_action="retry", retries=2, after_retries="stop"), arrow_step()])
    res = r.run()
    assert res.reason == R.STEP_FAILED
    assert w.screen.grab_count == 3  # 1 try + 2 retries
    assert w.click_log == []

    w2 = World(heart=False)
    r2 = make_runner(w2, [heart_step(not_found_action="retry", retries=2, after_retries="skip"), arrow_step()])
    assert r2.run().reason == R.COMPLETED
    assert w2.click_log == ["A"]


def test_fallback_key_pressed_when_not_found():
    w = World(heart=False)
    r = make_runner(w, [heart_step(not_found_action="key", fallback_key="esc"), arrow_step()])
    res = r.run()
    assert res.reason == R.COMPLETED
    assert [k.key for k in w.input.keys] == ["esc"]
    assert w.click_log == ["A"]


def test_timeout_keeps_scanning_until_found():
    w = World(heart=False)
    w.on_grab = lambda n: setattr(w, "heart", w.clock.now() >= 1.0)
    r = make_runner(w, [heart_step(timeout=3.0)], scan_interval=0.2)
    r.run()
    assert w.click_log == ["H"]
    assert 1.0 <= w.input.clicks[0].t <= 1.3


def test_timeout_expires_when_never_found():
    w = World(heart=False)
    r = make_runner(w, [heart_step(timeout=2.0, not_found_action="stop")], scan_interval=0.25)
    res = r.run()
    assert res.reason == R.STEP_FAILED
    assert res.elapsed == pytest.approx(2.0, abs=0.15)


def test_click_only_if_found_skips_silently_and_does_not_wait():
    w = World(heart=False)
    steps = [heart_step(click_only_if_found=True, wait_after=5.0, not_found_action="stop"), arrow_step()]
    events = []
    r = make_runner(w, steps, events=events)
    res = r.run()
    assert res.reason == R.COMPLETED
    assert w.click_log == ["A"]
    assert w.input.clicks[0].t < 0.5  # the 5 s wait_after was not spent on a skipped step
    assert any("click-only-if-found" in e.message for e in events)


def test_click_only_if_found_clicks_when_present():
    w = World(heart=True)
    r = make_runner(w, [heart_step(click_only_if_found=True), arrow_step()])
    r.run()
    assert w.click_log == ["H", "A"]


def test_missing_template_image_never_crashes():
    w = World()
    r = make_runner(w, [Step(name="ghost", template="nope.png", wait_after=0, timeout=0, not_found_action="skip"),
                        arrow_step()])
    res = r.run()
    assert res.reason == R.COMPLETED and w.click_log == ["A"]


# ------------------------------------------------------------------ limits / stop

def test_loop_count():
    w = World()
    res = make_runner(w, [heart_step(), arrow_step()], loop_count=5).run()
    assert res.loops == 5 and len(w.input.clicks) == 10


def test_click_limit_stops_exactly():
    w = World()
    res = make_runner(w, [heart_step(), arrow_step()], infinite_loop=True, max_total_clicks=7).run()
    assert res.reason == R.CLICK_LIMIT
    assert res.clicks == 7 and len(w.input.clicks) == 7


def test_click_limit_does_not_wait_after_last_click():
    w = World()
    make_runner(w, [heart_step(wait_after=10.0)], infinite_loop=True, max_total_clicks=1).run()
    assert w.clock.now() < 1.0


def test_stop_signal_from_event_handler():
    w = World()
    holder = {}

    def on_event(ev):
        if ev.kind == "click" and len(w.input.clicks) == 3:
            holder["r"].request_stop()

    r = make_runner(w, [heart_step(wait_after=1.0), arrow_step(wait_after=1.0)], infinite_loop=True)
    r.on_event = on_event
    holder["r"] = r
    res = r.run()
    assert res.reason == R.USER
    assert len(w.input.clicks) == 3


def test_stop_signal_from_another_thread_interrupts_long_wait():
    w = World()
    profile = Profile(steps=[heart_step(wait_after=30.0)],
                      settings=Settings(start_delay=0, jitter_percent=0, infinite_loop=True).normalise())
    r = Runner(profile, w.screen, FakeInput(Clock(), position=(500, 500)), clock=Clock(),
               templates=TemplateStore(None, w.templates))
    out = {}
    th = threading.Thread(target=lambda: out.update(res=r.run()))
    t0 = time.monotonic()
    th.start()
    time.sleep(0.4)
    r.request_stop()
    th.join(3)
    assert not th.is_alive()
    assert out["res"].reason == R.USER
    assert time.monotonic() - t0 < 2.0  # nowhere near the 30 s wait


def test_corner_abort():
    w = World()
    w.input.on_click = lambda a: setattr(w.input, "position", (0.0, 0.0)) if len(w.input.clicks) == 2 else None
    res = make_runner(w, [heart_step(wait_after=0.5)], infinite_loop=True).run()
    assert res.reason == R.CORNER
    assert len(w.input.clicks) == 2


@pytest.mark.parametrize("pos", [(0, 0), (799, 0), (0, 599), (799, 599)])
def test_all_four_corners_abort(pos):
    w = World()
    w.input.position = pos
    res = make_runner(w, [heart_step()], infinite_loop=True).run()
    assert res.reason == R.CORNER and not w.input.clicks


def test_corner_abort_can_be_disabled():
    w = World()
    w.input.position = (0, 0)
    res = make_runner(w, [heart_step()], corner_abort=False).run()
    assert res.reason == R.COMPLETED


def test_end_condition_stops_run():
    w = World()
    w.input.on_click = lambda a: (w.__setattr__("end", True) if len(w.input.clicks) >= 3 else None)
    end = Step(name="end", template="end.png", threshold=0.9, multi_scale=False, timeout=0)
    res = make_runner(w, [heart_step(wait_after=0.2), arrow_step(wait_after=0.2)], end=end,
                      infinite_loop=True).run()
    assert res.reason == R.END_CONDITION
    assert len(w.input.clicks) == 3


def test_end_condition_disabled_is_ignored():
    w = World(end=True)
    end = Step(name="end", template="end.png", enabled=False)
    assert make_runner(w, [heart_step()], end=end).run().reason == R.COMPLETED


def test_idle_loops_stop_runaway_flow():
    w = World(heart=False, arrow=False)
    res = make_runner(w, [heart_step(), arrow_step()], infinite_loop=True, max_idle_loops=4).run()
    assert res.reason == R.IDLE and res.loops == 4


# ------------------------------------------------------------------ dry run / events / errors

def test_dry_run_never_clicks_but_reports_and_counts():
    w = World()
    events = []
    res = make_runner(w, [heart_step(), arrow_step(), heart_step(not_found_action="key")], dry=True,
                      events=events, loop_count=2).run()
    assert res.dry_run and res.clicks == 6
    assert w.input.actions == []
    clicks = [e for e in events if e.kind == "click"]
    assert len(clicks) == 6 and all(e.data["dry"] for e in clicks)
    assert all("rect" in e.data for e in clicks)


def test_dry_run_does_not_press_fallback_key():
    w = World(heart=False)
    make_runner(w, [heart_step(not_found_action="key")], dry=True).run()
    assert w.input.actions == []


def test_log_contains_confidence_and_click_position():
    w = World()
    events = []
    make_runner(w, [heart_step()], events=events).run()
    msgs = [e.message for e in events]
    assert any("confidence" in m and "FOUND" in m for m in msgs)
    assert any("click at (" in m for m in msgs)
    assert events[-1].kind == "finished"


def test_invalid_profile_refuses_to_run():
    w = World()
    res = make_runner(w, [Step(name="no template")]).run()
    assert res.reason == R.INVALID and not w.input.actions
    assert make_runner(w, []).run().reason == R.INVALID


def test_screen_failure_does_not_crash():
    class Broken(FakeScreen):
        def grab(self):
            raise RuntimeError("permission denied")

    w = World()
    broken = Broken(make_background())
    r = make_runner(w, [heart_step(timeout=1.0)])
    r.screen = broken
    res = r.run()
    assert res.reason == R.ERROR


def test_listener_exception_does_not_crash_run():
    w = World()
    r = make_runner(w, [heart_step()])
    r.on_event = lambda e: 1 / 0
    assert r.run().reason == R.COMPLETED


def test_probe_reports_confidence_and_never_clicks():
    w = World()
    r = make_runner(w, [heart_step()])
    hit = r.probe(heart_step())
    assert hit.found and hit.confidence > 0.95
    assert w.input.actions == []
    w2 = World(heart=False)
    miss = make_runner(w2, [heart_step()]).probe(heart_step())
    assert not miss.found and 0 <= miss.confidence < 0.85


def test_instagram_style_flow_with_prelike_skipping():
    """Generic version of the headline use case: heart is clicked only when visible."""
    w = World()
    state = {"story": 0}
    liked_stories = {1, 3}

    def render_flags(n):
        w.heart = state["story"] not in liked_stories

    w.on_grab = render_flags

    def on_click(a):
        w._clicked(a)
        if w.click_log[-1] == "A":
            state["story"] += 1
        elif w.click_log[-1] == "H":
            liked_stories.add(state["story"])

    w.input.on_click = on_click
    steps = [heart_step(click_only_if_found=True, wait_after=2.0), arrow_step(wait_after=1.5)]
    res = make_runner(w, steps, loop_count=5).run()
    assert res.reason == R.COMPLETED
    # stories 0,2,4 get liked (H) - 1 and 3 were already liked
    assert w.click_log == ["H", "A", "A", "H", "A", "A", "H", "A"]
