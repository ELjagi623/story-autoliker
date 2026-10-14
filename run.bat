@echo off
rem One-command launcher (Windows):  run.bat          -> start ClickFlow
rem                                   run.bat test     -> run the test suite
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    if errorlevel 1 ( echo Python 3.11+ is required. Install it from python.org & exit /b 1 )
)
if not exist ".venv\.deps_installed" (
    echo Installing dependencies...
    ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    ".venv\Scripts\python.exe" -m pip install --quiet -r requirements-dev.txt || exit /b 1
    echo ok> ".venv\.deps_installed"
)
if /i "%~1"=="test" (
    ".venv\Scripts\python.exe" -m pytest %2 %3 %4 %5
) else (
    ".venv\Scripts\python.exe" run_clickflow.py %*
)
