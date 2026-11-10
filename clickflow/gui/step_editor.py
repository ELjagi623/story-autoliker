"""Editor panel for one Step (simple view / advanced view), plus the small end-condition editor.

One widget tree serves both modes: ``set_advanced(False)`` shows only what a newcomer needs (name, target image,
click type, "only if found"); ``set_advanced(True)`` unfolds every setting in collapsible groups. All controls keep
the same attribute names in both modes, so the data binding below does not care which one is on screen.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QHBoxLayout, QLineEdit, QSpinBox, QVBoxLayout, QWidget

from ..models import (AFTER_RETRY_ACTIONS, CLICK_TYPES, NOT_FOUND_ACTIONS, Preset, Step, effective_region,
                      effective_template, set_region)
from ..storage import ProfileError, read_image
from .i18n import tr
from .qtutils import bgr_to_pixmap
from .widgets import (Alert, Group, HatchedThumb, Segmented, SafeComboBox, SafeDoubleSpinBox, SafeSpinBox, Switch,
                      SwitchRow, ThresholdSlider, Thumbnail, button, field, label)


def not_found_labels() -> dict[str, str]:
    return {"skip": tr("Skip and continue"), "retry": tr("Retry N times"), "stop": tr("Stop the run"),
            "key": tr("Press a fallback key")}


def after_retry_labels() -> dict[str, str]:
    return {"stop": tr("then stop the run"), "skip": tr("then skip the step")}


def click_labels() -> dict[str, str]:
    return {"left": tr("Left"), "right": tr("Right"), "double": tr("Double")}


def load_thumbnail(thumb: Thumbnail, directory: Optional[Path], rel: str) -> None:
    """Show the template ``rel`` (relative to the profile folder) on ``thumb``."""
    if not rel or directory is None:
        thumb.show_pixmap(None)
        thumb.setToolTip("")
        return
    try:
        img = read_image(Path(directory) / rel)
    except ProfileError:
        thumb.show_pixmap(None, tr("missing file"))
        thumb.setToolTip(rel)
        return
    thumb.show_pixmap(bgr_to_pixmap(img))
    thumb.setToolTip(f"{img.shape[1]} x {img.shape[0]} px - {rel}")


def _dspin(lo: float, hi: float, step: float, decimals: int = 2, suffix: str = "") -> QDoubleSpinBox:
    s = SafeDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(decimals)
    s.setSuffix(suffix)
    s.setKeyboardTracking(True)  # apply while typing, not only after Enter / focus-out
    return s


def _spin(lo: int, hi: int, suffix: str = "") -> QSpinBox:
    s = SafeSpinBox()
    s.setRange(lo, hi)
    s.setSuffix(suffix)
    s.setKeyboardTracking(True)  # apply while typing, not only after Enter / focus-out
    return s


def _row(*items, spacing: int = 12, stretch: bool = True) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    for it in items:
        if it is None:
            lay.addStretch(1)
        else:
            lay.addWidget(it, 1 if stretch else 0)
    return lay


def _detach(w: QWidget) -> None:
    """Take ``w`` out of whatever layout holds it so it can be added to another one."""
    p = w.parentWidget()
    if p is not None and p.layout() is not None:
        p.layout().removeWidget(w)


class StepEditor(QWidget):
    changed = Signal()
    capture_requested = Signal()
    region_requested = Signal()
    show_boxes_requested = Signal()
    test_requested = Signal()
    guard_capture_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._step: Optional[Step] = None
        self._dir: Optional[Path] = None
        self._preset: Optional[Preset] = None
        self._region_on = False
        self._waits_locked = False
        self._loading = False
        self._advanced = False
        self._build()

    # ------------------------------------------------------------------ UI

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        # ---- basic: name, target image, buttons
        self.enabled = Switch()
        self.enabled_box = QWidget()
        eb = QHBoxLayout(self.enabled_box)
        eb.setContentsMargins(0, 0, 4, 0)
        eb.setSpacing(8)
        self.enabled_lbl = label(tr("Enabled"), "muted")
        eb.addWidget(self.enabled_lbl)
        eb.addWidget(self.enabled)
        self.grp_basic = Group(tr("Step details"), True, self.enabled_box)
        self.name = QLineEdit()
        self.name_field = field(tr("Name"), self.name)
        self.grp_basic.add(self.name_field)

        self.thumb = Thumbnail(120, 80)
        self.thumb_hidden = HatchedThumb(120, 80)
        self.thumb_hidden.setVisible(False)
        self.btn_capture = button(tr("Re-select"), "select", tip=tr("Dims the screen; drag a rectangle around the target."))
        self.btn_test = button(tr("Test this step"), "test", tip=tr("Look for the target once and highlight it. Does NOT click."))
        self.target_caption = label(tr("Target image"), "field")
        tcol = QVBoxLayout()
        tcol.setContentsMargins(0, 0, 0, 0)
        tcol.setSpacing(6)
        tcol.addWidget(self.target_caption)
        tbox = QHBoxLayout()
        tbox.setSpacing(12)
        tbox.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignTop)
        tbox.addWidget(self.thumb_hidden, 0, Qt.AlignmentFlag.AlignTop)
        side = QVBoxLayout()
        self._side = side
        side.setSpacing(10)
        brow = QHBoxLayout()
        brow.setSpacing(8)
        brow.addWidget(self.btn_capture)
        brow.addWidget(self.btn_test)
        brow.addStretch(1)
        side.addLayout(brow)
        self.region_alert = Alert("", "wn", tr("Set up"))
        self.region_hint = self.region_alert.label  # (kept name) the status text
        self.region_alert.action.clicked.connect(self.region_requested)
        side.addWidget(self.region_alert)
        side.addStretch(1)
        tbox.addLayout(side, 1)
        tcol.addLayout(tbox)
        self._target_block = QWidget()
        self._target_block.setLayout(tcol)
        self.grp_basic.add(self._target_block)
        root.addWidget(self.grp_basic)

        # ---- click type + only-if-found (lives in the basic card in simple mode, in "Click" in advanced mode)
        self.click_type = Segmented()
        labels = click_labels()
        for c in CLICK_TYPES:
            self.click_type.addItem(labels[c], c)
        self.click_field = field(tr("Click type"), self.click_type)
        self.only_row = SwitchRow(tr("Click only if found"), tr("Silently skip when the target is absent"))
        self.only_if_found = self.only_row.switch
        self.only_if_found.setToolTip(tr("Use for 'already liked' checks: a missing target is not an error "
                                         "and no wait-after is spent."))
        self.click_block = QWidget()
        cb = QHBoxLayout(self.click_block)
        cb.setContentsMargins(0, 0, 0, 0)
        cb.setSpacing(24)
        cb.addWidget(self.click_field, 5)
        cb.addWidget(self.only_row, 6, Qt.AlignmentFlag.AlignBottom)
        self.grp_basic.add(self.click_block)

        # ---- advanced groups
        self.grp_match = Group(tr("Match"), True)
        self.threshold = ThresholdSlider(tr("Match strictness"))
        self.threshold.setToolTip(tr("Minimum match confidence (0.50 - 1.00). Higher = stricter."))
        self.grp_match.add(self.threshold)
        self.multi_scale = Switch()
        self.multi_scale.setToolTip(tr("Tolerates a different on-screen size than the captured image."))
        self.scale_min = _dspin(0.1, 1.0, 0.05)
        self.scale_max = _dspin(1.0, 5.0, 0.05)
        self.scale_lbl = label(tr("Resize range"), "muted")
        ms = QHBoxLayout()
        ms.setSpacing(10)
        ms_title = label(tr("Auto-resize matching"))
        ms_title.setStyleSheet("font-weight: 600;")
        ms.addWidget(self.multi_scale)
        ms.addWidget(ms_title)
        ms.addStretch(1)
        ms.addWidget(self.scale_lbl)
        ms.addWidget(self.scale_min)
        ms.addWidget(label("-", "hint"))
        ms.addWidget(self.scale_max)
        self.grp_match.add(ms)
        self.grayscale_row = SwitchRow(tr("Grayscale (faster)"))
        self.grayscale = self.grayscale_row.switch
        self.grp_match.add(self.grayscale_row)
        self.outline_row = SwitchRow(tr("Outline / transparent icon"),
                                     tr("Ignore the background showing through the icon (e.g. an outline heart)"))
        self.ignore_background = self.outline_row.switch
        self.ignore_background.setToolTip(tr("Compares only the icon's own lines. Use it for see-through icons drawn "
                                             "over photos or videos, which otherwise fail on busy backgrounds."))
        self.grp_match.add(self.outline_row)
        root.addWidget(self.grp_match)

        self.grp_area = Group(tr("Search area"), True)
        self.btn_region = button(tr("Draw"), "select", tip=tr("Drag a rectangle around the area where the target shows up. "
                                                              "It is saved and applied on every run (per display preset)."))
        self.btn_clear_region = button(tr("Clear"))
        self.btn_show_boxes = button(tr("Show boxes"), "eye", tip=tr("Briefly draw the search areas of all steps on the screen."))
        self.area_btn_row = QWidget()
        ab = QHBoxLayout(self.area_btn_row)
        ab.setContentsMargins(0, 0, 0, 0)
        ab.setSpacing(8)
        for b in (self.btn_region, self.btn_clear_region, self.btn_show_boxes):
            ab.addWidget(b)
        ab.addStretch(1)
        self.grp_area.add(self.area_btn_row)
        self.rx, self.ry = _spin(-20000, 20000), _spin(-20000, 20000)
        self.rw, self.rh = _spin(1, 20000), _spin(1, 20000)
        self.grp_area.add(_row(field("x", self.rx), field("y", self.ry), field(tr("Width"), self.rw),
                               field(tr("Height"), self.rh)))
        root.addWidget(self.grp_area)

        self.grp_click = Group(tr("Click"), True)
        self.ox, self.oy = _spin(-5000, 5000, " px"), _spin(-5000, 5000, " px")
        self.offset_row = QWidget()
        orow = _row(field(tr("Click offset dx"), self.ox), field("dy", self.oy))
        self.offset_row.setLayout(orow)
        self.grp_click.add(self.offset_row)
        root.addWidget(self.grp_click)

        self.grp_wait = Group(tr("Waits & failure handling"), True)
        self.waits_note = Alert("", "info")
        self.grp_wait.add(self.waits_note)
        self.chk_manual = QCheckBox(tr("Advanced: edit waits manually"))
        self.chk_manual.setToolTip(tr("Untick = the Speed setting controls the timing of every step. Tick = each step uses "
                                      "its own 'Wait before / Wait after' and Speed is ignored."))
        self.grp_wait.add(self.chk_manual)
        self.wait_before = _dspin(0, 3600, 0.1, 2, " s")
        self.wait_after = _dspin(0, 3600, 0.1, 2, " s")
        self.timeout = _dspin(0, 3600, 0.5, 2, " s")
        self.timeout.setToolTip(tr("How long to keep looking for the target. 0 = look exactly once."))
        self.grp_wait.add(_row(field(tr("Wait before"), self.wait_before), field(tr("Wait after"), self.wait_after),
                               field(tr("Find timeout"), self.timeout)))
        self.not_found = SafeComboBox()
        for a, text in not_found_labels().items():
            if a in NOT_FOUND_ACTIONS:
                self.not_found.addItem(text, a)
        self.retries = _spin(0, 1000)
        self.after_retries = SafeComboBox()
        for a, text in after_retry_labels().items():
            if a in AFTER_RETRY_ACTIONS:
                self.after_retries.addItem(text, a)
        self.fallback_key = QLineEdit()
        self.fallback_key.setPlaceholderText(tr("e.g. esc, right, ctrl+w"))
        self.nf_field = field(tr("If not found"), self.not_found)
        self.grp_wait.add(self.nf_field)
        self.grp_wait.add(_row(field(tr("Retry"), self.retries), field(tr("After the last retry"), self.after_retries),
                               field(tr("Fallback key"), self.fallback_key)))
        self.rescue_row = SwitchRow(tr("Look again where it was last found"),
                                    tr("If not found: search right there once more, a little less strictly"))
        self.rescue_near_last = self.rescue_row.switch
        self.grp_wait.add(self.rescue_row)
        self.blind_row = SwitchRow(tr("If still not found, click where it was last found"),
                                   tr("At most {n} times in a row, and only shortly after a real match", n=3))
        self.fallback_click_last = self.blind_row.switch
        self.grp_wait.add(self.blind_row)
        self.guard_thumb = Thumbnail(72, 48)
        self.btn_guard = button(tr("Capture"), "select", tip=tr("Drag a rectangle around the image that means 'already "
                                                               "done', e.g. the red (liked) heart."))
        self.btn_clear_guard = button(tr("Clear"))
        self.guard_threshold = _dspin(0.5, 1.0, 0.01)
        self.guard_threshold.setToolTip(tr("How closely the screen must match the 'skip if present' image."))
        gcol = QVBoxLayout()
        gcol.setContentsMargins(0, 0, 0, 0)
        gcol.setSpacing(6)
        gcol.addWidget(label(tr("Skip if this image is there"), "field"))
        grow = QHBoxLayout()
        grow.setSpacing(8)
        grow.addWidget(self.guard_thumb, 0, Qt.AlignmentFlag.AlignTop)
        grow.addWidget(self.btn_guard)
        grow.addWidget(self.btn_clear_guard)
        grow.addWidget(field(tr("Strictness"), self.guard_threshold))
        grow.addStretch(1)
        gcol.addLayout(grow)
        self.guard_block = QWidget()
        self.guard_block.setLayout(gcol)
        self.guard_block.setToolTip(tr("Checked before any fallback click: when this image is near the last position, "
                                       "the step is skipped. For likes, capture the red (already liked) heart."))
        self.grp_wait.add(self.guard_block)
        self.guard_alert = Alert(tr("Without a 'skip if present' image, a blind click can undo something already done "
                                    "(e.g. unlike a liked story)."), "wn")
        self.grp_wait.add(self.guard_alert)
        root.addWidget(self.grp_wait)
        root.addStretch(1)

        for w in (self.name, self.fallback_key):
            w.editingFinished.connect(self._apply)
        for w in (self.enabled, self.only_if_found, self.multi_scale, self.grayscale, self.ignore_background,
                  self.rescue_near_last, self.fallback_click_last):
            w.toggled.connect(self._apply)
        for w in (self.threshold, self.rx, self.ry, self.rw, self.rh, self.ox, self.oy, self.wait_before,
                  self.wait_after, self.timeout, self.retries, self.scale_min, self.scale_max, self.guard_threshold):
            w.valueChanged.connect(self._apply)
        for w in (self.click_type, self.not_found, self.after_retries):
            w.currentIndexChanged.connect(self._apply)
        self.btn_capture.clicked.connect(self.capture_requested)
        self.btn_region.clicked.connect(self.region_requested)
        self.btn_clear_region.clicked.connect(self._clear_region)
        self.btn_show_boxes.clicked.connect(self.show_boxes_requested)
        self.btn_test.clicked.connect(self.test_requested)
        self.btn_guard.clicked.connect(self.guard_capture_requested)
        self.btn_clear_guard.clicked.connect(self._clear_guard)
        self.set_advanced(False)
        self.set_step(None, None)

    # ------------------------------------------------------------------ simple / advanced

    def is_advanced(self) -> bool:
        return self._advanced

    def set_advanced(self, adv: bool) -> None:
        self._advanced = adv
        # shared pieces move between the basic card (simple) and their advanced groups
        for lay in (self.grp_basic.body_lay, self.grp_click.body_lay, self.grp_area.body_lay, self._side):
            lay.removeWidget(self.click_block)
            lay.removeWidget(self.region_alert)
        if adv:
            self.grp_click.body_lay.insertWidget(0, self.click_block)
            self.grp_area.body_lay.insertWidget(0, self.region_alert)
        else:
            self.grp_basic.body_lay.addWidget(self.click_block)
            self._side.insertWidget(1, self.region_alert)
        self.grp_basic.set_title(tr("Basic") if adv else tr("Step details"))
        self.enabled_box.setVisible(adv)
        self.region_alert.show()
        self.click_block.show()
        for g in (self.grp_match, self.grp_area, self.grp_click, self.grp_wait):
            g.setVisible(adv)
        self.offset_row.setVisible(adv)
        self.name_field.setVisible(True)
        self._update_enabled_state()

    # ------------------------------------------------------------------ binding

    def set_step(self, step: Optional[Step], directory: Optional[Path], preset: Optional[Preset] = None) -> None:
        self._step, self._dir, self._preset = step, directory, preset
        self.setEnabled(step is not None)
        if step is None:
            return
        self._loading = True
        try:
            self.name.setText(step.name)
            self.enabled.setChecked(step.enabled)
            load_thumbnail(self.thumb, directory, effective_template(step, preset))
            self.threshold.setValue(step.threshold)
            region = effective_region(step, preset)
            self._region_on = region is not None
            r = region or (0, 0, 100, 100)
            self.rx.setValue(r[0]), self.ry.setValue(r[1]), self.rw.setValue(r[2]), self.rh.setValue(r[3])
            self.ox.setValue(step.offset_x)
            self.oy.setValue(step.offset_y)
            self.click_type.setCurrentIndex(max(0, self.click_type.findData(step.click_type)))
            self.only_if_found.setChecked(step.click_only_if_found)
            self.wait_before.setValue(step.wait_before)
            self.wait_after.setValue(step.wait_after)
            self.timeout.setValue(step.timeout)
            self.not_found.setCurrentIndex(max(0, self.not_found.findData(step.not_found_action)))
            self.retries.setValue(step.retries)
            self.after_retries.setCurrentIndex(max(0, self.after_retries.findData(step.after_retries)))
            self.fallback_key.setText(step.fallback_key)
            self.multi_scale.setChecked(step.multi_scale)
            self.scale_min.setValue(step.scale_min)
            self.scale_max.setValue(step.scale_max)
            self.grayscale.setChecked(step.grayscale)
            self.ignore_background.setChecked(step.ignore_background)
            self.rescue_near_last.setChecked(step.rescue_near_last)
            self.fallback_click_last.setChecked(step.fallback_click_last)
            self.guard_threshold.setValue(step.guard_threshold)
            load_thumbnail(self.guard_thumb, directory, step.guard_template)
        finally:
            self._loading = False
        self._update_enabled_state()

    def refresh_guard(self) -> None:
        """Re-read the step's guard image (after a capture) and update the warning."""
        if self._step:
            load_thumbnail(self.guard_thumb, self._dir, self._step.guard_template)
            self._update_enabled_state()

    def _clear_guard(self) -> None:
        if self._step is None:
            return
        self._step.guard_template = ""
        self.refresh_guard()
        self.changed.emit()

    def set_waits_locked(self, locked: bool, shown_before: float = 0.0, shown_after: float = 0.0) -> None:
        """Slider mode: the Speed setting decides the waits, so the two fields are greyed out and show what is in force
        (display only - the step's own stored values are left untouched and come back in advanced mode)."""
        self._waits_locked = locked
        self.waits_note.setVisible(locked)
        if locked:
            self.waits_note.set_text(tr("Speed is on Auto: before/after waits are set by Speed (fixed {s:g} s).",
                                        s=shown_before))
        for w in (self.wait_before, self.wait_after):
            w.setEnabled(not locked)
        if locked:
            self._loading = True
            try:
                self.wait_before.setValue(shown_before)
                self.wait_after.setValue(shown_after)
            finally:
                self._loading = False
        elif self._step is not None:
            self._loading = True
            try:
                self.wait_before.setValue(self._step.wait_before)
                self.wait_after.setValue(self._step.wait_after)
            finally:
                self._loading = False

    def set_previews_visible(self, visible: bool) -> None:
        """Hide the target preview while a run is active: the preview is a picture of the very target being
        searched for, so with a wide scale range the matcher could find *it* on screen and click it."""
        self.thumb.setVisible(visible)
        self.thumb_hidden.setVisible(not visible)
        self.guard_thumb.setVisible(visible)

    def refresh_thumbnail(self) -> None:
        if self._step:
            load_thumbnail(self.thumb, self._dir, effective_template(self._step, self._preset))

    def refresh_region(self) -> None:
        if self._step:
            self.set_step(self._step, self._dir, self._preset)

    def set_region_values(self, region: Optional[tuple[int, int, int, int]]) -> None:
        """Set (or clear, with None) this step's search box programmatically and save it into the model."""
        if self._step is None:
            return
        self._loading = True
        try:
            self._region_on = region is not None
            r = region or (0, 0, 100, 100)
            self.rx.setValue(r[0]), self.ry.setValue(r[1]), self.rw.setValue(r[2]), self.rh.setValue(r[3])
        finally:
            self._loading = False
        self._apply()

    def _clear_region(self) -> None:
        self.set_region_values(None)

    def _update_enabled_state(self) -> None:
        action = self.not_found.currentData()
        optional = self.only_if_found.isChecked()
        self.not_found.setEnabled(not optional)
        self.nf_field.setEnabled(not optional)
        self.retries.setEnabled(action == "retry" and not optional)
        self.after_retries.setEnabled(action == "retry" and not optional)
        self.fallback_key.setEnabled(action == "key" and not optional)
        for w in (self.rx, self.ry, self.rw, self.rh):
            w.setEnabled(self._region_on)
        self.btn_clear_region.setEnabled(self._region_on)
        where = f" ({self._preset.name})" if self._preset else ""
        if self._region_on:
            self.region_alert.set_tone("ok")
            self.region_alert.set_text(tr("Search area set{where}: only this area is scanned, so it is faster.", where=where))
            self.region_alert.action.setVisible(False)
            self.grp_area.set_tag(tr("Set"), "ok")
        else:
            self.region_alert.set_tone("wn")
            self.region_alert.set_text(tr("No search area{where}: the whole screen is scanned, which is slower and can pick "
                                          "look-alikes.", where=where))
            self.region_alert.action.setVisible(True)
            self.grp_area.set_tag(tr("Not set"), "wn")
        has_guard = bool(self._step and self._step.guard_template)
        self.btn_clear_guard.setEnabled(has_guard)
        self.guard_threshold.setEnabled(has_guard)
        self.guard_alert.setVisible(self.fallback_click_last.isChecked() and not has_guard)
        multi = self.multi_scale.isChecked()
        self.scale_min.setEnabled(multi)
        self.scale_max.setEnabled(multi)
        self.scale_lbl.setEnabled(multi)

    def commit(self) -> None:
        """Read every field into the step now (used before saving; does not depend on focus events)."""
        self._apply()

    def _apply(self, *_args) -> None:
        s = self._step
        if s is None or self._loading:
            return
        s.name = self.name.text().strip() or "Step"
        s.enabled = self.enabled.isChecked()
        s.threshold = self.threshold.value()
        set_region(s, self._preset,
                   (self.rx.value(), self.ry.value(), self.rw.value(), self.rh.value()) if self._region_on else None)
        s.offset_x, s.offset_y = self.ox.value(), self.oy.value()
        s.click_type = self.click_type.currentData()
        s.click_only_if_found = self.only_if_found.isChecked()
        if not self._waits_locked:  # in slider mode the (display-only) fields must not overwrite the stored waits
            s.wait_before, s.wait_after = self.wait_before.value(), self.wait_after.value()
        s.timeout = self.timeout.value()
        s.not_found_action = self.not_found.currentData()
        s.retries = self.retries.value()
        s.after_retries = self.after_retries.currentData()
        s.fallback_key = self.fallback_key.text().strip()
        s.multi_scale = self.multi_scale.isChecked()
        s.scale_min, s.scale_max = self.scale_min.value(), self.scale_max.value()
        s.grayscale = self.grayscale.isChecked()
        s.ignore_background = self.ignore_background.isChecked()
        s.rescue_near_last = self.rescue_near_last.isChecked()
        s.fallback_click_last = self.fallback_click_last.isChecked()
        s.guard_threshold = self.guard_threshold.value()
        self._update_enabled_state()
        self.changed.emit()


class EndConditionEditor(Group):
    """Edits Profile.end_condition (a Step used only for its target image / strictness / search area)."""

    changed = Signal()
    capture_requested = Signal()
    region_requested = Signal()

    def __init__(self) -> None:
        enabled = Switch()
        super().__init__(tr("End condition"), True, enabled)
        self.enabled = enabled
        self.head_btn.setToolTip(tr("Stop the run as soon as this image is seen."))
        self._step: Optional[Step] = None
        self._dir: Optional[Path] = None
        self._preset: Optional[Preset] = None
        self._loading = False
        self.subtitle = label(tr("Stop as soon as this image is seen"), "hint")
        self.add(self.subtitle)
        self.thumb = Thumbnail(104, 72)
        self.btn_capture = button(tr("Re-select"), "select")
        self.btn_region = button(tr("Draw search area"), "select")
        self.btn_clear_region = button(tr("Clear"))
        col = QVBoxLayout()
        col.setSpacing(8)
        r1 = QHBoxLayout()
        r1.setSpacing(8)
        r1.addWidget(self.btn_capture)
        r1.addWidget(self.btn_region)
        r1.addWidget(self.btn_clear_region)
        r1.addStretch(1)
        col.addLayout(r1)
        self.region_label = label(tr("Search area: whole screen"), "hint")
        col.addWidget(self.region_label)
        col.addStretch(1)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignTop)
        self.thumb_hidden = HatchedThumb(104, 72)
        self.thumb_hidden.setVisible(False)
        row.addWidget(self.thumb_hidden, 0, Qt.AlignmentFlag.AlignTop)
        row.addLayout(col, 1)
        self.add(row)
        self.threshold = ThresholdSlider(tr("Match strictness"))
        self.add(self.threshold)
        self.enabled.toggled.connect(self._apply)
        self.threshold.valueChanged.connect(self._apply)
        self.btn_capture.clicked.connect(self.capture_requested)
        self.btn_region.clicked.connect(self.region_requested)
        self.btn_clear_region.clicked.connect(self._clear_region)
        self.set_step(None, None)

    def set_step(self, step: Optional[Step], directory: Optional[Path], preset: Optional[Preset] = None) -> None:
        self._step, self._dir, self._preset = step, directory, preset
        self._loading = True
        try:
            self.enabled.setChecked(bool(step and step.enabled))
            self.threshold.setValue(step.threshold if step else 0.85)
            load_thumbnail(self.thumb, directory, effective_template(step, preset) if step else "")
            r = effective_region(step, preset) if step else None
            self.region_label.setText(tr("Search area: x={x} y={y} w={w} h={h}", x=r[0], y=r[1], w=r[2], h=r[3]) if r
                                      else tr("Search area: whole screen"))
            self.btn_clear_region.setEnabled(r is not None)
        finally:
            self._loading = False

    def set_previews_visible(self, visible: bool) -> None:
        self.thumb.setVisible(visible)
        self.thumb_hidden.setVisible(not visible)

    def _clear_region(self) -> None:
        if self._step is not None:
            set_region(self._step, self._preset, None)
            self.set_step(self._step, self._dir, self._preset)
            self.changed.emit()

    def commit(self) -> None:
        self._apply()

    def _apply(self, *_a) -> None:
        if self._step is None or self._loading:
            return
        self._step.enabled = self.enabled.isChecked()
        self._step.threshold = self.threshold.value()
        self.changed.emit()
