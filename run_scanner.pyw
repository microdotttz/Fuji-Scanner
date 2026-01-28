#!/usr/bin/env python
"""
Launcher script for Fuji TCG Scanner GUI.

Double-click this file to launch the scanner application.
"""

import sys
import os

# Add src to path for development
src_path = os.path.join(os.path.dirname(__file__), 'src')
if os.path.exists(src_path):
    sys.path.insert(0, src_path)

from fuji_tcg_scanner.gui import run_gui

if __name__ == "__main__":
    run_gui()
