#!/usr/bin/env bash
# One-command launcher (macOS / Linux):  ./run.sh        -> start ClickFlow
#                                        ./run.sh test   -> run the test suite
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
if [ ! -x ".venv/bin/python" ]; then
    echo "Creating virtual environment..."
    "$PY" -m venv .venv
fi
if [ ! -f ".venv/.deps_installed" ]; then
    echo "Installing dependencies..."
    .venv/bin/python -m pip install --quiet --upgrade pip
    .venv/bin/python -m pip install --quiet -r requirements-dev.txt
    touch .venv/.deps_installed
fi
if [ "$1" = "test" ]; then
    shift
    exec .venv/bin/python -m pytest "$@"
fi
exec .venv/bin/python run_clickflow.py "$@"
