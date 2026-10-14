# ClickFlow reference
Detailed behaviour, design decisions, architecture and troubleshooting. For an overview and quick start, see the [README](../README.md).


<p align="center"><img src="../assets/icon.png" width="96" alt="ClickFlow icon"></p>

ClickFlow finds icons on the screen by **image matching** and clicks them in a **user-defined order with user-defined waits**.
It is a generic tool: there is no site- or app-specific logic in the code. The bundled
`instagram_story_like` profile is just data (two steps: *heart* and *next-arrow*).

Features: a step list with per-step template image, threshold, search box, click type, waits and failure handling - a speed slider -
per-display presets that switch automatically by screen resolution - *Test this step* with an automatic diagnosis - dry run -
stop hotkey / red STOP button / screen-corner emergency stop - a live log. 中文说明见 [README.zh-CN.md](../README.zh-CN.md).

> **Terms-of-service warning.** Automating likes (or any other interaction) may violate Instagram's - or any other
> service's - terms of use and can get an account limited or banned. If you use ClickFlow for this, keep the **volume low**,
> use **long, randomised delays** (the jitter setting), and set a small **max-click limit**. You are responsible for how you use it.
> ClickFlow is an independent project, not affiliated with or endorsed by Instagram, Meta or any other service.

## Download (Windows 10 / 11, 64-bit)

Grab **`ClickFlow.exe`** from the project's *Releases* page: a single file, no installation, no Python needed. Double-click it.

* First start creates `C:\Users\<you>\ClickFlow\` (profiles + logs) and a default profile. Uninstall = delete the exe and that folder.
* Windows SmartScreen may say "unknown publisher" (the exe is not code-signed) - *More info > Run anyway*. Some antivirus tools
  flag every PyInstaller one-file program; you can compare the file's SHA-256 with the `ClickFlow.exe.sha256` published next to
  it, or build it yourself from source (below).
* The default profile opens with sensible settings and the two template images; the **search boxes are empty** - draw one per
  step on your own screen (see *Quick start*).

## Build the exe yourself

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python build_exe.py          # -> dist\ClickFlow.exe (one file), then runs its built-in self-test
.venv\Scripts\python build_exe.py --onedir # -> dist\ClickFlow\ (folder, handy for swapping the LGPL libraries)
```

`ClickFlow.exe --selftest report.txt` checks that everything a run needs is inside the bundle (matcher, default profile, Qt window,
input layer, licence files) without touching your data. The recipe is [`clickflow.spec`](../clickflow.spec).

## Run from source

Requires **Python 3.11+** (developed and tested on 3.13).

| | |
|---|---|
| Windows | `run.bat` |
| macOS / Linux (X11) | `./run.sh` |

The script creates `.venv`, installs `requirements-dev.txt` once, and starts the app.
Run the tests with `run.bat test` / `./run.sh test`. Manual equivalent:

```
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt     # (.venv/bin/pip on macOS/Linux)
.venv/Scripts/python run_clickflow.py                  # or: python -m clickflow
```

User data (profiles, logs) lives in `~/ClickFlow` (override with the `CLICKFLOW_HOME` environment variable).
The default profile is copied there on first start; the last profile you used is reopened next time.

## OS notes and permissions

* **Windows** - works out of the box. The process opts into per-monitor DPI awareness so screenshots, clicks and the mouse
  position share physical-pixel coordinates (125 %/150 % scaling is handled). Windows cannot send input to windows running
  as Administrator unless ClickFlow is also elevated. A *locked* workstation cannot be captured at all.
* **macOS** - ClickFlow checks on start and before every run and shows a message if a permission is missing:
  * *System Settings > Privacy & Security > **Screen Recording*** - enable your terminal (or the ClickFlow app).
  * *... > **Accessibility*** - needed to click. The global stop hotkey may additionally need *Input Monitoring*.
  * Retina: screenshots are 2x the click coordinate space; ClickFlow converts (a `Frame` carries the pixel scale). Restart the app after granting permissions.
* **Linux** - X11 session required (Wayland blocks screen capture and synthetic input; ClickFlow warns).

## How to stop a run (any of these, any time)

1. Press the **stop hotkey** (default **F8**; change it in *Global settings > Stop hotkey*). On Windows it is detected by polling the
   OS key state every 10 ms (independent of any keyboard hook, catches even very short taps) *and* by a pynput global hotkey.
2. Click the red **STOP** button that floats at the top-centre of the screen while a run is active (it never steals keyboard focus).
3. Move the mouse into **any screen corner**.
4. Click *Stop* in the app (if it is not minimised).

## Speed

The **Speed** bar at the top of the window controls how long it takes from one click to the next, with one slider:

| Slider | Time between clicks |
|---|---|
| 100 % (right, "Fast") | no added delay: as fast as the scan + click allow (about 0.25-0.3 s) |
| 75 % | about 0.4 s |
| 50 % (default for new profiles) | about 0.6 s |
| 25 % | about 1.0 s |
| 0 % (left, "Slow") | 1.5 s |

The steps in between are geometric (each notch is the same relative change). ClickFlow measures how long its own scan + click take and
subtracts that, so the spacing lands on the chosen value instead of "chosen value + processing time" (measured on the real screen and mouse: 1.50 / 0.96 / 0.61 / 0.39 s
for 0 / 25 / 50 / 75 %). The *Randomness (jitter)* percentage still varies each interval, so the number is an average.

**Advanced: edit waits manually.** Ticking this box turns the slider off and gives every step its own *Wait before / Wait after* (Step tab),
exactly like before the slider existed; no spacing is enforced. The per-step values you typed are kept when you switch back to the slider and
come back when you tick Advanced again (they are never overwritten by the slider). In slider mode the two fields are greyed out and show the small fixed
wait (0.05 s) that is in force.

Profiles saved before the slider existed keep their exact timing: if both waits of every step are the same and at most 0.1 s, the profile opens
in slider mode at 100 % (the same speed); anything else opens in Advanced mode with its own waits.

## Quick start - the Instagram story example

1. Start ClickFlow; the `instagram_story_like` profile opens (a yellow note at the top explains it). It includes two **sample template
   images** captured on the author's screen and **empty search boxes**, because icon size, theme and display scaling differ per machine.
2. Open the story viewer so the heart and the "next story" arrow are visible.
3. Select a step and press **Test this step**: it looks once and says plainly whether a run **would** or **would not** click, with the
   confidence. If it says NOT FOUND, read the diagnosis (and use *Apply suggested fix*), or press **Capture template...** and drag a tight
   rectangle around the icon on *your* screen - the same drag then asks for the **search box**. Capture the **unliked** (outline) heart
   for step 1 and the **next-story arrow** for step 2.
4. Draw a **search box** for every step (*Draw search box...*): much faster and more reliable than scanning the whole screen.
5. Press **Dry run** to watch the whole flow with boxes and no clicks.
6. Press **Start**. You have the start delay (default 2 s) to switch to the story window. **F8**, the red STOP button, or moving the
   mouse into any screen corner stops it.

The default profile runs at the fastest speed with a 500-click limit and infinite loops - **lower the Speed slider and the click limit
for real use** (see the terms-of-service warning above).

The flow is: find heart -> click -> short wait -> find arrow -> click -> wait -> repeat. Step 1 uses **Click only if found**, so stories
that are already liked (filled heart, no match) are skipped without waiting. Optionally, enable an **End condition** (Global
settings tab) with an image that only appears when the stories are over; the run stops when it is seen.

You can try everything safely on the bundled practice target: `python -m clickflow.mock_window` shows a fake story viewer
(heart + arrow) that counts clicks.

## Concepts

A **profile** is a folder: `profile.json` + `templates/*.png`. Zip export/import (File menu) bundles both.

**Step fields** - name - template - match threshold (0.5-1.0) - optional search region - click offset from the match centre -
click type (left / right / double) - wait before / after - find timeout (0 = look once) - not-found action:
*skip*, *retry N times* (then stop or skip), *stop the run*, or *press a fallback key* - click-only-if-found - matching
options (multi-scale range, grayscale) - enabled.

**Global settings** - loop count or infinite - random jitter % on every wait - max total clicks - stop hotkey - corner-abort
- start delay - scan interval - idle-loop limit - monitor index. Plus the optional **end condition**.

## Search boxes and display presets (big screens, several monitors)

**Search box.** Scanning a whole big screen is slow (about 0.8 s on one 2560x1440 monitor, 2.3 s on three) and can pick a
look-alike elsewhere or time out before it finds the icon. A search box limits a step to the area where its icon appears:
about 55 ms per scan regardless of screen size. Draw it once and it is applied on every run:

* **Capture template...** now continues straight into **"drag the search box"** on the same screenshot (the template is
  outlined in cyan, other steps' boxes in orange; **Esc** skips and scans the whole screen). A step that already has a box
  keeps it.
* **Draw search box...** redraws only the box; **Clear box** removes it; **Show boxes** briefly draws all boxes on the real screen.
* The step list shows `[no search box]` for steps that still scan the whole screen, and the editor warns in orange.

**Display presets.** A preset stores the search boxes (and, if you capture them, template images) for one display
*resolution*. Boxes are stored relative to the monitor's top-left corner, so rearranging monitors in the OS settings does not break them.

* Pick the preset in the **Display preset** bar; while a preset is selected, *Capture template*, *Draw search box* and the
  numeric box fields edit **that preset** (the Default configuration is untouched). A new preset starts without boxes and uses the
  default templates until you capture its own.
* **New preset...** asks which detected monitor it is for; **Detect displays** shows the monitors and which preset matches each.
* **Auto-switch by detected resolution** (on by default): when a run starts, ClickFlow lists the connected monitors, picks the
  preset whose resolution matches, and captures *that monitor*. If several monitors share a resolution it probes each one and chooses
  the one where the icons are actually found. No matching preset -> the Default configuration is used and the log says why.
* The log names what was chosen, e.g. `Display preset: preset 'Laptop' matches Monitor 2: 1920x1080`, and the preset
  combo follows the choice.

## Troubleshooting: "Test this step shows the right spot, but nothing is clicked"

A step only clicks when the match confidence reaches its **threshold**. *Test this step* always draws a box around the best
*candidate*, even when the confidence is too low, so the box can sit exactly on the icon while the step is still "not found".
The log now states it plainly (`FOUND ... A run WOULD click` / `NOT FOUND ... A run would NOT click this step`), the box is labelled
`NOT FOUND - no click`, and a failed test runs a **diagnosis** on the same screenshot with the restrictions lifted one by one:

| Diagnosis | Meaning | One-click fix |
|---|---|---|
| size | icon is on screen but at a different size than the template (browser zoom, window size or display scaling changed) | widen the scale range |
| search box | icon is on screen but outside the search box | box around where it really is |
| threshold | something similar is there, confidence a bit too low | lower threshold |
| absent | nothing resembling the template | re-capture the template while the icon is visible |

Template sizes are searched from 0.35x to 2.5x of the captured size by default (profiles saved with the old 0.7-1.4 range are upgraded
on load). The scale that matched last time is tried first, so repeat scans stay fast. For the best precision, re-capture a template whenever the
icon's on-screen size changed.

### Decisions made (the brief said not to ask)

* **Coordinates.** Regions, offsets and click points are in *screen coordinates* = what the OS input layer uses (physical px on
  Windows/Linux, points on macOS). Matching works in physical pixels; `Frame.to_screen` converts. Multi-monitor with *mixed* DPI is best effort.
* **Matching.** `cv2.matchTemplate` (TM_CCOEFF_NORMED), grayscale by default (faster; untick for colour-only differences).
  Multi-scale: a coarse grid (0.7-1.4 by 0.1, always incl. 1.0, nearest first, early exit on >=0.95), then a fine refinement around the best scale.
  Flat single-colour templates use an absolute RMS score instead (correlation is undefined for them). Don't use them.
* **Click-only-if-found** = a missing icon is *not* a failure: no error, no retries, no wait-after is spent. The find timeout still applies (set 0 for a single look).
* **Wait-after is only spent after an action** (click or fallback key), never after a skipped step.
* **Retry N** repeats the whole find-with-timeout N more times; afterwards the step *stops* the run (default) or skips, as configured.
* **Click limit** counts clicks (a double-click counts once; dry-run "clicks" count too) and stops immediately at the limit.
* **Corner abort** triggers when the cursor is inside any corner of the captured area (2 px tolerance). Don't point a step at a screen corner.
* **Idle protection**: after 10 consecutive loops in which nothing was found or clicked, the run stops (setting `max_idle_loops`, 0 = never) so a broken template cannot spin forever.
* **Window handling**: ClickFlow minimises itself while capturing, testing and running (configurable) so it never covers the target.
* Fallback keys use pyautogui names (`esc`, `right`, `ctrl+w`).

## Architecture

```
clickflow/
  models.py     Step / Settings / Profile dataclasses, validation, clamping
  storage.py    profile.json + PNG templates, zip export/import (unicode-safe image I/O)
  matcher.py    Matcher: OpenCV multi-scale template matching (pure function of numpy arrays)
  screen.py     ScreenProvider ABC, MssScreen (real), Frame/Rect coordinate maths
  inputs.py     InputProvider ABC, PyAutoGuiInput (real), NullInput
  fakes.py      FakeScreen / FakeInput  (tests)       clock.py  Clock / FakeClock
  runner.py     Runner: the step engine; talks only to the abstractions; never raises
  hotkey.py     global stop hotkey (pynput)           platform_utils.py  OS, DPI, permissions
  keystate.py   hook-free stop key (Windows)         presets.py         display presets, monitor auto-pick
  diagnose.py   "why was it not found" + fixes        app.py             entry point, --selftest, crash log
  gui/          PySide6 main window, step editor, capture overlay, highlighter, worker threads
  mock_window.py  fake story viewer used by the end-to-end tests
```

The Runner runs in a worker `QThread`; the GUI only receives events through signals, so it never freezes.

## Tests

`run.bat test` / `./run.sh test` (or `python -m pytest`). The report header states whether a real display is available.

| Area | File |
|---|---|
| Matcher: synthetic screenshots, several scales, noise, missing template, regions, flat templates | `tests/test_matcher.py` |
| Runner with fake providers: order, waits, jitter, retries, loops, click limit, stop signal, corner abort, end condition, dry-run | `tests/test_runner.py` |
| Profile save/load round trip, zip export/import, clamping, zip-slip | `tests/test_storage.py` |
| GUI: list ops, editor binding, capture-overlay coordinate mapping, highlighter, example profile | `tests/test_gui.py` |
| End-to-end vs. mock window (heart/arrow order and counts, click-only-if-found, end condition, dry-run, limits, corner, stop, full GUI flow) | `tests/test_e2e_mock_window.py` |
| Presets: model/storage, resolution matching, monitor-relative boxes, probing, fallback | `tests/test_presets.py` |
| GUI presets, two-stage template + search-box drag, per-monitor coordinates, box display | `tests/test_gui_presets.py` |
| End-to-end search boxes / auto-switch, incl. two displays of different resolution | `tests/test_e2e_presets.py` |
| Stop key polling | `tests/test_keystate.py` |

The end-to-end tests run on two backends: **real** (mss screenshots + pyautogui mouse; needs an unlocked display, otherwise they are
reported as skipped with the reason) and **qt** (identical Runner/Matcher/window, but screenshots and clicks go through Qt, so they
work headless). The real backend moves your actual mouse for a few seconds.

## Known limits

* Image matching needs the icon to look similar to the template (theme/colour changes need a new template; multi-scale handles size only, not rotation).
* The stop hotkey uses `pynput`; on macOS it may need Input Monitoring permission, on Linux an X11 session. The Stop button and corner abort always work.
* Mixed-DPI multi-monitor setups are best effort; pick one monitor in Global settings if captures look offset. Multi-monitor auto-switching is verified with simulated displays (two windows of different resolution) and on a single real monitor, not on a real second monitor.
* Not tested on macOS or Linux (only on Windows 11) - see the final report.

> **Scrolling never changes a setting.** Drop-downs and number boxes ignore the mouse wheel until you click into them, so
> scrolling the step editor cannot flip e.g. *Left click* into *Right click*. The step list also flags any non-left click type
> (`[RIGHT-CLICK]`), and every run starts by logging what each step will do.

## License

ClickFlow is free software under the **[MIT License](../LICENSE)**. The packaged program bundles third-party components under their own
licences (notably **Qt for Python / PySide6 and pynput under the LGPL-3.0**, OpenCV under Apache-2.0); see
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) and the full texts in [`LICENSES/`](../LICENSES/). The program also shows them under
*Help > Open-source licenses*. Contributions are welcome: see [CONTRIBUTING.md](../CONTRIBUTING.md). No warranty; you are responsible for how you use it.
