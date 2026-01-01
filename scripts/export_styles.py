#!/usr/bin/env python3
"""Export QGIS layer styles from a project into QML files.

Usage: export_styles.py [--force] PROJECT_QGZ STYLING_DIR

Requires QGIS Python environment (qgis.core).
"""
import os
import sys

force = False
args = sys.argv[1:]
if args and args[0] == '--force':
    force = True
    args = args[1:]

if len(args) < 2:
    print("Usage: export_styles.py [--force] PROJECT_QGZ STYLING_DIR")
    sys.exit(2)

proj_path = args[0]
styling_dir = args[1]

try:
    from qgis.core import QgsApplication, QgsProject
except Exception:
    print("Error: QGIS Python bindings not available. Run this with QGIS Python.")
    sys.exit(2)

if not os.path.isfile(proj_path):
    print(f"Project not found: {proj_path}")
    sys.exit(2)
os.makedirs(styling_dir, exist_ok=True)

QgsApplication.setPrefixPath(os.environ.get('QGIS_PREFIX_PATH', ''), True)
qgs = QgsApplication([], False)
qgs.initQgis()

project = QgsProject.instance()
if not project.read(proj_path):
    print(f"Failed to read project: {proj_path}")
    qgs.exitQgis()
    sys.exit(2)

for layer in project.mapLayers().values():
    name = layer.name()
    try:
        src = layer.source()
        basename = os.path.splitext(os.path.basename(src))[0]
    except Exception:
        basename = None

    out_name = f"{name}.qml"
    out_path = os.path.join(styling_dir, out_name)
    if os.path.exists(out_path) and not force:
        print(f"Skipping existing style {out_path} (use --force to overwrite)")
        continue

    print(f"Exporting style for layer {name} -> {out_path}")
    try:
        # Try saving by layer name first; API may vary so we guard exceptions
        ok = False
        try:
            layer.saveNamedStyle(out_path)
            ok = True
        except Exception:
            # fallback: attempt to write style via layer.renderer().dump()
            try:
                style_xml = layer.renderer().dump()
                with open(out_path, 'w') as fh:
                    fh.write(style_xml)
                ok = True
            except Exception as e:
                print(f"  Failed to export style for {name}: {e}")
        if not ok:
            print(f"  Could not export style for {name}")
    except Exception as e:
        print(f"  Error exporting style for {name}: {e}")

qgs.exitQgis()
sys.exit(0)
