<div align="center">

<img src="assets/icon.png" width="96" alt="ClickFlow icon">

# ClickFlow

**Find icons on your screen and click them in the order you choose, with the waits you choose.**

[![Latest release](https://img.shields.io/github/v/release/Eljagi826/story-autoliker?style=flat-square)](https://github.com/Eljagi826/story-autoliker/releases/latest)
[![MIT license](https://img.shields.io/badge/license-MIT-f4c430?style=flat-square)](LICENSE)
![Platform](https://img.shields.io/badge/Windows_10%2F11-tested-0078d4?style=flat-square)

[Download](#download) · [Quick start](#quick-start) · [Features](#features) · [Reference](docs/reference.md) · [中文](README.zh-CN.md)

</div>

ClickFlow watches the screen, finds an icon by **image matching**, and clicks it. You build a list of steps (find this, click, wait, find that, click, wait) and ClickFlow repeats them until you stop it.

It is a generic tool with no site-specific logic. The bundled `instagram_story_like` profile, which likes a story and moves to the next one, is just data: two steps, a heart and a next-arrow.

> [!WARNING]
> Automating likes or any other interaction may violate Instagram's, or any other service's, terms of use and can get an account limited or banned. Keep the volume low, use long randomised delays (the jitter setting), and set a small max-click limit. You are responsible for how you use it. ClickFlow is an independent project and is not affiliated with or endorsed by Instagram, Meta or any other service.

## Download

Get **`ClickFlow.exe`** from the [latest release](https://github.com/Eljagi826/story-autoliker/releases/latest). It is a single file for Windows 10 / 11 (64-bit): no installer, no Python. Double-click to run.

- The first start creates `C:\Users\<you>\ClickFlow\` for profiles and logs. To uninstall, delete the exe and that folder.
- Windows SmartScreen may say "unknown publisher" because the exe is not code-signed. Choose **More info > Run anyway**.
- Some antivirus tools flag every PyInstaller one-file program. Compare the file's SHA-256 with the `ClickFlow.exe.sha256` published next to it, or [build it yourself](docs/reference.md#build-the-exe-yourself).

Prefer source? You need Python 3.11+. Run `run.bat` on Windows or `./run.sh` on macOS / Linux (X11); the script creates a virtual environment and starts the app.

## Quick start

The example below uses the Instagram story profile. The icons look different on every screen, so you capture them once on yours.

1. Start ClickFlow. The `instagram_story_like` profile opens.
2. Open the story viewer so the heart and the "next story" arrow are visible.
3. Select a step and press **Capture template...**. Drag a tight rectangle around the icon, then drag a **search box** around the area where it appears. Use the unliked (outline) heart for step 1 and the next-story arrow for step 2.
4. Press **Test this step**. It looks once and tells you plainly whether a run would click, and with what confidence. If not, it explains why and offers a one-click fix.
5. Press **Dry run** to watch the whole flow with boxes and no clicks.
6. Press **Start**. You get a 2-second delay to switch to the story window.

> [!IMPORTANT]
> The default profile runs at top speed with a 500-click limit and infinite loops. Lower the **Speed** slider and the click limit before real use.

To practise safely, run `python -m clickflow.mock_window`. It shows a fake story viewer that counts clicks.

## Features

- **Flexible steps.** Each step has its own template image, match threshold, search box, click offset, click type (left, right, double), waits, timeout, and what to do when nothing is found (skip, retry, stop, or press a fallback key).
- **Speed slider.** One control sets the time between clicks, from no added delay to 1.5 s. Tick *Advanced* to edit each step's waits by hand.
- **Search boxes and display presets.** A search box limits a step to where its icon appears, which is about 55 ms per scan on any screen size. Presets store boxes per display resolution and switch automatically for each monitor.
- **Test this step.** A single look that says whether a run would click. On failure it diagnoses the cause (icon size changed, outside the search box, threshold too strict, or absent) and can apply the fix.
- **Safe by design.** Dry run, a total click limit, random delay jitter, and an optional end-condition image.
- **Live log.** Every step's confidence, position and click coordinates.

## Stopping a run

Any of these works at any time:

| Method | How |
| --- | --- |
| Hotkey | Press **F8** (configurable in *Global settings*) |
| STOP button | Click the red button floating at the top-centre of the screen |
| Screen corner | Move the mouse into any corner of the screen |
| Stop in the app | Click *Stop* in the ClickFlow window |

## Platform notes

- **Windows** works out of the box, including 125% / 150% display scaling. Windows cannot send input to windows running as Administrator unless ClickFlow is elevated too, and a locked workstation cannot be captured.
- **macOS** needs *Screen Recording* and *Accessibility* permissions (the stop hotkey may also need *Input Monitoring*). ClickFlow checks on start and tells you what is missing.
- **Linux** needs an X11 session. Wayland blocks screen capture and synthetic input.

> [!NOTE]
> ClickFlow has been tested on Windows 11 only. macOS and Linux support is best effort.

## Documentation

- [Reference](docs/reference.md): how matching works, display presets, design decisions, architecture, tests, known limits and troubleshooting
- [Contributing](CONTRIBUTING.md): set up, run the tests, design rules
