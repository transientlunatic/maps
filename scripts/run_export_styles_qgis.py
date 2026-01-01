#!/usr/bin/env python3
"""Wrapper to run export_styles.py under QGIS when invoked with `qgis.bin --code <file>`.

This script sets up absolute paths and argv for the exporter, then
executes the `scripts/export_styles.py` module in-process.
"""
import os
import sys

# Use the current working directory (Makefile and commands run with cwd
# set to the repository root). Avoid relying on __file__ which may not be
# defined when QGIS exec()s the file content.
ROOT = os.path.abspath(os.getcwd())
HERE = os.path.join(ROOT, 'scripts')
proj = os.path.join(ROOT, 'projects', 'basemap.qgz')
styling = os.path.join(ROOT, 'styling')

sys.argv = ['export_styles.py', '--force', proj, styling]

script_path = os.path.join(HERE, 'export_styles.py')
if not os.path.exists(script_path):
    print('export_styles.py not found at', script_path)
    sys.exit(2)

exec(open(script_path).read())
