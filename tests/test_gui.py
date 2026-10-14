"""GUI behaviour tests (no clicking): list operations, editor binding, capture overlay, highlighter."""
import json
import time

import numpy as np
import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from clickflow import storage
from clickflow.gui.main_window import MainWindow
from clickflow.gui.overlays import CaptureOverlay, Highlighter
from clickflow.models import Step

from helpers import make_background, make_heart


@pytest.fixture()
def gui(qapp, tmp_path):
    prof = storage.new_profile("gui test", root=tmp_path / "profiles")
    win = MainWindow(prof, start_hotkey=False)
    win.show()
    win.chk_manual.setChecked(True)  # these tests edit per-step waits: advanced mode
    yield win
    win.dirty = False
    win.close()


def test_add_duplicate_move_delete_toggle(gui):
    gui.add_step()
    gui.add_step()
    gui.add_step()
    assert [s.name for s in gui.profile.steps] == ["Step 1", "Step 2", "Step 3"]
    gui.step_list.setCurrentRow(0)
    storage.save_template(gui.profile.directory, gui.profile.steps[0], make_heart(30))
    gui.duplicate_step()
    assert len(gui.profile.steps) == 4 and gui.profile.steps[1].name == "Step 1 copy"
    assert gui.profile.steps[1].template and gui.profile.steps[1].template != gui.profile.steps[0].template
    gui.step_list.setCurrentRow(1)
    gui.move_step(1)
    assert gui.profile.steps[2].name == "Step 1 copy"
    gui.move_step(-1)
    gui.move_step(-1)
    assert gui.profile.steps[0].name == "Step 1 copy"
    gui.step_list.setCurrentRow(3)
    gui.delete_step()
    assert [s.name for s in gui.profile.steps] == ["Step 1 copy", "Step 1", "Step 2"]
    assert gui.step_list.count() == 3
    item = gui.step_list.item(1)
    item.setCheckState(Qt.CheckState.Unchecked)
    assert gui.profile.steps[1].enabled is False
    assert gui.dirty


def test_editor_fields_write_back_to_step(gui):
    gui.add_step()
    gui.step_list.setCurrentRow(0)
    e, s = gui.step_editor, gui.profile.steps[0]
    e.threshold.setValue(0.93)
    e.click_type.setCurrentIndex(e.click_type.findData("double"))
    e.wait_before.setValue(1.5)
    e.wait_after.setValue(2.25)
    e.timeout.setValue(8)
    e.ox.setValue(7)
    e.oy.setValue(-3)
    e.not_found.setCurrentIndex(e.not_found.findData("key"))
    e.fallback_key.setText("right")
    e.fallback_key.editingFinished.emit()
    assert not e.rx.isEnabled() and "WHOLE screen" in e.region_hint.text()  # no search box yet: warned
    e.set_region_values((10, 20, 300, 200))
    assert e.rx.isEnabled() and "Search box set" in e.region_hint.text()
    e.rw.setValue(300), e.rh.setValue(200)  # fine-tuning the numbers also works
    assert (s.threshold, s.click_type, s.wait_before, s.wait_after, s.timeout) == (0.93, "double", 1.5, 2.25, 8)
    assert (s.offset_x, s.offset_y, s.not_found_action, s.fallback_key) == (7, -3, "key", "right")
    assert s.region == (10, 20, 300, 200)
    assert e.fallback_key.isEnabled() and not e.retries.isEnabled()
    e.not_found.setCurrentIndex(e.not_found.findData("retry"))
    assert e.retries.isEnabled() and not e.fallback_key.isEnabled()
    # switch selection and back: values are restored from the model
    gui.add_step()
    gui.step_list.setCurrentRow(1)
    gui.step_list.setCurrentRow(0)
    assert e.threshold.value() == 0.93 and e.rw.value() == 300


def test_settings_and_save_load_through_ui(gui):
    gui.s_infinite.setChecked(True)
    gui.s_jitter.setValue(35)
    gui.s_maxclicks.setValue(25)
    gui.s_hotkey.setText("F9")
    gui.s_hotkey.editingFinished.emit()
    gui.notes.setPlainText("hello notes")
    gui.add_step()
    assert gui.save()
    data = json.loads((gui.profile.directory / "profile.json").read_text(encoding="utf-8"))
    assert data["settings"]["infinite_loop"] is True and data["settings"]["jitter_percent"] == 35
    assert data["settings"]["max_total_clicks"] == 25 and data["settings"]["stop_hotkey"] == "F9"
    assert data["notes"] == "hello notes"
    gui.load_into_ui(storage.load_profile(gui.profile.directory))
    assert gui.s_infinite.isChecked() and gui.s_maxclicks.value() == 25 and not gui.s_loops.isEnabled()
    assert gui.banner.isVisible() or gui.banner.text() == "hello notes"


def test_default_profile_opens_with_templates_note_and_no_search_boxes(qapp, tmp_path):
    from clickflow.app import ensure_example

    path = ensure_example()
    assert path and path.exists()
    prof = storage.load_profile(path)
    assert "SEARCH BOXES ARE EMPTY" in prof.notes
    assert len(prof.steps) == 2 and prof.steps[0].click_only_if_found
    assert prof.validate() == []  # templates ship with it, so a run can start right away
    win = MainWindow(prof, start_hotkey=False)
    try:
        assert win.banner.text().startswith("Sample profile")
        assert "NO TEMPLATE" not in win.step_list.item(0).text()
        assert "no search box" in win.step_list.item(0).text()  # the nudge to draw one
    finally:
        win.dirty = False
        win.close()


def test_start_refuses_without_templates(gui, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    gui.add_step()
    gui.start_run(dry=False)
    assert gui._run_thread is None and shown and "template" in shown[0].lower()


def test_capture_overlay_maps_drag_to_screenshot_pixels(qapp):
    img = np.zeros((600, 800, 3), np.uint8)  # 'physical' screenshot is 2x the 400x300 widget
    ov = CaptureOverlay(img, QRect(50, 50, 400, 300), "hint")
    got = []
    ov.selected.connect(lambda *r: got.append(r))
    ov.open()
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(100, 50))
    QTest.mouseMove(ov, QPoint(150, 100))
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(200, 150))
    assert got == [(200, 100, 200, 200)]


def test_capture_overlay_cancel_and_tiny_drag(qapp):
    ov = CaptureOverlay(np.zeros((300, 400, 3), np.uint8), QRect(0, 0, 400, 300), "hint")
    got, cancelled = [], []
    ov.selected.connect(lambda *r: got.append(r))
    ov.cancelled.connect(lambda: cancelled.append(1))
    ov.open()
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(10, 10))
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(12, 12))
    assert not got and not cancelled  # too small: ignored, overlay stays open
    QTest.keyClick(ov, Qt.Key.Key_Escape)
    assert cancelled == [1]


def test_highlighter_shows_then_hides(qapp):
    h = Highlighter()
    h.flash((100, 100, 50, 50), "0.93", True, ms=150)
    assert h.isVisible()
    end = time.monotonic() + 1.5
    while h.isVisible() and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.02)
    assert not h.isVisible()


def _type_without_committing(widget, text):
    """Type into a spin box like a user does, but do NOT press Enter / Tab (no focus-out)."""
    widget.setFocus()
    widget.selectAll()
    QTest.keyClicks(widget, text)


def test_save_picks_up_values_typed_but_not_yet_committed(gui):
    """Regression: typing a wait time and clicking Save (a toolbar button never takes focus)
    must save the typed value, not the previous one."""
    gui.add_step()
    gui.step_list.setCurrentRow(0)
    gui.tabs.setCurrentIndex(1)
    _type_without_committing(gui.s_start_delay, "9")
    _type_without_committing(gui.s_loops, "42")
    gui.s_jitter.setFocus()
    gui.s_jitter.selectAll()
    QTest.keyClicks(gui.s_jitter, "45")
    gui.tabs.setCurrentIndex(0)
    _type_without_committing(gui.step_editor.timeout, "12")
    _type_without_committing(gui.step_editor.wait_after, "7.5")  # last field typed, never committed
    assert gui.save()
    data = json.loads((gui.profile.directory / "profile.json").read_text(encoding="utf-8"))
    assert data["steps"][0]["wait_after"] == 7.5
    assert data["steps"][0]["timeout"] == 12
    assert data["settings"]["start_delay"] == 9
    assert data["settings"]["loop_count"] == 42
    assert data["settings"]["jitter_percent"] == 45
    # and a fresh load from disk shows the same values
    re = storage.load_profile(gui.profile.directory)
    assert re.steps[0].wait_after == 7.5 and re.settings.start_delay == 9.0


def test_typing_marks_profile_dirty_immediately(gui):
    gui.add_step()
    gui.step_list.setCurrentRow(0)
    gui.dirty = False
    _type_without_committing(gui.step_editor.wait_before, "3")
    assert gui.dirty
    assert gui.profile.steps[0].wait_before == 3.0


def test_settings_survive_save_and_app_restart(qapp, tmp_path):
    """The user story: edit wait seconds + global settings, press Save (toolbar action), restart the app.

    The restart is simulated with the same startup path the app uses; the new window must show the edited values.
    """
    from clickflow.app import startup_profile

    prof = storage.new_profile("my flow", root=tmp_path / "profiles")
    win = MainWindow(prof, start_hotkey=False)
    win.show()
    win.chk_manual.setChecked(True)
    win.add_step()
    win.step_list.setCurrentRow(0)
    _type_without_committing(win.step_editor.wait_after, "6.5")
    _type_without_committing(win.step_editor.wait_before, "1.25")
    win.tabs.setCurrentIndex(1)
    _type_without_committing(win.s_start_delay, "12")
    win.s_infinite.setChecked(True)
    _type_without_committing(win.s_maxclicks, "77")
    win.s_hotkey.setFocus()
    win.s_hotkey.selectAll()
    QTest.keyClicks(win.s_hotkey, "F9")  # typed, Enter never pressed
    win.act_save.trigger()  # exactly what the toolbar's Save button does
    assert not win.dirty
    win.dirty = False
    win.close()

    loaded = startup_profile()  # no path given: must reopen the profile used last, not the bundled example
    assert loaded is not None and loaded.name == "my flow"
    win2 = MainWindow(loaded, start_hotkey=False)
    try:
        assert win2.profile.steps[0].wait_after == 6.5 and win2.profile.steps[0].wait_before == 1.25
        win2.step_list.setCurrentRow(0)
        assert win2.step_editor.wait_after.value() == 6.5
        assert win2.s_start_delay.value() == 12 and win2.s_infinite.isChecked()
        assert win2.s_maxclicks.value() == 77 and win2.s_hotkey.text() == "F9"
    finally:
        win2.dirty = False
        win2.close()


def test_startup_falls_back_to_example_when_nothing_remembered(qapp):
    from clickflow.app import startup_profile

    p = startup_profile()
    assert p is not None and p.name == "instagram_story_like"


def test_template_previews_are_hidden_while_a_run_is_active(gui):
    """The preview is a picture of the searched icon; if it stays on screen the matcher may find (and click) it."""
    gui.add_step()
    gui.step_list.setCurrentRow(0)
    storage.save_template(gui.profile.directory, gui.profile.steps[0], make_heart(40))
    gui._show_step(gui.profile.steps[0])
    assert gui.step_editor.thumb.isVisibleTo(gui.step_editor) and gui.end_editor.thumb.isVisibleTo(gui.end_editor)
    gui._set_running(True)
    assert not gui.step_editor.thumb.isVisibleTo(gui.step_editor)
    assert not gui.end_editor.thumb.isVisibleTo(gui.end_editor)
    gui._set_running(False)
    assert gui.step_editor.thumb.isVisibleTo(gui.step_editor) and gui.end_editor.thumb.isVisibleTo(gui.end_editor)


@pytest.mark.parametrize("w,h", [(1366, 728), (1280, 680), (1024, 700), (1920, 1040), (2560, 1400)])
def test_initial_window_size_always_fits_the_screen(w, h):
    iw, ih = MainWindow.initial_size(w, h)
    assert iw <= w and ih <= h and iw >= 900 * min(1, w / 1000) and ih >= 600 * min(1, h / 700)
    assert iw <= 1180 and ih <= 820  # never larger than the design size


def test_window_can_shrink_to_a_small_laptop_screen(gui):
    """The Global settings page used to force a ~935 px tall window; it is scrollable now."""
    hint = gui.minimumSizeHint()
    assert hint.height() <= 560 and hint.width() <= 1000, (hint.width(), hint.height())
    gui.resize(1000, 560)
    assert gui.height() <= 600


def test_settings_tab_is_scrollable_but_still_reachable(gui):
    from PySide6.QtWidgets import QScrollArea

    page = gui.tabs.widget(1)
    assert isinstance(page, QScrollArea)
    assert page.widget().findChild(type(gui.s_loops)) is not None  # the controls live inside the scroll area
    gui.s_loops.setValue(7)
    assert gui.profile.settings.loop_count == 7
