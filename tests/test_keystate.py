import threading
import time

import pytest

from clickflow.keystate import StopKeyWatcher, vk_codes


def test_vk_codes():
    assert vk_codes("F8") == [0x77]
    assert vk_codes("ctrl+shift+s") == [0x11, 0x10, ord("S")]
    assert vk_codes("esc") == [0x1B]
    for bad in ("", "ctrl", "banana", "f99"):
        with pytest.raises(ValueError):
            vk_codes(bad)


class FakeKeys:
    """Simulates GetAsyncKeyState: set .down to the held VK codes; .tapped for 'pressed since last call'."""

    def __init__(self):
        self.down, self.tapped, self.lock = set(), set(), threading.Lock()

    def __call__(self, vk):
        with self.lock:
            s = 0x8000 if vk in self.down else 0
            if vk in self.tapped:
                s |= 0x0001
                self.tapped.discard(vk)
            return s


def wait_for(cond, timeout=1.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end and not cond():
        time.sleep(0.005)
    return cond()


def test_fires_on_press_once_per_press():
    keys, hits = FakeKeys(), []
    w = StopKeyWatcher("F8", lambda: hits.append(1), poll=0.005, get_state=keys)
    assert w.start()
    try:
        time.sleep(0.05)
        assert not hits
        keys.down.add(0x77)
        assert wait_for(lambda: hits)
        time.sleep(0.1)
        assert len(hits) == 1  # holding the key does not retrigger
        keys.down.clear()
        time.sleep(0.05)
        keys.down.add(0x77)
        assert wait_for(lambda: len(hits) == 2)
    finally:
        w.stop()


def test_catches_a_tap_shorter_than_the_poll_interval():
    keys, hits = FakeKeys(), []
    w = StopKeyWatcher("F8", lambda: hits.append(1), poll=0.05, get_state=keys)
    w.start()
    try:
        keys.tapped.add(0x77)  # pressed and released between two polls
        assert wait_for(lambda: hits)
    finally:
        w.stop()


def test_modifier_combo_needs_all_keys():
    keys, hits = FakeKeys(), []
    w = StopKeyWatcher("ctrl+s", lambda: hits.append(1), poll=0.005, get_state=keys)
    w.start()
    try:
        keys.down.add(ord("S"))
        time.sleep(0.1)
        assert not hits  # ctrl is not held
        keys.down.clear()
        keys.down.update({0x11, ord("S")})
        assert wait_for(lambda: hits)
    finally:
        w.stop()


def test_invalid_hotkey_does_not_start():
    w = StopKeyWatcher("nonsense", lambda: None, get_state=lambda vk: 0)
    assert not w.start() and w.error


@pytest.mark.skipif(not StopKeyWatcher.supported(), reason="OS key-state polling is Windows-only")
def test_real_f8_keypress_is_detected(needs_display):
    import pyautogui

    hits = []
    w = StopKeyWatcher("F8", lambda: hits.append(1))
    assert w.start()
    try:
        time.sleep(0.1)
        pyautogui.keyDown("f8"); time.sleep(0.06); pyautogui.keyUp("f8")  # a physical tap lasts ~50-150 ms
        assert wait_for(lambda: hits, 2.0), "real F8 keypress was not seen by the watcher"
    finally:
        w.stop()
