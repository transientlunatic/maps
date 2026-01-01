#!/usr/bin/env python3
"""Export styles only for layers using safe providers to avoid QGIS crashes.

Usage: export_styles_safe.py [--force]

Runs inside QGIS Python and writes QML files into `styling/`.
"""
import os
import sys

force = False
args = sys.argv[1:]
if args and args[0] == '--force':
    force = True
    args = args[1:]

try:
    from qgis.core import QgsApplication, QgsProject
except Exception:
    print("Error: QGIS Python bindings not available. Run this with QGIS Python.")
    sys.exit(2)

ROOT = os.path.abspath(os.getcwd())
proj_path = os.path.join(ROOT, 'projects', 'basemap.qgz')
styling_dir = os.path.join(ROOT, 'styling')
os.makedirs(styling_dir, exist_ok=True)

QgsApplication.setPrefixPath(os.environ.get('QGIS_PREFIX_PATH', ''), True)
qgs = QgsApplication([], False)
qgs.initQgis()

project = QgsProject.instance()
if not project.read(proj_path):
    print(f"Failed to read project: {proj_path}")
    qgs.exitQgis()
    sys.exit(2)

# Providers that are generally safe to export styles from
SAFE_PROVIDERS = set(['delimitedtext', 'ogr', 'gdal', 'postgres', 'spatialite'])

for layer in project.mapLayers().values():
    try:
        ptype = layer.providerType()
    except Exception:
        ptype = ''
    name = layer.name()
    if ptype not in SAFE_PROVIDERS:
        print(f"Skipping layer {name} with provider {ptype}")
        continue

    out_path = os.path.join(styling_dir, f"{name}.qml")
    if os.path.exists(out_path) and not force:
        print(f"Skipping existing style {out_path}")
        continue

    print(f"Exporting style for layer {name} (provider={ptype}) -> {out_path}")
    try:
        layer.saveNamedStyle(out_path)
    except Exception as e:
        print(f"  Failed to save style for {name}: {e}")

qgs.exitQgis()
sys.exit(0)
