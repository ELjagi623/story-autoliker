"""Profile persistence: JSON + PNG templates in a folder, zip export/import.

All image I/O goes through ``numpy`` buffers (``imdecode`` / ``imencode``) because
``cv2.imread`` / ``imwrite`` fail on paths containing non-ASCII characters on Windows.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .models import Preset, Profile, Step, set_template

PROFILE_FILE = "profile.json"
TEMPLATE_DIR = "templates"


class ProfileError(Exception):
    pass


def default_home() -> Path:
    """Root folder for user data (profiles, logs). Override with CLICKFLOW_HOME."""
    env = os.environ.get("CLICKFLOW_HOME")
    return Path(env) if env else Path.home() / "ClickFlow"


def profiles_root() -> Path:
    return default_home() / "profiles"


def slugify(name: str) -> str:
    slug = re.sub(r"[^\w\-]+", "_", name, flags=re.UNICODE).strip("_")
    return slug or "profile"


# ---------------------------------------------------------------- images

def read_image(path: Path | str) -> np.ndarray:
    """Read an image as BGR uint8. Raises ProfileError when unreadable."""
    try:
        buf = np.fromfile(str(path), dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except OSError as exc:
        raise ProfileError(f"Cannot read image {path}: {exc}") from exc
    if img is None:
        raise ProfileError(f"Not a valid image: {path}")
    return img


def write_png(path: Path | str, image: np.ndarray) -> None:
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise ProfileError(f"Could not encode PNG for {path}")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    buf.tofile(str(path))


def _template_rel(step: Step, preset: Optional[Preset] = None) -> str:
    suffix = f"_{preset.id}" if preset is not None else ""
    return f"{TEMPLATE_DIR}/{slugify(step.name)[:40]}_{step.id}{suffix}.png"


def save_template(directory: Path, step: Step, image: np.ndarray, preset: Optional[Preset] = None) -> str:
    """Write ``image`` as the step's template (or as ``preset``'s override for it); returns the relative file name."""
    rel = _template_rel(step, preset)
    write_png(Path(directory) / rel, image)
    set_template(step, preset, rel)
    return rel


def copy_template(directory: Path, src: Step, dst: Step) -> None:
    """Give ``dst`` its own copy of ``src``'s template file (used when duplicating a step)."""
    if not src.template:
        return
    src_path = Path(directory) / src.template
    if not src_path.exists():
        return
    rel = _template_rel(dst)
    dst_path = Path(directory) / rel
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src_path, dst_path)
    dst.template = rel


def copy_preset_entries(directory: Path, profile: Profile, src: Step, dst: Step) -> None:
    """When a step is duplicated, give the copy the same search boxes / template overrides in every preset."""
    for p in profile.presets:
        if src.id in p.regions:
            p.regions[dst.id] = p.regions[src.id]
        rel = p.templates.get(src.id)
        if rel and (Path(directory) / rel).exists():
            new_rel = _template_rel(dst, p)
            shutil.copyfile(Path(directory) / rel, Path(directory) / new_rel)
            p.templates[dst.id] = new_rel


class TemplateStore:
    """Loads and caches template images for a profile folder.

    ``preloaded`` lets tests supply images in memory without touching the disk.
    """

    def __init__(self, directory: Optional[Path], preloaded: Optional[dict[str, np.ndarray]] = None):
        self.directory = Path(directory) if directory else None
        self._cache: dict[str, tuple[float, np.ndarray]] = {}
        self._preloaded = dict(preloaded or {})

    def get(self, name: str) -> np.ndarray:
        if name in self._preloaded:
            return self._preloaded[name]
        if self.directory is None:
            raise ProfileError(f"Template '{name}' not found (profile has no folder).")
        path = self.directory / name
        try:
            mtime = path.stat().st_mtime
        except OSError as exc:
            raise ProfileError(f"Template file missing: {path}") from exc
        cached = self._cache.get(name)
        if cached and cached[0] == mtime:
            return cached[1]
        img = read_image(path)
        self._cache[name] = (mtime, img)
        return img


# ---------------------------------------------------------------- profiles

def _unique_folder(root: Path, name: str) -> Path:
    folder = root / slugify(name)
    n = 2
    while folder.exists():
        folder = root / f"{slugify(name)}_{n}"
        n += 1
    return folder


def new_profile(name: str, root: Optional[Path] = None) -> Profile:
    root = Path(root) if root else profiles_root()
    folder = _unique_folder(root, name)
    folder.mkdir(parents=True)
    profile = Profile(name=name, directory=folder)
    save_profile(profile)
    return profile


def _all_steps(profile: Profile) -> list[Step]:
    return list(profile.steps) + ([profile.end_condition] if profile.end_condition else [])


def template_files(profile: Profile) -> list[str]:
    """Every template file the profile refers to (step templates and preset overrides)."""
    files = [s.template for s in _all_steps(profile) if s.template]
    for p in profile.presets:
        files += [t for t in p.templates.values() if t]
    return list(dict.fromkeys(files))


def save_profile(profile: Profile, directory: Optional[Path] = None) -> Path:
    """Write profile.json (atomically). Returns the json path."""
    target = Path(directory) if directory else profile.directory
    if target is None:
        raise ProfileError("Profile has no folder; use new_profile() or pass a directory.")
    target.mkdir(parents=True, exist_ok=True)
    if profile.directory is not None and Path(profile.directory) != target:
        _copy_templates(profile, Path(profile.directory), target)  # "save as"
    profile.directory = target
    path = target / PROFILE_FILE
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path


def _copy_templates(profile: Profile, src: Path, dst: Path) -> None:
    for rel in template_files(profile):
        if (src / rel).exists():
            out = dst / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src / rel, out)


def load_profile(path: Path | str) -> Profile:
    """Load from a profile folder or a profile.json file."""
    p = Path(path)
    json_path = p / PROFILE_FILE if p.is_dir() else p
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProfileError(f"Profile file not found: {json_path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileError(f"Cannot read profile {json_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError(f"{json_path} is not a ClickFlow profile.")
    try:
        return Profile.from_dict(data, directory=json_path.parent)
    except (TypeError, ValueError) as exc:
        raise ProfileError(f"Invalid profile {json_path}: {exc}") from exc


def export_profile(profile: Profile, zip_path: Path | str) -> Path:
    """Bundle profile.json and its templates into a single zip file."""
    if profile.directory is None:
        raise ProfileError("Save the profile before exporting it.")
    save_profile(profile)
    zip_path = Path(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(profile.directory / PROFILE_FILE, PROFILE_FILE)
        for rel in template_files(profile):
            f = profile.directory / rel
            if f.exists():
                zf.write(f, rel)
    return zip_path


def import_profile(zip_path: Path | str, root: Optional[Path] = None) -> Profile:
    """Unpack an exported zip into a new profile folder and load it."""
    root = Path(root) if root else profiles_root()
    with zipfile.ZipFile(zip_path) as zf:
        if PROFILE_FILE not in zf.namelist():
            raise ProfileError("Zip does not contain a profile.json.")
        name = json.loads(zf.read(PROFILE_FILE).decode("utf-8")).get("name", "imported")
        folder = _unique_folder(root, str(name))
        folder.mkdir(parents=True)
        base = folder.resolve()
        for member in zf.infolist():
            dest = (folder / member.filename).resolve()
            if base != dest and base not in dest.parents:  # zip-slip protection
                raise ProfileError(f"Unsafe path in zip: {member.filename}")
            if member.is_dir():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(member))
    return load_profile(folder)


# ---------------------------------------------------------------- "reopen where I left off"

def _last_file() -> Path:
    return default_home() / "last_profile.txt"


def remember_last_profile(directory: Path | str) -> None:
    try:
        _last_file().parent.mkdir(parents=True, exist_ok=True)
        _last_file().write_text(str(directory), encoding="utf-8")
    except OSError:
        pass  # purely a convenience


def last_profile_dir() -> Optional[Path]:
    try:
        p = Path(_last_file().read_text(encoding="utf-8").strip())
    except OSError:
        return None
    return p if (p / PROFILE_FILE).exists() else None
