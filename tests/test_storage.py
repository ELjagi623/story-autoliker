import json
import zipfile

import numpy as np
import pytest

from clickflow import storage
from clickflow.models import Profile, Settings, Step
from clickflow.storage import ProfileError

from helpers import make_heart


def sample_profile(tmp_path):
    p = storage.new_profile("Röund Trip 测试", root=tmp_path / "profiles")
    p.notes = "some notes"
    p.settings = Settings(loop_count=7, infinite_loop=True, jitter_percent=33.0, max_total_clicks=12,
                          stop_hotkey="F9", monitor=1, start_delay=1.5).normalise()
    a = Step(name="Heart", threshold=0.91, region=(10, 20, 300, 200), offset_x=4, offset_y=-6,
             click_type="double", wait_before=0.3, wait_after=2.0, timeout=7.5,
             not_found_action="retry", retries=4, after_retries="skip", fallback_key="ctrl+w",
             click_only_if_found=True, multi_scale=False, scale_min=0.8, scale_max=1.2, grayscale=False)
    b = Step(name="Next", enabled=False, click_type="right", not_found_action="key")
    p.steps = [a, b]
    storage.save_template(p.directory, a, make_heart(40))
    end = Step(name="End", enabled=True, threshold=0.8)
    storage.save_template(p.directory, end, make_heart(30, filled=False))
    p.end_condition = end
    return p


def test_round_trip_preserves_everything(tmp_path):
    p = sample_profile(tmp_path)
    storage.save_profile(p)
    q = storage.load_profile(p.directory)
    assert q.to_dict() == p.to_dict()
    assert q.directory == p.directory
    assert q.steps[0].region == (10, 20, 300, 200)
    assert isinstance(q.steps[0].region, tuple)
    assert q.settings.stop_hotkey == "F9"
    assert q.end_condition.template == p.end_condition.template


def test_load_from_json_file_path(tmp_path):
    p = sample_profile(tmp_path)
    storage.save_profile(p)
    q = storage.load_profile(p.directory / "profile.json")
    assert q.name == p.name


def test_template_image_round_trip_with_unicode_path(tmp_path):
    p = sample_profile(tmp_path)
    img = make_heart(40)
    loaded = storage.read_image(p.directory / p.steps[0].template)
    assert np.array_equal(loaded, img)
    store = storage.TemplateStore(p.directory)
    assert np.array_equal(store.get(p.steps[0].template), img)


def test_template_store_reloads_after_change(tmp_path):
    p = sample_profile(tmp_path)
    store = storage.TemplateStore(p.directory)
    first = store.get(p.steps[0].template)
    import os, time
    new = make_heart(60)
    path = p.directory / p.steps[0].template
    storage.write_png(path, new)
    os.utime(path, (time.time() + 5, time.time() + 5))
    assert store.get(p.steps[0].template).shape == new.shape != first.shape


def test_values_are_clamped_on_load(tmp_path):
    folder = tmp_path / "bad"
    folder.mkdir()
    data = {"steps": [{"name": "x", "threshold": 7, "click_type": "teleport", "timeout": -3,
                       "not_found_action": "explode", "unknown_future_field": 1}],
            "settings": {"jitter_percent": 900, "loop_count": 0}}
    (folder / "profile.json").write_text(json.dumps(data))
    q = storage.load_profile(folder)
    s = q.steps[0]
    assert s.threshold == 1.0 and s.click_type == "left" and s.timeout == 0.0 and s.not_found_action == "skip"
    assert q.settings.jitter_percent == 100.0 and q.settings.loop_count == 1
    assert Step(threshold=0.1).normalise().threshold == 0.5


def test_corrupt_and_missing_profiles_raise_clean_errors(tmp_path):
    with pytest.raises(ProfileError):
        storage.load_profile(tmp_path / "nowhere")
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "profile.json").write_text("{not json")
    with pytest.raises(ProfileError):
        storage.load_profile(bad)
    (bad / "profile.json").write_text("[1,2]")
    with pytest.raises(ProfileError):
        storage.load_profile(bad)


def test_save_as_copies_templates(tmp_path):
    p = sample_profile(tmp_path)
    old = p.directory
    storage.save_profile(p, tmp_path / "copy")
    assert p.directory == tmp_path / "copy"
    assert (tmp_path / "copy" / p.steps[0].template).exists()
    assert (old / p.steps[0].template).exists()


def test_duplicate_template_gets_own_file(tmp_path):
    p = sample_profile(tmp_path)
    src = p.steps[0]
    dup = Step.from_dict(src.to_dict())
    dup.id, dup.name = "feedbeef", "Heart copy"
    storage.copy_template(p.directory, src, dup)
    assert dup.template != src.template and (p.directory / dup.template).exists()


def test_export_import_round_trip(tmp_path):
    p = sample_profile(tmp_path)
    z = storage.export_profile(p, tmp_path / "out.zip")
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
    assert "profile.json" in names and p.steps[0].template in names and p.end_condition.template in names
    q = storage.import_profile(z, root=tmp_path / "imported")
    assert q.directory != p.directory
    assert q.to_dict() == p.to_dict()
    assert np.array_equal(storage.read_image(q.directory / q.steps[0].template), make_heart(40))
    again = storage.import_profile(z, root=tmp_path / "imported")  # name clash -> new folder
    assert again.directory != q.directory


def test_import_rejects_zip_slip(tmp_path):
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("profile.json", json.dumps({"name": "evil"}))
        zf.writestr("../escape.txt", "x")
    with pytest.raises(ProfileError):
        storage.import_profile(z, root=tmp_path / "r")
    assert not (tmp_path / "r" / "escape.txt").exists()
    assert not (tmp_path / "escape.txt").exists()


def test_validate_reports_missing_templates():
    p = Profile(steps=[Step(name="a"), Step(name="b", template="t.png")])
    problems = p.validate()
    assert len(problems) == 1 and "'a'" in problems[0]
    assert Profile().validate()  # no steps at all
