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
            "Sea",
            "OSM - Water",
            "merged-hillshade-315",
            "merged-dem",
        ],
        "extra_layers": {
            "Sea": {
                "source": "data/sea.gpkg|layername=sea",
                "style": "styling/Sea.qml",
            },
        },
        # Styles from styling/ that replace the project's own for these layers.
        # The DEM ramp has extra levels below 200 m (see scripts/lowland_ramp.py).
        "styles": {"merged-dem": "styling/merged-dem.qml"},
        # Sharp coastlines: the project's sea is a coarse polygon that its style blurs. The
        # "Sea" layer (from the DEM, `make data/sea.gpkg`) replaces it. (The forest keeps
        # its soft edge.)
        "replace_sea": "OSM - Water",
        "transparent": False,
    },
    # Forest, drawn from the project's "OSM - Forestry" layer as a transparent overlay so
    # that it can be switched off. Put it above the topology.
    "forests": {
        "layers": ["OSM - Forestry"],
        "transparent": True,
    },
    # Valley mist from data/mist.tif (`make data/mist.tif`), after Eduard Imhof's aerial
    # perspective: a pale blue haze that collects on valley floors in rugged country. It is
    # strongest zoomed out and fades as you zoom in, so it never washes out close-up detail.
    "mist": {
        "layers": ["Valley Mist"],
        "extra_layers": {
            "Valley Mist": {
                "type": "raster",
                "source": "data/mist.tif",
                "style": "styling/Valley Mist.qml",
            },
        },
        "opacity_by_zoom": {9: 1.0, 10: 1.0, 11: 0.85, 12: 0.55, 13: 0.3},
        "transparent": True,
    },
    "dbobih": {
        "layers": ["Database of British and Irish Hills"],
        "transparent": True,
    },
    "trigs": {
        "layers": ["Trig Points"],
        "transparent": True,
    },
    # Railways and stations from OpenStreetMap (`make data/transport.gpkg`).
    # These layers are not in the QGIS project: they are loaded from data/ and
    # styled with the QML in styling/, so railways and stations stand out
    # against the topology. Open both in QGIS to edit the styles.
    "transport": {
        "layers": ["Rail Stations", "Rail Lines"],
        "extra_layers": {
            "Rail Lines": {
                "source": "data/transport.gpkg|layername=rail_lines",
                "style": "styling/Rail Lines.qml",
            },
            "Rail Stations": {
                "source": "data/transport.gpkg|layername=rail_stations",
                "style": "styling/Rail Stations.qml",
            },
        },
        "transparent": True,
    },
    # A quiet road layer (`make data/roads.gpkg`): thin grey lines that stay
    # behind the railways. Styled with styling/Roads.qml.
    "roads": {
        "layers": ["Roads"],
        "extra_layers": {
            "Roads": {
                "source": "data/roads.gpkg|layername=roads",
                "style": "styling/Roads.qml",
            },
        },
        "transparent": True,
    },
    # Bothies and shelters (`make data/shelters.gpkg`), styled with styling/Shelters.qml.
    "shelters": {
        "layers": ["Shelters"],
        "extra_layers": {
            "Shelters": {
                "source": "data/shelters.gpkg|layername=shelters",
                "style": "styling/Shelters.qml",
            },
        },
        "transparent": True,
    },
    # Footpaths, tracks and bridleways (`make data/paths.gpkg`), styled with styling/Paths.qml.
    "paths": {
        "layers": ["Paths"],
        "extra_layers": {
            "Paths": {
                "source": "data/paths.gpkg|layername=paths",
                "style": "styling/Paths.qml",
            },
        },
        "transparent": True,
    },
    # Named rivers, streams and canals with labels along them, plus waterfalls
    # (`make data/rivers.gpkg`), styled with styling/Rivers.qml and styling/Waterfalls.qml.
    "rivers": {
        "layers": ["Waterfalls", "Rivers"],
        "extra_layers": {
            "Rivers": {
                "source": "data/rivers.gpkg|layername=rivers",
                "style": "styling/Rivers.qml",
            },
            "Waterfalls": {
                "source": "data/rivers.gpkg|layername=waterfalls",
                "style": "styling/Waterfalls.qml",
            },
        },
        "transparent": True,
    },
    # Trailheads and facilities (`make data/facilities.gpkg`): car parks, campsites, hostels,
    # toilets, viewpoints, visitor centres, ferry terminals and routes, mountain rescue posts.
    "facilities": {
        "layers": ["Facilities", "Ferries"],
        "extra_layers": {
            "Facilities": {
                "source": "data/facilities.gpkg|layername=facilities",
                "style": "styling/Facilities.qml",
            },
            "Ferries": {
                "source": "data/facilities.gpkg|layername=ferries",
                "style": "styling/Ferries.qml",
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


def drop_project_sea(layer):
    """Switch off the sea polygons of a vector tile layer styled like "OSM - Water".

    The project draws a coarse, generalised sea and blurs it; the topology tiles draw a sharper
    sea from the DEM instead (the "Sea" layer), so both of the project's sea styles go. Its beach
    polygons follow the same coarse coast, so they would show as a stripe beside the new, more
    accurate coastline and go too.
    """
    from qgis.core import QgsVectorTileBasicRenderer

    styles = layer.renderer().styles()
    for style in styles:
        if style.styleName() in ("ocean (small scale)", "ocean (large scale)") or style.layerName() == "beach":
            style.setEnabled(False)
    renderer = QgsVectorTileBasicRenderer()
    renderer.setStyles(styles)
    layer.setRenderer(renderer)


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
        QgsRasterLayer,
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

    if spec.get("replace_sea"):
        drop_project_sea(project.mapLayersByName(spec["replace_sea"])[0])

    for name, qml in spec.get("styles", {}).items():
        _, ok = project.mapLayersByName(name)[0].loadNamedStyle(qml)
        if not ok:
            sys.exit(f"Could not load style {qml}")

    # Layers that are not part of the project: load them with their QML style.
    for name, extra in spec.get("extra_layers", {}).items():
        if extra.get("type") == "raster":
            layer = QgsRasterLayer(extra["source"], name, "gdal")
        else:
            layer = QgsVectorLayer(extra["source"], name, "ogr")
        if not layer.isValid():
            sys.exit(f"Could not open {extra['source']} (run `make data/transport.gpkg`)")
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
        # Some tile sets fade with zoom: set the opacity of their layers for this zoom
        fade = spec.get("opacity_by_zoom")
        if fade:
            for layer in ordered:
                layer.setOpacity(fade.get(z, 1.0))
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
