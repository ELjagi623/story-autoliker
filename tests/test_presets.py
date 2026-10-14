import numpy as np
import pytest

from clickflow import presets as P
from clickflow import runner as R
from clickflow import storage
from clickflow.clock import FakeClock
from clickflow.fakes import FakeInput, FakeMultiScreen
from clickflow.models import (Preset, Profile, Settings, Step, effective_region, effective_template, set_region,
                              set_template)
from clickflow.runner import Runner
from clickflow.screen import Frame, MonitorInfo
from clickflow.storage import TemplateStore

from helpers import make_arrow, make_background, make_heart, paste


def mon_image(w, h, seed, items=()):
    img = make_background(w, h, seed=seed)
    for icon, x, y in items:
        img = paste(img, icon, x, y)
    return img


HEART, ARROW = make_heart(48), make_arrow(40)
TEMPLATES = {"heart.png": HEART, "arrow.png": ARROW, "heart_hd.png": HEART, "arrow_override.png": ARROW}


def step(**kw):
    d = dict(name="heart", template="heart.png", wait_after=0.0, timeout=0.0, multi_scale=False, threshold=0.9)
    d.update(kw)
    return Step(**d)


def make_runner(screen, profile, **kw):
    clock = FakeClock()
    inputs = FakeInput(clock, position=(5000, 5000))  # outside every monitor: never a corner
    events = []
    r = Runner(profile, screen, inputs, clock=clock, templates=TemplateStore(None, TEMPLATES),
               on_event=events.append, **kw)
    return r, inputs, events


def profile_with(steps, presets=(), **settings):
    base = dict(start_delay=0.0, jitter_percent=0.0, scan_interval=0.1, corner_abort=True, speed_manual=True)
    base.update(settings)
    return Profile(name="p", steps=steps, presets=list(presets), settings=Settings(**base).normalise())


# ---------------------------------------------------------------- model helpers

def test_effective_helpers_and_fallbacks():
    s = Step(name="a", template="base.png", region=(1, 2, 3, 4))
    p = Preset(name="P")
    assert effective_region(s, None) == (1, 2, 3, 4)
    assert effective_region(s, p) is None  # a preset never inherits another display's coordinates
    assert effective_template(s, p) == "base.png"  # but it does inherit the template image
    set_region(s, p, (9, 8, 7, 6))
    set_template(s, p, "p.png")
    assert effective_region(s, p) == (9, 8, 7, 6) and effective_template(s, p) == "p.png"
    assert s.region == (1, 2, 3, 4) and s.template == "base.png"  # the base is untouched
    set_region(s, p, None)
    assert effective_region(s, p) is None


def test_preset_round_trip_and_old_profiles_still_load(tmp_path):
    prof = storage.new_profile("pp", root=tmp_path / "r")
    st = Step(name="Heart")
    storage.save_template(prof.directory, st, HEART)
    pr = Preset(name="Laptop", resolution=(1920, 1080), monitor=2, regions={st.id: (10, 20, 300, 200)})
    storage.save_template(prof.directory, st, HEART, preset=pr)
    prof.steps, prof.presets = [st], [pr]
    prof.settings.active_preset, prof.settings.auto_preset = pr.id, False
    storage.save_profile(prof)
    q = storage.load_profile(prof.directory)
    assert q.to_dict() == prof.to_dict()
    assert q.presets[0].regions[st.id] == (10, 20, 300, 200) and isinstance(q.presets[0].resolution, tuple)
    assert q.settings.active_preset == pr.id and q.settings.auto_preset is False
    assert pr.templates[st.id] != st.template  # separate file per preset
    # a profile written before presets existed
    old = Profile.from_dict({"name": "old", "steps": [{"name": "x"}], "settings": {"loop_count": 2}})
    assert old.presets == [] and old.settings.auto_preset is True


def test_export_import_keeps_preset_templates(tmp_path):
    prof = storage.new_profile("exp", root=tmp_path / "r")
    st = Step(name="Heart")
    pr = Preset(name="Alt", resolution=(100, 100))
    storage.save_template(prof.directory, st, HEART, preset=pr)  # only the preset has an image
    prof.steps, prof.presets = [st], [pr]
    z = storage.export_profile(prof, tmp_path / "e.zip")
    q = storage.import_profile(z, root=tmp_path / "imp")
    assert np.array_equal(storage.read_image(q.directory / q.presets[0].templates[st.id]), HEART)


def test_duplicate_and_remove_step_refs(tmp_path):
    prof = storage.new_profile("dup", root=tmp_path / "r")
    a = Step(name="A")
    pr = Preset(name="P", regions={a.id: (1, 1, 5, 5)})
    storage.save_template(prof.directory, a, HEART, preset=pr)
    prof.steps, prof.presets = [a], [pr]
    b = Step(name="A copy")
    storage.copy_preset_entries(prof.directory, prof, a, b)
    assert pr.regions[b.id] == (1, 1, 5, 5) and pr.templates[b.id] != pr.templates[a.id]
    assert (prof.directory / pr.templates[b.id]).exists()
    prof.remove_step_refs(a.id)
    assert a.id not in pr.regions and a.id not in pr.templates and b.id in pr.regions


def test_validate_counts_preset_templates():
    st = Step(name="only in preset")
    pr = Preset(name="P", resolution=(1, 1), templates={st.id: "x.png"})
    assert Profile(steps=[st], presets=[pr]).validate() == []  # some preset provides it
    assert Profile(steps=[st], presets=[Preset(name="Q")]).validate()  # nobody does
    assert Profile(steps=[st], presets=[Preset(name="Q")]).validate(pr) == []


# ---------------------------------------------------------------- candidates / regions

def test_candidates_priority_and_resolution_match():
    m1 = MonitorInfo(1, 0, 0, 2560, 1440, True)
    m2 = MonitorInfo(2, 2560, 0, 1920, 1080, False)
    m3 = MonitorInfo(3, 4480, 0, 1920, 1080, False)
    big, small = Preset(name="big", resolution=(2560, 1440)), Preset(name="small", resolution=(1920, 1080), monitor=3)
    pairs = P.candidates([big, small], [m1, m2, m3])
    assert [(p.name, m.index) for p, m in pairs] == [("small", 3), ("big", 1), ("small", 2)]
    assert P.candidates([Preset(name="x", resolution=(800, 600))], [m1, m2, m3]) == []


def test_resolve_region_adds_monitor_origin_only_for_presets():
    f = Frame(np.zeros((100, 200, 3), np.uint8), left=1000, top=50)
    s = Step(name="a", region=(5, 6, 7, 8))
    p = Preset(name="P", regions={s.id: (10, 20, 30, 40)})
    assert P.resolve_region(s, None, f) == (5, 6, 7, 8)  # default box = global coordinates
    assert P.resolve_region(s, p, f) == (1010, 70, 30, 40)  # preset box = relative to the monitor
    assert P.resolve_region(Step(name="b"), p, f) is None


# ---------------------------------------------------------------- the Runner with presets

def two_monitors(heart2_at=(300, 200), heart1_at=None):
    items1 = [(HEART, *heart1_at)] if heart1_at else []
    m1 = mon_image(800, 600, 1, items1)
    m2 = mon_image(1024, 768, 2, [(HEART, *heart2_at)])
    return FakeMultiScreen({1: (m1, 0, 0), 2: (m2, 800, 0)})


def test_auto_selects_monitor_and_preset_by_resolution():
    screen = two_monitors()
    st = step()
    preset = Preset(name="Desk", resolution=(1024, 768), regions={st.id: (250, 150, 200, 150)})
    prof = profile_with([st], [preset])
    r, inp, events = make_runner(screen, prof)  # screen starts on monitor 1
    res = r.run()
    assert res.reason == R.COMPLETED and res.clicks == 1
    assert screen.current == 2
    c = inp.clicks[0]  # monitor 2 sits at x=800: heart centre (300+24, 200+24)
    assert (c.x, c.y) == pytest.approx((800 + 324, 224), abs=1.5)
    msg = next(e for e in events if e.kind == "preset")
    assert "Desk" in msg.message and "Monitor 2" in msg.message and msg.data["monitor"] == 2


def test_search_box_ignores_identical_icon_outside_it():
    """The whole point of the search box: a look-alike elsewhere on a big screen is never clicked."""
    m = mon_image(1024, 768, 3, [(HEART, 100, 100), (HEART, 600, 400)])
    screen = FakeMultiScreen({1: (m, 0, 0)})
    st = step()
    boxed = Preset(name="Boxed", resolution=(1024, 768), regions={st.id: (560, 360, 150, 120)})
    r, inp, _ = make_runner(screen, profile_with([st], [boxed]))
    r.run()
    c = inp.clicks[0]
    assert (c.x, c.y) == pytest.approx((624, 424), abs=1.5)  # the second heart, not the first


def test_preset_regions_follow_the_monitor_not_the_desktop_layout():
    """Same preset, monitor moved to a different desktop position: the box still applies."""
    st = step()
    preset = Preset(name="D", resolution=(1024, 768), regions={st.id: (250, 150, 200, 150)})
    for left in (800, -1024, 3000):
        m2 = mon_image(1024, 768, 2, [(HEART, 300, 200)])
        screen = FakeMultiScreen({1: (mon_image(800, 600, 1), 0, 0), 2: (m2, left, 0)})
        r, inp, _ = make_runner(screen, profile_with([st], [preset]))
        assert r.run().clicks == 1
        assert inp.clicks[0].x == pytest.approx(left + 324, abs=1.5)


def test_same_resolution_on_two_monitors_probes_for_the_icon():
    st = step()
    preset = Preset(name="Same", resolution=(800, 600))
    for icon_on in (1, 2):
        m1 = mon_image(800, 600, 1, [(HEART, 200, 200)] if icon_on == 1 else [])
        m2 = mon_image(800, 600, 2, [(HEART, 200, 200)] if icon_on == 2 else [])
        screen = FakeMultiScreen({1: (m1, 0, 0), 2: (m2, 800, 0)})
        r, inp, events = make_runner(screen, profile_with([st], [preset]))
        res = r.run()
        assert res.clicks == 1 and screen.current == icon_on, (icon_on, events[-3:])
        expected_x = (0 if icon_on == 1 else 800) + 224
        assert inp.clicks[0].x == pytest.approx(expected_x, abs=1.5)


def test_no_matching_resolution_falls_back_to_default_settings_with_warning():
    m = mon_image(800, 600, 1, [(HEART, 100, 100)])
    screen = FakeMultiScreen({1: (m, 0, 0)})
    st = step(region=(50, 50, 200, 200))  # default (global) box
    other = Preset(name="4K", resolution=(3840, 2160), regions={st.id: (0, 0, 10, 10)})
    r, inp, events = make_runner(screen, profile_with([st], [other]))
    res = r.run()
    assert res.reason == R.COMPLETED and res.clicks == 1  # default box used, the 4K preset ignored
    warn = [e for e in events if e.level == "warn" and "Display presets" in e.message]
    assert warn and "no preset matches" in warn[0].message and "Monitor 1: 800x600" in warn[0].message
    assert not [e for e in events if e.kind == "preset"]


def test_manual_preset_with_auto_off_and_unmatched_resolution_runs_anyway():
    m = mon_image(800, 600, 1, [(HEART, 100, 100)])
    screen = FakeMultiScreen({1: (m, 0, 0)})
    st = step()
    pre = Preset(name="Mine", resolution=(1234, 567), monitor=1, regions={st.id: (60, 60, 150, 150)})
    prof = profile_with([st], [pre], auto_preset=False)
    r, inp, events = make_runner(screen, prof, preset=pre)
    assert r.run().clicks == 1
    ev = next(e for e in events if e.kind == "preset")
    assert ev.level == "warn" and "anyway" in ev.message


def test_auto_off_without_explicit_preset_uses_defaults():
    m = mon_image(800, 600, 1, [(HEART, 100, 100)])
    st = step()
    pre = Preset(name="P", resolution=(800, 600), regions={st.id: (0, 0, 10, 10)})  # would miss the heart
    r, inp, events = make_runner(FakeMultiScreen({1: (m, 0, 0)}), profile_with([st], [pre], auto_preset=False))
    assert r.run().clicks == 1
    assert not [e for e in events if e.kind == "preset"]


def test_preset_template_overrides_the_base_template():
    m = mon_image(800, 600, 1, [(ARROW, 300, 300)])  # only the arrow is on this display
    st = step(template="heart.png")
    pre = Preset(name="Hd", resolution=(800, 600), templates={st.id: "arrow_override.png"})
    r, inp, _ = make_runner(FakeMultiScreen({1: (m, 0, 0)}), profile_with([st], [pre]))
    assert r.run().clicks == 1
    assert inp.clicks[0].x == pytest.approx(320, abs=1.5)


def test_chosen_preset_without_any_template_is_reported_invalid():
    st = Step(name="needs img", wait_after=0, timeout=0)
    other = Preset(name="Has", resolution=(1, 1), templates={st.id: "heart.png"})
    mine = Preset(name="Lacks", resolution=(800, 600))
    m = mon_image(800, 600, 1)
    r, inp, events = make_runner(FakeMultiScreen({1: (m, 0, 0)}), profile_with([st], [other, mine]))
    res = r.run()
    assert res.reason == R.INVALID and not inp.actions


def test_end_condition_uses_preset_template_and_box():
    end_tpl = make_arrow(40)
    m = mon_image(800, 600, 1, [(HEART, 100, 100)])
    st = step()
    end = Step(name="end", enabled=True, template="", threshold=0.9, multi_scale=False)
    pre = Preset(name="P", resolution=(800, 600), templates={end.id: "arrow.png"},
                 regions={end.id: (400, 400, 200, 200)})
    state = {"shown": False}

    def render():
        img = m
        if state["shown"]:
            img = paste(m, end_tpl, 450, 450)
        return img

    screen = FakeMultiScreen({1: (render, 0, 0)})
    prof = profile_with([st], [pre], infinite_loop=True, max_idle_loops=0)
    prof.end_condition = end
    r, inp, events = make_runner(screen, prof)
    inp.on_click = lambda a: state.__setitem__("shown", True)
    res = r.run()
    assert res.reason == R.END_CONDITION and len(inp.clicks) == 1


def test_not_found_message_mentions_best_candidate_location():
    m = mon_image(800, 600, 1)
    st = step(not_found_action="skip", threshold=0.99)
    r, _, events = make_runner(FakeMultiScreen({1: (m, 0, 0)}), profile_with([st]))
    r.run()
    assert any("best candidate at (" in e.message for e in events)
