#!/usr/bin/env python3
"""Export a single layer's style when run under QGIS (use env LAYER_TO_EXPORT).

Run via:
  LAYER_TO_EXPORT='Layer Name' /usr/bin/qgis.bin --noplugins --code /path/to/export_one_layer_qgis.py

This avoids passing large inline code and lets us probe layers individually.
"""
import os
import sys

layer_name = os.environ.get('LAYER_TO_EXPORT')
if not layer_name:
    print('LAYER_TO_EXPORT not set')
    sys.exit(2)

ROOT = os.path.abspath(os.getcwd())
proj_path = os.path.join(ROOT, 'projects', 'basemap.qgz')
styling_dir = os.path.join(ROOT, 'styling')
os.makedirs(styling_dir, exist_ok=True)

try:
    from qgis.core import QgsApplication, QgsProject
except Exception:
    print('QGIS Python bindings not available')
    sys.exit(2)

QgsApplication.setPrefixPath(os.environ.get('QGIS_PREFIX_PATH', ''), True)
qgs = QgsApplication([], False)
qgs.initQgis()

project = QgsProject.instance()
if not project.read(proj_path):
    print('Failed to read project', proj_path)
    qgs.exitQgis()
    sys.exit(2)

target_layer = None
for layer in project.mapLayers().values():
    if layer.name() == layer_name:
        target_layer = layer
        break

if target_layer is None:
    # try matching by source basename
    for layer in project.mapLayers().values():
        try:
            src = layer.source()
            base = os.path.splitext(os.path.basename(src))[0]
            if base == layer_name:
                target_layer = layer
                break
        except Exception:
            continue

if target_layer is None:
    print('Layer not found in project:', layer_name)
    qgs.exitQgis()
    sys.exit(3)

out_path = os.path.join(styling_dir, f"{layer_name}.qml")
print('Exporting', layer_name, '->', out_path)
try:
    target_layer.saveNamedStyle(out_path)
    print('OK')
except Exception as e:
    print('Error exporting', layer_name, e)

qgs.exitQgis()
sys.exit(0)
