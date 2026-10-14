# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for ClickFlow.   Build with:  python build_exe.py

Default: ONE self-contained file (dist/ClickFlow.exe). Set CLICKFLOW_ONEDIR=1 for a folder build
(dist/ClickFlow/), which makes it easy to swap the LGPL libraries (Qt, pynput) - see THIRD_PARTY_NOTICES.md.
"""
import os
import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH)
ONEDIR = os.environ.get("CLICKFLOW_ONEDIR") == "1"

# ---- version (read from the package without importing it)
VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "clickflow" / "__init__.py").read_text(encoding="utf-8")).group(1)
v = [int(x) for x in (VERSION.split(".") + ["0", "0", "0"])[:4]]

# ---- Windows version resource (shown in the file's Properties dialog)
version_file = ROOT / "build" / "version_info.txt"
version_file.parent.mkdir(exist_ok=True)
version_file.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({v[0]}, {v[1]}, {v[2]}, {v[3]}), prodvers=({v[0]}, {v[1]}, {v[2]}, {v[3]}),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'ClickFlow contributors'),
      StringStruct('FileDescription', 'ClickFlow - image-matching auto clicker'),
      StringStruct('FileVersion', '{VERSION}'),
      StringStruct('InternalName', 'ClickFlow'),
      StringStruct('LegalCopyright', 'MIT License. Third-party components: see THIRD_PARTY_NOTICES.md'),
      StringStruct('OriginalFilename', 'ClickFlow.exe'),
      StringStruct('ProductName', 'ClickFlow'),
      StringStruct('ProductVersion', '{VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ])
""", encoding="utf-8")

# ---- what goes inside
datas = [
    (str(ROOT / "examples"), "examples"),        # the default profile (+ its template images)
    (str(ROOT / "assets"), "assets"),            # window icon
    (str(ROOT / "LICENSE"), "."),                # shown in Help > Open-source licenses
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
    (str(ROOT / "LICENSES"), "LICENSES"),
]
hiddenimports = collect_submodules("pynput") + ["pyautogui", "pymsgbox", "pytweening", "pyscreeze"]

# Never ship these: mouseinfo is GPLv3 (pyautogui only imports it for a debug helper ClickFlow never calls),
# tkinter/test tooling are unused, and the big Qt modules below are not needed by a QtWidgets app.
excludes = [
    "mouseinfo", "tkinter", "_tkinter", "pytest", "_pytest", "IPython", "matplotlib", "PIL", "scipy",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtQml",
    "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtPdf",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtSql", "PySide6.QtNetwork", "PySide6.QtSvg",
    "PySide6.QtOpenGL", "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtTest",
]

a = Analysis(
    [str(ROOT / "run_clickflow.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
# OpenCV wheels carry an FFmpeg DLL (LGPL-2.1) for video I/O. ClickFlow only reads PNG screenshots: leave it out.
a.binaries = [b for b in a.binaries if "ffmpeg" not in b[0].lower()]
# Qt pieces a QtWidgets desktop tool never loads (QML/Quick, PDF, SVG, on-screen keyboard) - about 20 MB.
_DROP = ("qt6quick", "qt6qml", "qt6pdf", "qt6virtualkeyboard", "qt6svg", "qsvg", "qpdf", "qtvirtualkeyboard")
a.binaries = [b for b in a.binaries if not any(k in os.path.basename(b[0]).lower() for k in _DROP)]

pyz = PYZ(a.pure)
common = dict(name="ClickFlow", debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
              console=False, icon=str(ROOT / "assets" / "icon.ico"), version=str(version_file))

if ONEDIR:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ClickFlow")
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], runtime_tmpdir=None, **common)
