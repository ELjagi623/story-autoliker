"""Build the standalone Windows program with PyInstaller.

    python build_exe.py            -> dist/ClickFlow.exe        (one self-contained file)
    python build_exe.py --onedir   -> dist/ClickFlow/           (folder; easier to swap the LGPL libraries)

Needs `pip install -r requirements-dev.txt`. Also prints the file size and SHA-256 and runs the built program's
own self-test (`ClickFlow.exe --selftest`), so a broken bundle is caught immediately.
"""
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent
env = dict(os.environ)
onedir = "--onedir" in sys.argv
if onedir:
    env["CLICKFLOW_ONEDIR"] = "1"

cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(root / "clickflow.spec")]
print(" ".join(cmd))
rc = subprocess.call(cmd, cwd=root, env=env)
if rc:
    sys.exit(rc)

exe = root / "dist" / ("ClickFlow/ClickFlow.exe" if onedir else "ClickFlow.exe")
if not exe.exists():  # macOS / Linux builds have no .exe suffix
    exe = exe.with_suffix("")
if not exe.exists():
    sys.exit(f"build finished but {exe} was not found")

digest = hashlib.sha256(exe.read_bytes()).hexdigest()
(exe.parent / (exe.name + ".sha256")).write_text(f"{digest}  {exe.name}\n", encoding="utf-8")
print(f"\nBuilt {exe}  ({exe.stat().st_size / 1e6:.1f} MB)\nSHA-256 {digest}")

report = Path(tempfile.mkdtemp()) / "selftest.txt"
print("\nRunning the packaged program's self-test ...")
subprocess.call([str(exe), "--selftest", str(report)], cwd=tempfile.gettempdir(), timeout=180)
text = report.read_text(encoding="utf-8") if report.exists() else "(no report written)"
print(text)
sys.exit(0 if "RESULT: ALL OK" in text else 1)
