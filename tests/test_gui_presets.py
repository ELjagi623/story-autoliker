"""GUI: display presets, per-display search boxes and the two-stage capture drag."""
import time

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

import clickflow.gui.main_window as mw
from clickflow import storage
from clickflow.gui.main_window import MainWindow
from clickflow.models import effective_region, effective_template
from clickflow.runner import Event
from clickflow.screen import Frame, MonitorInfo

from helpers import make_background, make_heart

MONS = [MonitorInfo(1, 0, 0, 2560, 1440, True), MonitorInfo(2, 2560, 0, 1920, 1080, False)]


@pytest.fixture()
def g(qapp, tmp_path, monkeypatch):
    """A MainWindow whose display detection is faked (two monitors) so preset logic is deterministic."""
    monkeypatch.setattr(MainWindow, "_detect_monitors", lambda self: MONS)
    prof = storage.new_profile("preset gui", root=tmp_path / "profiles")
    win = MainWindow(prof, start_hotkey=False)
    win.show()
    win._refresh_displays_label()
    yield win
    win.dirty = False
    win.close()


def test_preset_create_switch_and_edits_go_to_the_right_place(g):
    g.add_step()
    g.step_list.setCurrentRow(0)
    step = g.profile.steps[0]
    g.step_editor.set_region_values((10, 20, 300, 200))  # default configuration
    assert step.region == (10, 20, 300, 200)

    big = g.create_preset("Desk", MONS[0])
    assert g.active_preset is big and g.preset_combo.currentData() == big.id
    assert big.resolution == (2560, 1440) and big.monitor == 1
    assert g.step_editor._region_on is False  # presets never inherit another display's box
    assert "preset 'Desk'" in g.step_editor.region_hint.text()
    g.step_editor.set_region_values((500, 600, 120, 90))
    assert big.regions[step.id] == (500, 600, 120, 90) and step.region == (10, 20, 300, 200)

    small = g.create_preset("Laptop", MONS[1])
    g.step_editor.set_region_values((5, 6, 70, 80))
    assert small.regions[step.id] == (5, 6, 70, 80) and big.regions[step.id] == (500, 600, 120, 90)

    g.preset_combo.setCurrentIndex(g.preset_combo.findData(big.id))  # user switches preset
    assert g.step_editor.rx.value() == 500 and g.active_preset is big
    g.preset_combo.setCurrentIndex(0)  # back to Default
    assert g.active_preset is None and g.step_editor.rx.value() == 10
    assert "Detected displays" in g.lbl_displays.text() and "Desk" in g.lbl_displays.text()
    assert "Laptop" in g.lbl_displays.text() and "no preset" not in g.lbl_displays.text()


def test_presets_and_active_choice_persist_through_save_and_reload(g):
    g.add_step()
    g.step_list.setCurrentRow(0)
    storage.save_template(g.profile.directory, g.profile.steps[0], make_heart(30))
    p = g.create_preset("Desk", MONS[0])
    g.step_editor.set_region_values((1, 2, 33, 44))
    g.chk_auto_preset.setChecked(False)
    assert g.save()
    re = storage.load_profile(g.profile.directory)
    assert re.presets[0].regions[re.steps[0].id] == (1, 2, 33, 44) and re.presets[0].resolution == (2560, 1440)
    assert re.settings.active_preset == p.id and re.settings.auto_preset is False
    g.load_into_ui(re)
    assert g.active_preset.name == "Desk" and not g.chk_auto_preset.isChecked()
    assert g.step_editor.rx.value() == 1


def test_capturing_inside_a_preset_saves_a_preset_template_not_the_default(g):
    g.add_step()
    g.step_list.setCurrentRow(0)
    step = g.profile.steps[0]
    storage.save_template(g.profile.directory, step, make_heart(30))
    base_tpl = step.template
    p = g.create_preset("Desk", MONS[0])
    g._save_crop(step, Frame(make_background(400, 300)), 10, 10, 50, 40)
    assert step.template == base_tpl and p.templates[step.id] != base_tpl
    assert (g.profile.directory / p.templates[step.id]).exists()
    assert effective_template(step, p) == p.templates[step.id]


def test_item_flags_show_missing_template_and_missing_search_box(g):
    g.add_step()
    assert "NO TEMPLATE" in g.step_list.item(0).text()
    storage.save_template(g.profile.directory, g.profile.steps[0], make_heart(30))
    g._refresh_items()
    assert "no search box" in g.step_list.item(0).text()
    g.step_list.setCurrentRow(0)
    g.step_editor.set_region_values((0, 0, 50, 50))
    assert "no search box" not in g.step_list.item(0).text()


def test_delete_and_duplicate_step_keep_presets_consistent(g):
    g.add_step()
    g.step_list.setCurrentRow(0)
    a = g.profile.steps[0]
    p = g.create_preset("Desk", MONS[0])
    g.step_editor.set_region_values((1, 1, 20, 20))
    storage.save_template(g.profile.directory, a, make_heart(30), preset=p)
    g.duplicate_step()
    b = g.profile.steps[1]
    assert p.regions[b.id] == (1, 1, 20, 20) and p.templates[b.id] != p.templates[a.id]
    g.step_list.setCurrentRow(0)
    g.delete_step()
    assert a.id not in p.regions and a.id not in p.templates and b.id in p.regions


def test_remove_preset_deletes_its_files_and_falls_back_to_default(g):
    g.add_step()
    st = g.profile.steps[0]
    p = g.create_preset("Gone", MONS[0])
    storage.save_template(g.profile.directory, st, make_heart(30), preset=p)
    f = g.profile.directory / p.templates[st.id]
    assert f.exists()
    g.remove_preset(p)
    assert not f.exists() and g.profile.presets == [] and g.active_preset is None
    assert g.preset_combo.count() == 1


def test_auto_selected_preset_event_updates_the_ui_without_marking_dirty(g):
    a = g.create_preset("A", MONS[0])
    b = g.create_preset("B", MONS[1])
    g.preset_combo.setCurrentIndex(g.preset_combo.findData(a.id))
    g.dirty = False
    g._on_event(Event("preset", "Display preset: ...", data={"preset": b.id, "monitor": 2}))
    assert g.active_preset is b and g.preset_combo.currentData() == b.id and not g.dirty


# ---- the two-stage capture drag: template first, then the search box, on one screenshot

class _OneFrameScreen:
    def __init__(self, frame):
        self.frame = frame

    def grab(self):
        return self.frame


def _drag(ov, fx0, fy0, fx1, fy1):
    w, h = ov.width(), ov.height()
    p0, p1 = QPoint(int(w * fx0), int(h * fy0)), QPoint(int(w * fx1), int(h * fy1))
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p0)
    QTest.mouseMove(ov, p1)
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p1)


def _wait_overlay(qapp, g, timeout=5):
    end = time.monotonic() + timeout
    while g._overlay is None and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)
    assert g._overlay is not None, "capture overlay did not appear"
    return g._overlay


@pytest.mark.parametrize("use_preset", [False, True])
def test_capture_template_then_search_box_in_one_go(qapp, g, monkeypatch, use_preset):
    frame = Frame(make_background(800, 600), left=100.0, top=50.0)  # a monitor whose origin is (100, 50)
    monkeypatch.setattr(mw, "MssScreen", lambda *a, **k: _OneFrameScreen(frame))
    g.add_step()
    g.step_list.setCurrentRow(0)
    step = g.profile.steps[0]
    if use_preset:
        g.create_preset("Desk", MONS[0])
    g.capture_step_template()

    ov = _wait_overlay(qapp, g)  # stage 1: the template
    assert "template" in ov._hint.lower() and not ov._guides
    _drag(ov, 0.25, 0.25, 0.50, 0.50)
    qapp.processEvents()
    tpl = effective_template(step, g.active_preset)
    assert tpl and (g.profile.directory / tpl).exists()
    img = storage.read_image(g.profile.directory / tpl)
    assert abs(img.shape[1] - 200) <= 2 and abs(img.shape[0] - 150) <= 2  # 25% x 25% of an 800x600 screenshot

    ov2 = _wait_overlay(qapp, g)  # stage 2 appeared automatically, on the same screenshot
    assert "SEARCH BOX" in ov2._hint and any(lab == "template" for *_r, lab in ov2._guides)
    _drag(ov2, 0.10, 0.10, 0.70, 0.80)
    qapp.processEvents()
    box = effective_region(step, g.active_preset)
    assert box is not None
    # screenshot pixel (80, 60) is at screen (100+80, 50+60); presets store it relative to the monitor
    expect_x, expect_y = (80, 60) if use_preset else (180, 110)
    assert abs(box[0] - expect_x) <= 2 and abs(box[1] - expect_y) <= 2
    assert abs(box[2] - 480) <= 2 and abs(box[3] - 420) <= 2
    if use_preset:
        assert step.region is None  # the default configuration was not touched
    assert g._overlay is None and not g.isMinimized()
    assert "no search box" not in g.step_list.item(0).text()


def test_search_box_stage_skipped_when_box_exists_and_esc_skips_it(qapp, g, monkeypatch):
    monkeypatch.setattr(mw, "MssScreen", lambda *a, **k: _OneFrameScreen(Frame(make_background(800, 600))))
    g.add_step()
    g.step_list.setCurrentRow(0)
    step = g.profile.steps[0]
    step.region = (1, 2, 30, 40)
    g.capture_step_template()
    ov = _wait_overlay(qapp, g)
    _drag(ov, 0.2, 0.2, 0.4, 0.4)
    qapp.processEvents()
    assert g._overlay is None and step.region == (1, 2, 30, 40)  # existing box kept, no second prompt

    step.region = None
    g.capture_step_template()
    ov = _wait_overlay(qapp, g)
    _drag(ov, 0.2, 0.2, 0.4, 0.4)
    ov2 = _wait_overlay(qapp, g)
    QTest.keyClick(ov2, Qt.Key.Key_Escape)  # skip the box
    qapp.processEvents()
    assert step.region is None and step.template  # template kept, scanning the whole screen
    assert g._overlay is None and not g.isMinimized()


def test_draw_search_box_alone_shows_other_steps_boxes_as_guides(qapp, g, monkeypatch):
    monkeypatch.setattr(mw, "MssScreen", lambda *a, **k: _OneFrameScreen(Frame(make_background(800, 600))))
    g.add_step()
    g.add_step()
    g.profile.steps[0].region = (100, 100, 200, 100)
    g.step_list.setCurrentRow(1)
    g.pick_step_region()
    ov = _wait_overlay(qapp, g)
    assert list(ov._guides) == [(100, 100, 200, 100, "Step 1")]
    _drag(ov, 0.5, 0.5, 0.9, 0.9)
    qapp.processEvents()
    assert g.profile.steps[1].region is not None


def test_show_search_boxes_draws_dashed_boxes(qapp, g):
    g.add_step()
    g.add_step()
    g.profile.steps[0].region = (100, 100, 200, 100)
    g.show_search_boxes()
    assert g.highlighter.isVisible() and len(g.highlighter._boxes) == 1
    assert g.highlighter._boxes[0][4] is True  # dashed = search box
    assert "Showing 1 search box" in g.log_view.toPlainText()
    g.highlighter._boxes.clear()
    g.highlighter.hide()
    g.profile.steps[0].region = None
    g.show_search_boxes()
    assert "No search boxes are set yet" in g.log_view.toPlainText()


def test_qt_geometry_picks_a_real_screen(qapp, g):
    frame = Frame(make_background(300, 200))
    r = g._qt_geometry(frame, 1)
    assert r.width() > 0 and r.height() > 0
    assert g._qt_geometry(frame, 0) == QGuiApplication.primaryScreen().virtualGeometry()
