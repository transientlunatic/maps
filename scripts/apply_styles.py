#!/usr/bin/env python3
"""Apply QML styles from a styling directory to layers in a QGIS project.

Usage (when run by qgis.bin):
  qgis.bin --code scripts/apply_styles.py [project_path] [styling_dir]

If run outside QGIS, the script will exit with a helpful message.
"""
import os
import sys

ROOT = os.path.abspath(os.getcwd())

def main():
    proj_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'projects', 'basemap.qgz')
    styling_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'styling')

    try:
        from qgis.core import QgsApplication, QgsProject
    except Exception as e:
        print('This script must be run with the QGIS Python environment (qgis.bin --code).')
        print('Import error:', e)
        sys.exit(2)

    app = QgsApplication([], False)
    app.initQgis()

    proj = QgsProject.instance()
    if not os.path.exists(proj_path):
        print('Project not found:', proj_path)
        app.exitQgis()
        sys.exit(2)

    ok = proj.read(proj_path)
    if not ok:
        print('Failed to read project:', proj_path)
        app.exitQgis()
        sys.exit(2)

    layers = list(proj.mapLayers().values())
    print('Found', len(layers), 'layers in project')

    applied = 0
    for layer in layers:
        name = layer.name()
        qml_name = name + '.qml'
        qml_path = os.path.join(styling_dir, qml_name)
        if os.path.exists(qml_path):
            try:
                res, msg = layer.loadNamedStyle(qml_path)
                if res:
                    layer.triggerRepaint()
                    applied += 1
                    print('Applied style to', name)
                else:
                    print('Failed to apply style to', name, '-', msg)
            except Exception as e:
                print('Error applying style to', name, '-', e)
        else:
            print('No QML for', name)

    # save project (overwrite)
    try:
        proj.write(proj_path)
        print('Project saved:', proj_path)
    except Exception as e:
        print('Failed to save project:', e)

    print('Styles applied:', applied)
    app.exitQgis()

if __name__ == '__main__':
    main()
#!/usr/bin/env python3
"""Apply QGIS QML styles from a styling directory to layers in a project.

Usage: apply_styles.py PROJECT_QGZ STYLING_DIR

Requires QGIS Python environment (qgis.core). Run under the same Python
environment as QGIS, or set `QGIS_PREFIX_PATH` env var appropriately.
"""
import os
import sys

try:
    from qgis.core import QgsApplication, QgsProject
except Exception as e:
    print("Error: QGIS Python bindings not available. Run this with QGIS Python.")
    sys.exit(2)

def main():
    if len(sys.argv) < 3:
        print("Usage: apply_styles.py PROJECT_QGZ STYLING_DIR")
        return 2

    proj_path = sys.argv[1]
    styling_dir = sys.argv[2]

    if not os.path.isfile(proj_path):
        print(f"Project not found: {proj_path}")
        return 2
    if not os.path.isdir(styling_dir):
        print(f"Styling directory not found: {styling_dir}")
        return 2

    QgsApplication.setPrefixPath(os.environ.get('QGIS_PREFIX_PATH', ''), True)
    qgs = QgsApplication([], False)
    qgs.initQgis()

    project = QgsProject.instance()
    if not project.read(proj_path):
        print(f"Failed to read project: {proj_path}")
        qgs.exitQgis()
        return 2

    for layer in project.mapLayers().values():
        name = layer.name()
        # fallback to basename of source (without ext)
        try:
            src = layer.source()
            basename = os.path.splitext(os.path.basename(src))[0]
        except Exception:
            basename = None

        candidates = []
        if name:
            candidates.append(os.path.join(styling_dir, f"{name}.qml"))
        if basename:
            candidates.append(os.path.join(styling_dir, f"{basename}.qml"))

        applied = False
        for qml in candidates:
            if os.path.isfile(qml):
                print(f"Applying style {qml} -> layer {name}")
                try:
                    res = layer.loadNamedStyle(qml)
                    # API may return (ok, err) or bool
                    if isinstance(res, tuple):
                        ok, err = res
                    else:
                        ok = bool(res)
                        err = None
                    if not ok:
                        print(f"  Warning: failed to apply {qml}: {err}")
                    else:
                        layer.triggerRepaint()
                        applied = True
                except Exception as e:
                    print(f"  Error applying {qml}: {e}")
                break

        if not applied:
            print(f"No style found for layer {name}")

    project.write(proj_path)
    qgs.exitQgis()
    return 0

if __name__ == '__main__':
    sys.exit(main())
