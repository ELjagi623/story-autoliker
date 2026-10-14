"""The ClickFlow main window."""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QGuiApplication, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QSplitter, QTabWidget, QToolBar, QVBoxLayout, QWidget,
)

from .. import platform_utils, storage
from .. import presets as presets_mod
from ..hotkey import HotkeyListener, parse_hotkey
from ..keystate import StopKeyWatcher
from ..inputs import NullInput, PyAutoGuiInput
from ..models import (FAST_WAIT, SLOW_INTERVAL, Preset, Profile, Step, click_interval, display_interval,
                      effective_region, effective_template, set_region)
from ..runner import Event, Hit, RunResult, Runner
from ..screen import MonitorInfo, MssScreen
from .overlays import CaptureOverlay, Highlighter, StopBadge
from .step_editor import EndConditionEditor, StepEditor
from .widgets import SafeComboBox, SafeDoubleSpinBox, SafeSlider, SafeSpinBox
from .worker import CallThread, RunThread

log = logging.getLogger("clickflow")

LEVEL_COLORS = {"info": "#d4d4d4", "warn": "#e6b422", "error": "#ff6b6b"}
KIND_COLORS = {"click": "#6cd97e", "match": "#7fb8ff", "start": "#ffffff", "finished": "#ffffff", "loop": "#9a9a9a"}


class MainWindow(QMainWindow):
    stop_hotkey_pressed = Signal()

    def __init__(self, profile: Optional[Profile] = None, *, start_hotkey: bool = True) -> None:
        super().__init__()
        self.setWindowTitle("ClickFlow")
        self._fit_to_screen()
        self.profile = profile or Profile(name="Untitled")
        self.dirty = False
        self._run_thread: Optional[RunThread] = None
        self._call_thread: Optional[CallThread] = None
        self._overlay: Optional[CaptureOverlay] = None
        self._was_minimized_for_run = False
        self.highlighter = Highlighter()
        self.stop_badge = StopBadge()
        self.stop_badge.clicked.connect(self.stop_run)
        self._building = False
        self._monitors: list[MonitorInfo] = []

        self._build_ui()
        self._build_actions()
        self.stop_hotkey_pressed.connect(self.stop_run)
        self.hotkey = HotkeyListener(self.profile.settings.stop_hotkey or "F8", self.stop_hotkey_pressed.emit)
        self.key_watcher = StopKeyWatcher(self.profile.settings.stop_hotkey or "F8", self.stop_hotkey_pressed.emit)
        self._hotkey_enabled = start_hotkey
        self.load_into_ui(self.profile)
        self._set_running(False)

    # ================================================================== window size

    @staticmethod
    def initial_size(available_width: int, available_height: int) -> tuple[int, int]:
        """Preferred window size that always fits the screen it opens on (laptops of 1366x768 and smaller)."""
        return (min(1180, int(available_width * 0.95)), min(820, int(available_height * 0.92)))

    def _fit_to_screen(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1180, 820)
            return
        avail = screen.availableGeometry()
        w, h = self.initial_size(avail.width(), avail.height())
        self.resize(w, h)
        self.move(avail.x() + max(0, (avail.width() - w) // 2), avail.y() + max(0, (avail.height() - h) // 3))

    # ================================================================== UI construction

    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet("QLabel { background:#fff3c4; color:#4a3b00; border:1px solid #d9b92e; padding:6px; }")
        self.banner.setVisible(False)
        outer.addWidget(self.banner)
        outer.addWidget(self._build_preset_bar())
        outer.addWidget(self._build_speed_bar())

        vsplit = QSplitter(Qt.Orientation.Vertical)
        hsplit = QSplitter(Qt.Orientation.Horizontal)

        # ---- left: step list
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Steps (tick = enabled, drag to reorder)"))
        self.step_list = QListWidget()
        self.step_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.step_list.currentRowChanged.connect(self._on_row_changed)
        self.step_list.itemChanged.connect(self._on_item_changed)
        self.step_list.model().rowsMoved.connect(self._on_rows_moved)
        ll.addWidget(self.step_list, 1)
        row1, row2 = QHBoxLayout(), QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_del = QPushButton("Delete")
        self.btn_dup = QPushButton("Duplicate")
        self.btn_up = QPushButton("Up")
        self.btn_down = QPushButton("Down")
        for b in (self.btn_add, self.btn_del, self.btn_dup):
            row1.addWidget(b)
        for b in (self.btn_up, self.btn_down):
            row2.addWidget(b)
        ll.addLayout(row1)
        ll.addLayout(row2)
        self.btn_add.clicked.connect(self.add_step)
        self.btn_del.clicked.connect(self.delete_step)
        self.btn_dup.clicked.connect(self.duplicate_step)
        self.btn_up.clicked.connect(lambda: self.move_step(-1))
        self.btn_down.clicked.connect(lambda: self.move_step(1))
        hsplit.addWidget(left)

        # ---- right: tabs
        self.tabs = QTabWidget()
        self.step_editor = StepEditor()
        self.step_editor.changed.connect(self._on_step_edited)
        self.step_editor.capture_requested.connect(self.capture_step_template)
        self.step_editor.region_requested.connect(self.pick_step_region)
        self.step_editor.show_boxes_requested.connect(self.show_search_boxes)
        self.step_editor.test_requested.connect(self.test_step)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(self.step_editor)
        self.tabs.addTab(sa, "Step")
        settings_scroll = QScrollArea()  # scrollable, so the window can shrink to small laptop screens
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setWidget(self._build_settings_tab())
        self.tabs.addTab(settings_scroll, "Global settings")
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Notes about this profile...")
        self.notes.textChanged.connect(self._on_notes_changed)
        self.tabs.addTab(self.notes, "Notes")
        hsplit.addWidget(self.tabs)
        hsplit.setStretchFactor(0, 1)
        hsplit.setStretchFactor(1, 2)
        vsplit.addWidget(hsplit)

        # ---- bottom: log
        logbox = QWidget()
        lb = QVBoxLayout(logbox)
        lb.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.addWidget(QLabel("Live log"))
        head.addStretch(1)
        clear = QPushButton("Clear")
        clear.clicked.connect(lambda: self.log_view.clear())
        head.addWidget(clear)
        lb.addLayout(head)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(3000)
        self.log_view.setStyleSheet("QPlainTextEdit { background:#1e1e1e; font-family: Consolas, Menlo, monospace; }")
        lb.addWidget(self.log_view)
        vsplit.addWidget(logbox)
        vsplit.setStretchFactor(0, 3)
        vsplit.setStretchFactor(1, 1)
        outer.addWidget(vsplit, 1)
        self.setCentralWidget(central)
        self.status_label = QLabel()
        self.statusBar().addWidget(self.status_label, 1)

    def _build_preset_bar(self) -> QWidget:
        self.preset_bar = QWidget()
        col = QVBoxLayout(self.preset_bar)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        row = QHBoxLayout()
        row.addWidget(QLabel("Display preset:"))
        self.preset_combo = SafeComboBox()
        self.preset_combo.setMinimumWidth(240)
        self.preset_combo.setToolTip("A preset stores the search boxes (and optionally template images) for one "
                                     "display resolution. Edits you make while a preset is selected go into that preset.")
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        self.btn_preset_new = QPushButton("New preset...")
        self.btn_preset_rename = QPushButton("Rename...")
        self.btn_preset_delete = QPushButton("Delete preset")
        self.chk_auto_preset = QCheckBox("Auto-switch preset / monitor by detected resolution")
        self.chk_auto_preset.setToolTip("At the start of a run, ClickFlow detects the connected monitors and picks "
                                        "the preset whose resolution matches (and the monitor it applies to).")
        self.chk_auto_preset.toggled.connect(self._apply_settings)
        for w in (self.preset_combo, self.btn_preset_new, self.btn_preset_rename, self.btn_preset_delete):
            row.addWidget(w)
        row.addWidget(self.chk_auto_preset)
        row.addStretch(1)
        self.btn_preset_new.clicked.connect(self.new_preset)
        self.btn_preset_rename.clicked.connect(self.rename_preset)
        self.btn_preset_delete.clicked.connect(self.delete_preset)
        col.addLayout(row)
        row2 = QHBoxLayout()
        self.lbl_displays = QLabel()
        self.lbl_displays.setWordWrap(True)
        self.btn_detect = QPushButton("Detect displays")
        self.btn_detect.clicked.connect(self._refresh_displays_label)
        row2.addWidget(self.lbl_displays, 1)
        row2.addWidget(self.btn_detect)
        col.addLayout(row2)
        return self.preset_bar

    def _build_speed_bar(self) -> QWidget:
        self.speed_bar = QWidget()
        row = QHBoxLayout(self.speed_bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel("Speed:"))
        self.lbl_slow = QLabel(f"Slow ({SLOW_INTERVAL:g} s)")
        self.speed_slider = SafeSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(0, 100)
        self.speed_slider.setTickPosition(self.speed_slider.TickPosition.TicksBelow)
        self.speed_slider.setTickInterval(10)
        self.speed_slider.setMinimumWidth(260)
        self.speed_slider.setToolTip("How long from one click to the next. Right = fastest (no added delay), "
                                     f"left = slowest ({SLOW_INTERVAL:g} s between clicks).")
        self.lbl_fast = QLabel("Fast")
        self.lbl_speed = QLabel()
        self.lbl_speed.setMinimumWidth(330)
        self.chk_manual = QCheckBox("Advanced: edit waits manually")
        self.chk_manual.setToolTip("Untick = the slider controls the timing of every step. Tick = each step uses its "
                                   "own 'Wait before / Wait after' (Step tab) and the slider is ignored.")
        row.addWidget(self.lbl_slow)
        row.addWidget(self.speed_slider, 1)
        row.addWidget(self.lbl_fast)
        row.addWidget(self.lbl_speed)
        row.addWidget(self.chk_manual)
        self.speed_slider.valueChanged.connect(self._apply_settings)
        self.chk_manual.toggled.connect(self._apply_settings)
        return self.speed_bar

    def _refresh_speed_ui(self) -> None:
        """Reflect profile.settings.speed / speed_manual in the speed bar and lock/unlock the per-step waits."""
        s = self.profile.settings
        manual = s.speed_manual
        self.speed_slider.setEnabled(not manual)
        self.lbl_slow.setEnabled(not manual)
        self.lbl_fast.setEnabled(not manual)
        if manual:
            self.lbl_speed.setText("Manual: every step uses its own wait before / after (Step tab)")
        else:
            iv = click_interval(s.speed)
            if iv <= 0:
                self.lbl_speed.setText(f"{s.speed}% - fastest: no added delay (about "
                                       f"{display_interval(s.speed):.2f} s between clicks)")
            else:
                self.lbl_speed.setText(f"{s.speed}% - at least {iv:.2f} s between clicks")
        self.step_editor.set_waits_locked(not manual, FAST_WAIT, FAST_WAIT)

    def _build_settings_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        form = QFormLayout()
        self.s_loops = SafeSpinBox()
        self.s_loops.setRange(1, 1_000_000)
        self.s_infinite = QCheckBox("Infinite loop (until stopped)")
        self.s_jitter = SafeDoubleSpinBox()
        self.s_jitter.setRange(0, 100)
        self.s_jitter.setSuffix(" %")
        self.s_jitter.setToolTip("Every wait is randomised by +/- this percentage.")
        self.s_maxclicks = SafeSpinBox()
        self.s_maxclicks.setRange(0, 1_000_000)
        self.s_maxclicks.setSpecialValueText("no limit")
        self.s_hotkey = QLineEdit()
        self.s_hotkey.setToolTip("Global stop hotkey, e.g. F8 or ctrl+shift+s")
        self.s_start_delay = SafeDoubleSpinBox()
        self.s_start_delay.setRange(0, 600)
        self.s_start_delay.setSuffix(" s")
        self.s_scan = SafeDoubleSpinBox()
        self.s_scan.setRange(0.02, 10)
        self.s_scan.setSingleStep(0.05)
        self.s_scan.setSuffix(" s")
        self.s_corner = QCheckBox("Moving the mouse into a screen corner stops the run")
        self.s_minimize = QCheckBox("Minimise ClickFlow while running")
        self.s_idle = SafeSpinBox()
        self.s_idle.setRange(0, 100000)
        self.s_idle.setSpecialValueText("never")
        self.s_idle.setToolTip("Stop after this many loops in a row in which nothing was found/clicked.")
        self.s_monitor = SafeSpinBox()
        self.s_monitor.setRange(0, 16)
        self.s_monitor.setToolTip("0 = all screens combined, 1 = primary monitor, 2 = second monitor ...")
        form.addRow("Loop count", self.s_loops)
        form.addRow("", self.s_infinite)
        form.addRow("Random delay jitter", self.s_jitter)
        form.addRow("Max total clicks", self.s_maxclicks)
        form.addRow("Stop hotkey", self.s_hotkey)
        form.addRow("Start delay", self.s_start_delay)
        form.addRow("Scan interval", self.s_scan)
        form.addRow("Stop after idle loops", self.s_idle)
        form.addRow("Monitor", self.s_monitor)
        form.addRow("", self.s_corner)
        form.addRow("", self.s_minimize)
        lay.addLayout(form)
        self.end_editor = EndConditionEditor()
        self.end_editor.changed.connect(self._mark_dirty)
        self.end_editor.capture_requested.connect(self.capture_end_template)
        self.end_editor.region_requested.connect(self.pick_end_region)
        lay.addWidget(self.end_editor)
        lay.addStretch(1)
        for w in (self.s_loops, self.s_maxclicks, self.s_idle, self.s_monitor):
            w.valueChanged.connect(self._apply_settings)
        for w in (self.s_jitter, self.s_start_delay, self.s_scan):
            w.valueChanged.connect(self._apply_settings)
        for w in (self.s_infinite, self.s_corner, self.s_minimize):
            w.toggled.connect(self._apply_settings)
        self.s_hotkey.editingFinished.connect(self._apply_hotkey)
        return page

    def _build_actions(self) -> None:
        def act(text, slot, shortcut=None):
            a = QAction(text, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(shortcut)
            return a

        self.act_new = act("&New profile...", self.new_profile, "Ctrl+N")
        self.act_open = act("&Open profile...", self.open_profile, "Ctrl+O")
        self.act_example = act("Open &example profile", self.open_example)
        self.act_save = act("&Save", self.save, "Ctrl+S")
        self.act_saveas = act("Save &as...", self.save_as, "Ctrl+Shift+S")
        self.act_import = act("&Import (.zip)...", self.import_zip)
        self.act_export = act("&Export (.zip)...", self.export_zip)
        self.act_quit = act("&Quit", self.close, "Ctrl+Q")
        self.act_run = act("&Start", lambda: self.start_run(dry=False), "Ctrl+R")
        self.act_dry = act("&Dry run (no clicks)", lambda: self.start_run(dry=True), "Ctrl+D")
        self.act_stop = act("S&top", self.stop_run, "Ctrl+.")
        fm = self.menuBar().addMenu("&File")
        for a in (self.act_new, self.act_open, self.act_example, None, self.act_save, self.act_saveas, None,
                  self.act_import, self.act_export, None, self.act_quit):
            fm.addSeparator() if a is None else fm.addAction(a)
        rm = self.menuBar().addMenu("&Run")
        for a in (self.act_run, self.act_dry, self.act_stop):
            rm.addAction(a)
        hm = self.menuBar().addMenu("&Help")
        hm.addAction(act("About / safety notes", self.show_about))
        hm.addAction(act("Open-source licenses...", self.show_licenses))
        tb = QToolBar("Run")
        tb.setMovable(False)
        for a in (self.act_run, self.act_dry, self.act_stop):
            tb.addAction(a)
        tb.addSeparator()
        for a in (self.act_save,):
            tb.addAction(a)
        self.addToolBar(tb)

    # ================================================================== logging

    def append_log(self, text: str, level: str = "info", kind: str = "") -> None:
        color = KIND_COLORS.get(kind) if level == "info" and kind in KIND_COLORS else LEVEL_COLORS.get(level, "#d4d4d4")
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cur = self.log_view.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.insertText(f"[{stamp}] {text}\n", fmt)
        self.log_view.setTextCursor(cur)
        self.log_view.ensureCursorVisible()
        log.log({"info": logging.INFO, "warn": logging.WARNING, "error": logging.ERROR}.get(level, logging.INFO), text)

    def _on_event(self, ev: Event) -> None:
        self.append_log(ev.message, ev.level, ev.kind)
        if ev.kind == "preset" and ev.data.get("preset"):
            # auto-detection picked a preset: reflect it in the UI (not a user edit, so not "dirty")
            self.profile.settings.active_preset = ev.data["preset"]
            self._refresh_presets()
        if ev.kind == "match" and self._run_thread is not None and self._run_thread.runner.dry_run:
            rect = ev.data.get("rect")
            if rect and ev.data.get("tag") != "end":
                self.highlighter.flash(rect, f"{ev.data['confidence']:.2f}", ev.data.get("found", False), 500)

    # ================================================================== profile <-> UI

    def load_into_ui(self, profile: Profile) -> None:
        self._building = True
        try:
            self.profile = profile
            self.step_list.clear()
            for s in profile.steps:
                self.step_list.addItem(self._make_item(s))
            s = profile.settings
            self.s_loops.setValue(s.loop_count)
            self.s_infinite.setChecked(s.infinite_loop)
            self.s_jitter.setValue(s.jitter_percent)
            self.s_maxclicks.setValue(s.max_total_clicks)
            self.s_hotkey.setText(s.stop_hotkey)
            self.s_start_delay.setValue(s.start_delay)
            self.s_scan.setValue(s.scan_interval)
            self.s_corner.setChecked(s.corner_abort)
            self.s_minimize.setChecked(s.minimize_on_run)
            self.s_idle.setValue(s.max_idle_loops)
            self.s_monitor.setValue(s.monitor)
            self.s_loops.setEnabled(not s.infinite_loop)
            self.speed_slider.setValue(s.speed)
            self.chk_manual.setChecked(s.speed_manual)
            self.notes.setPlainText(profile.notes)
            if profile.end_condition is None:
                profile.end_condition = Step(name="End condition", enabled=False)
            self._refresh_presets()
            self.end_editor.set_step(profile.end_condition, profile.directory, self.active_preset)
        finally:
            self._building = False
        self.dirty = False
        if profile.directory:
            storage.remember_last_profile(profile.directory)
        self._refresh_banner()
        self._refresh_title()
        if self.step_list.count():
            self.step_list.setCurrentRow(0)
        else:
            self.step_editor.set_step(None, None)
        self._refresh_displays_label()
        self._refresh_speed_ui()
        if self._hotkey_enabled:
            self._start_hotkey()

    def _make_item(self, step: Step) -> QListWidgetItem:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, step.id)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled
                      | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        item.setCheckState(Qt.CheckState.Checked if step.enabled else Qt.CheckState.Unchecked)
        self._style_item(item, step)
        return item

    def _style_item(self, item: QListWidgetItem, step: Step) -> None:
        idx = self.profile.steps.index(step) + 1 if step in self.profile.steps else 0
        flags = []
        tpl = effective_template(step, self.active_preset)
        if not tpl:
            flags.append("NO TEMPLATE")
        elif effective_region(step, self.active_preset) is None:
            flags.append("no search box")
        if step.click_only_if_found:
            flags.append("optional")
        if step.click_type != "left":
            flags.append(step.click_type.upper() + "-CLICK")  # unusual: make it impossible to miss
        suffix = f"   [{', '.join(flags)}]" if flags else ""
        item.setText(f"{idx}. {step.name}{suffix}")
        if not tpl:
            item.setForeground(QColor("#e8554f"))
        elif not step.enabled:
            item.setForeground(QColor("#8a8a8a"))
        else:
            item.setData(Qt.ItemDataRole.ForegroundRole, None)  # theme default (works in light and dark)

    def _refresh_items(self) -> None:
        self._building = True
        try:
            for i, s in enumerate(self.profile.steps):
                item = self.step_list.item(i)
                if item:
                    self._style_item(item, s)
                    item.setCheckState(Qt.CheckState.Checked if s.enabled else Qt.CheckState.Unchecked)
        finally:
            self._building = False

    def _refresh_banner(self) -> None:
        notes = self.profile.notes.strip()
        if notes:
            first = notes if len(notes) <= 420 else notes[:420] + "... (see Notes tab)"
            self.banner.setText(first)
            self.banner.setVisible(True)
        else:
            self.banner.setVisible(False)

    def _refresh_title(self) -> None:
        star = " *" if self.dirty else ""
        self.setWindowTitle(f"ClickFlow - {self.profile.name}{star}")
        self.status_label.setText(str(self.profile.directory) if self.profile.directory else "unsaved profile")

    def _mark_dirty(self) -> None:
        if self._building:
            return
        self.dirty = True
        self._refresh_title()

    @property
    def active_preset(self) -> Optional[Preset]:
        return self.profile.preset_by_id(self.profile.settings.active_preset)

    def _show_step(self, step: Optional[Step]) -> None:
        self.step_editor.set_step(step, self.profile.directory if step else None, self.active_preset)
        self.step_editor.set_waits_locked(not self.profile.settings.speed_manual, FAST_WAIT, FAST_WAIT)

    def current_step(self) -> Optional[Step]:
        row = self.step_list.currentRow()
        return self.profile.steps[row] if 0 <= row < len(self.profile.steps) else None

    # ---- list/editor callbacks

    def _on_row_changed(self, row: int) -> None:
        if self._building:
            return
        step = self.current_step()
        self._show_step(step)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._building:
            return
        row = self.step_list.row(item)
        if 0 <= row < len(self.profile.steps):
            enabled = item.checkState() == Qt.CheckState.Checked
            if self.profile.steps[row].enabled != enabled:
                self.profile.steps[row].enabled = enabled
                self._mark_dirty()
                if row == self.step_list.currentRow():
                    self._show_step(self.profile.steps[row])

    def _on_rows_moved(self, *_a) -> None:
        if self._building:
            return
        by_id = {s.id: s for s in self.profile.steps}
        order = [self.step_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.step_list.count())]
        if sorted(order) == sorted(by_id):
            self.profile.steps = [by_id[i] for i in order]
            self._mark_dirty()
            QTimer.singleShot(0, self._refresh_items)

    def _on_step_edited(self) -> None:
        self._mark_dirty()
        self._refresh_items()

    def _on_notes_changed(self) -> None:
        if self._building:
            return
        self.profile.notes = self.notes.toPlainText()
        self._mark_dirty()
        self._refresh_banner()

    # ---- step list operations

    def add_step(self) -> None:
        s = Step(name=f"Step {len(self.profile.steps) + 1}")
        self.profile.steps.append(s)
        self.step_list.addItem(self._make_item(s))
        self.step_list.setCurrentRow(self.step_list.count() - 1)
        self._mark_dirty()
        self._refresh_items()

    def delete_step(self) -> None:
        row = self.step_list.currentRow()
        if row < 0:
            return
        self.profile.remove_step_refs(self.profile.steps[row].id)
        del self.profile.steps[row]
        self._building = True
        self.step_list.takeItem(row)
        self._building = False
        self._mark_dirty()
        self._refresh_items()
        if self.step_list.count():
            self.step_list.setCurrentRow(min(row, self.step_list.count() - 1))
        else:
            self.step_editor.set_step(None, None)

    def duplicate_step(self) -> None:
        step = self.current_step()
        if step is None:
            return
        row = self.step_list.currentRow()
        dup = Step.from_dict(step.to_dict())
        dup.id = Step().id
        dup.name = f"{step.name} copy"
        if self.profile.directory:
            storage.copy_template(self.profile.directory, step, dup)
            storage.copy_preset_entries(self.profile.directory, self.profile, step, dup)
        self.profile.steps.insert(row + 1, dup)
        self.step_list.insertItem(row + 1, self._make_item(dup))
        self.step_list.setCurrentRow(row + 1)
        self._mark_dirty()
        self._refresh_items()

    def move_step(self, delta: int) -> None:
        row = self.step_list.currentRow()
        new = row + delta
        if row < 0 or not (0 <= new < len(self.profile.steps)):
            return
        steps = self.profile.steps
        steps[row], steps[new] = steps[new], steps[row]
        self._building = True
        item = self.step_list.takeItem(row)
        self.step_list.insertItem(new, item)
        self._building = False
        self.step_list.setCurrentRow(new)
        self._mark_dirty()
        self._refresh_items()

    # ---- settings

    def _apply_settings(self, *_a) -> None:
        if self._building:
            return
        s = self.profile.settings
        s.loop_count = self.s_loops.value()
        s.infinite_loop = self.s_infinite.isChecked()
        s.jitter_percent = self.s_jitter.value()
        s.max_total_clicks = self.s_maxclicks.value()
        s.start_delay = self.s_start_delay.value()
        s.scan_interval = self.s_scan.value()
        s.corner_abort = self.s_corner.isChecked()
        s.minimize_on_run = self.s_minimize.isChecked()
        s.max_idle_loops = self.s_idle.value()
        s.monitor = self.s_monitor.value()
        s.auto_preset = self.chk_auto_preset.isChecked()
        s.speed = self.speed_slider.value()
        s.speed_manual = self.chk_manual.isChecked()
        self._refresh_speed_ui()
        self.s_loops.setEnabled(not s.infinite_loop)
        self._mark_dirty()

    def _apply_hotkey(self) -> None:
        text = self.s_hotkey.text().strip()
        try:
            parse_hotkey(text)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid hotkey", str(exc))
            self.s_hotkey.setText(self.profile.settings.stop_hotkey)
            return
        if text != self.profile.settings.stop_hotkey:
            self.profile.settings.stop_hotkey = text
            self._mark_dirty()
            self._start_hotkey()

    def _start_hotkey(self) -> None:
        """Two independent stop-key mechanisms: a polling watcher (Windows) and a pynput global hotkey."""
        if not self._hotkey_enabled:
            return
        key = self.profile.settings.stop_hotkey or "F8"
        self.hotkey.hotkey = key
        self.key_watcher.hotkey = key
        polling = self.key_watcher.start()
        hooked = self.hotkey.start()
        if polling or hooked:
            how = " + ".join(n for n, ok in (("key-state polling", polling), ("global hook", hooked)) if ok)
            self.append_log(f"Stop hotkey active: {key} ({how}). Also: red STOP button on screen, "
                            "or move the mouse into a screen corner.", "info")
        else:
            self.append_log(f"Could not register stop hotkey '{key}': {self.hotkey.error}. "
                            "Use the red STOP button or the screen-corner emergency stop.", "warn")

    # ================================================================== display presets

    def _detect_monitors(self) -> list[MonitorInfo]:
        try:
            self._monitors = MssScreen(0).monitors()
        except Exception as exc:  # no display / permission
            self._monitors = []
            self.append_log(f"Could not detect displays: {exc}", "warn")
        return self._monitors

    def _refresh_displays_label(self) -> None:
        mons = self._detect_monitors()
        if not mons:
            self.lbl_displays.setText("Detected displays: none (screen capture unavailable)")
            return
        parts = []
        for m in mons:
            match = [p.name for p in self.profile.presets if p.resolution == m.resolution]
            parts.append(f"{m.label}" + (f" -> preset '{', '.join(match)}'" if match else " -> no preset"))
        self.lbl_displays.setText("Detected displays: " + "   |   ".join(parts))

    def _refresh_presets(self) -> None:
        """Rebuild the preset combo from the profile (signals blocked, so this never marks the profile dirty)."""
        s = self.profile.settings
        self.preset_combo.blockSignals(True)
        self.chk_auto_preset.blockSignals(True)
        try:
            self.preset_combo.clear()
            self.preset_combo.addItem("Default (no preset)", "")
            for p in self.profile.presets:
                self.preset_combo.addItem(p.label, p.id)
            idx = self.preset_combo.findData(s.active_preset)
            if idx < 0:
                s.active_preset = ""
                idx = 0
            self.preset_combo.setCurrentIndex(idx)
            self.chk_auto_preset.setChecked(s.auto_preset)
        finally:
            self.preset_combo.blockSignals(False)
            self.chk_auto_preset.blockSignals(False)
        has = self.active_preset is not None
        self.btn_preset_rename.setEnabled(has)
        self.btn_preset_delete.setEnabled(has)

    def _on_preset_selected(self, idx: int) -> None:
        if self._building:
            return
        self.profile.settings.active_preset = self.preset_combo.itemData(idx) or ""
        self._mark_dirty()
        self._refresh_for_preset()

    def _refresh_for_preset(self) -> None:
        """The selected preset changed: show its boxes/templates in the editors and the step list."""
        self._refresh_presets()
        self._show_step(self.current_step())
        self.end_editor.set_step(self.profile.end_condition, self.profile.directory, self.active_preset)
        self._refresh_items()

    def create_preset(self, name: str, monitor: MonitorInfo) -> Preset:
        preset = Preset(name=name.strip() or monitor.label, resolution=monitor.resolution, monitor=monitor.index)
        self.profile.presets.append(preset)
        self.profile.settings.active_preset = preset.id
        self._mark_dirty()
        self._refresh_for_preset()
        self._refresh_displays_label()
        return preset

    def new_preset(self) -> None:
        mons = self._detect_monitors()
        if not mons:
            QMessageBox.warning(self, "No displays", "Could not detect any display (is screen capture allowed?).")
            return
        mon = mons[0]
        if len(mons) > 1:
            labels = [m.label for m in mons]
            choice, ok = QInputDialog.getItem(self, "New preset", "Which display is this preset for?", labels, 0, False)
            if not ok:
                return
            mon = mons[labels.index(choice)]
        name, ok = QInputDialog.getText(self, "New preset", "Preset name:", text=f"{mon.width}x{mon.height}")
        if not ok:
            return
        preset = self.create_preset(name, mon)
        self.append_log(f"Created preset '{preset.name}' for {mon.label}. It starts without search boxes: select each step "
                        "and press 'Draw search box...' on this display (templates fall back to the default ones; "
                        "capture new ones if the icons look different here).", "info")

    def rename_preset(self) -> None:
        p = self.active_preset
        if p is None:
            return
        name, ok = QInputDialog.getText(self, "Rename preset", "Preset name:", text=p.name)
        if ok and name.strip():
            p.name = name.strip()
            self._mark_dirty()
            self._refresh_for_preset()
            self._refresh_displays_label()

    def remove_preset(self, preset: Preset) -> None:
        for rel in preset.templates.values():  # the preset's own template files go with it
            try:
                (Path(self.profile.directory) / rel).unlink(missing_ok=True)
            except (OSError, TypeError):
                pass
        self.profile.presets = [p for p in self.profile.presets if p.id != preset.id]
        if self.profile.settings.active_preset == preset.id:
            self.profile.settings.active_preset = ""
        self._mark_dirty()
        self._refresh_for_preset()
        self._refresh_displays_label()

    def delete_preset(self) -> None:
        p = self.active_preset
        if p is None:
            return
        r = QMessageBox.question(self, "Delete preset", f"Delete preset '{p.name}' and its search boxes?")
        if r == QMessageBox.StandardButton.Yes:
            self.remove_preset(p)

    # ================================================================== file operations

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        r = QMessageBox.question(self, "Unsaved changes", "Save changes to this profile first?",
                                 QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                                 | QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Cancel:
            return False
        if r == QMessageBox.StandardButton.Save:
            return self.save()
        return True

    def _ensure_dir(self) -> bool:
        if self.profile.directory is None:
            self.profile.directory = storage.new_profile(self.profile.name).directory
        return True

    def new_profile(self) -> None:
        if not self._confirm_discard():
            return
        name, ok = QInputDialog.getText(self, "New profile", "Profile name:", text="My profile")
        if not ok or not name.strip():
            return
        self.load_into_ui(storage.new_profile(name.strip()))

    def open_profile(self) -> None:
        if not self._confirm_discard():
            return
        start = str(storage.profiles_root())
        Path(start).mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(self, "Open profile", start, "ClickFlow profile (profile.json);;JSON (*.json)")
        if path:
            self.open_path(path)

    def open_path(self, path) -> bool:
        try:
            self.load_into_ui(storage.load_profile(path))
        except storage.ProfileError as exc:
            QMessageBox.critical(self, "Cannot open profile", str(exc))
            return False
        self.append_log(f"Loaded profile '{self.profile.name}' from {self.profile.directory}")
        if self.profile.notes.strip():
            self.append_log("NOTE: " + self.profile.notes.strip().splitlines()[0], "warn")
        return True

    def open_example(self) -> None:
        from ..app import ensure_example

        if not self._confirm_discard():
            return
        path = ensure_example()
        if path:
            self.open_path(path)
        else:
            QMessageBox.warning(self, "Example missing", "The bundled example profile could not be found.")

    def _flush_pending_edits(self) -> None:
        """Commit anything the user typed but has not confirmed yet (Enter / Tab / focus-out).

        Toolbar buttons and menu actions do not take keyboard focus, so a value typed into a field
        would otherwise still be sitting in the editor when Save / Start reads the profile.
        """
        for spin in self.findChildren(QAbstractSpinBox):
            spin.interpretText()  # emits valueChanged if the typed text differs
        # Text fields only report "editing finished" on a focus-out event, which the OS may never deliver
        # (e.g. the window is not the active one). So read every editor explicitly instead of relying on focus.
        self.step_editor.commit()
        self.end_editor.commit()
        self._apply_settings()
        text = self.s_hotkey.text().strip()
        if text != self.profile.settings.stop_hotkey:
            self._apply_hotkey()

    def save(self) -> bool:
        self._flush_pending_edits()
        try:
            self._ensure_dir()
            self.profile.notes = self.notes.toPlainText()
            storage.save_profile(self.profile)
        except (OSError, storage.ProfileError) as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return False
        self.dirty = False
        self._refresh_title()
        self.append_log(f"Saved profile to {self.profile.directory}")
        return True

    def save_as(self) -> None:
        name, ok = QInputDialog.getText(self, "Save profile as", "New profile name:", text=self.profile.name + " copy")
        if not ok or not name.strip():
            return
        folder = storage.profiles_root() / storage.slugify(name.strip())
        if folder.exists():
            QMessageBox.warning(self, "Exists", f"A profile folder named '{folder.name}' already exists.")
            return
        self.profile.name = name.strip()
        try:
            storage.save_profile(self.profile, folder)
        except (OSError, storage.ProfileError) as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.dirty = False
        self.end_editor.set_step(self.profile.end_condition, self.profile.directory, self.active_preset)
        self._refresh_title()
        self.append_log(f"Saved profile as {self.profile.directory}")

    def export_zip(self) -> None:
        if not self.save():
            return
        default = str(Path.home() / f"{storage.slugify(self.profile.name)}.zip")
        path, _ = QFileDialog.getSaveFileName(self, "Export profile", default, "Zip archive (*.zip)")
        if path:
            try:
                storage.export_profile(self.profile, path)
                self.append_log(f"Exported profile to {path}")
            except (OSError, storage.ProfileError) as exc:
                QMessageBox.critical(self, "Export failed", str(exc))

    def import_zip(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import profile", str(Path.home()), "Zip archive (*.zip)")
        if path:
            try:
                self.load_into_ui(storage.import_profile(path))
                self.append_log(f"Imported profile '{self.profile.name}'")
            except Exception as exc:
                QMessageBox.critical(self, "Import failed", str(exc))

    def show_about(self) -> None:
        from .. import __version__

        QMessageBox.information(
            self, "About ClickFlow",
            f"ClickFlow {__version__} - finds icons on screen by image matching and clicks them in a flow you define.\n"
            "Free software under the MIT License (see Help > Open-source licenses).\n\n"
            "Safety: press the stop hotkey (default F8), click the red STOP button, or move the mouse into any screen "
            "corner to stop at any time.\n\n"
            "Terms of service: automating likes or other actions may violate a website's or app's terms "
            "(for example Instagram's). Use at low volume, with sensible delays, a click limit, and at your own risk.\n\n"
            "ClickFlow is an independent project. It is not affiliated with, endorsed by or sponsored by Instagram, "
            "Meta or any other service it can be pointed at; all product names belong to their owners.")

    def show_licenses(self) -> None:
        """Show LICENSE and THIRD_PARTY_NOTICES.md (bundled inside the exe as well)."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox

        from ..app import resource_root

        dlg = QDialog(self)
        dlg.setWindowTitle("Open-source licenses")
        dlg.resize(820, 620)
        lay = QVBoxLayout(dlg)
        tabs = QTabWidget()
        for title, name in (("ClickFlow (MIT)", "LICENSE"), ("Third-party notices", "THIRD_PARTY_NOTICES.md")):
            view = QPlainTextEdit()
            view.setReadOnly(True)
            try:
                view.setPlainText((resource_root() / name).read_text(encoding="utf-8"))
            except OSError:
                view.setPlainText(f"{name} was not found next to the program.")
            tabs.addTab(view, title)
        lay.addWidget(tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        self._licenses_dialog = dlg
        dlg.exec()

    # ================================================================== capture

    def _capture_monitor_info(self) -> Optional[MonitorInfo]:
        """The monitor the active preset applies to (None for the default configuration)."""
        preset = self.active_preset
        if preset is None:
            return None
        return presets_mod.resolve_explicit(preset, self._detect_monitors()).monitor

    def _capture_monitor(self) -> int:
        """mss monitor index used for capturing: the active preset's monitor, else the global setting."""
        info = self._capture_monitor_info()
        return info.index if info else self.profile.settings.monitor

    def _qt_geometry(self, frame, monitor_index: int) -> QRect:
        """Qt screen rectangle (logical units) that corresponds to the captured frame."""
        screens = QGuiApplication.screens()
        primary = QGuiApplication.primaryScreen()
        if monitor_index == 0 or not screens:
            return primary.virtualGeometry()
        ih, iw = frame.image.shape[:2]
        best, best_key = None, None
        for sc in screens:
            g, dpr = sc.geometry(), sc.devicePixelRatio()
            key = (abs(g.width() * dpr - iw) + abs(g.height() * dpr - ih),
                   abs(g.x() * dpr - frame.left) + abs(g.y() * dpr - frame.top))
            if best_key is None or key < best_key:
                best, best_key = sc, key
        if best is None or best_key[0] > 60:  # sizes disagree: fall back to the enumeration order
            best = screens[monitor_index - 1] if 0 < monitor_index <= len(screens) else primary
        return best.geometry()

    def _begin_capture(self, hint: str, on_rect, guides=None) -> None:
        """Hide the window, screenshot the screen, show the drag overlay; call on_rect(frame, x, y, w, h).

        ``guides(frame)`` may return boxes to draw for orientation. ``on_rect`` may return
        ``(hint, on_rect, guides)`` to chain a second drag on the same screenshot.
        """
        if self._overlay is not None:
            return
        if not self._ensure_permissions():
            return
        mon = self._capture_monitor()
        self.showMinimized()

        def snap():
            try:
                frame = MssScreen(mon).grab()
            except Exception as exc:
                self._restore_window()
                QMessageBox.critical(self, "Screen capture failed", str(exc))
                return
            self._show_overlay(frame, mon, hint, on_rect, guides)

        QTimer.singleShot(450, snap)

    def _show_overlay(self, frame, mon: int, hint: str, on_rect, guides=None) -> None:
        ov = CaptureOverlay(frame.image, self._qt_geometry(frame, mon), hint, guides=guides(frame) if guides else [])
        self._overlay = ov
        ov.selected.connect(lambda x, y, w, h: self._capture_done(on_rect, frame, mon, x, y, w, h))
        ov.cancelled.connect(self._capture_cancelled)
        ov.open()

    def _capture_done(self, on_rect, frame, mon: int, x, y, w, h) -> None:
        self._overlay = None
        follow = None
        try:
            follow = on_rect(frame, x, y, w, h)
        finally:
            if not follow:
                self._restore_window()
        if follow:
            hint, next_cb, guides = follow
            self._show_overlay(frame, mon, hint, next_cb, guides)

    def _capture_cancelled(self) -> None:
        self._overlay = None
        self._restore_window()

    def _restore_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _box_from_frame(self, frame, x, y, w, h) -> tuple[int, int, int, int]:
        """Overlay selection (screenshot pixels) -> search box in the units the active config stores.

        Default config: global screen coordinates. Preset: relative to the monitor's top-left corner.
        """
        g = frame.rect_to_screen(x, y, w, h).as_tuple()
        if self.active_preset is not None:
            return (g[0] - int(round(frame.left)), g[1] - int(round(frame.top)), g[2], g[3])
        return g

    def _guides_for(self, frame, exclude: Optional[Step] = None) -> list[tuple[int, int, int, int, str]]:
        """Existing search boxes of the other steps, in screenshot pixels, so the user sees what is already covered."""
        out = []
        steps = [s for s in self.profile.steps if s is not exclude and s.enabled]
        for st in steps:
            box = presets_mod.resolve_region(st, self.active_preset, frame)
            img = frame.region_to_image(box) if box else None
            if img:
                out.append((img[0], img[1], img[2] - img[0], img[3] - img[1], st.name))
        return out

    def _save_crop(self, step: Step, frame, x, y, w, h) -> None:
        self._ensure_dir()
        crop = frame.image[y:y + h, x:x + w].copy()
        preset = self.active_preset
        rel = storage.save_template(self.profile.directory, step, crop, preset=preset)
        where = f" (preset '{preset.name}')" if preset else ""
        self.append_log(f"Captured template for '{step.name}'{where}: {w}x{h} px -> {rel}")
        self._mark_dirty()

    def _set_box(self, step: Step, frame, x, y, w, h) -> None:
        box = self._box_from_frame(frame, x, y, w, h)
        set_region(step, self.active_preset, box)
        preset = self.active_preset
        where = f" (preset '{preset.name}')" if preset else ""
        self.append_log(f"Search box for '{step.name}'{where}: x={box[0]} y={box[1]} w={box[2]} h={box[3]} - "
                        "applied automatically on every run.")
        self._mark_dirty()

    def capture_step_template(self) -> None:
        step = self.current_step()
        if step is None:
            return

        def box_done(frame, x, y, w, h):
            self._set_box(step, frame, x, y, w, h)
            self._show_step(step)
            self._refresh_items()

        def done(frame, x, y, w, h):
            self._save_crop(step, frame, x, y, w, h)
            self._show_step(step)
            self._refresh_items()
            if effective_region(step, self.active_preset) is None:
                # No search box yet: continue straight on the same screenshot (Esc skips = whole screen).
                return ("Now drag the SEARCH BOX: the area where this icon appears (a bit bigger than the icon). "
                        "Esc / right-click = skip, scan the whole screen.",
                        box_done, lambda fr: [(x, y, w, h, "template")] + self._guides_for(fr, step))

        self._begin_capture("Drag a rectangle around the icon (the template). Esc / right-click cancels.", done,
                            lambda fr: self._guides_for(fr, step))

    def pick_step_region(self) -> None:
        step = self.current_step()
        if step is None:
            return

        def done(frame, x, y, w, h):
            self._set_box(step, frame, x, y, w, h)
            self._show_step(step)
            self._refresh_items()

        self._begin_capture("Drag the SEARCH BOX: the area where this icon appears. Esc / right-click cancels.", done,
                            lambda fr: self._guides_for(fr, step))

    def capture_end_template(self) -> None:
        step = self.profile.end_condition

        def done(frame, x, y, w, h):
            self._save_crop(step, frame, x, y, w, h)
            self.end_editor.set_step(step, self.profile.directory, self.active_preset)

        self._begin_capture("Drag a rectangle around the image that means 'finished'.", done)

    def pick_end_region(self) -> None:
        step = self.profile.end_condition

        def done(frame, x, y, w, h):
            self._set_box(step, frame, x, y, w, h)
            self.end_editor.set_step(step, self.profile.directory, self.active_preset)

        self._begin_capture("Drag the area where the end image shows up.", done,
                            lambda fr: self._guides_for(fr))

    def show_search_boxes(self) -> None:
        """Briefly draw every search box (blue, dashed) on the real screen."""
        preset = self.active_preset
        mon = self._capture_monitor_info()
        ox, oy = (mon.left, mon.top) if (preset is not None and mon is not None) else (0, 0)
        steps = [s for s in self.profile.steps if s.enabled]
        if self.profile.end_condition and self.profile.end_condition.enabled:
            steps.append(self.profile.end_condition)
        shown = 0
        for st in steps:
            r = effective_region(st, preset)
            if r:
                rect = (r[0] + ox, r[1] + oy, r[2], r[3]) if preset is not None else r
                self.highlighter.flash(rect, st.name, False, 3500, kind="region")
                shown += 1
        if shown:
            self.append_log(f"Showing {shown} search box(es) on screen for a few seconds (blue, dashed).")
        else:
            self.append_log("No search boxes are set yet - select a step and press 'Draw search box...'.", "warn")

    # ================================================================== test / run

    def _ensure_permissions(self) -> bool:
        issues = platform_utils.check_permissions()
        if issues:
            QMessageBox.warning(self, "Permission needed", "\n\n".join(f"{i.name}:\n{i.message}" for i in issues))
            self.append_log("Missing OS permission: " + ", ".join(i.name for i in issues), "error")
            return False
        return True

    def test_step(self) -> None:
        step = self.current_step()
        if step is None or self._call_thread is not None or self._run_thread is not None:
            return
        if not effective_template(step, self.active_preset):
            QMessageBox.information(self, "No template", "Capture a template for this step first.")
            return
        if not self._ensure_permissions():
            return
        self.save()
        self.append_log(f"Testing step '{step.name}' (no click) ...")
        self.showMinimized()

        preset = self.active_preset
        monitor = self._capture_monitor()

        def probe():
            events: list[Event] = []
            runner = Runner(self.profile, MssScreen(monitor), NullInput(), dry_run=True,
                            on_event=events.append, preset=preset)
            hit = runner.probe(step)
            diag = None if hit.found else runner.diagnose(step)  # why not? (same screen, restrictions lifted)
            return hit, events, diag

        def finish(result) -> None:
            hit, events, diag = result
            self._call_thread = None
            self._restore_window()
            for ev in events:
                if ev.kind == "preset" or ev.level == "warn" and "Display presets" in ev.message:
                    self.append_log(ev.message, ev.level)
            self._report_test(step, hit, diag)

        def failed(msg: str) -> None:
            self._call_thread = None
            self._restore_window()
            self.append_log(f"Test failed: {msg}", "error")

        def go():
            t = CallThread(probe)
            t.result.connect(finish)
            t.failed.connect(failed)
            self._call_thread = t
            t.start()

        QTimer.singleShot(500, go)

    def _report_test(self, step: Step, hit, diag) -> None:
        """Log the outcome of 'Test this step' in plain words: would a run click, and if not, why."""
        if hit.found:
            r = hit.rect
            self.append_log(f"Test '{step.name}': FOUND - confidence {hit.confidence:.3f} (threshold "
                            f"{step.threshold:.2f}). A run WOULD click at "
                            f"({r.center[0] + step.offset_x:.0f},{r.center[1] + step.offset_y:.0f}).")
            self.append_log(f"  match box at ({r.left:.0f},{r.top:.0f}) size {r.width:.0f}x{r.height:.0f}, "
                            f"scale {hit.scale:.2f}")
            self.highlighter.flash(r.as_tuple(), f"{hit.confidence:.2f} FOUND", True, 1500)
            return
        self.append_log(f"Test '{step.name}': NOT FOUND - confidence {hit.confidence:.3f} is below the threshold "
                        f"{step.threshold:.2f}. A run would NOT click this step.", "warn")
        if hit.rect.width:
            r = hit.rect
            self.append_log(f"  (the orange box marks only the BEST CANDIDATE at ({r.left:.0f},{r.top:.0f}), "
                            f"scale {hit.scale:.2f} - it is not a match)", "warn")
            self.highlighter.flash(r.as_tuple(), f"{hit.confidence:.2f} NOT FOUND - no click", False, 2500)
        if diag is not None and diag.kind != "ok":
            for line in diag.text.splitlines():
                self.append_log("  " + line, "warn")
            if self._ask_test_fix(step, diag) and diag.fix:
                self.apply_fix(step, diag.fix)

    def _ask_test_fix(self, step: Step, diag) -> bool:
        """Show the diagnosis; return True if the user wants the proposed fix applied."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(f"Test '{step.name}': not found")
        box.setText("This step would NOT click.\n\n" + diag.text)
        apply_btn = None
        if diag.fix:
            apply_btn = box.addButton("Apply suggested fix", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return apply_btn is not None and box.clickedButton() is apply_btn

    def apply_fix(self, step: Step, fix: dict) -> None:
        """Apply a Diagnosis.fix to ``step`` (scale range / multi-scale / threshold / search box)."""
        done = []
        for key in ("multi_scale", "scale_min", "scale_max", "threshold"):
            if key in fix:
                setattr(step, key, fix[key])
                done.append(f"{key}={fix[key]}")
        if "region" in fix:
            preset = self.active_preset
            mon = self._capture_monitor_info()
            ox, oy = (mon.left, mon.top) if (preset is not None and mon is not None) else (0, 0)
            l, t, w, h = fix["region"]
            set_region(step, preset, (int(l - ox), int(t - oy), int(w), int(h)))
            done.append("search box")
        step.normalise()
        self._show_step(step)
        self._refresh_items()
        self._mark_dirty()
        self.append_log(f"Applied fix to '{step.name}': {', '.join(done)}. Press 'Test this step' again.")

    def start_run(self, dry: bool) -> None:
        if self._run_thread is not None:
            return
        problems = self.profile.validate()
        if problems:
            QMessageBox.warning(self, "Cannot start", "\n".join(problems))
            return
        try:
            parse_hotkey(self.profile.settings.stop_hotkey)
        except ValueError:
            pass
        if not self._ensure_permissions():
            return
        if not self.save():
            return
        try:
            screen = MssScreen(self._capture_monitor())
            inputs = PyAutoGuiInput()
        except Exception as exc:
            QMessageBox.critical(self, "Cannot start", f"Could not initialise screen/input: {exc}")
            return
        runner = Runner(self.profile, screen, inputs, dry_run=dry, preset=self.active_preset)
        thread = RunThread(runner)
        thread.event.connect(self._on_event)
        thread.done.connect(self._run_finished)
        self._run_thread = thread
        self._set_running(True)
        s = self.profile.settings
        self.stop_badge.show_badge(s.stop_hotkey)
        self.append_log(f"{'Dry run' if dry else 'Run'} starting - press {s.stop_hotkey or 'the Stop button'} "
                        f"or move the mouse to a screen corner to stop. Switch to your target window now "
                        f"({s.start_delay:.0f}s).", "warn")
        self._was_minimized_for_run = s.minimize_on_run
        if s.minimize_on_run:
            self.showMinimized()
        thread.start()

    def stop_run(self) -> None:
        if self._run_thread is not None:
            self._run_thread.request_stop()

    def _run_finished(self, result: RunResult) -> None:
        thread = self._run_thread
        self._run_thread = None
        if thread is not None:
            thread.wait(2000)
        self._set_running(False)
        self.stop_badge.hide()
        self._restore_window()
        mode = "Dry run" if result.dry_run else "Run"
        self.append_log(f"{mode} finished: {result.reason} - {result.clicks} click(s), {result.loops} loop(s), "
                        f"{result.elapsed:.1f}s", "info")

    def _set_running(self, running: bool) -> None:
        self.act_run.setEnabled(not running)
        self.act_dry.setEnabled(not running)
        self.act_stop.setEnabled(running)
        self.tabs.setEnabled(not running)
        self.preset_bar.setEnabled(not running)
        # the editors show a picture of each template: keep it off the screen while the matcher is looking
        self.step_editor.set_previews_visible(not running)
        self.end_editor.set_previews_visible(not running)
        self.speed_bar.setEnabled(not running)
        for b in (self.btn_add, self.btn_del, self.btn_dup, self.btn_up, self.btn_down, self.step_list):
            b.setEnabled(not running)

    # ================================================================== shutdown

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._run_thread is not None:
            self._run_thread.request_stop()
            self._run_thread.wait(3000)
        if not self._confirm_discard():
            event.ignore()
            return
        self.hotkey.stop()
        self.key_watcher.stop()
        self.stop_badge.close()
        self.highlighter.close()
        event.accept()
