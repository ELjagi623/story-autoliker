import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Never touch the real ~/ClickFlow during tests."""
    monkeypatch.setenv("CLICKFLOW_HOME", str(tmp_path / "home"))


def pytest_report_header(config):
    from clickflow import platform_utils

    ok, why = platform_utils.display_available()
    return f"ClickFlow: os={platform_utils.os_name()} display={'available' if ok else 'NOT available: ' + why}"


@pytest.fixture(scope="session")
def display():
    """(available, reason). Real-display tests skip with a clear message when False."""
    from clickflow import platform_utils

    return platform_utils.display_available()


@pytest.fixture(scope="session")
def qapp(display):
    """One QApplication for the whole session. Falls back to Qt's offscreen platform when there is no display."""
    if not display[0]:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def needs_display(display):
    if not display[0]:
        pytest.skip(f"no usable display: {display[1]} - end-to-end test with real mouse/screen NOT verified")
