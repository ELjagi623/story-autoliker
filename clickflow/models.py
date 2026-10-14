"""Profile data model: Steps, global settings and the Profile container.

A profile is serialised to ``profile.json`` inside its own folder; template images
live next to it in ``templates/``.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = 3  # 3: speed slider; 2: the template scale search range defaults to 0.35-2.5 (was 0.7-1.4)

DEFAULT_SCALE_MIN = 0.35
DEFAULT_SCALE_MAX = 2.5
OLD_SCALE_RANGE = (0.7, 1.4)  # schema 1 default; migrated on load

CLICK_TYPES = ("left", "right", "double")
NOT_FOUND_ACTIONS = ("skip", "retry", "stop", "key")
AFTER_RETRY_ACTIONS = ("skip", "stop")

MIN_THRESHOLD = 0.5
MAX_THRESHOLD = 1.0


# ---- speed: one slider for "how long from one click to the next"
SPEED_MIN, SPEED_MAX = 0, 100
FAST_INTERVAL = 0.25  # seconds between clicks at the fastest setting (what the scan + click themselves take)
SLOW_INTERVAL = 1.5  # seconds between clicks at the slowest setting
FAST_WAIT = 0.05  # per-step wait before / after used while the slider is in charge (small; the pacing does the rest)


def click_interval(speed: float) -> float:
    """Minimum seconds between two clicks for a speed setting (0 = slowest, 100 = fastest).

    100 means "no added delay at all" (returns 0.0); below that the interval grows geometrically from
    FAST_INTERVAL up to SLOW_INTERVAL, so every step on the slider feels like the same relative change.
    """
    speed = max(SPEED_MIN, min(SPEED_MAX, float(speed)))
    if speed >= SPEED_MAX:
        return 0.0
    return FAST_INTERVAL * (SLOW_INTERVAL / FAST_INTERVAL) ** ((SPEED_MAX - speed) / (SPEED_MAX - SPEED_MIN))


def display_interval(speed: float) -> float:
    """The interval shown to the user: never below what a scan + click physically takes."""
    return max(FAST_INTERVAL, click_interval(speed))


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _pick(cls, data: dict[str, Any]) -> dict[str, Any]:
    """Keep only keys that are fields of ``cls`` (forward/backward compatible loading)."""
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in names}


@dataclass
class Step:
    name: str = "New step"
    id: str = field(default_factory=_new_id)
    enabled: bool = True
    template: str = ""  # file name relative to the profile folder, e.g. "templates/heart_ab12cd34.png"
    threshold: float = 0.85
    # Search region in screen (input) coordinates: left, top, width, height. None = whole screen.
    region: Optional[tuple[int, int, int, int]] = None
    offset_x: int = 0
    offset_y: int = 0
    click_type: str = "left"
    wait_before: float = 0.0
    wait_after: float = 1.0
    timeout: float = 5.0  # seconds to keep looking; 0 = look exactly once
    not_found_action: str = "skip"
    retries: int = 2
    after_retries: str = "stop"  # what to do once all retries failed
    fallback_key: str = "esc"
    # "Click only if found": a missing icon is not a failure; the step is silently skipped.
    click_only_if_found: bool = False
    # Matching options
    multi_scale: bool = True
    scale_min: float = DEFAULT_SCALE_MIN  # template sizes tried, relative to the captured size
    scale_max: float = DEFAULT_SCALE_MAX
    grayscale: bool = True

    def normalise(self) -> "Step":
        """Clamp every field into its legal range (used after loading / GUI edits)."""
        self.threshold = _clamp(float(self.threshold), MIN_THRESHOLD, MAX_THRESHOLD)
        self.wait_before = max(0.0, float(self.wait_before))
        self.wait_after = max(0.0, float(self.wait_after))
        self.timeout = max(0.0, float(self.timeout))
        self.retries = max(0, int(self.retries))
        self.scale_min = _clamp(float(self.scale_min), 0.1, 1.0)
        self.scale_max = _clamp(float(self.scale_max), 1.0, 5.0)
        if self.click_type not in CLICK_TYPES:
            self.click_type = "left"
        if self.not_found_action not in NOT_FOUND_ACTIONS:
            self.not_found_action = "skip"
        if self.after_retries not in AFTER_RETRY_ACTIONS:
            self.after_retries = "stop"
        if self.region is not None:
            r = tuple(int(v) for v in self.region)
            self.region = r if len(r) == 4 and r[2] > 0 and r[3] > 0 else None
        return self

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["region"] = list(self.region) if self.region else None
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Step":
        data = dict(_pick(cls, data))
        if data.get("region"):
            data["region"] = tuple(data["region"])
        else:
            data["region"] = None
        return cls(**data).normalise()


@dataclass
class Preset:
    """Per-display overrides: where to look (search boxes) and, optionally, which template image to use.

    A preset belongs to a display *resolution* (``resolution`` = width x height of one monitor as the OS
    reports it). When a monitor with that resolution is present, ClickFlow selects the preset automatically.
    Search boxes are stored relative to the monitor's top-left corner, so they survive moving monitors
    around in the OS display settings.
    """

    name: str = "Preset"
    id: str = field(default_factory=_new_id)
    resolution: tuple[int, int] = (0, 0)
    monitor: int = 0  # preferred mss monitor index (1-based) when several monitors share the resolution; 0 = any
    # step id -> (left, top, width, height) relative to the monitor; a missing entry means "whole monitor"
    regions: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)
    # step id -> template file used instead of the step's own template on this display
    templates: dict[str, str] = field(default_factory=dict)

    def normalise(self) -> "Preset":
        w, h = (int(v) for v in (list(self.resolution) + [0, 0])[:2])
        self.resolution = (max(0, w), max(0, h))
        self.monitor = max(0, int(self.monitor))
        clean: dict[str, tuple[int, int, int, int]] = {}
        for k, r in (self.regions or {}).items():
            r = tuple(int(v) for v in r)
            if len(r) == 4 and r[2] > 0 and r[3] > 0:
                clean[str(k)] = r
        self.regions = clean
        self.templates = {str(k): str(v) for k, v in (self.templates or {}).items() if v}
        return self

    @property
    def label(self) -> str:
        w, h = self.resolution
        return f"{self.name} ({w}x{h})" if w and h else self.name

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "id": self.id, "resolution": list(self.resolution), "monitor": self.monitor,
            "regions": {k: list(v) for k, v in self.regions.items()},
            "templates": dict(self.templates),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Preset":
        d = dict(_pick(cls, data))
        d["resolution"] = tuple(d.get("resolution") or (0, 0))
        return cls(**d).normalise()


def effective_region(step: "Step", preset: Optional[Preset]) -> Optional[tuple[int, int, int, int]]:
    """The search box that applies to ``step``: the preset's (monitor-relative) one, or the step's own."""
    if preset is None:
        return step.region
    return preset.regions.get(step.id)


def set_region(step: "Step", preset: Optional[Preset], region: Optional[tuple[int, int, int, int]]) -> None:
    if preset is None:
        step.region = tuple(region) if region else None
    elif region:
        preset.regions[step.id] = tuple(int(v) for v in region)
    else:
        preset.regions.pop(step.id, None)


def effective_template(step: "Step", preset: Optional[Preset]) -> str:
    """Template file for ``step`` on this display: the preset's override if any, else the step's own."""
    if preset is not None and preset.templates.get(step.id):
        return preset.templates[step.id]
    return step.template


def set_template(step: "Step", preset: Optional[Preset], rel: str) -> None:
    if preset is None:
        step.template = rel
    else:
        preset.templates[step.id] = rel


@dataclass
class Settings:
    loop_count: int = 1
    infinite_loop: bool = False
    jitter_percent: float = 20.0  # random +/- percentage applied to every wait
    max_total_clicks: int = 0  # 0 = no limit
    stop_hotkey: str = "F8"
    corner_abort: bool = True  # moving the mouse into a screen corner stops the run
    scan_interval: float = 0.25  # seconds between screenshots while waiting for an icon
    start_delay: float = 3.0  # seconds before the first action (time to switch windows)
    minimize_on_run: bool = True
    max_idle_loops: int = 10  # stop after this many loops that did nothing (0 = never)
    monitor: int = 0  # mss monitor index: 0 = all screens combined, 1 = primary, ...
    # Pick the display preset (and the monitor) automatically from the detected screen resolutions at start.
    auto_preset: bool = True
    active_preset: str = ""  # id of the preset being edited / last used; "" = the default (no preset)
    # Speed: with the slider in charge (speed_manual False) every step waits FAST_WAIT before/after and the
    # Runner keeps at least click_interval(speed) seconds between clicks. In manual ("advanced") mode each
    # step's own wait_before / wait_after apply instead and no spacing is enforced.
    speed: int = 50
    speed_manual: bool = False

    def normalise(self) -> "Settings":
        self.loop_count = max(1, int(self.loop_count))
        self.jitter_percent = _clamp(float(self.jitter_percent), 0.0, 100.0)
        self.max_total_clicks = max(0, int(self.max_total_clicks))
        self.scan_interval = max(0.02, float(self.scan_interval))
        self.start_delay = max(0.0, float(self.start_delay))
        self.max_idle_loops = max(0, int(self.max_idle_loops))
        self.monitor = max(0, int(self.monitor))
        self.speed = int(max(SPEED_MIN, min(SPEED_MAX, round(float(self.speed)))))
        self.stop_hotkey = str(self.stop_hotkey or "").strip()
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        return cls(**_pick(cls, data)).normalise()


def _legacy_speed(profile: "Profile") -> tuple[bool, int]:
    """(speed_manual, speed) for a profile saved before the speed slider existed.

    Waits that are uniform and already tiny (<= 0.1 s before and after on every enabled step) are exactly what the
    slider's fastest setting does, so such profiles open in slider mode at 100%. Anything else keeps its own
    per-step waits (manual mode), so existing timing never changes behind the user's back.
    """
    steps = [s for s in profile.steps if s.enabled]
    if steps and all(abs(s.wait_before - s.wait_after) < 1e-9 and s.wait_before <= 0.1 + 1e-9 for s in steps) \
            and len({round(s.wait_before, 6) for s in steps}) == 1:
        return False, SPEED_MAX
    return True, 50


@dataclass
class Profile:
    name: str = "Untitled"
    notes: str = ""
    settings: Settings = field(default_factory=Settings)
    steps: list[Step] = field(default_factory=list)
    # Optional end condition: when this template is seen on screen the run stops.
    # It is a Step whose ``enabled`` flag switches the check on; click fields are ignored.
    end_condition: Optional[Step] = None
    presets: list[Preset] = field(default_factory=list)
    version: int = SCHEMA_VERSION
    # Folder holding profile.json and templates/. Not serialised.
    directory: Optional[Path] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "notes": self.notes,
            "settings": self.settings.to_dict(),
            "steps": [s.to_dict() for s in self.steps],
            "end_condition": self.end_condition.to_dict() if self.end_condition else None,
            "presets": [p.to_dict() for p in self.presets],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], directory: Optional[Path] = None) -> "Profile":
        prof = cls._from_dict(data, directory)
        if "speed_manual" not in (data.get("settings") or {}):
            prof.settings.speed_manual, prof.settings.speed = _legacy_speed(prof)
        if prof.version < 2:  # schema 1 profiles carry the old narrow default scale range: widen it
            for st in list(prof.steps) + ([prof.end_condition] if prof.end_condition else []):
                if (st.scale_min, st.scale_max) == OLD_SCALE_RANGE:
                    st.scale_min, st.scale_max = DEFAULT_SCALE_MIN, DEFAULT_SCALE_MAX
        prof.version = SCHEMA_VERSION
        return prof

    @classmethod
    def _from_dict(cls, data: dict[str, Any], directory: Optional[Path] = None) -> "Profile":
        end = data.get("end_condition")
        return cls(
            name=str(data.get("name", "Untitled")),
            notes=str(data.get("notes", "")),
            settings=Settings.from_dict(data.get("settings", {}) or {}),
            steps=[Step.from_dict(s) for s in data.get("steps", []) or []],
            end_condition=Step.from_dict(end) if end else None,
            presets=[Preset.from_dict(p) for p in data.get("presets", []) or []],
            version=int(data.get("version", SCHEMA_VERSION)),
            directory=Path(directory) if directory else None,
        )

    def preset_by_id(self, preset_id: str) -> Optional[Preset]:
        return next((p for p in self.presets if p.id == preset_id), None)

    def remove_step_refs(self, step_id: str) -> None:
        """Forget a deleted step in every preset."""
        for p in self.presets:
            p.regions.pop(step_id, None)
            p.templates.pop(step_id, None)

    def validate(self, preset: Optional[Preset] = None) -> list[str]:
        """Return human readable problems that would prevent a run.

        With ``preset=None`` a step counts as having a template if its own template or *any* preset
        supplies one (the preset in use is only known once the displays have been detected).
        """
        def has_template(s: Step) -> bool:
            if preset is not None:
                return bool(effective_template(s, preset))
            return bool(s.template) or any(p.templates.get(s.id) for p in self.presets)

        problems: list[str] = []
        enabled = [s for s in self.steps if s.enabled]
        if not enabled:
            problems.append("The profile has no enabled steps.")
        for s in enabled:
            if not has_template(s):
                problems.append(f"Step '{s.name}' has no template image - capture one first.")
        e = self.end_condition
        if e and e.enabled and not has_template(e):
            problems.append("The end condition is enabled but has no template image.")
        return problems
