# Third-party notices

ClickFlow's own source code is released under the **MIT License** (see `LICENSE`).

The standalone Windows program (`ClickFlow.exe`, built with PyInstaller) bundles the free software listed below. Each
component stays under its own licence; the full texts of the GNU licences and the Apache licence are in the `LICENSES/`
folder of the source repository (and are shown in the program under *Help > Open-source licenses*). Versions are the ones
used for the official build.

## What is inside

| Component | Version | Licence | Used for |
|---|---|---|---|
| Python (runtime) | 3.13 | PSF License | the interpreter |
| **PySide6** / Qt for Python, **shiboken6**, Qt 6 libraries | 6.12.0 | **LGPL-3.0** (also offered under GPL-2/3 and a commercial licence; ClickFlow uses the LGPL-3.0 option) | the user interface |
| **pynput** | 1.8.x | **LGPL-3.0** | global hotkey (stop key) |
| OpenCV (`opencv-python-headless`) | 5.0.x | Apache-2.0 | template matching |
| NumPy | 2.5.x | BSD-3-Clause (plus 0BSD, MIT, Zlib, CC0 parts) | image arrays |
| mss | 10.x | MIT | screen capture |
| PyAutoGUI | 0.9.54 | BSD-3-Clause | mouse clicks and key presses |
| PyMsgBox, PyScreeze, PyTweening, PyGetWindow, PyRect | various | BSD-3-Clause / MIT | PyAutoGUI's own dependencies |
| six | 1.17 | MIT | pynput dependency |
| PyInstaller (bootloader) | 6.x | GPL-2.0-or-later **with a special exception** that allows the executables it produces to be distributed under any licence | packaging only |

Deliberately **not** shipped: `mouseinfo` (GPL-3.0; PyAutoGUI imports it only for a debug window that ClickFlow never opens) and the
FFmpeg library that OpenCV wheels contain (LGPL-2.1; ClickFlow never reads video). Test tools (pytest) are not part of the program.

## LGPL components: your right to replace them

Qt for Python (PySide6, shiboken6, the Qt libraries) and pynput are licensed under the GNU Lesser General Public Licence v3.
ClickFlow **does not modify** them. They are linked dynamically (they are separate libraries inside the bundle) and ClickFlow's
code is MIT-licensed and independent of them. As the LGPL requires, you are free to use ClickFlow with a different (even modified)
version of these libraries:

* **Build from source** with any PySide6 / pynput version you like: `pip install -r requirements.txt`, then
  `python build_exe.py` (one file) or `python build_exe.py --onedir` (a folder in which the Qt `.dll` files and the pynput
  package can simply be replaced). Running from source (`python run_clickflow.py`) uses whatever versions are installed.
* **Source code of the libraries:** Qt for Python: <https://code.qt.io/cgit/pyside/pyside-setup.git/> and
  <https://pypi.org/project/PySide6/>; Qt: <https://download.qt.io/official_releases/qt/>; pynput:
  <https://github.com/moses-palmer/pynput>.
* The LGPL-3.0 and GPL-3.0 texts are in `LICENSES/LGPL-3.0.txt` and `LICENSES/GPL-3.0.txt`.

This product uses Qt, which is a registered trademark of The Qt Company Ltd. ClickFlow is not affiliated with or endorsed by The Qt Company.

## Other notices

* OpenCV is licensed under the Apache License 2.0 (`LICENSES/Apache-2.0.txt`); its NOTICE terms apply to the bundled library.
* NumPy, mss, PyAutoGUI and its helpers are redistributed in binary form under their BSD / MIT licences; their copyright notices and
  disclaimers are those of the respective projects (see their repositories on PyPI / GitHub).
* **Sample images.** The default profile contains two tiny template images (a heart icon and a "next" arrow) captured from
  the author's screen so that the example works out of the box. They are used only for on-screen image matching. All product names,
  logos and trademarks (including Instagram and Meta) belong to their owners; ClickFlow is an independent project and is not
  affiliated with, endorsed by or sponsored by them. Replace the templates with your own captures if you redistribute ClickFlow
  and want to avoid shipping any third-party artwork.

## No warranty

ClickFlow and the components above are provided "as is", without warranty of any kind. You are responsible for how you use the
program, including compliance with the terms of the websites and applications you automate.
