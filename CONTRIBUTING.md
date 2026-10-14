# Contributing to ClickFlow

Thanks for helping! Bug reports, ideas and pull requests are welcome.

## Set up

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt      # Windows;  .venv/bin/pip on macOS/Linux
.venv\Scripts\python -m pytest                          # or: run.bat test / ./run.sh test
.venv\Scripts\python run_clickflow.py                   # start the app
```

## Tests

The test report header says whether a real display is available.

* Everything except the *real* end-to-end tests runs without a display (Qt's offscreen platform is used).
* The **real** tests (`tests/test_e2e_*.py`, `[real]` variants) drive your actual mouse and screen against a small mock window for a few
  seconds. They are skipped automatically, with a reason, when the desktop is locked or headless. Don't touch the mouse while they run.
* New behaviour should come with a test. The `Runner` works with fake providers (`clickflow/fakes.py`), the matcher is a pure function
  of numpy arrays, and the GUI can be exercised offscreen - prefer those over real-screen tests.

## Design rules worth keeping

* **No site- or app-specific logic.** ClickFlow is generic; example data (profiles) may mention a site, code must not.
* Keep the separation: `ScreenProvider` / `InputProvider` / `Matcher` / `Runner` / profile storage / GUI. The Runner never raises.
* Anything that clicks must be stoppable immediately (stop key, STOP button, screen corner) - waits are interruptible slices.
* Coordinates: matching works in screenshot pixels, clicks in screen units; `Frame` converts (HiDPI / Retina).
* Don't add dependencies lightly: the packaged exe ships all of them. A dependency under GPL/AGPL cannot be bundled with the MIT code
  (see `THIRD_PARTY_NOTICES.md`; e.g. PyAutoGUI's optional `mouseinfo` is excluded for that reason).

## Building the exe

`python build_exe.py` (see `clickflow.spec`). If you add or remove a bundled third-party package, update `THIRD_PARTY_NOTICES.md` and the
`LICENSES/` folder in the same pull request.

## Pull requests

Keep them focused, describe what changed and how you tested it, and make sure `python -m pytest` passes. By contributing you agree that your
contribution is licensed under the project's MIT License.
