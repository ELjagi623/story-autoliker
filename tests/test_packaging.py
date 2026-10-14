"""Everything about shipping: the default profile, the self-test, licence files, the build recipe, repo hygiene."""
import json
import re
import struct
from pathlib import Path

import pytest

from clickflow import app, storage

ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ the default profile

def test_default_profile_keeps_the_authors_settings_but_has_no_search_boxes():
    d = json.loads((ROOT / "examples" / "instagram_story_like" / "profile.json").read_text(encoding="utf-8"))
    like, nxt = d["steps"]
    assert (like["name"], like["click_type"], like["threshold"], like["click_only_if_found"]) == (
        "Like (heart) - only if not yet liked", "left", 0.88, True)
    assert (nxt["name"], nxt["click_type"], nxt["threshold"], nxt["not_found_action"], nxt["retries"]) == (
        "Next story (arrow)", "left", 0.85, "retry", 5)
    for st in d["steps"]:
        assert st["region"] is None, "search boxes must be cleared"
        assert (st["wait_before"], st["wait_after"], st["timeout"]) == (0.05, 0.05, 3.0)
        assert st["multi_scale"] is True and (st["scale_min"], st["scale_max"]) == (0.35, 2.5)
    assert d["end_condition"]["region"] is None and d["end_condition"]["enabled"] is False
    assert d["presets"] == [] and d["settings"]["active_preset"] == ""
    s = d["settings"]
    assert (s["speed"], s["speed_manual"], s["jitter_percent"], s["max_total_clicks"], s["infinite_loop"],
            s["stop_hotkey"], s["start_delay"], s["scan_interval"]) == (100, False, 30.0, 500, True, "F8", 2.0, 0.3)


def test_default_profile_templates_ship_with_it_and_load():
    prof = storage.load_profile(ROOT / "examples" / "instagram_story_like")
    assert prof.validate() == []
    store = storage.TemplateStore(prof.directory)
    for st in prof.steps:
        assert (prof.directory / st.template).exists()
        h, w = store.get(st.template).shape[:2]
        assert 20 <= h <= 200 and 20 <= w <= 200


def test_first_run_copies_the_default_profile_and_never_overwrites_edits(tmp_path):
    p = app.ensure_example()
    assert p == storage.profiles_root() / "instagram_story_like" and (p / "profile.json").exists()
    assert len(list((p / "templates").glob("*.png"))) == 2
    first = storage.load_profile(p)
    first.steps[0].threshold = 0.5
    storage.save_profile(first)
    app.ensure_example()  # second start: must not restore the shipped defaults over the user's edits
    assert storage.load_profile(p).steps[0].threshold == 0.5
    assert app.startup_profile().name == "instagram_story_like"


# ------------------------------------------------------------------ the packaged program's self-test

def test_selftest_passes(qapp, tmp_path, capsys):
    out = tmp_path / "selftest.txt"
    rc = app.selftest(str(out))
    text = out.read_text(encoding="utf-8")
    assert rc == 0 and text.strip().endswith("RESULT: ALL OK"), text
    for name in ("matcher (multi-scale)", "default profile", "main window", "license files", "stop hotkey"):
        assert re.search(rf"^OK\s+{re.escape(name)}", text, re.M), (name, text)
    assert "FAIL" not in text  # screen capture may only WARN (locked / headless desktop)


def test_version_flag(capsys):
    from clickflow import __version__

    assert app.main(["clickflow", "--version"]) == 0
    assert __version__ in capsys.readouterr().out
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


# ------------------------------------------------------------------ licences

def test_license_files_are_present_and_correct():
    mit = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert mit.startswith("MIT License") and "Permission is hereby granted" in mit and "2026" in mit
    for name, needle in (("LGPL-3.0.txt", "GNU LESSER GENERAL PUBLIC LICENSE"), ("GPL-3.0.txt", "GNU GENERAL PUBLIC LICENSE"),
                         ("Apache-2.0.txt", "Apache License")):
        text = (ROOT / "LICENSES" / name).read_text(encoding="utf-8")
        assert needle in text and len(text) > 5000, name


def test_third_party_notices_cover_the_bundled_libraries_and_lgpl_rights():
    t = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    for needle in ("PySide6", "LGPL-3.0", "pynput", "OpenCV", "Apache-2.0", "NumPy", "mss", "PyAutoGUI", "PyInstaller",
                   "mouseinfo", "replace", "build_exe.py", "not affiliated", "Instagram"):
        assert needle in t, needle


def test_the_gpl_package_mouseinfo_is_never_shipped():
    spec = (ROOT / "clickflow.spec").read_text(encoding="utf-8")
    assert re.search(r'excludes\s*=\s*\[[^\]]*"mouseinfo"', spec, re.S)
    assert "ffmpeg" in spec.lower()  # the LGPL FFmpeg DLL of the OpenCV wheel is dropped too
    reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "mouseinfo" not in reqs


def test_help_menu_licence_dialog_reads_the_bundled_files(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog, QPlainTextEdit

    from clickflow.gui.main_window import MainWindow

    shown = {}

    def fake_exec(self):
        shown["texts"] = [w.toPlainText() for w in self.findChildren(QPlainTextEdit)]
        return 0

    monkeypatch.setattr(QDialog, "exec", fake_exec)
    win = MainWindow(storage.new_profile("lic", root=tmp_path / "p"), start_hotkey=False)
    try:
        win.show_licenses()
        texts = shown["texts"]
        assert len(texts) == 2
        assert any(t.startswith("MIT License") for t in texts)
        assert any("LGPL" in t and "PySide6" in t for t in texts)
    finally:
        win.dirty = False
        win.close()


# ------------------------------------------------------------------ build inputs

def test_icon_assets_are_valid():
    png = (ROOT / "assets" / "icon.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    ico = (ROOT / "assets" / "icon.ico").read_bytes()
    reserved, kind, count = struct.unpack("<HHH", ico[:6])
    assert (reserved, kind) == (0, 1) and count >= 6
    sizes = []
    for i in range(count):
        w, h, _c, _r, _planes, _bpp, length, offset = struct.unpack("<BBBBHHII", ico[6 + 16 * i:22 + 16 * i])
        assert ico[offset:offset + 8] == b"\x89PNG\r\n\x1a\n" and offset + length <= len(ico)
        sizes.append(w or 256)
    assert 256 in sizes and 16 in sizes


def test_spec_bundles_everything_the_app_needs_at_runtime():
    spec = (ROOT / "clickflow.spec").read_text(encoding="utf-8")
    for needle in ('"examples"', '"assets"', '"LICENSE"', "THIRD_PARTY_NOTICES.md", '"LICENSES"', "run_clickflow.py",
                   "console=False", "assets\" / \"icon.ico", "collect_submodules(\"pynput\")"):
        assert needle in spec, needle
    for p in ("examples", "assets", "LICENSE", "THIRD_PARTY_NOTICES.md", "LICENSES", "run_clickflow.py"):
        assert (ROOT / p).exists(), p


def test_spec_version_matches_the_package():
    from clickflow import __version__

    assert re.search(r'__version__\s*=\s*"%s"' % re.escape(__version__), (ROOT / "clickflow" / "__init__.py").read_text())


# ------------------------------------------------------------------ repo hygiene (ready to publish)

TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".spec", ".ini", ".bat", ".sh", ".toml", ".cfg", ".gitignore"}
SKIP_DIRS = {".venv", "build", "dist", ".pytest_cache", "__pycache__", ".git"}


def project_text_files():
    for p in ROOT.rglob("*"):
        if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES | {""} and not (set(p.relative_to(ROOT).parts) & SKIP_DIRS):
            if p.name.startswith("LGPL") or p.name.startswith("GPL") or p.name.startswith("Apache"):
                continue
            yield p


def test_no_personal_paths_or_emails_in_the_repo():
    bad = []
    pats = [re.compile(r"[A-Za-z]:\\Users\\(?!<|你的用户名|\*|%)"), re.compile(r"[\w.+-]+@(gmail|qq|163|outlook|hotmail)\.", re.I),
            re.compile(r"/Users/(?!<)[A-Za-z0-9_]+/"), re.compile(r"/home/(?!<)[a-z0-9_]+/")]
    for p in project_text_files():
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pat in pats:
            m = pat.search(text)
            if m and p.name != "test_packaging.py":
                bad.append((str(p.relative_to(ROOT)), m.group(0)))
    assert not bad, bad


def test_gitignore_keeps_build_output_and_environments_out():
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for needle in (".venv/", "dist/", "build/", "__pycache__/", ".pytest_cache/"):
        assert needle in gi
    assert "*.spec" not in gi  # clickflow.spec is source and must be committed


def test_required_open_source_files_exist():
    for name in ("LICENSE", "README.md", "README.zh-CN.md", "THIRD_PARTY_NOTICES.md", "CONTRIBUTING.md", "CHANGELOG.md",
                 "requirements.txt", "clickflow.spec", "build_exe.py"):
        assert (ROOT / name).is_file(), name
