"""End-to-end: the real app flow against a local mock window.

The mock window (clickflow.mock_window) shows a fake heart button and a fake next arrow and
counts clicks on each. Every scenario runs twice (see harness.py):

* backend "real" - real mss screenshots + real pyautogui mouse (skipped, loudly, without a display)
* backend "qt"   - real Runner/Matcher/window, Qt-widget screenshots and Qt mouse events (headless-safe)
"""
import threading
import time

import pytest

from clickflow import runner as R
from clickflow import storage
from clickflow.mock_window import ARROW_RECT, END_RECT, HEART_RECT, MockStoryWindow
from clickflow.models import Settings, Step
from clickflow.runner import Runner

from harness import QtBackend, RealBackend, pump, run_in_thread

pytestmark = pytest.mark.e2e

INNER = (10, 10, -10, -10)  # crop inside the round button so a template never contains story background


@pytest.fixture(params=["qt", "real"])
def backend(request, qapp, display):
    if request.param == "real":
        if not display[0]:
            pytest.skip(f"REAL-DISPLAY e2e NOT verified - no usable display: {display[1]}")
        b = RealBackend(qapp)
        yield b
        b.restore()
    else:
        yield QtBackend(qapp)


@pytest.fixture()
def make_window(qapp):
    windows = []

    def factory(**kw):
        win = MockStoryWindow(**kw)
        win.show()
        win.raise_()
        pump(qapp, 0.4)
        windows.append(win)
        return win

    yield factory
    for w in windows:
        w.close()


def build_profile(tmp_path, win, *, with_end=False, template_scale=1.0, loops=4, infinite=False, optional_heart=False,
                  wait=0.25, max_clicks=0):
    import cv2

    prof = storage.new_profile("e2e", root=tmp_path / "profiles")
    unliked = next(i for i in range(win.num_stories) if i not in win.liked)
    heart_img = win.grab_region(HEART_RECT.adjusted(*INNER), story=unliked)
    arrow_img = win.grab_region(ARROW_RECT.adjusted(*INNER), story=unliked)
    if template_scale != 1.0:
        heart_img = cv2.resize(heart_img, None, fx=template_scale, fy=template_scale, interpolation=cv2.INTER_AREA)
        arrow_img = cv2.resize(arrow_img, None, fx=template_scale, fy=template_scale, interpolation=cv2.INTER_AREA)
    heart = Step(name="heart", threshold=0.85, wait_before=0.05, wait_after=wait,
                 timeout=1.0 if optional_heart else 3.0, click_only_if_found=optional_heart)
    arrow = Step(name="arrow", threshold=0.85, wait_before=0.05, wait_after=wait, timeout=3.0,
                 not_found_action="stop")
    storage.save_template(prof.directory, heart, heart_img)
    storage.save_template(prof.directory, arrow, arrow_img)
    prof.steps = [heart, arrow]
    prof.settings = Settings(loop_count=loops, infinite_loop=infinite, jitter_percent=0, start_delay=0.2, speed_manual=True,
                             scan_interval=0.1, max_total_clicks=max_clicks, max_idle_loops=0).normalise()
    if with_end:
        end = Step(name="end", threshold=0.85, enabled=True)
        storage.save_template(prof.directory, end,
                              win.grab_region(END_RECT.adjusted(8, 8, -8, -8), story=win.num_stories))
        prof.end_condition = end
    storage.save_profile(prof)
    return prof


def make_runner(backend, win, prof, **kw):
    screen, inputs = backend.providers(win)
    return Runner(prof, screen, inputs, **kw)


def assert_clicks_on_centres(win):
    """Every click landed on the middle of its button: proves the screenshot->click coordinate mapping."""
    for c in win.clicks:
        rect = HEART_RECT if c.kind == "heart" else ARROW_RECT
        cx, cy = rect.center().x(), rect.center().y()
        assert abs(c.local_x - cx) <= 4 and abs(c.local_y - cy) <= 4, (c, cx, cy)


def test_heart_then_arrow_in_order_and_count(qapp, tmp_path, backend, make_window):
    win = make_window(num_stories=10)
    prof = build_profile(tmp_path, win, loops=4)
    res = run_in_thread(qapp, make_runner(backend, win, prof))
    assert res.reason == R.COMPLETED, res
    assert win.sequence == ["heart", "arrow"] * 4
    assert (win.heart_clicks, win.arrow_clicks) == (4, 4)
    assert win.story == 4
    assert not [c for c in win.clicks if c.kind == "other"]
    assert_clicks_on_centres(win)


def test_click_only_if_found_and_end_condition(qapp, tmp_path, backend, make_window):
    """Stories 1 and 4 are already liked: the heart is skipped there. The run ends on the end marker."""
    win = make_window(num_stories=6, preliked={1, 4})
    prof = build_profile(tmp_path, win, with_end=True, infinite=True, optional_heart=True)
    events = []
    res = run_in_thread(qapp, make_runner(backend, win, prof, on_event=events.append))
    log = "\n".join(f"{e.t:8.2f} {e.message}" for e in events)  # shown by pytest if an assertion fails
    assert res.reason == R.END_CONDITION, f"{res}\n{log}"
    assert win.sequence == ["heart", "arrow", "arrow", "heart", "arrow", "heart", "arrow", "arrow",
                            "heart", "arrow"], f"{win.sequence}\n{log}"
    assert (win.heart_clicks, win.arrow_clicks) == (4, 6)
    assert win.finished
    assert_clicks_on_centres(win)


def test_template_at_different_size_still_matches(qapp, tmp_path, backend, make_window):
    win = make_window(num_stories=10)
    prof = build_profile(tmp_path, win, template_scale=0.8, loops=3)
    res = run_in_thread(qapp, make_runner(backend, win, prof))
    assert res.reason == R.COMPLETED, res
    assert win.sequence == ["heart", "arrow"] * 3
    assert_clicks_on_centres(win)


def test_dry_run_does_not_click(qapp, tmp_path, backend, make_window):
    win = make_window(num_stories=10)
    prof = build_profile(tmp_path, win, loops=2)
    events = []
    res = run_in_thread(qapp, make_runner(backend, win, prof, dry_run=True, on_event=events.append))
    pump(qapp, 0.3)
    assert res.reason == R.COMPLETED and res.dry_run and res.clicks == 4
    assert win.clicks == [] and win.story == 0
    boxes = [e for e in events if e.kind == "click"]
    assert len(boxes) == 4 and all("rect" in e.data for e in boxes)


def test_click_limit(qapp, tmp_path, backend, make_window):
    win = make_window(num_stories=20)
    prof = build_profile(tmp_path, win, infinite=True, max_clicks=5)
    res = run_in_thread(qapp, make_runner(backend, win, prof))
    assert res.reason == R.CLICK_LIMIT
    assert win.sequence == ["heart", "arrow", "heart", "arrow", "heart"]


def test_corner_abort(qapp, tmp_path, backend, make_window):
    win = make_window(num_stories=20)
    prof = build_profile(tmp_path, win, infinite=True, wait=1.5)
    moved = {"done": False}

    def tick():
        if win.heart_clicks >= 1 and not moved["done"]:
            moved["done"] = True
            backend.move_mouse_to_corner()

    t0 = time.monotonic()
    res = run_in_thread(qapp, make_runner(backend, win, prof), on_tick=tick)
    assert res.reason == R.CORNER
    assert len(win.clicks) == 1
    assert time.monotonic() - t0 < 6


def test_stop_request_during_run(qapp, tmp_path, backend, make_window):
    win = make_window(num_stories=30)
    prof = build_profile(tmp_path, win, infinite=True, wait=0.5)
    runner = make_runner(backend, win, prof)

    def tick():
        if win.heart_clicks >= 2:
            runner.request_stop()

    res = run_in_thread(qapp, runner, on_tick=tick)
    assert res.reason == R.USER
    n = len(win.clicks)
    pump(qapp, 1.0)
    assert len(win.clicks) == n  # nothing is clicked after stopping


def test_full_gui_flow_create_save_load_run(qapp, tmp_path, monkeypatch, backend, make_window):
    """Definition of Done, driven through the real MainWindow: create a profile, edit it, save,
    reload from disk, press Start and watch the mock window receive the clicks."""
    from clickflow.gui.main_window import MainWindow

    monkeypatch.setattr(storage, "profiles_root", lambda: tmp_path / "profiles")
    win = make_window(num_stories=10, preliked={1}, position=(900, 300))
    backend.patch_gui(monkeypatch, win)
    gui = MainWindow(storage.new_profile("gui flow", root=tmp_path / "profiles"), start_hotkey=False)
    try:
        gui.show()
        gui.add_step()
        gui.add_step()
        h, a = gui.profile.steps
        gui.step_list.setCurrentRow(0)
        gui.step_editor.name.setText("heart")
        gui.step_editor.name.editingFinished.emit()
        gui.step_editor.only_if_found.setChecked(True)
        gui.step_editor.timeout.setValue(0.6)
        gui.step_editor.wait_after.setValue(0.25)
        gui.step_list.setCurrentRow(1)
        gui.step_editor.name.setText("arrow")
        gui.step_editor.name.editingFinished.emit()
        gui.step_editor.wait_after.setValue(0.25)
        storage.save_template(gui.profile.directory, h, win.grab_region(HEART_RECT.adjusted(*INNER), story=0))
        storage.save_template(gui.profile.directory, a, win.grab_region(ARROW_RECT.adjusted(*INNER), story=0))
        gui.s_loops.setValue(3)
        gui.s_jitter.setValue(0)
        gui.s_start_delay.setValue(0.3)
        gui.s_minimize.setChecked(False)
        gui._apply_settings()
        assert gui.save()

        reloaded = storage.load_profile(gui.profile.directory)  # fresh from disk
        assert [s.name for s in reloaded.steps] == ["heart", "arrow"] and reloaded.steps[0].click_only_if_found
        gui.load_into_ui(reloaded)
        assert gui.step_list.count() == 2

        gui.start_run(dry=False)
        assert gui._run_thread is not None
        end = time.monotonic() + 60
        while gui._run_thread is not None and time.monotonic() < end:
            qapp.processEvents()
            time.sleep(0.005)
        assert gui._run_thread is None, "run did not finish"
        # stories 0 and 2 are unliked -> hearts; story 1 was pre-liked -> skipped
        text = gui.log_view.toPlainText()
        assert win.sequence == ["heart", "arrow", "arrow", "heart", "arrow"], f"{win.sequence}\n{text}"
        assert "confidence" in text and "click at (" in text
    finally:
        gui.dirty = False
        gui.close()


def _gui_with_profile(tmp_path, monkeypatch, backend, win, prof):
    from clickflow.gui.main_window import MainWindow

    monkeypatch.setattr(storage, "profiles_root", lambda: tmp_path / "profiles")
    backend.patch_gui(monkeypatch, win)
    gui = MainWindow(prof, start_hotkey=False)
    gui.show()
    return gui


def test_gui_test_step_reports_confidence_and_never_clicks(qapp, tmp_path, monkeypatch, backend, make_window):
    win = make_window(num_stories=10)
    prof = build_profile(tmp_path, win)
    gui = _gui_with_profile(tmp_path, monkeypatch, backend, win, prof)
    monkeypatch.setattr(type(gui), "_ask_test_fix", lambda self, step, diag: False)  # no modal dialog in tests
    try:
        gui.step_list.setCurrentRow(0)
        gui.test_step()
        end = time.monotonic() + 15
        while time.monotonic() < end and "Test 'heart'" not in gui.log_view.toPlainText():
            qapp.processEvents()
            time.sleep(0.01)
        text = gui.log_view.toPlainText()
        assert "Test 'heart': FOUND" in text and "confidence" in text
        assert win.clicks == []  # testing a step must not click
        assert gui.highlighter.isVisible()  # the match box is drawn
        # a step whose icon is not on screen reports a miss with a confidence
        win.set_story(win.num_stories)
        pump(qapp, 0.3)
        gui.test_step()
        end = time.monotonic() + 15
        while time.monotonic() < end and "NOT FOUND" not in gui.log_view.toPlainText():
            qapp.processEvents()
            time.sleep(0.01)
        assert "NOT FOUND" in gui.log_view.toPlainText() and win.clicks == []
    finally:
        gui.dirty = False
        gui.close()


def test_gui_dry_run_draws_boxes_and_does_not_click(qapp, tmp_path, monkeypatch, backend, make_window):
    win = make_window(num_stories=10)
    prof = build_profile(tmp_path, win, loops=2)
    prof.settings.minimize_on_run = False
    gui = _gui_with_profile(tmp_path, monkeypatch, backend, win, prof)
    try:
        flashes = []
        orig = gui.highlighter.flash
        gui.highlighter.flash = lambda *a, **k: (flashes.append(a), orig(*a, **k))
        gui.start_run(dry=True)
        end = time.monotonic() + 60
        while gui._run_thread is not None and time.monotonic() < end:
            qapp.processEvents()
            time.sleep(0.005)
        assert gui._run_thread is None
        assert win.clicks == []
        assert len(flashes) >= 4
        assert "[dry-run] would left-click" in gui.log_view.toPlainText()
    finally:
        gui.dirty = False
        gui.close()


def test_f8_stops_a_running_gui_run(qapp, tmp_path, monkeypatch, backend, make_window):
    """User story: 'once it runs it is hard to stop'. Press F8 (really, via the OS) mid-run and the run ends."""
    from clickflow.gui.main_window import MainWindow
    from clickflow.keystate import StopKeyWatcher

    if backend.name != "real" or not StopKeyWatcher.supported():
        pytest.skip("needs the real backend on Windows (sends a real F8 key press)")
    import pyautogui

    win = make_window(num_stories=40)
    prof = build_profile(tmp_path, win, infinite=True, wait=0.4)
    prof.settings.minimize_on_run = False
    gui = _gui_with_profile(tmp_path, monkeypatch, backend, win, prof)
    gui.hotkey.hotkey = "F8"
    gui._hotkey_enabled = True
    gui._start_hotkey()
    try:
        gui.start_run(dry=False)
        assert gui.stop_badge.isVisible()  # the red STOP button is on screen while running
        end = time.monotonic() + 40
        while win.heart_clicks < 2 and time.monotonic() < end:
            qapp.processEvents()
            time.sleep(0.005)
        assert win.heart_clicks >= 2
        t_press = time.monotonic()
        pyautogui.keyDown("f8"); time.sleep(0.06); pyautogui.keyUp("f8")  # a physical tap lasts ~50-150 ms
        while gui._run_thread is not None and time.monotonic() < t_press + 5:
            qapp.processEvents()
            time.sleep(0.005)
        assert gui._run_thread is None, "F8 did not stop the run"
        assert time.monotonic() - t_press < 2.0
        assert not gui.stop_badge.isVisible()
        n = len(win.clicks)
        pump(qapp, 1.0)
        assert len(win.clicks) == n
    finally:
        gui.dirty = False
        gui.close()


def test_stop_badge_click_stops_run(qapp, tmp_path, monkeypatch, backend, make_window):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    win = make_window(num_stories=40)
    prof = build_profile(tmp_path, win, infinite=True, wait=0.4)
    prof.settings.minimize_on_run = False
    gui = _gui_with_profile(tmp_path, monkeypatch, backend, win, prof)
    try:
        gui.start_run(dry=False)
        end = time.monotonic() + 40
        while win.heart_clicks < 1 and time.monotonic() < end:
            qapp.processEvents()
            time.sleep(0.005)
        QTest.mouseClick(gui.stop_badge, Qt.MouseButton.LeftButton)  # same path as a user click
        end = time.monotonic() + 5
        while gui._run_thread is not None and time.monotonic() < end:
            qapp.processEvents()
            time.sleep(0.005)
        assert gui._run_thread is None
        assert "user" in gui.log_view.toPlainText().split("Run finished:")[-1][:30]
    finally:
        gui.dirty = False
        gui.close()


def test_template_twice_the_size_of_the_icon_on_screen_still_clicks(qapp, tmp_path, backend, make_window):
    """The reported bug: icons on screen ~0.5x the captured template. With default settings nothing was
    clicked (best match stuck at the edge of the old 0.7-1.4 scale range, confidence far below the threshold)."""
    win = make_window(num_stories=10)
    prof = build_profile(tmp_path, win, template_scale=2.0, loops=3)  # template is 2x the icon on screen
    assert (prof.steps[0].scale_min, prof.steps[0].scale_max) == (0.35, 2.5)  # defaults, nothing tuned
    events = []
    res = run_in_thread(qapp, make_runner(backend, win, prof, on_event=events.append))
    assert res.reason == R.COMPLETED, res
    assert win.sequence == ["heart", "arrow"] * 3
    assert_clicks_on_centres(win)
    assert any("scale 0.50" in e.message or "scale 0.5" in e.message for e in events if e.kind == "match")


def test_gui_test_step_explains_and_fixes_a_scale_mismatch(qapp, tmp_path, monkeypatch, backend, make_window):
    """Test this step on a template that is 5x too big for the (old, narrow) scale range: it says the step would
    NOT click, explains why, and 'Apply suggested fix' makes the next test succeed."""
    win = make_window(num_stories=10)
    prof = build_profile(tmp_path, win, template_scale=5.0)
    for st in prof.steps:
        st.scale_min, st.scale_max = 0.7, 1.4  # the old default range
    gui = _gui_with_profile(tmp_path, monkeypatch, backend, win, prof)
    asked = []
    monkeypatch.setattr(type(gui), "_ask_test_fix", lambda self, step, diag: asked.append(diag) or True)
    try:
        gui.step_list.setCurrentRow(0)
        gui.test_step()
        end = time.monotonic() + 30
        while time.monotonic() < end and not asked:
            qapp.processEvents()
            time.sleep(0.01)
        assert asked and asked[0].kind == "scale", [a.kind for a in asked]
        text = gui.log_view.toPlainText()
        assert "NOT FOUND" in text and "would NOT click" in text and "smaller than your captured template" in text
        assert "best candidate" in text.lower()  # the orange box is explained as a candidate, not a match
        step = prof.steps[0]
        assert step.scale_min < 0.7 and "Applied fix" in text and gui.dirty
        assert win.clicks == []
        asked.clear()
        gui.test_step()
        end = time.monotonic() + 30
        while time.monotonic() < end and "A run WOULD click" not in gui.log_view.toPlainText():
            qapp.processEvents()
            time.sleep(0.01)
        assert "A run WOULD click" in gui.log_view.toPlainText() and not asked
        assert win.clicks == []
    finally:
        gui.dirty = False
        gui.close()
