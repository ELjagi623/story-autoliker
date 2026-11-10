# Changelog

## 1.2.0 - 2026-11-10

**Transparent icons and "not found" fallbacks** (profile schema 4; older profiles open unchanged, every new option is off).

* **Outline / transparent icon** matching mode: only the icon's stroke is compared, so see-through icons such as Instagram's outline
  heart are no longer missed on busy story backgrounds. *Test this step* diagnoses this case and offers the switch as a one-click fix.
* **Look again where it was last found**: a relaxed search right around the last match before giving up.
* **If still not found, click where it was last found**, guarded by a **Skip if this image is there** image (e.g. the red, liked heart),
  at most 3 blind clicks in a row and only within 5 loops of a real match.
* The Instagram example turns on outline mode and the rescue for the heart step.

**Redesigned interface** (profiles from 1.1.0 open as before).

* New look with **light and dark themes** (follows the system, switchable in the top bar) and an **English / Chinese** interface.
* **Simple and Advanced modes.** Simple shows only: the step cards, the target image, click type, *click only if found*, a three-step
  speed control, repeat count / infinite and a click limit. Advanced unfolds every setting in collapsible groups
  (*Basic, Match, Search area, Click, Waits & failure handling*) plus a *Global settings* tab (stop hotkey, timing, end condition,
  display presets, notes).
* **Run dashboard** while running: status, clicks, loops, elapsed time, current step and the latest match confidence; the big Start
  button turns into *Stop - F8*. A welcome screen guides an empty profile.
* Friendlier wording: *template -> target image*, *search box -> search area*, *threshold -> match strictness*, *Monitor 0..16 -> a
  display drop-down*. The stop hotkey is now captured by pressing the key instead of typing its name.
* Restyled screen overlays (selection, match boxes, red STOP badge). Target thumbnails are still hidden while a run is active.
* Icons: original MIT artwork (`assets/icons/icons.svg`), rendered with QtSvg.

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
