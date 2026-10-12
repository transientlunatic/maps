#!/usr/bin/env python3
"""Render an XYZ PNG tile set from the QGIS project using headless QGIS.

Usage:
    QT_QPA_PLATFORM=offscreen python3 scripts/render_tiles.py \
        --project projects/basemap.qgz --tileset topology \
        --extent -4.5,56.2,-4.2,56.35 --zmin 9 --zmax 12

Each tile set is a list of layers from the project that are switched on while
every other layer is switched off. Tiles are written to
<out>/<tileset>/<version>/{z}/{x}/{y}.png.

Needs the QGIS Python bindings (python3-qgis on Debian/Ubuntu) and, because
the OSM water and forest layers are ArcGIS vector tile services, network
access to basemaps.arcgis.com.
"""
import argparse
import os
import sys

# Layers (by name in the project) drawn for each tile set, listed top to
# bottom. The order here overrides the project's own: the project draws the
# contours beneath the forest, which hides them.
TILESETS = {
    "topology": {
        "layers": [
            "Contours",
            "OSM - Water",
            "OSM - Forestry",
            "merged-hillshade-315",
            "merged-dem",
        ],
        "transparent": False,
    },
    "dbobih": {
        "layers": ["Database of British and Irish Hills"],
        "transparent": True,
    },
    "trigs": {
        "layers": ["Trig Points"],
        "transparent": True,
    },
    # Names of lochs, lined up along each loch's main axis. These layers are
    # not in the QGIS project: they are loaded from data/ and styled with the
    # QML in styling/ (open both in QGIS to edit the style).
    "waternames": {
        "layers": ["Water Names"],
        "extra_layers": {
            "Water Names": {
                "source": "data/water-names.gpkg|layername=water_names",
                "style": "styling/Water Names.qml",
            },
        },
        "transparent": True,
    },
}


# Label fields that hold a feature's name (the other labels show heights etc.)
NAME_FIELDS = {"Name", "tp_name", "string_to_array(\"Name\", ' [', '')[0]"}


def set_name_font(layer, family):
    """Switch the font of the layer's name labels to `family`."""
    from qgis.core import QgsRuleBasedLabeling

    labeling = layer.labeling()
    if not isinstance(labeling, QgsRuleBasedLabeling):
        return
    for rule in labeling.rootRule().descendants():
        settings = rule.settings()
        if settings is None or settings.fieldName not in NAME_FIELDS:
            continue
        settings = type(settings)(settings)
        fmt = settings.format()
        font = fmt.font()
        font.setFamily(family)
        fmt.setFont(font)
        fmt.setNamedStyle("Regular")
        settings.setFormat(fmt)
        rule.setSettings(settings)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--project", required=True, help="QGIS project (.qgz/.qgs)")
    p.add_argument("--tileset", required=True, choices=sorted(TILESETS))
    p.add_argument("--out", default="data/tiles", help="output root directory")
    p.add_argument("--version", default="dev", help="version directory name")
    p.add_argument(
        "--extent", required=True,
        help="west,south,east,north in degrees (EPSG:4326)",
    )
    p.add_argument(
        "--name-font", default="Lato",
        help="font family for hill and trig point names ('' keeps the project's)",
    )
    p.add_argument("--zmin", type=int, default=9)
    p.add_argument("--zmax", type=int, default=13)
    p.add_argument("--dpi", type=int, default=96)
    p.add_argument(
        "--metatile", type=int, default=9,
        help="tiles per metatile side (avoids label clipping at tile edges)",
    )
    return p.parse_args()


def main():
    args = parse_args()

    from qgis.core import (
        QgsApplication,
        QgsProcessingContext,
        QgsProcessingFeedback,
        QgsProject,
        QgsVectorLayer,
    )

    west, south, east, north = (float(v) for v in args.extent.split(","))
    spec = TILESETS[args.tileset]

    app = QgsApplication([], False)
    app.initQgis()

    # The processing plugin lives in a QGIS-specific directory
    sys.path.append(os.path.join(QgsApplication.pkgDataPath(), "python", "plugins"))
    import processing
    from processing.core.Processing import Processing

    Processing.initialize()

    project = QgsProject.instance()
    if not project.read(args.project):
        sys.exit(f"Could not read project {args.project}")

    # Layers that are not part of the project: load them with their QML style.
    for name, extra in spec.get("extra_layers", {}).items():
        layer = QgsVectorLayer(extra["source"], name, "ogr")
        if not layer.isValid():
            sys.exit(f"Could not open {extra['source']} (run `make {args.tileset}`)")
        _, ok = layer.loadNamedStyle(extra["style"])
        if not ok:
            sys.exit(f"Could not load style {extra['style']}")
        project.addMapLayer(layer)

    # Switch off everything, then switch on this tile set's layers.
    root = project.layerTreeRoot()
    for node in root.findLayers():
        node.setItemVisibilityChecked(False)
    ordered = []
    for name in spec["layers"]:
        layers = project.mapLayersByName(name)
        if not layers:
            sys.exit(f"Layer {name!r} not found in {args.project}")
        ordered.append(layers[0])
        if args.name_font:
            set_name_font(layers[0], args.name_font)
        node = root.findLayer(layers[0].id())
        # Parent groups must be on too, or the layer will not draw.
        node.setItemVisibilityCheckedParentRecursive(True)
    root.setHasCustomLayerOrder(True)
    root.setCustomLayerOrder(ordered)

    context = QgsProcessingContext()
    context.setProject(project)

    out_dir = os.path.join(args.out, args.tileset, args.version)
    os.makedirs(out_dir, exist_ok=True)

    from qgis.PyQt.QtGui import QColor

    background = QColor(0, 0, 0, 0) if spec["transparent"] else QColor(255, 255, 255, 255)
    for z in range(args.zmin, args.zmax + 1):
        print(f"[{args.tileset}] zoom {z}", flush=True)
        processing.run(
            "native:tilesxyzdirectory",
            {
                "EXTENT": f"{west},{east},{south},{north} [EPSG:4326]",
                "ZOOM_MIN": z,
                "ZOOM_MAX": z,
                "DPI": args.dpi,
                "BACKGROUND_COLOR": background,
                "ANTIALIAS": True,
                "TILE_FORMAT": 0,  # PNG
                "QUALITY": 75,
                "METATILESIZE": args.metatile,
                "TILE_WIDTH": 256,
                "TILE_HEIGHT": 256,
                "TMS_CONVENTION": False,
                "HTML_TITLE": "",
                "HTML_ATTRIBUTION": "",
                "HTML_OSM": False,
                "OUTPUT_DIRECTORY": out_dir,
                "OUTPUT_HTML": "TEMPORARY_OUTPUT",
            },
            context=context,
            feedback=QgsProcessingFeedback(),
        )

    app.exitQgis()


if __name__ == "__main__":
    main()
