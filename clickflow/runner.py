"""Runner: the step engine.

The Runner only talks to the abstract ScreenProvider / InputProvider / Clock, so it runs
unchanged against fakes in tests (no display needed) and against the real OS in the app.
It never raises out of ``run()``: every failure is logged and turned into a stop reason.
"""
from __future__ import annotations

import random
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .clock import Clock
from .inputs import InputProvider
from .matcher import MatchResult, Matcher, scale_list
from . import diagnose as diagnose_mod
from . import presets as presets_mod
from .models import FAST_WAIT, Preset, Profile, Step, click_interval, display_interval, effective_template
from .screen import Frame, Rect, ScreenProvider
from .storage import ProfileError, TemplateStore

# Stop reasons
COMPLETED = "completed"
USER = "user"
CORNER = "corner"
CLICK_LIMIT = "click_limit"
END_CONDITION = "end_condition"
STEP_FAILED = "step_failed"
IDLE = "idle"
INVALID = "invalid_profile"
ERROR = "error"

SLEEP_SLICE = 0.05  # waits are chopped into slices so Stop / corner abort react quickly
CORNER_TOLERANCE = 2.0
MAX_CONSECUTIVE_ERRORS = 5


@dataclass
class Event:
    kind: str  # log | start | loop | step | match | click | key | finished
    message: str
    level: str = "info"  # info | warn | error
    t: float = 0.0
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    reason: str
    message: str
    clicks: int = 0
    loops: int = 0
    elapsed: float = 0.0
    dry_run: bool = False


@dataclass
class Hit:
    """A template located on screen, in screen coordinates."""

    found: bool
    confidence: float
    rect: Rect = field(default_factory=lambda: Rect(0, 0, 0, 0))
    scale: float = 1.0

    @property
    def center(self) -> tuple[float, float]:
        return self.rect.center


class _Stop(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


class Runner:
    def __init__(
        self,
        profile: Profile,
        screen: ScreenProvider,
        inputs: InputProvider,
        *,
        matcher: Optional[Matcher] = None,
        clock: Optional[Clock] = None,
        rng: Optional[random.Random] = None,
        on_event: Optional[Callable[[Event], None]] = None,
        dry_run: bool = False,
        templates: Optional[TemplateStore] = None,
        preset: Optional[Preset] = None,
    ) -> None:
        self.profile = profile
        self.screen = screen
        self.inputs = inputs
        self.matcher = matcher or Matcher()
        self.clock = clock or Clock()
        self.rng = rng or random.Random()
        self.on_event = on_event
        self.dry_run = dry_run
        self.templates = templates or TemplateStore(profile.directory)
        self.preset = preset  # display preset in use (may be replaced by auto-detection at start)
        self._setup_done = False
        self._last_click_t: Optional[float] = None  # clock time of the previous click (for speed pacing)
        self._overhead = 0.2  # smoothed seconds from "start looking" to "clicked" (scan + click themselves)
        self._search_t0 = 0.0
        self._scale_hint: dict[str, float] = {}  # step id -> scale that matched last time (tried first)
        self._stop = threading.Event()
        self._stop_reason = USER
        self.clicks = 0
        self.loops = 0
        self._actions_this_loop = 0
        self._errors = 0
        self._idle_loops = 0

    # ------------------------------------------------------------------ control

    def request_stop(self, reason: str = USER) -> None:
        """Thread-safe: ask the run to stop at the next opportunity (<= ~50 ms)."""
        if not self._stop.is_set():
            self._stop_reason = reason
            self._stop.set()

    @property
    def stop_requested(self) -> bool:
        return self._stop.is_set()

    # ------------------------------------------------------------------ events

    def _emit(self, kind: str, message: str, level: str = "info", **data: Any) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(Event(kind, message, level, self.clock.now(), data))
        except Exception:  # a broken listener must never kill the run
            pass

    def _log(self, message: str, level: str = "info") -> None:
        self._emit("log", message, level)

    # ------------------------------------------------------------------ public API

    def run(self) -> RunResult:
        s = self.profile.settings
        t0 = self.clock.now()
        mode = "DRY RUN (no clicks)" if self.dry_run else "RUN"
        problems = self.profile.validate()
        if problems:
            for p in problems:
                self._log(p, "error")
            return self._finish(INVALID, "; ".join(problems), t0)
        enabled = [st for st in self.profile.steps if st.enabled]
        loops_txt = "infinite" if s.infinite_loop else str(s.loop_count)
        limit_txt = str(s.max_total_clicks) if s.max_total_clicks else "none"
        self._emit("start", f"{mode} started: {len(enabled)} step(s), loops={loops_txt}, click limit={limit_txt}")
        if s.speed_manual:
            self._log("  speed: MANUAL - each step uses its own wait before / after")
        else:
            iv = click_interval(s.speed)
            self._log(f"  speed: {s.speed}% - " + ("no added delay (as fast as scan + click allow, about "
                                                    f"{display_interval(s.speed):.2f} s between clicks)" if iv <= 0 else
                                                    f"at least {iv:.2f} s between clicks"))
        for i, st in enumerate(enabled, 1):  # what each step will do, so a wrong setting is visible at a glance
            box = "search box" if st.region or any(p.regions.get(st.id) for p in self.profile.presets) else "WHOLE screen"
            action = "click-only-if-found" if st.click_only_if_found else f"if missing: {st.not_found_action}"
            wb, wa = self._waits(st)
            self._log(f"  step {i}: '{st.name}' -> {st.click_type.upper()} click, threshold {st.threshold:.2f}, "
                      f"{box}, wait {wb:g}s before / {wa:g}s after, {action}")
        try:
            self._sleep(s.start_delay, jitter=False, label="start delay")
            self._select_setup()
            late = self.profile.validate(self.preset) if self.profile.presets else []
            if late:
                for p in late:
                    self._log(p, "error")
                raise _Stop(INVALID, "; ".join(late))
            while True:
                if not s.infinite_loop and self.loops >= s.loop_count:
                    raise _Stop(COMPLETED, f"All {s.loop_count} loop(s) completed.")
                self.loops += 1
                self._actions_this_loop = 0
                total = "inf" if s.infinite_loop else str(s.loop_count)
                self._emit("loop", f"--- loop {self.loops}/{total} ---", loop=self.loops)
                for step in enabled:
                    self._check_abort()
                    self._run_step(step)
                self._check_idle(s.scan_interval)
        except _Stop as stop:
            return self._finish(stop.reason, stop.message, t0)
        except Exception as exc:  # last line of defence: never crash the worker thread
            self._log(f"Unexpected error: {type(exc).__name__}: {exc}", "error")
            return self._finish(ERROR, f"Unexpected error: {exc}", t0)

    def probe(self, step: Step) -> Hit:
        """Find ``step``'s template once and report; never clicks (powers 'Test this step')."""
        self._select_setup()
        rel = effective_template(step, self.preset)
        try:
            template = self.templates.get(rel) if rel else None
        except ProfileError as exc:
            self._log(str(exc), "error")
            return Hit(False, 0.0)
        if template is None:
            self._log(f"Step '{step.name}' has no template - capture one first.", "error")
            return Hit(False, 0.0)
        try:
            frame = self.screen.grab()
        except Exception as exc:
            self._log(f"Screen capture failed: {exc}", "error")
            return Hit(False, 0.0)
        hit = self._match(frame, step, template)
        self._report_match(step, hit, tag="test")
        return hit

    def diagnose(self, step: Step) -> diagnose_mod.Diagnosis:
        """Search once with the restrictions removed to explain why ``step`` is (not) found."""
        self._select_setup()
        rel = effective_template(step, self.preset)
        if not rel:
            return diagnose_mod.Diagnosis("absent", "This step has no template image yet.",
                                          ["Capture one with 'Capture template...'."])
        try:
            template = self.templates.get(rel)
            frame = self.screen.grab()
            return diagnose_mod.diagnose(frame, step, template, self.preset, self.matcher)
        except Exception as exc:
            return diagnose_mod.Diagnosis("absent", f"Diagnosis failed: {exc}")

    # ------------------------------------------------------------------ display presets

    def _select_setup(self) -> None:
        """Choose the display preset and monitor (once). Auto-detects from the screen resolutions."""
        if self._setup_done:
            return
        self._setup_done = True
        profile = self.profile
        if not profile.presets:
            return
        try:
            monitors = self.screen.monitors()
            sel = None
            if profile.settings.auto_preset:
                sel = presets_mod.choose(profile, self.screen, self._load_template, self.matcher)
                if sel.preset is None and self.preset is not None:
                    sel = presets_mod.resolve_explicit(self.preset, monitors)
                    sel.reason = f"auto-detect found no match; {sel.reason}"
            elif self.preset is not None:
                sel = presets_mod.resolve_explicit(self.preset, monitors)
            if sel is None or sel.preset is None:
                reason = sel.reason if sel else "no preset selected"
                self._log(f"Display presets: {reason}. Using the default step settings.", "warn")
                return
        except Exception as exc:  # never let detection kill the run
            self._log(f"Display detection failed ({exc}); using the default step settings.", "warn")
            return
        self.preset = sel.preset
        if sel.monitor is not None:
            self.screen.set_monitor(sel.monitor.index)
        level = "warn" if "anyway" in sel.reason else "info"
        self._emit("preset", f"Display preset: {sel.reason}", level, preset=sel.preset.id,
                   monitor=sel.monitor.index if sel.monitor else 0)

    def _load_template(self, rel: str):
        return self.templates.get(rel)

    # ------------------------------------------------------------------ run internals

    def _finish(self, reason: str, message: str, t0: float) -> RunResult:
        level = "info" if reason in (COMPLETED, USER, END_CONDITION, CLICK_LIMIT, CORNER) else "warn"
        if reason in (ERROR, INVALID):
            level = "error"
        self._log(f"Stopped ({reason}): {message}", level)
        result = RunResult(reason, message, self.clicks, self.loops, self.clock.now() - t0, self.dry_run)
        self._emit("finished", message, level, result=result)
        return result

    def _check_idle(self, interval: float) -> None:
        """Called after every loop: prevents a hot spin and stops runaway do-nothing loops."""
        s = self.profile.settings
        if self._actions_this_loop > 0:
            self._idle_loops = 0
            return
        self._idle_loops += 1
        if s.max_idle_loops and self._idle_loops >= s.max_idle_loops:
            raise _Stop(IDLE, f"{self._idle_loops} loops in a row found nothing to do.")
        self._sleep(interval, jitter=False, label=None)

    def _check_abort(self) -> None:
        if self._stop.is_set():
            raise _Stop(self._stop_reason, "Stopped by user (stop hotkey / Stop button).")
        if self.profile.settings.corner_abort:
            try:
                x, y = self.inputs.mouse_position()
                b = self.screen.bounds()
            except Exception:
                return
            tol = CORNER_TOLERANCE
            if not (b.left - tol <= x <= b.right + tol and b.top - tol <= y <= b.bottom + tol):
                return  # cursor is on a monitor we are not capturing: not a corner of ours
            near_x = x <= b.left + tol or x >= b.right - 1 - tol
            near_y = y <= b.top + tol or y >= b.bottom - 1 - tol
            if near_x and near_y:
                raise _Stop(CORNER, "Mouse moved to a screen corner - emergency stop.")

    def _sleep(self, seconds: float, *, jitter: bool, label: Optional[str]) -> None:
        """Interruptible sleep. With ``jitter`` the duration is randomised by +/- jitter%."""
        if seconds <= 0:
            return
        if jitter:
            j = self.profile.settings.jitter_percent / 100.0
            if j > 0:
                seconds = max(0.0, seconds * (1.0 + self.rng.uniform(-j, j)))
        if label and seconds >= 0.05:
            self._log(f"wait {seconds:.2f}s ({label})")
        end = self.clock.now() + seconds
        while True:
            self._check_abort()
            remaining = end - self.clock.now()
            if remaining <= 1e-9:
                return
            self.clock.sleep(min(SLEEP_SLICE, remaining))

    def _waits(self, step: Step) -> tuple[float, float]:
        """(wait before, wait after) in force for ``step``: its own values, or the slider's small fixed ones."""
        if self.profile.settings.speed_manual:
            return step.wait_before, step.wait_after
        return FAST_WAIT, FAST_WAIT

    def _pace(self) -> None:
        """Slider mode: hold back so that clicks are at least click_interval(speed) apart.

        Called just before looking for the next icon, so the screenshot is fresh when the click happens.
        The time the scan + click themselves take (``_overhead``, smoothed) is subtracted, which makes the
        click-to-click spacing land on the chosen interval rather than interval + overhead.
        """
        s = self.profile.settings
        if s.speed_manual or self._last_click_t is None:
            return
        interval = click_interval(s.speed)
        if interval <= 0:
            return
        j = s.jitter_percent / 100.0
        if j > 0:
            interval *= 1.0 + self.rng.uniform(-j, j)
        remaining = self._last_click_t + interval - self._overhead - self.clock.now()
        if remaining > 0.02:
            self._sleep(remaining, jitter=False, label=f"pace, speed {s.speed}%")

    def _run_step(self, step: Step) -> None:
        self._emit("step", f"Step '{step.name}'", step=step.name)
        wait_before, wait_after = self._waits(step)
        self._sleep(wait_before, jitter=True, label=f"before '{step.name}'")

        try:
            template = self.templates.get(effective_template(step, self.preset))
        except ProfileError as exc:
            self._log(f"Step '{step.name}': {exc}", "error")
            self._not_found(step, Hit(False, 0.0))
            return

        attempts = 1 + (step.retries if step.not_found_action == "retry" and not step.click_only_if_found else 0)
        hit = Hit(False, 0.0)
        self._pace()
        self._search_t0 = self.clock.now()
        for attempt in range(1, attempts + 1):
            hit = self._search(step, template)
            if hit.found:
                break
            if attempt < attempts:
                self._log(f"Step '{step.name}': not found (best {hit.confidence:.2f}), retry {attempt}/{step.retries}", "warn")

        if not hit.found:
            self._not_found(step, hit)
            return
        self._act(step, hit)
        self._sleep(wait_after, jitter=True, label=f"after '{step.name}'")

    def _search(self, step: Step, template) -> Hit:
        """Take screenshots until the template matches or the step timeout expires."""
        s = self.profile.settings
        deadline = self.clock.now() + step.timeout
        best = Hit(False, 0.0)
        while True:
            self._check_abort()
            frame = self._grab()
            if frame is not None:
                self._check_end(frame)
                hit = self._match(frame, step, template)
                if hit.confidence > best.confidence:
                    best = hit
                if hit.found:
                    return hit
            remaining = deadline - self.clock.now()
            if remaining <= 1e-9:
                return best
            self._sleep(min(s.scan_interval, remaining), jitter=False, label=None)

    def _grab(self) -> Optional[Frame]:
        try:
            frame = self.screen.grab()
            self._errors = 0
            return frame
        except Exception as exc:
            self._errors += 1
            self._log(f"Screen capture failed ({self._errors}/{MAX_CONSECUTIVE_ERRORS}): {exc}", "error")
            if self._errors >= MAX_CONSECUTIVE_ERRORS:
                raise _Stop(ERROR, "Screen capture keeps failing - check OS screen-recording permission.")
            return None

    def _match(self, frame: Frame, step: Step, template) -> Hit:
        region = None
        box = presets_mod.resolve_region(step, self.preset, frame)
        if box:
            region = frame.region_to_image(box)
            if region is None:
                return Hit(False, 0.0)
        scales = (scale_list(step.scale_min, step.scale_max, first=self._scale_hint.get(step.id))
                  if step.multi_scale else [1.0])
        try:
            m: MatchResult = self.matcher.find(
                frame.image, template, step.threshold, scales=scales, region=region, grayscale=step.grayscale
            )
        except Exception as exc:  # OpenCV error on odd input: treat as a miss, never crash
            self._log(f"Matcher error: {exc}", "error")
            return Hit(False, 0.0)
        if m.w == 0:
            return Hit(False, m.confidence)
        if m.found:
            self._scale_hint[step.id] = m.scale
        return Hit(m.found, m.confidence, frame.rect_to_screen(m.x, m.y, m.w, m.h), m.scale)

    def _check_end(self, frame: Frame) -> None:
        end = self.profile.end_condition
        if not (end and end.enabled and effective_template(end, self.preset)):
            return
        try:
            template = self.templates.get(effective_template(end, self.preset))
        except ProfileError as exc:
            self._log(f"End condition: {exc}", "error")
            return
        hit = self._match(frame, end, template)
        if hit.found:
            self._report_match(end, hit, tag="end")
            raise _Stop(END_CONDITION, f"End condition template found (confidence {hit.confidence:.2f}).")

    def _click_point(self, step: Step, hit: Hit) -> tuple[float, float]:
        cx, cy = hit.center
        return (cx + step.offset_x, cy + step.offset_y)

    def _report_match(self, step: Step, hit: Hit, tag: str = "") -> None:
        if hit.rect.width:
            r = hit.rect
            where = f" at ({r.left:.0f},{r.top:.0f}) {r.width:.0f}x{r.height:.0f} scale {hit.scale:.2f}"
        else:
            where = ""
        verdict = "FOUND" if hit.found else "not found"
        label = f"[{tag}] " if tag else ""
        self._emit(
            "match",
            f"{label}'{step.name}': {verdict}, confidence {hit.confidence:.3f} (threshold {step.threshold:.2f}){where}",
            "info" if hit.found else "warn",
            step=step.name, found=hit.found, confidence=hit.confidence, rect=hit.rect.as_tuple(), tag=tag,
        )

    def _act(self, step: Step, hit: Hit) -> None:
        s = self.profile.settings
        self._report_match(step, hit)
        x, y = self._click_point(step, hit)
        if s.max_total_clicks and self.clicks >= s.max_total_clicks:
            raise _Stop(CLICK_LIMIT, f"Click limit of {s.max_total_clicks} reached.")
        button = "right" if step.click_type == "right" else "left"
        n = 2 if step.click_type == "double" else 1
        if self.dry_run:
            self._emit("click", f"[dry-run] would {step.click_type}-click at ({x:.0f},{y:.0f})",
                       x=x, y=y, dry=True, step=step.name, rect=hit.rect.as_tuple())
        else:
            try:
                self.inputs.click(x, y, button, n)
            except Exception as exc:
                self._log(f"Click failed: {exc}", "error")
                raise _Stop(ERROR, f"Click failed: {exc}")
            self._emit("click", f"{step.click_type}-click at ({x:.0f},{y:.0f})", x=x, y=y, dry=False, step=step.name)
        now = self.clock.now()
        self._overhead = min(1.0, 0.5 * self._overhead + 0.5 * max(0.0, now - self._search_t0))
        self._last_click_t = now
        self.clicks += 1
        self._actions_this_loop += 1
        if s.max_total_clicks and self.clicks >= s.max_total_clicks:
            raise _Stop(CLICK_LIMIT, f"Click limit of {s.max_total_clicks} reached.")

    def _not_found(self, step: Step, hit: Hit) -> None:
        detail = f"best confidence {hit.confidence:.2f} < threshold {step.threshold:.2f}"
        if hit.rect.width:
            detail += f", best candidate at ({hit.rect.left:.0f},{hit.rect.top:.0f}) scale {hit.scale:.2f}"
            if not step.multi_scale and abs(hit.scale - 1.0) < 1e-6:
                detail += "; multi-scale is OFF, so only the exact captured size is searched"
            elif step.multi_scale and (hit.scale <= step.scale_min * 1.08 or hit.scale >= step.scale_max / 1.08):
                detail += ("; the best match is at the EDGE of the scale range - the icon is probably a different "
                           "size than the template (use 'Test this step' for a diagnosis)")
        if step.click_only_if_found:
            self._log(f"Step '{step.name}': not present ({detail}) - skipped (click-only-if-found)")
            return
        action = step.not_found_action
        if action == "key":
            self._log(f"Step '{step.name}': not found ({detail}) - pressing fallback key '{step.fallback_key}'", "warn")
            self._press_key(step)
            self._sleep(self._waits(step)[1], jitter=True, label=f"after '{step.name}'")
        elif action == "retry":
            # retries already used up
            if step.after_retries == "skip":
                self._log(f"Step '{step.name}': not found after {step.retries} retries ({detail}) - skipped", "warn")
            else:
                raise _Stop(STEP_FAILED, f"Step '{step.name}' not found after {step.retries} retries ({detail}).")
        elif action == "stop":
            raise _Stop(STEP_FAILED, f"Step '{step.name}' not found ({detail}).")
        else:
            self._log(f"Step '{step.name}': not found ({detail}) - skipped", "warn")

    def _press_key(self, step: Step) -> None:
        if not step.fallback_key:
            self._log(f"Step '{step.name}': no fallback key configured", "warn")
            return
        if self.dry_run:
            self._emit("key", f"[dry-run] would press '{step.fallback_key}'", key=step.fallback_key, dry=True)
        else:
            try:
                self.inputs.press_key(step.fallback_key)
            except Exception as exc:
                self._log(f"Key press failed: {exc}", "error")
                return
            self._emit("key", f"pressed key '{step.fallback_key}'", key=step.fallback_key, dry=False)
        self._actions_this_loop += 1
