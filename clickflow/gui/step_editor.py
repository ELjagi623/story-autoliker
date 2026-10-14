"""Editor panel for one Step, plus the small end-condition editor."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ..models import (AFTER_RETRY_ACTIONS, CLICK_TYPES, NOT_FOUND_ACTIONS, Preset, Step, effective_region,
                      effective_template, set_region)
from ..storage import ProfileError, read_image
from .qtutils import bgr_to_pixmap
from .widgets import SafeComboBox, SafeDoubleSpinBox, SafeSpinBox

NOT_FOUND_LABELS = {
    "skip": "Skip this step and continue",
    "retry": "Retry N times",
    "stop": "Stop the run",
    "key": "Press a fallback key and continue",
}
AFTER_RETRY_LABELS = {"stop": "then stop the run", "skip": "then skip the step"}
CLICK_LABELS = {"left": "Left click", "right": "Right click", "double": "Double click"}


class Thumbnail(QLabel):
    def __init__(self, width: int = 260, height: int = 90) -> None:
        super().__init__("(no template captured)")
        self.setMinimumSize(width, height)
        self.setMaximumHeight(height + 10)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("QLabel { background: #202020; color: #aaa; border: 1px solid #555; }")
        self._w, self._h = width, height

    def show_template(self, directory: Optional[Path], rel: str) -> None:
        if not rel or directory is None:
            self.clear()
            self.setText("(no template captured)")
            return
        try:
            img = read_image(Path(directory) / rel)
        except ProfileError:
            self.clear()
            self.setText(f"(missing file: {rel})")
            return
        pix = bgr_to_pixmap(img)
        self.setPixmap(pix.scaled(self._w, self._h, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation))
        self.setToolTip(f"{img.shape[1]} x {img.shape[0]} px - {rel}")


def _dspin(lo: float, hi: float, step: float, decimals: int = 2, suffix: str = "") -> QDoubleSpinBox:
    s = SafeDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(decimals)
    s.setSuffix(suffix)
    s.setKeyboardTracking(True)  # apply while typing, not only after Enter / focus-out
    return s


def _spin(lo: int, hi: int) -> QSpinBox:
    s = SafeSpinBox()
    s.setRange(lo, hi)
    s.setKeyboardTracking(True)  # apply while typing, not only after Enter / focus-out
    return s


class StepEditor(QWidget):
    changed = Signal()
    capture_requested = Signal()
    region_requested = Signal()
    show_boxes_requested = Signal()
    test_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._step: Optional[Step] = None
        self._dir: Optional[Path] = None
        self._preset: Optional[Preset] = None
        self._region_on = False
        self._waits_locked = False
        self._loading = False
        self._build()

    # ------------------------------------------------------------------ UI

    def _build(self) -> None:
        root = QVBoxLayout(self)

        self.name = QLineEdit()
        self.enabled = QCheckBox("Step enabled")
        top = QFormLayout()
        top.addRow("Name", self.name)
        top.addRow("", self.enabled)
        root.addLayout(top)

        tbox = QGroupBox("Template image")
        tl = QVBoxLayout(tbox)
        self.thumb = Thumbnail()
        tl.addWidget(self.thumb)
        row = QHBoxLayout()
        self.btn_capture = QPushButton("Capture template...")
        self.btn_capture.setToolTip("Dims the screen; drag a rectangle around the icon.")
        self.btn_test = QPushButton("Test this step")
        self.btn_test.setToolTip("Look for the icon once and highlight it. Does NOT click.")
        row.addWidget(self.btn_capture)
        row.addWidget(self.btn_test)
        tl.addLayout(row)
        form = QFormLayout()
        self.threshold = _dspin(0.5, 1.0, 0.01)
        self.threshold.setToolTip("Minimum match confidence (0.5 - 1.0). Higher = stricter.")
        form.addRow("Match threshold", self.threshold)
        tl.addLayout(form)
        root.addWidget(tbox)

        sbox = QGroupBox("Search box (where to look) and click")
        sf = QFormLayout(sbox)
        self.region_hint = QLabel()
        self.region_hint.setWordWrap(True)
        sf.addRow(self.region_hint)
        brow = QHBoxLayout()
        self.btn_region = QPushButton("Draw search box...")
        self.btn_region.setToolTip("Drag a rectangle around the area where this icon shows up. It is saved and "
                                   "applied automatically on every run (per display preset).")
        self.btn_clear_region = QPushButton("Clear box")
        self.btn_show_boxes = QPushButton("Show boxes")
        self.btn_show_boxes.setToolTip("Briefly draw the search boxes of all steps on the screen.")
        for b in (self.btn_region, self.btn_clear_region, self.btn_show_boxes):
            brow.addWidget(b)
        sf.addRow(brow)
        rrow = QHBoxLayout()
        self.rx, self.ry = _spin(-20000, 20000), _spin(-20000, 20000)
        self.rw, self.rh = _spin(1, 20000), _spin(1, 20000)
        for lbl, w in (("x", self.rx), ("y", self.ry), ("w", self.rw), ("h", self.rh)):
            rrow.addWidget(QLabel(lbl))
            rrow.addWidget(w)
        sf.addRow(rrow)
        orow = QHBoxLayout()
        self.ox, self.oy = _spin(-5000, 5000), _spin(-5000, 5000)
        orow.addWidget(QLabel("dx"))
        orow.addWidget(self.ox)
        orow.addWidget(QLabel("dy"))
        orow.addWidget(self.oy)
        sf.addRow("Click offset from match centre", orow)
        self.click_type = SafeComboBox()
        for c in CLICK_TYPES:
            self.click_type.addItem(CLICK_LABELS[c], c)
        sf.addRow("Click type", self.click_type)
        self.only_if_found = QCheckBox("Click only if found (silently skip when the icon is absent)")
        self.only_if_found.setToolTip("Use for 'already liked' checks: a missing icon is not an error "
                                      "and no wait-after is spent.")
        sf.addRow(self.only_if_found)
        root.addWidget(sbox)

        wbox = QGroupBox("Timing and failure handling")
        wf = QFormLayout(wbox)
        self.wait_before = _dspin(0, 3600, 0.1, 2, " s")
        self.wait_after = _dspin(0, 3600, 0.1, 2, " s")
        self.timeout = _dspin(0, 3600, 0.5, 2, " s")
        self.timeout.setToolTip("How long to keep looking for the icon. 0 = look exactly once.")
        self.waits_note = QLabel()
        self.waits_note.setWordWrap(True)
        self.waits_note.setStyleSheet("QLabel { color:#7fb8ff; }")
        self.waits_note.setVisible(False)
        wf.addRow(self.waits_note)
        wf.addRow("Wait before", self.wait_before)
        wf.addRow("Wait after", self.wait_after)
        wf.addRow("Find timeout", self.timeout)
        self.not_found = SafeComboBox()
        for a in NOT_FOUND_ACTIONS:
            self.not_found.addItem(NOT_FOUND_LABELS[a], a)
        wf.addRow("If not found", self.not_found)
        rr = QHBoxLayout()
        self.retries = _spin(0, 1000)
        self.after_retries = SafeComboBox()
        for a in AFTER_RETRY_ACTIONS:
            self.after_retries.addItem(AFTER_RETRY_LABELS[a], a)
        rr.addWidget(self.retries)
        rr.addWidget(QLabel("retries,"))
        rr.addWidget(self.after_retries)
        wf.addRow("Retry", rr)
        self.fallback_key = QLineEdit()
        self.fallback_key.setPlaceholderText("e.g. esc, right, ctrl+w")
        wf.addRow("Fallback key", self.fallback_key)
        root.addWidget(wbox)

        abox = QGroupBox("Matching options")
        af = QFormLayout(abox)
        self.multi_scale = QCheckBox("Multi-scale search (tolerates different icon sizes)")
        self.scale_min = _dspin(0.1, 1.0, 0.05)
        self.scale_max = _dspin(1.0, 5.0, 0.05)
        self.grayscale = QCheckBox("Match in grayscale (faster)")
        af.addRow(self.multi_scale)
        sr = QHBoxLayout()
        sr.addWidget(self.scale_min)
        sr.addWidget(QLabel("to"))
        sr.addWidget(self.scale_max)
        af.addRow("Scale range", sr)
        af.addRow(self.grayscale)
        root.addWidget(abox)
        root.addStretch(1)

        for w in (self.name, self.fallback_key):
            w.editingFinished.connect(self._apply)
        for w in (self.enabled, self.only_if_found, self.multi_scale, self.grayscale):
            w.toggled.connect(self._apply)
        for w in (self.threshold, self.rx, self.ry, self.rw, self.rh, self.ox, self.oy, self.wait_before,
                  self.wait_after, self.timeout, self.retries, self.scale_min, self.scale_max):
            w.valueChanged.connect(self._apply)
        for w in (self.click_type, self.not_found, self.after_retries):
            w.currentIndexChanged.connect(self._apply)
        self.btn_capture.clicked.connect(self.capture_requested)
        self.btn_region.clicked.connect(self.region_requested)
        self.btn_clear_region.clicked.connect(self._clear_region)
        self.btn_show_boxes.clicked.connect(self.show_boxes_requested)
        self.btn_test.clicked.connect(self.test_requested)
        self.set_step(None, None)

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
            self.thumb.show_template(directory, effective_template(step, preset))
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
        finally:
            self._loading = False
        self._update_enabled_state()

    def set_waits_locked(self, locked: bool, shown_before: float = 0.0, shown_after: float = 0.0) -> None:
        """Slider mode: the Speed slider decides the waits, so the two fields are greyed out and show what is in force
        (display only - the step's own stored values are left untouched and come back in advanced mode)."""
        self._waits_locked = locked
        self.waits_note.setVisible(locked)
        if locked:
            self.waits_note.setText("Wait times are set by the Speed slider at the top. Tick 'Advanced' there to edit "
                                    "them per step.")
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
        """Hide the template preview while a run is active: the preview is a picture of the very icon being
        searched for, so with a wide scale range the matcher could find *it* on screen and click it."""
        self.thumb.setVisible(visible)

    def refresh_thumbnail(self) -> None:
        if self._step:
            self.thumb.show_template(self._dir, effective_template(self._step, self._preset))

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
        self.retries.setEnabled(action == "retry" and not optional)
        self.after_retries.setEnabled(action == "retry" and not optional)
        self.fallback_key.setEnabled(action == "key" and not optional)
        for w in (self.rx, self.ry, self.rw, self.rh):
            w.setEnabled(self._region_on)
        self.btn_clear_region.setEnabled(self._region_on)
        where = f" (preset '{self._preset.name}')" if self._preset else ""
        if self._region_on:
            self.region_hint.setText(f"Search box set{where}: only this area is scanned on every run.")
            self.region_hint.setStyleSheet("QLabel { color:#3fb950; }")
        else:
            self.region_hint.setText(f"No search box{where}: the WHOLE screen is scanned - slow on big or multiple "
                                     "monitors, and it can pick look-alikes or miss. Draw a box around the area "
                                     "where this icon appears.")
            self.region_hint.setStyleSheet("QLabel { color:#e6b422; }")
        multi = self.multi_scale.isChecked()
        self.scale_min.setEnabled(multi)
        self.scale_max.setEnabled(multi)

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
        self._update_enabled_state()
        self.changed.emit()


class EndConditionEditor(QGroupBox):
    """Edits Profile.end_condition (a Step used only for its template/threshold/region)."""

    changed = Signal()
    capture_requested = Signal()
    region_requested = Signal()

    def __init__(self) -> None:
        super().__init__("End condition - stop the run when this image appears")
        self._step: Optional[Step] = None
        self._dir: Optional[Path] = None
        self._preset: Optional[Preset] = None
        self._loading = False
        lay = QVBoxLayout(self)
        self.enabled = QCheckBox("Enable end condition")
        self.thumb = Thumbnail(260, 70)
        row = QHBoxLayout()
        self.btn_capture = QPushButton("Capture template...")
        self.btn_region = QPushButton("Draw search box...")
        self.btn_clear_region = QPushButton("Clear region")
        for b in (self.btn_capture, self.btn_region, self.btn_clear_region):
            row.addWidget(b)
        self.threshold = _dspin(0.5, 1.0, 0.01)
        self.region_label = QLabel("Region: whole screen")
        form = QFormLayout()
        form.addRow("Match threshold", self.threshold)
        lay.addWidget(self.enabled)
        lay.addWidget(self.thumb)
        lay.addLayout(row)
        lay.addLayout(form)
        lay.addWidget(self.region_label)
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
            self.thumb.show_template(directory, effective_template(step, preset) if step else "")
            r = effective_region(step, preset) if step else None
            self.region_label.setText(f"Search box: x={r[0]} y={r[1]} w={r[2]} h={r[3]}" if r
                                      else "Search box: none (whole screen)")
        finally:
            self._loading = False

    def set_previews_visible(self, visible: bool) -> None:
        self.thumb.setVisible(visible)

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
