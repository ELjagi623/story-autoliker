"""OS detection, DPI awareness and permission checks."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

_dpi_done = False


def os_name() -> str:
    """'windows', 'macos' or 'linux'."""
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def ensure_dpi_aware() -> None:
    """Make the process per-monitor DPI aware on Windows so screenshots, clicks and the
    mouse position all use the same physical-pixel coordinates. No-op elsewhere
    (macOS reports points for input and mss handles the Retina pixel scale)."""
    global _dpi_done
    if _dpi_done or os_name() != "windows":
        return
    _dpi_done = True
    try:
        import ctypes

        try:
            # PER_MONITOR_AWARE_V2 (same mode Qt 6 selects)
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # already set by Qt / older Windows - harmless
        pass


@dataclass
class PermissionIssue:
    name: str
    message: str


def check_permissions() -> list[PermissionIssue]:
    """Return problems that will stop ClickFlow from working on this OS (empty = fine)."""
    issues: list[PermissionIssue] = []
    system = os_name()
    if system == "macos":
        issues += _check_macos()
    elif system == "linux":
        if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" and not os.environ.get("DISPLAY"):
            issues.append(
                PermissionIssue(
                    "Wayland",
                    "ClickFlow needs an X11 session: screen capture and synthetic input are blocked "
                    "on Wayland. Log in with an 'X11' / 'Xorg' session.",
                )
            )
        elif not os.environ.get("DISPLAY"):
            issues.append(PermissionIssue("Display", "No DISPLAY found; a graphical session is required."))
    return issues


def _check_macos() -> list[PermissionIssue]:
    issues: list[PermissionIssue] = []
    try:
        import Quartz  # type: ignore

        if hasattr(Quartz, "CGPreflightScreenCaptureAccess") and not Quartz.CGPreflightScreenCaptureAccess():
            try:
                Quartz.CGRequestScreenCaptureAccess()
            except Exception:
                pass
            issues.append(
                PermissionIssue(
                    "Screen Recording",
                    "Screen Recording permission is missing.\n"
                    "Open System Settings > Privacy & Security > Screen Recording, enable your terminal "
                    "(or the ClickFlow app), then restart ClickFlow.",
                )
            )
    except ImportError:
        pass
    try:
        from ApplicationServices import AXIsProcessTrusted  # type: ignore

        if not AXIsProcessTrusted():
            issues.append(
                PermissionIssue(
                    "Accessibility",
                    "Accessibility permission is missing, so ClickFlow cannot click.\n"
                    "Open System Settings > Privacy & Security > Accessibility, enable your terminal "
                    "(or the ClickFlow app), then restart ClickFlow. The global stop hotkey may also "
                    "need Input Monitoring permission.",
                )
            )
    except ImportError:
        pass
    return issues


def display_available() -> tuple[bool, str]:
    """Is a real screen capturable in this process? Returns (ok, reason-if-not)."""
    system = os_name()
    if system == "linux" and not os.environ.get("DISPLAY"):
        return False, "no DISPLAY environment variable (headless session)"
    try:
        import mss
        import numpy as np

        factory = getattr(mss, "MSS", None) or mss.mss
        with factory() as sct:
            shot = sct.grab(sct.monitors[0])
            if shot.width < 2 or shot.height < 2:
                return False, "screen capture returned an empty image"
            arr = np.frombuffer(shot.bgra, dtype=np.uint8)
            if arr.size == 0:
                return False, "screen capture returned no data"
    except Exception as exc:  # no display, permission denied, ...
        return False, f"screen capture failed: {exc}"
    return True, ""


def input_to_qt_factor(device_pixel_ratio: float) -> float:
    """Multiplier turning input coordinates into Qt logical coordinates.

    Windows/Linux input coordinates are physical pixels (Qt logical = physical / dpr);
    macOS input coordinates are already points (= Qt logical).
    """
    if os_name() == "macos":
        return 1.0
    return 1.0 / max(device_pixel_ratio, 0.01)
