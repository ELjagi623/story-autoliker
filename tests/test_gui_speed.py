"""The Speed bar (slider + 'Advanced: edit waits manually') in the main window, and its real-world timing."""
import json
import statistics
import time

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication

from clickflow import runner as R
from clickflow import storage
from clickflow.gui.main_window import MainWindow
from clickflow.models import FAST_WAIT, Profile, Step, click_interval

from harness import run_in_thread
from test_e2e_mock_window import backend, build_profile, make_runner, make_window  # noqa: F401


@pytest.fixture()
def g(qapp, tmp_path):
    win = MainWindow(storage.new_profile("speed", root=tmp_path / "p"), start_hotkey=False)
    win.show()
    win.add_step()
    win.step_list.setCurrentRow(0)
    yield win
    win.dirty = False
    win.close()


def test_new_profile_starts_in_slider_mode_with_the_waits_locked(g):
    assert g.speed_slider.value() == 50 and not g.chk_manual.isChecked() and g.speed_slider.isEnabled()
    assert "at least 0.61 s between clicks" in g.lbl_speed.text()
    e = g.step_editor
    assert not e.wait_before.isEnabled() and not e.wait_after.isEnabled()
    assert e.waits_note.isVisibleTo(e) and "Speed slider" in e.waits_note.text()
    assert e.wait_before.value() == FAST_WAIT == e.wait_after.value()  # shows what is in force


def test_moving_the_slider_updates_the_setting_and_the_readout(g):
    g.speed_slider.setValue(0)
    assert g.profile.settings.speed == 0 and "at least 1.50 s between clicks" in g.lbl_speed.text()
    g.speed_slider.setValue(100)
    assert g.profile.settings.speed == 100 and "fastest: no added delay" in g.lbl_speed.text()
    assert "0.25 s" in g.lbl_speed.text()
    g.speed_slider.setValue(25)
    assert f"{click_interval(25):.2f} s" in g.lbl_speed.text() and g.dirty


def test_slider_labels_state_the_slow_end(g):
    assert "1.5" in g.lbl_slow.text() and "Slow" in g.lbl_slow.text() and "Fast" in g.lbl_fast.text()
    assert g.speed_slider.minimum() == 0 and g.speed_slider.maximum() == 100


def test_advanced_unlocks_per_step_waits_and_disables_the_slider(g):
    step = g.profile.steps[0]
    step.wait_before, step.wait_after = 0.4, 2.5  # the step's own, stored values
    g._show_step(step)
    assert g.step_editor.wait_after.value() == FAST_WAIT  # locked: shows the slider's value, not the stored 2.5
    g.chk_manual.setChecked(True)
    assert g.profile.settings.speed_manual and not g.speed_slider.isEnabled()
    e = g.step_editor
    assert e.wait_before.isEnabled() and e.wait_after.isEnabled() and not e.waits_note.isVisibleTo(e)
    assert (e.wait_before.value(), e.wait_after.value()) == (0.4, 2.5)  # the stored values are back
    assert "Manual" in g.lbl_speed.text()
    e.wait_after.setValue(3.25)
    assert step.wait_after == 3.25


def test_switching_back_to_the_slider_keeps_the_manual_values_but_stops_using_them(g):
    g.chk_manual.setChecked(True)
    step = g.profile.steps[0]
    g.step_editor.wait_before.setValue(0.7)
    g.step_editor.wait_after.setValue(1.9)
    g.chk_manual.setChecked(False)
    assert (step.wait_before, step.wait_after) == (0.7, 1.9)  # not overwritten
    assert g.step_editor.wait_after.value() == FAST_WAIT and not g.step_editor.wait_after.isEnabled()
    g.step_editor.commit()  # saving while locked must not write the display-only values into the step
    assert (step.wait_before, step.wait_after) == (0.7, 1.9)
    g.chk_manual.setChecked(True)
    assert (g.step_editor.wait_before.value(), g.step_editor.wait_after.value()) == (0.7, 1.9)


def test_other_step_edits_in_slider_mode_do_not_touch_stored_waits(g):
    step = g.profile.steps[0]
    step.wait_before, step.wait_after = 0.4, 2.5
    g._show_step(step)
    g.step_editor.timeout.setValue(9)
    g.step_editor.threshold.setValue(0.9)
    assert (step.wait_before, step.wait_after, step.timeout, step.threshold) == (0.4, 2.5, 9, 0.9)


def test_speed_settings_persist_through_save_and_reload(g):
    g.speed_slider.setValue(12)
    assert g.save()
    data = json.loads((g.profile.directory / "profile.json").read_text(encoding="utf-8"))
    assert data["settings"]["speed"] == 12 and data["settings"]["speed_manual"] is False
    g.chk_manual.setChecked(True)
    g.save()
    re = storage.load_profile(g.profile.directory)
    assert (re.settings.speed, re.settings.speed_manual) == (12, True)
    g.load_into_ui(re)
    assert g.speed_slider.value() == 12 and g.chk_manual.isChecked() and not g.speed_slider.isEnabled()


def test_a_value_typed_into_the_slider_mode_waits_is_never_possible_but_a_typed_speed_free_field_saves(g):
    """Save in slider mode must not fail or alter timing fields (flush path calls commit on the locked editor)."""
    g.step_editor.wait_after.setEnabled(False)
    assert g.save()


def test_users_existing_profile_opens_on_the_fastest_setting(qapp, tmp_path):
    """Both steps wait 0.05 s before/after (the user's real file): opens in slider mode at 100%."""
    d = tmp_path / "legacy"
    d.mkdir()
    steps = [Step(name="Like", wait_before=0.05, wait_after=0.05, click_only_if_found=True).to_dict(),
             Step(name="Next", wait_before=0.05, wait_after=0.05).to_dict()]
    (d / "profile.json").write_text(json.dumps({"version": 2, "name": "legacy", "steps": steps,
                                                "settings": {"jitter_percent": 30.0}}), encoding="utf-8")
    win = MainWindow(storage.load_profile(d), start_hotkey=False)
    try:
        assert win.speed_slider.value() == 100 and not win.chk_manual.isChecked()
        assert "fastest" in win.lbl_speed.text()
        win.step_list.setCurrentRow(0)
        assert not win.step_editor.wait_after.isEnabled()
    finally:
        win.dirty = False
        win.close()


def test_a_legacy_profile_with_long_waits_opens_in_advanced_mode(qapp, tmp_path):
    d = tmp_path / "legacy2"
    d.mkdir()
    (d / "profile.json").write_text(json.dumps({"version": 2, "name": "slow", "steps": [
        Step(name="Like", wait_before=0.5, wait_after=2.0).to_dict()], "settings": {}}), encoding="utf-8")
    win = MainWindow(storage.load_profile(d), start_hotkey=False)
    try:
        win.step_list.setCurrentRow(0)
        assert win.chk_manual.isChecked() and not win.speed_slider.isEnabled()
        assert win.step_editor.wait_after.value() == 2.0 and win.step_editor.wait_after.isEnabled()
    finally:
        win.dirty = False
        win.close()


def test_the_speed_slider_ignores_the_wheel_unless_focused(g):
    g.chk_manual.setFocus()
    before = g.speed_slider.value()
    pos = QPointF(10, 5)
    ev = QWheelEvent(pos, g.speed_slider.mapToGlobal(pos), QPoint(0, 0), QPoint(0, 120), Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(g.speed_slider, ev)
    assert g.speed_slider.value() == before


# ---------------------------------------------------------------- real timing against the mock window

def click_gaps(win):
    t = [c.t for c in win.clicks]
    return [b - a for a, b in zip(t, t[1:])]


def slider_profile(tmp_path, win, speed, loops):
    prof = build_profile(tmp_path, win, loops=loops)
    prof.settings.speed_manual = False
    prof.settings.speed = speed
    return prof


@pytest.mark.parametrize("speed,expected,tol", [(0, 1.5, 0.30), (50, click_interval(50), 0.20)])
def test_real_click_to_click_time_follows_the_slider(qapp, tmp_path, backend, make_window, speed, expected, tol):
    win = make_window(num_stories=20)
    prof = slider_profile(tmp_path, win, speed, loops=4 if speed else 3)
    res = run_in_thread(qapp, make_runner(backend, win, prof))
    assert res.reason == R.COMPLETED, res
    g = click_gaps(win)[2:]  # the first gaps are still calibrating the scan+click overhead estimate
    assert g and abs(statistics.median(g) - expected) <= tol, (speed, expected, g)
    assert max(g) < expected + 0.5 and min(g) > expected - 0.5, g


def test_real_fastest_setting_is_much_faster_than_the_slowest(qapp, tmp_path, backend, make_window):
    win = make_window(num_stories=20)
    prof = slider_profile(tmp_path, win, 100, loops=6)
    res = run_in_thread(qapp, make_runner(backend, win, prof))
    assert res.reason == R.COMPLETED
    g = click_gaps(win)
    assert statistics.median(g) < 0.6, g  # no added delay: limited by scan + click only (about 0.25 s on this machine)
    assert win.sequence == ["heart", "arrow"] * 6
