# Changelog

## 1.1.0

First public release.

* Single-file Windows build (`ClickFlow.exe`) with a built-in `--selftest`; MIT licence, third-party notices, licence viewer in the Help menu.
* **Speed slider**: one control for the time between clicks (fastest = no added delay, slowest = 1.5 s) with an *Advanced* manual mode.
* **Search boxes** with an automatic "template, then search box" drag, per-step boxes shown on screen, and **display presets** that are
  selected (together with the monitor) from the detected screen resolutions.
* **Test this step** now says whether a run would click and diagnoses why not (icon size outside the scale range, outside the search box,
  threshold too strict, absent) with one-click fixes. Template scale search widened to 0.35-2.5x; the matching scale is remembered.
* Drop-downs and number boxes ignore the mouse wheel until focused (scrolling no longer changes settings); non-left click types are flagged.
* Reliable stop: hook-free stop-key polling on Windows, red STOP button, screen-corner stop.
* Saving commits half-typed values; the last used profile is reopened.

## 1.0.0

Initial version: step engine, matcher, GUI, profiles, dry run, end condition, example profile.
