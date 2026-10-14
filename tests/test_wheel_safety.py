"""Regression: scrolling the step editor with the mouse wheel must never change a setting.

A user's saved profile ended up with the heart step set to RIGHT click and the arrow to DOUBLE click: the wheel,
scrolling over the "Click type" combo box, had cycled its value.
"""
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication

from clickflow import runner as R
from clickflow import storage
from clickflow.gui.main_window import MainWindow
from clickflow.gui.widgets import SafeComboBox, SafeDoubleSpinBox, SafeSpinBox
from clickflow.models import Profile, Settings, Step

from test_runner import make_runner, heart_step, arrow_step  # noqa: F401
from helpers import make_heart


def wheel(widget, delta=-120):
    pos = QPointF(widget.width() / 2, widget.height() / 2)
    ev = QWheelEvent(pos, widget.mapToGlobal(pos), QPoint(0, 0), QPoint(0, delta), Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, ev)
    return ev


@pytest.fixture()
def gui(qapp, tmp_path):
    win = MainWindow(storage.new_profile("wheel", root=tmp_path / "p"), start_hotkey=False)
    win.show()
    win.chk_manual.setChecked(True)
    win.add_step()
    win.step_list.setCurrentRow(0)
    win.step_editor.name.setFocus()  # focus is on the name field, like a user who is just scrolling the form
    yield win
    win.dirty = False
    win.close()


def test_wheel_over_unfocused_click_type_does_not_change_it_and_is_passed_on(gui):
    e = gui.step_editor
    assert e.click_type.currentData() == "left"
    for _ in range(5):
        ev = wheel(e.click_type, -120)
        assert not ev.isAccepted()  # ignored -> the enclosing scroll area handles it
    for _ in range(5):
        wheel(e.click_type, +120)
    assert e.click_type.currentData() == "left" and gui.profile.steps[0].click_type == "left"


@pytest.mark.parametrize("name", ["wait_before", "wait_after", "timeout", "threshold", "retries", "rx", "ox"])
def test_wheel_over_unfocused_numbers_does_not_change_them(gui, name):
    w = getattr(gui.step_editor, name)
    before = w.value()
    wheel(w, -120)
    wheel(w, +120)
    assert w.value() == before


def test_every_editor_input_is_wheel_safe(gui):
    """No plain QComboBox/QSpinBox may sneak back in anywhere in the main window."""
    from PySide6.QtWidgets import QAbstractSpinBox, QComboBox

    for w in gui.findChildren(QComboBox):
        assert isinstance(w, SafeComboBox), w.objectName() or w
    for w in gui.findChildren(QAbstractSpinBox):
        if w.parent() is not None and w.parent().__class__.__name__ == "QComboBox":
            continue
        assert isinstance(w, (SafeSpinBox, SafeDoubleSpinBox)), w


def test_wheel_still_works_after_the_user_clicks_into_the_control(gui):
    sp = gui.step_editor.wait_after
    sp.setFocus()
    if not sp.hasFocus():
        pytest.skip("this platform did not grant focus to the window")
    before = sp.value()
    wheel(sp, +120)
    assert sp.value() > before


def test_settings_tab_inputs_are_protected_too(gui):
    before = (gui.s_loops.value(), gui.s_jitter.value(), gui.s_maxclicks.value(), gui.preset_combo.currentIndex())
    for w in (gui.s_loops, gui.s_jitter, gui.s_maxclicks, gui.preset_combo):
        wheel(w, -120)
    assert (gui.s_loops.value(), gui.s_jitter.value(), gui.s_maxclicks.value(),
            gui.preset_combo.currentIndex()) == before


def test_unusual_click_types_are_flagged_in_the_step_list(gui):
    gui.step_editor.click_type.setCurrentIndex(gui.step_editor.click_type.findData("right"))
    assert "RIGHT-CLICK" in gui.step_list.item(0).text()
    gui.step_editor.click_type.setCurrentIndex(gui.step_editor.click_type.findData("left"))
    assert "CLICK" not in gui.step_list.item(0).text().replace("click-only", "")


def test_run_log_starts_with_a_plan_of_every_step():
    from helpers import World
    from test_runner import make_runner

    w = World()
    events = []
    r = make_runner(w, [heart_step(click_type="right"), arrow_step(click_type="double")], events=events)
    r.run()
    plan = [e.message for e in events if e.message.startswith("  step ")]
    assert len(plan) == 2
    assert "RIGHT click" in plan[0] and "DOUBLE click" in plan[1] and "WHOLE screen" in plan[0]
