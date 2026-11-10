"""The redesigned UI: simple / advanced modes, theme, language, step cards, hotkey capture, run dashboard."""
import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest

from clickflow import storage
from clickflow.gui import i18n, icons, prefs, theme
from clickflow.gui.main_window import MainWindow
from clickflow.gui.widgets import HotkeyEdit, Segmented, StepDelegate, Switch, ThresholdSlider, hotkey_from_event
from clickflow.runner import Event


@pytest.fixture()
def win(qapp, tmp_path):
    w = MainWindow(storage.new_profile("design", root=tmp_path / "profiles"), start_hotkey=False)
    w.show()
    yield w
    w.dirty = False
    w.close()


def test_empty_profile_shows_the_welcome_screen_and_disables_start(win):
    assert win.main_stack.currentIndex() == 1 and not win.btn_start.isEnabled() and not win.btn_dry.isEnabled()
    win.add_step()
    assert win.main_stack.currentIndex() == 0 and win.btn_start.isEnabled() and win.step_count.text() == "1"
    win.step_list.setCurrentRow(0)
    win.delete_step()
    assert win.main_stack.currentIndex() == 1


def test_simple_mode_hides_the_advanced_groups_and_remembers_the_choice(win):
    win.add_step()
    e = win.step_editor
    assert not win.tabs.isVisibleTo(win) and not e.grp_match.isVisibleTo(e) and not e.grp_wait.isVisibleTo(e)
    assert e.click_type.isVisibleTo(e) and e.only_if_found.isVisibleTo(e) and win.run_card.isVisibleTo(win)
    win.set_mode(True)
    assert win.tabs.isVisibleTo(win) and e.grp_match.isVisibleTo(e) and e.grp_wait.isVisibleTo(e)
    assert e.click_type.isVisibleTo(e)  # the click type moved into the "Click" group, it did not vanish
    assert prefs.get("mode") == "advanced"
    win.tabs.setCurrentIndex(1)
    assert win.right_stack.currentIndex() == 1 and win.run_card.parentWidget() is not None
    win.set_mode(False)
    assert win.right_stack.currentIndex() == 0 and prefs.get("mode") == "simple"


def test_the_run_card_is_one_widget_shared_by_both_modes(win):
    """Loop / speed / click-limit controls must keep working after moving between the simple and advanced layouts."""
    win.add_step()
    win.set_mode(True)
    win.s_loops.setValue(9)
    win.set_mode(False)
    assert win.profile.settings.loop_count == 9 and win.s_loops.value() == 9


def test_infinite_toggle_and_click_limit_switch(win):
    win.s_infinite.setChecked(True)
    assert win.profile.settings.infinite_loop and not win.s_loops.isEnabled() and win.repeat_seg.currentIndex() == 1
    win.s_infinite.setChecked(False)
    assert not win.profile.settings.infinite_loop and win.s_loops.isEnabled()
    win.max_row.switch.setChecked(False)
    assert win.profile.settings.max_total_clicks == 0
    win.max_row.switch.setChecked(True)
    assert win.profile.settings.max_total_clicks == 500  # back to the remembered value
    win.s_maxclicks.setValue(0)
    assert not win.max_row.switch.isChecked()


def test_speed_presets_move_the_slider_and_the_slider_selects_a_preset(win):
    win.speed_seg.setCurrentIndex(0)
    assert win.speed_slider.value() == 0 and win.profile.settings.speed == 0
    win.speed_seg.setCurrentIndex(2)
    assert win.speed_slider.value() == 100
    win.speed_slider.setValue(33)
    assert win.speed_seg.currentIndex() == -1  # between presets: nothing highlighted
    win.speed_slider.setValue(50)
    assert win.speed_seg.currentData() == 50


def test_step_cards_toggle_with_their_switch(qapp, win):
    win.add_step()
    qapp.processEvents()  # let the list lay out so the card has a real position
    item = win.step_list.item(0)
    rect = win.step_list.visualItemRect(item)
    card = QRect(rect.x() + 1, rect.y() + 1, rect.width() - 2, 64)
    sw = StepDelegate.switch_rect(card)
    assert win.profile.steps[0].enabled
    QTest.mouseClick(win.step_list.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, sw.center())
    assert not win.profile.steps[0].enabled and item.checkState() == Qt.CheckState.Unchecked and win.dirty


def test_running_hides_thumbnails_in_the_list_and_swaps_the_start_button(win):
    win.add_step()
    win.step_list.setCurrentRow(0)
    assert win.btn_start.property("variant") == "primary"
    win._set_running(True)
    try:
        assert win.right_stack.currentIndex() == 2 and not win.tabs.isVisibleTo(win)
        assert win.btn_start.property("variant") == "danger" and "Stop" in win.btn_start.text()
        assert win.step_list.item(0).data(Qt.ItemDataRole.UserRole + 1)["hidden"] is True
        assert not win.step_editor.thumb.isVisibleTo(win.step_editor) and win.step_editor.thumb_hidden.isVisibleTo(win.step_editor)
        assert not win.step_list.isEnabled() and not win.mode_seg.isEnabled()
    finally:
        win._set_running(False)
    assert win.btn_start.property("variant") == "primary" and win.step_list.isEnabled()
    assert win.step_list.item(0).data(Qt.ItemDataRole.UserRole + 1)["hidden"] is False


def test_dashboard_counts_clicks_loops_and_the_current_step(win):
    win.add_step()
    win.add_step()
    win.profile.settings.max_total_clicks = 4
    win._set_running(True)
    try:
        win._stats.update(t0=__import__("time").monotonic(), total=2, started=True)
        name = win.profile.steps[1].name
        for ev in (Event("loop", "--- loop 1/inf ---", "info", 0.0, {"loop": 1}),
                   Event("step", f"Step '{name}'", "info", 0.0, {"step": name}),
                   Event("click", "left-click at (1,2)", "info", 0.0, {"x": 1, "y": 2, "dry": False}),
                   Event("click", "left-click at (1,2)", "info", 0.0, {"x": 1, "y": 2, "dry": False})):
            win._on_event(ev)
        assert win.tile_clicks.n.text() == "2" and win.tile_loops.n.text() == "1"
        assert win.tile_step.n.text() == "2 / 2" and win.dash_progress.value() == 500
    finally:
        win._set_running(False)


def test_dark_theme_changes_the_tokens_and_icons_render(qapp):
    theme.apply(qapp, "light")
    light = theme.tok("bg")
    theme.apply(qapp, "dark")
    try:
        assert theme.mode() == "dark" and theme.tok("bg") != light
        px = icons.pixmap("play", theme.tok("tx"), 16, 2.0)
        assert not px.isNull() and px.width() == 32
        assert icons.has("play") and not icons.has("no-such-icon")
    finally:
        theme.apply(qapp, "light")


def test_language_switch_rebuilds_the_window_without_losing_state(win):
    win.add_step()
    win.step_list.setCurrentRow(0)
    win.s_loops.setValue(7)
    win.append_log("hello log")
    win.set_mode(True)
    win._toggle_language()
    try:
        assert i18n.language() == "zh"
        assert win.btn_start.text() == "开始" and win.profile.settings.loop_count == 7
        assert win.s_loops.value() == 7 and win.step_list.count() == 1 and win.step_list.currentRow() == 0
        assert win.dirty  # the unsaved edits are still unsaved
        assert "hello log" in win.log_view.toPlainText()
        assert win._advanced and win.step_editor.is_advanced()
    finally:
        win._toggle_language()
    assert i18n.language() == "en" and win.btn_start.text() == "Start"


def test_chinese_run_log_lines():
    from clickflow.gui.i18n_zh import format_event

    assert format_event(Event("loop", "--- loop 3/inf ---", "info", 0, {})) == "第 3 轮开始"
    assert "置信度 0.94" in format_event(Event("match", "'Like': FOUND, confidence 0.941 (threshold 0.85)", "info", 0, {}))
    assert format_event(Event("click", "left-click at (812,604)", "info", 0, {})) == "左键点击 (812, 604)"
    assert format_event(Event("log", "something else", "info", 0, {})) == "something else"  # unknown lines pass through


def test_every_translated_string_keeps_its_placeholders():
    import re

    from clickflow.gui.i18n_zh import ZH

    ph = re.compile(r"\{[^}]*\}")
    for en, zh in ZH.items():
        assert sorted(ph.findall(en)) == sorted(ph.findall(zh)), (en, zh)


def test_hotkey_field_captures_a_key_press_instead_of_text(qapp):
    edit = HotkeyEdit()
    edit.show()
    got = []
    edit.editingFinished.connect(lambda: got.append(edit.text()))
    edit.setFocus()
    QTest.keyClick(edit, Qt.Key.Key_F9)
    QTest.keyClick(edit, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    QTest.keyClick(edit, Qt.Key.Key_Shift)  # a lone modifier is not a hotkey
    assert got == ["F9", "ctrl+shift+s"] and edit.text() == "ctrl+shift+s"
    from clickflow.hotkey import parse_hotkey

    assert parse_hotkey(edit.text()) == "<ctrl>+<shift>+s"  # what the field produces is always accepted


def test_invalid_hotkey_text_is_rejected_and_reverted(win, monkeypatch):
    from clickflow.gui import dialogs

    shown = []
    monkeypatch.setattr(dialogs, "warn", lambda parent, title, text: shown.append(title))
    win.s_hotkey.setText("not-a-key")
    win._apply_hotkey()
    assert shown == ["Invalid hotkey"] and win.s_hotkey.text() == win.profile.settings.stop_hotkey


def test_segmented_and_threshold_have_the_combo_and_float_apis(qapp):
    seg = Segmented()
    for text, data in (("a", 1), ("b", 2), ("c", 3)):
        seg.addItem(text, data)
    changes = []
    seg.currentIndexChanged.connect(changes.append)
    seg.setCurrentIndex(2)
    assert seg.currentData() == 3 and seg.findData(2) == 1 and changes == [2]
    seg.clearSelection()
    assert seg.currentIndex() == -1
    t = ThresholdSlider("x")
    got = []
    t.valueChanged.connect(got.append)
    t.setValue(0.93)
    assert abs(t.value() - 0.93) < 1e-9 and got and abs(got[-1] - 0.93) < 1e-9
    t.setValue(2.0)
    assert t.value() == 1.0  # clamped to the slider range
    s = Switch()
    s.setChecked(True)
    assert s.isChecked()


def test_hotkey_names_map_to_what_the_parser_accepts(qapp):
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent

    from clickflow.hotkey import parse_hotkey

    for key in (Qt.Key.Key_F1, Qt.Key.Key_F24, Qt.Key.Key_Space, Qt.Key.Key_Home, Qt.Key.Key_PageDown, Qt.Key.Key_A,
                Qt.Key.Key_5, Qt.Key.Key_Pause):
        ev = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
        name = hotkey_from_event(ev)
        assert name and parse_hotkey(name), (key, name)


def test_topbar_preset_menu_lists_selects_and_reflects_the_active_preset(win, monkeypatch):
    from clickflow.screen import MonitorInfo

    mon = MonitorInfo(1, 0, 0, 2560, 1440, True)
    monkeypatch.setattr(MainWindow, "_detect_monitors", lambda self: [mon])
    assert win.preset_btn.isVisibleTo(win) and "Default" in win.preset_btn.text()
    p = win.create_preset("Desk", mon)
    assert "Desk" in win.preset_btn.text() and win.active_preset is p
    win._fill_preset_menu()
    acts = {a.text(): a for a in win.preset_menu.actions() if a.text()}
    checked = [t for t, a in acts.items() if a.isCheckable() and a.isChecked() and "Desk" in t]
    assert checked, list(acts)
    acts["Default (no preset)"].trigger()  # pick "no preset" from the top bar
    assert win.active_preset is None and "Default" in win.preset_btn.text()
    win._fill_preset_menu()
    acts = {a.text(): a for a in win.preset_menu.actions() if a.text()}
    assert not acts["Rename preset..."].isEnabled() and not acts["Delete preset..."].isEnabled()  # nothing to rename
    win._set_running(True)
    try:
        assert not win.preset_btn.isEnabled()  # locked while a run is active
    finally:
        win._set_running(False)


def test_the_default_theme_is_light_and_neutral(qapp):
    from clickflow.gui import prefs

    prefs.reset_cache()
    assert prefs.get("theme") == "light"
    for name in ("light", "dark"):
        for key in ("bg", "pn", "cd"):
            c = theme.TOKENS[name][key].lstrip("#")
            r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
            assert abs(b - r) <= 12, (name, key, c)  # no blue cast in the backgrounds
