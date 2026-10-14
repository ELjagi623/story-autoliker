"""End-to-end: search boxes and display presets against the mock window.

Every scenario runs on the "real" backend (real screen + real mouse; skipped without a display) and on the
headless "qt" backend. The two-monitor scenario uses two mock windows of different sizes as two displays.
"""
import pytest

from clickflow import runner as R
from clickflow import storage
from clickflow.matcher import Matcher
from clickflow.mock_window import ARROW_RECT, HEART_RECT, MockStoryWindow
from clickflow.models import Preset, Settings, Step
from clickflow.runner import Runner

from harness import QtMultiBackend, pump, run_in_thread
from test_e2e_mock_window import (INNER, _gui_with_profile, assert_clicks_on_centres, backend, build_profile,  # noqa: F401
                                  make_runner, make_window)

pytestmark = pytest.mark.e2e

PAD = 70  # padding (screen units) around the located icon when drawing its search box


def locate(screen, profile, step):
    """Where does ``step``'s template appear on the screen right now? -> (monitor, box local to the monitor)."""
    mon = screen.monitors()[0]
    screen.set_monitor(mon.index)
    frame = screen.grab()
    tpl = storage.read_image(profile.directory / step.template)
    r = Matcher().find(frame.image, tpl, 0.9)
    assert r.found, f"could not locate '{step.name}' on screen (confidence {r.confidence:.2f})"
    g = frame.rect_to_screen(r.x, r.y, r.w, r.h)
    return mon, (int(g.left - mon.left - PAD), int(g.top - mon.top - PAD), int(g.width + 2 * PAD), int(g.height + 2 * PAD))


def make_preset(screen, profile, name="Auto"):
    mon = None
    regions = {}
    for st in profile.steps:
        mon, box = locate(screen, profile, st)
        regions[st.id] = box
    return Preset(name=name, resolution=mon.resolution, monitor=mon.index, regions=regions)


def inside(rect, box, origin):
    l, t, w, h = rect
    bl, bt, bw, bh = box[0] + origin[0], box[1] + origin[1], box[2], box[3]
    return l >= bl - 1 and t >= bt - 1 and l + w <= bl + bw + 1 and t + h <= bt + bh + 1


def test_search_boxes_in_a_preset_are_applied_automatically(qapp, tmp_path, backend, make_window):
    win = make_window(num_stories=10)
    prof = build_profile(tmp_path, win, loops=3)
    screen, inputs = backend.providers(win)
    preset = make_preset(screen, prof)
    prof.presets = [preset]
    events = []
    res = run_in_thread(qapp, Runner(prof, screen, inputs, on_event=events.append))
    assert res.reason == R.COMPLETED, res
    assert win.sequence == ["heart", "arrow"] * 3
    assert_clicks_on_centres(win)
    sel = [e for e in events if e.kind == "preset"]
    assert len(sel) == 1 and "Auto" in sel[0].message
    mon = screen.monitors()[0]
    for e in (e for e in events if e.kind == "match" and e.data.get("found")):
        step = next(s for s in prof.steps if s.name == e.data["step"])
        assert inside(e.data["rect"], preset.regions[step.id], (mon.left, mon.top)), (e.data, preset.regions)


def test_matching_resolution_beats_the_wrong_preset_the_user_had_selected(qapp, tmp_path, backend, make_window):
    win = make_window(num_stories=10)
    prof = build_profile(tmp_path, win, loops=2)
    screen, inputs = backend.providers(win)
    good = make_preset(screen, prof, "Right display")
    bogus = {st.id: (0, 0, 40, 40) for st in prof.steps}  # a box where nothing is: would never find the icons
    wrong = Preset(name="Other display", resolution=(3840, 2160), regions=bogus)
    prof.presets = [wrong, good]
    prof.settings.active_preset = wrong.id
    events = []
    res = run_in_thread(qapp, Runner(prof, screen, inputs, on_event=events.append, preset=wrong))
    assert res.reason == R.COMPLETED, res
    assert win.sequence == ["heart", "arrow"] * 2
    assert any(e.kind == "preset" and "Right display" in e.message for e in events)
    assert not any("Other display" in e.message for e in events if e.kind == "preset")


def test_no_matching_preset_falls_back_to_the_default_configuration(qapp, tmp_path, backend, make_window):
    win = make_window(num_stories=10)
    prof = build_profile(tmp_path, win, loops=2)
    screen, inputs = backend.providers(win)
    prof.presets = [Preset(name="4K only", resolution=(3840, 2160),
                           regions={st.id: (0, 0, 40, 40) for st in prof.steps})]
    events = []
    res = run_in_thread(qapp, Runner(prof, screen, inputs, on_event=events.append))
    assert res.reason == R.COMPLETED and win.sequence == ["heart", "arrow"] * 2
    assert any(e.level == "warn" and "no preset matches" in e.message for e in events)


def test_a_wrong_search_box_is_why_nothing_gets_clicked(qapp, tmp_path, backend, make_window):
    """Documents the failure mode the feature addresses: the icon is on screen but outside the box."""
    win = make_window(num_stories=10)
    prof = build_profile(tmp_path, win, loops=1)
    screen, inputs = backend.providers(win)
    p = make_preset(screen, prof)
    p.regions[prof.steps[0].id] = (0, 0, 30, 30)
    prof.steps[0].not_found_action = "stop"
    prof.steps[0].timeout = 0.5
    prof.presets = [p]
    events = []
    res = run_in_thread(qapp, Runner(prof, screen, inputs, on_event=events.append))
    assert res.reason == R.STEP_FAILED and win.clicks == []
    assert any("best confidence" in e.message for e in events)


def test_auto_switching_between_two_displays_of_different_resolution(qapp, tmp_path):
    """Display 1 is 560x430, display 2 is 700x520 (a different resolution). The preset for 700x520 must
    send the run to display 2: the clicks land in that window only, the other one is never touched."""
    from PySide6.QtCore import Qt  # noqa: F401

    a = MockStoryWindow(num_stories=10, position=(40, 60))
    b = MockStoryWindow(num_stories=10, position=(900, 60))
    b.setFixedSize(700, 520)
    for w in (a, b):
        w.show()
    pump(qapp, 0.4)
    try:
        be = QtMultiBackend(qapp)
        mons = {1: (a, 0, 0), 2: (b, 1000, 0)}
        screen, inputs = be.providers(mons)
        prof = build_profile(tmp_path, b, loops=3)  # templates grabbed from display 2
        preset_b = Preset(name="Second display", resolution=(700, 520))
        screen.set_monitor(2)
        mon2, box_h = locate_on(screen, prof, prof.steps[0], 2)
        _, box_a = locate_on(screen, prof, prof.steps[1], 2)
        preset_b.regions = {prof.steps[0].id: box_h, prof.steps[1].id: box_a}
        preset_a = Preset(name="First display", resolution=(560, 430),
                          regions={st.id: (0, 0, 20, 20) for st in prof.steps})  # bogus: must not be used
        prof.presets = [preset_a, preset_b]
        screen.set_monitor(1)  # the run starts on display 1
        events = []
        res = run_in_thread(qapp, Runner(prof, screen, inputs, on_event=events.append))
        assert res.reason == R.COMPLETED, (res, [e.message for e in events[-6:]])
        assert b.sequence == ["heart", "arrow"] * 3 and a.clicks == []
        assert screen.current == 2
        msg = next(e for e in events if e.kind == "preset")
        assert "Second display" in msg.message and msg.data["monitor"] == 2
        assert inputs.pos[0] >= 1000  # the last click used display 2's global coordinates (origin x = 1000)
    finally:
        a.close()
        b.close()


def locate_on(screen, profile, step, monitor_index):
    screen.set_monitor(monitor_index)
    mon = next(m for m in screen.monitors() if m.index == monitor_index)
    frame = screen.grab()
    tpl = storage.read_image(profile.directory / step.template)
    r = Matcher().find(frame.image, tpl, 0.9)
    assert r.found, r.confidence
    g = frame.rect_to_screen(r.x, r.y, r.w, r.h)
    return mon, (int(g.left - mon.left - PAD), int(g.top - mon.top - PAD), int(g.width + 2 * PAD), int(g.height + 2 * PAD))


def test_gui_start_auto_switches_the_selected_preset(qapp, tmp_path, monkeypatch, backend, make_window):
    """The wrong preset is selected in the UI; pressing Start detects the display and switches to the right one."""
    import time

    win = make_window(num_stories=10)
    prof = build_profile(tmp_path, win, loops=2)
    screen, _ = backend.providers(win)
    good = make_preset(screen, prof, "Right display")
    wrong = Preset(name="Other display", resolution=(3840, 2160),
                   regions={st.id: (0, 0, 40, 40) for st in prof.steps})
    prof.presets = [wrong, good]
    prof.settings.active_preset = wrong.id
    prof.settings.minimize_on_run = False
    storage.save_profile(prof)
    gui = _gui_with_profile(tmp_path, monkeypatch, backend, win, prof)
    try:
        assert gui.active_preset is wrong
        gui.start_run(dry=False)
        end = time.monotonic() + 60
        while gui._run_thread is not None and time.monotonic() < end:
            qapp.processEvents()
            time.sleep(0.005)
        assert gui._run_thread is None
        assert win.sequence == ["heart", "arrow"] * 2
        assert gui.active_preset is good and gui.preset_combo.currentData() == good.id
        assert "Display preset:" in gui.log_view.toPlainText() and "Right display" in gui.log_view.toPlainText()
    finally:
        gui.dirty = False
        gui.close()
