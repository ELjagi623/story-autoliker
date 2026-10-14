import cv2
import numpy as np
import pytest

from clickflow.matcher import Matcher, scale_list

from helpers import make_arrow, make_background, make_heart, paste


@pytest.fixture
def matcher():
    return Matcher()


def center_of(r):
    return r.x + r.w / 2, r.y + r.h / 2


def test_exact_match_position(matcher):
    bg = make_background(seed=3)
    icon = make_heart(48)
    shot = paste(bg, icon, 321, 123)
    r = matcher.find(shot, icon, 0.9)
    assert r.found and r.confidence > 0.99
    assert (r.x, r.y, r.w, r.h) == (321, 123, 48, 48)


@pytest.mark.parametrize("scale", [0.7, 0.8, 0.9, 1.1, 1.25, 1.4])
def test_multi_scale_finds_resized_icon(matcher, scale):
    bg = make_background(seed=4)
    template = make_heart(48)
    on_screen = cv2.resize(template, None, fx=scale, fy=scale,
                           interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    shot = paste(bg, on_screen, 400, 300)
    r = matcher.find(shot, template, 0.8, scales=scale_list(0.7, 1.4))
    assert r.found, f"scale {scale}: confidence {r.confidence:.2f}"
    cx, cy = center_of(r)
    expect = 400 + on_screen.shape[1] / 2, 300 + on_screen.shape[0] / 2
    assert abs(cx - expect[0]) <= 3 and abs(cy - expect[1]) <= 3
    assert abs(r.scale - scale) <= 0.08


def test_single_scale_misses_resized_icon_but_multi_scale_finds_it(matcher):
    bg = make_background(seed=5)
    template = make_heart(48)
    big = cv2.resize(template, None, fx=1.3, fy=1.3, interpolation=cv2.INTER_CUBIC)
    shot = paste(bg, big, 100, 100)
    assert not matcher.find(shot, template, 0.85, scales=[1.0]).found
    assert matcher.find(shot, template, 0.85, scales=scale_list(0.7, 1.5)).found


@pytest.mark.parametrize("sigma", [4, 10, 18])
def test_noise_tolerance(matcher, sigma):
    rng = np.random.default_rng(7)
    bg = make_background(seed=6)
    icon = make_arrow(40)
    shot = paste(bg, icon, 500, 222).astype(np.float32)
    shot += rng.normal(0, sigma, shot.shape)
    shot = np.clip(shot, 0, 255).astype(np.uint8)
    r = matcher.find(shot, icon, 0.7)
    assert r.found
    assert abs(r.x - 500) <= 1 and abs(r.y - 222) <= 1


def test_missing_template_not_found_but_reports_confidence(matcher):
    bg = make_background(seed=8)
    r = matcher.find(bg, make_heart(48), 0.85, scales=scale_list(0.7, 1.4))
    assert not r.found
    assert 0.0 <= r.confidence < 0.85


def test_distinguishes_similar_icons(matcher):
    """Outline heart template must not match a filled heart at the 0.85 threshold."""
    bg = make_background(seed=9)
    shot = paste(bg, make_heart(48, filled=True), 200, 200)
    r = matcher.find(shot, make_heart(48, filled=False), 0.85)
    assert not r.found


def test_region_limits_search_and_offsets_result(matcher):
    bg = make_background(seed=10)
    icon = make_heart(48)
    shot = paste(bg, icon, 600, 400)
    assert matcher.find(shot, icon, 0.9, region=(600 - 10, 400 - 10, 600 + 60, 400 + 60)).found
    r = matcher.find(shot, icon, 0.9, region=(0, 0, 300, 300))
    assert not r.found
    r = matcher.find(shot, icon, 0.9, region=(550, 350, 700, 500))
    assert r.found and (r.x, r.y) == (600, 400)  # reported in full-image coordinates


def test_template_larger_than_image_does_not_crash(matcher):
    r = matcher.find(np.zeros((20, 20, 3), np.uint8), make_heart(48), 0.8, scales=scale_list(0.7, 1.4))
    assert not r.found


def test_flat_template_does_not_crash_or_false_match(matcher):
    flat = np.full((30, 30, 3), 128, np.uint8)
    bg = make_background(seed=11)
    r = matcher.find(bg, flat, 0.9)
    assert not r.found
    assert not np.isnan(r.confidence)


def test_color_and_gray_modes_agree_on_clear_match(matcher):
    bg = make_background(seed=12)
    icon = make_heart(48)
    shot = paste(bg, icon, 50, 60)
    assert matcher.find(shot, icon, 0.9, grayscale=True).found
    assert matcher.find(shot, icon, 0.9, grayscale=False).found


def test_scale_list_contains_one_first_and_covers_range():
    s = scale_list(0.7, 1.4)
    assert s[0] == 1.0
    assert min(s) <= 0.71 and max(s) >= 1.39
    assert len(s) == len(set(s))


def test_textured_template_on_flat_screen_does_not_false_match(matcher):
    black = np.zeros((300, 400, 3), np.uint8)
    white = np.full((300, 400, 3), 255, np.uint8)
    for flat in (black, white):
        r = matcher.find(flat, make_heart(48), 0.85, scales=scale_list(0.7, 1.4))
        assert not r.found
