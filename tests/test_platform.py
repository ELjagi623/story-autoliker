import pytest

from clickflow import platform_utils
from clickflow.hotkey import parse_hotkey
from clickflow.screen import Frame

import numpy as np


@pytest.mark.parametrize("text,expected", [
    ("F8", "<f8>"), ("f12", "<f12>"), ("Ctrl+Shift+S", "<ctrl>+<shift>+s"),
    ("esc", "<esc>"), ("Alt+F4", "<alt>+<f4>"), ("pageup", "<page_up>"),
])
def test_parse_hotkey(text, expected):
    assert parse_hotkey(text) == expected


@pytest.mark.parametrize("bad", ["", "   ", "ctrl+", "banana", "f99"])
def test_parse_hotkey_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_hotkey(bad)


def test_os_name_is_known():
    assert platform_utils.os_name() in ("windows", "macos", "linux")


def test_frame_coordinate_conversions_retina():
    f = Frame(np.zeros((200, 400, 3), np.uint8), left=10, top=20, scale_x=2.0, scale_y=2.0)
    assert f.to_screen(100, 60) == (60.0, 50.0)
    assert f.to_image(60, 50) == (100.0, 60.0)
    assert f.bounds.width == 200 and f.bounds.height == 100
    assert f.region_to_image((10, 20, 50, 25)) == (0, 0, 100, 50)
    assert f.region_to_image((5000, 5000, 10, 10)) is None


def test_input_to_qt_factor():
    f = platform_utils.input_to_qt_factor(1.5)
    assert f == pytest.approx(1.0 if platform_utils.os_name() == "macos" else 1 / 1.5)
