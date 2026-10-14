"""Application entry point."""
from __future__ import annotations

import logging
import logging.handlers
import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Optional

from . import __version__, platform_utils, storage

EXAMPLE_NAME = "instagram_story_like"


def _resource_root() -> Path:
    """Project root (or the PyInstaller bundle directory when frozen)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


resource_root = _resource_root


def ensure_example() -> Optional[Path]:
    """Copy the bundled default profile into the user's profiles folder (once). Returns its folder."""
    src = _resource_root() / "examples" / EXAMPLE_NAME
    dst = storage.profiles_root() / EXAMPLE_NAME
    if not src.exists():
        return dst if dst.exists() else None
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
    return dst


def startup_profile(path: Optional[str] = None):
    """Profile to open at start: the given path, else the one used last time, else the bundled example."""
    candidates = [Path(path)] if path else []
    if not path:
        last = storage.last_profile_dir()
        if last:
            candidates.append(last)
        example = ensure_example()
        if example:
            candidates.append(example)
    for c in candidates:
        try:
            return storage.load_profile(c)
        except storage.ProfileError:
            continue
    return None


def setup_logging() -> None:
    folder = storage.default_home() / "logs"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(folder / "clickflow.log", maxBytes=500_000, backupCount=2,
                                                       encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        root = logging.getLogger("clickflow")
        root.setLevel(logging.INFO)
        root.addHandler(handler)
    except OSError:
        pass


def install_crash_handler() -> None:
    """A windowed build has no console: write uncaught exceptions to the log and tell the user where it is."""

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        logging.getLogger("clickflow").error("Uncaught exception:\n%s", text)
        try:
            crash = storage.default_home() / "logs" / "crash.log"
            crash.parent.mkdir(parents=True, exist_ok=True)
            with open(crash, "a", encoding="utf-8") as f:
                f.write(text + "\n")
            from PySide6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                QMessageBox.critical(None, "ClickFlow - unexpected error",
                                     f"{exc_type.__name__}: {exc}\n\nDetails were written to:\n{crash}")
        except Exception:
            pass

    sys.excepthook = hook


def set_window_icon(app) -> None:
    from PySide6.QtGui import QIcon

    icon = _resource_root() / "assets" / "icon.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))


# ---------------------------------------------------------------- self-test (used to verify a packaged build)

def selftest(out_path: Optional[str] = None) -> int:
    """Check that everything a run needs is present and working, without touching the user's data.

    ``ClickFlow.exe --selftest result.txt`` writes the report to ``result.txt`` (a windowed exe has no console).
    Screen capture is reported as a warning only: it legitimately fails on a locked or headless desktop.
    """
    lines: list[str] = []
    state = {"ok": True}

    def check(name: str, fn, warn_only: bool = False) -> None:
        try:
            lines.append(f"OK    {name}: {fn()}")
        except Exception as exc:
            lines.append(f"{'WARN ' if warn_only else 'FAIL '} {name}: {type(exc).__name__}: {exc}")
            if not warn_only:
                state["ok"] = False

    home = tempfile.mkdtemp(prefix="clickflow_selftest_")
    import os

    os.environ["CLICKFLOW_HOME"] = home  # never touch the real ~/ClickFlow

    def versions():
        import cv2, mss, numpy  # noqa: E401
        import PySide6

        return (f"clickflow {__version__}, python {sys.version.split()[0]}, numpy {numpy.__version__}, "
                f"opencv {cv2.__version__}, mss {mss.__version__}, PySide6 {PySide6.__version__}, "
                f"os {platform_utils.os_name()}, frozen={getattr(sys, 'frozen', False)}")

    def matcher():
        import cv2, numpy as np  # noqa: E401

        from .matcher import Matcher, scale_list

        rng = np.random.default_rng(1)
        shot = rng.integers(0, 255, (200, 300, 3), dtype=np.uint8)
        tpl = shot[60:100, 120:170].copy()
        small = cv2.resize(tpl, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        shot2 = rng.integers(0, 255, (200, 300, 3), dtype=np.uint8)
        shot2[60:60 + small.shape[0], 120:120 + small.shape[1]] = small
        r = Matcher().find(shot2, tpl, 0.8, scales=scale_list(0.35, 2.5))
        assert r.found and abs(r.x - 120) <= 2 and abs(r.y - 60) <= 2, r
        return f"found half-size template at ({r.x},{r.y}) confidence {r.confidence:.2f} scale {r.scale:.2f}"

    def default_profile():
        from .models import Profile  # noqa: F401

        path = ensure_example()
        prof = storage.load_profile(path)
        problems = prof.validate()
        assert not problems, problems
        assert all(s.region is None for s in prof.steps), "default search boxes should be empty"
        return f"'{prof.name}', {len(prof.steps)} steps, speed {prof.settings.speed}%, templates load"

    def templates_load():
        prof = storage.load_profile(storage.profiles_root() / EXAMPLE_NAME)
        store = storage.TemplateStore(prof.directory)
        sizes = [store.get(s.template).shape[:2] for s in prof.steps]
        return f"template sizes {sizes}"

    def licenses():
        root = _resource_root()
        names = ["LICENSE", "THIRD_PARTY_NOTICES.md", "LICENSES"]
        missing = [n for n in names if not (root / n).exists()]
        assert not missing, f"missing in bundle: {missing}"
        return "LICENSE, THIRD_PARTY_NOTICES.md, LICENSES/ present"

    def gui():
        from PySide6.QtWidgets import QApplication

        from .gui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        win = MainWindow(storage.load_profile(storage.profiles_root() / EXAMPLE_NAME), start_hotkey=False)
        n = win.step_list.count()
        speed = win.lbl_speed.text()
        win.show()  # really creates the native window: proves the Qt platform plugin loaded
        app.processEvents()
        shown = win.isVisible()
        win.dirty = False
        win.close()
        assert n == 2 and shown
        return f"main window built and shown (platform '{app.platformName()}'), {n} steps, speed bar: '{speed}'"

    def input_layer():
        from .inputs import PyAutoGuiInput

        x, y = PyAutoGuiInput().mouse_position()
        return f"pyautogui ok, cursor at ({x:.0f},{y:.0f})"

    def hotkeys():
        from .hotkey import parse_hotkey
        from .keystate import StopKeyWatcher, vk_codes

        assert parse_hotkey("F8") == "<f8>" and vk_codes("F8") == [0x77]
        try:
            import pynput  # noqa: F401

            pn = "pynput importable"
        except Exception as exc:
            pn = f"pynput unavailable ({exc})"
        return f"parse ok, key-state polling supported={StopKeyWatcher.supported()}, {pn}"

    def capture():
        from .screen import MssScreen

        s = MssScreen(0)
        f = s.grab()
        return f"captured {f.image.shape[1]}x{f.image.shape[0]}, monitors: " + ", ".join(m.label for m in s.monitors())

    check("versions", versions)
    check("matcher (multi-scale)", matcher)
    check("default profile", default_profile)
    check("templates", templates_load)
    check("license files", licenses)
    check("main window", gui)
    check("input layer", input_layer)
    check("stop hotkey", hotkeys)
    check("screen capture", capture, warn_only=True)
    lines.append("RESULT: " + ("ALL OK" if state["ok"] else "FAILED"))
    text = "\n".join(lines)
    if out_path:
        Path(out_path).write_text(text + "\n", encoding="utf-8")
    try:
        print(text)
    except Exception:
        pass
    shutil.rmtree(home, ignore_errors=True)
    return 0 if state["ok"] else 1


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--version" in argv:
        print(f"ClickFlow {__version__}")
        return 0
    if "--selftest" in argv:
        i = argv.index("--selftest")
        out = argv[i + 1] if len(argv) > i + 1 and not argv[i + 1].startswith("-") else None
        platform_utils.ensure_dpi_aware()
        return selftest(out)
    platform_utils.ensure_dpi_aware()  # before Qt creates windows
    from PySide6.QtWidgets import QApplication

    from .gui.main_window import MainWindow

    setup_logging()
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("ClickFlow")
    app.setApplicationVersion(__version__)
    install_crash_handler()
    set_window_icon(app)
    profile = startup_profile(argv[1] if len(argv) > 1 else None)
    win = MainWindow(profile)
    win.show()
    for issue in platform_utils.check_permissions():
        win.append_log(f"{issue.name}: {issue.message}", "error")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
