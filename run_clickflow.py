"""Launcher used by run.bat / run.sh and by the PyInstaller build."""
import sys

from clickflow.app import main

if __name__ == "__main__":
    sys.exit(main())
