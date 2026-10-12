# Basemap project

Builds the map tiles for Scotland used at <https://www.daniel-williams.co.uk/map/>.

The cartography lives in a QGIS project (`projects/basemap.qgz`, with layer styles
exported to `styling/`). This repository prepares the data the project needs and
renders it to XYZ PNG tiles with headless QGIS, so the tiles can be regenerated
without opening QGIS.

Each build goes in a version directory (`<version>` below): `dev` by default, or
the release tag for release builds (`make TILE_VERSION=v1.2 ...`).

Three tile sets are produced, matching the layers in the site's Leaflet map:

| Tile set   | Contents                                                              | Path                                   |
|------------|-----------------------------------------------------------------------|----------------------------------------|
| `topology` | Hypsometric tints, hillshade, contours, OSM water and forest          | `data/tiles/topology/<version>/{z}/{x}/{y}.png` |
| `dbobih`   | Hill markers, names and heights (transparent)                         | `data/tiles/dbobih/<version>/{z}/{x}/{y}.png`   |
| `trigs`    | Ordnance Survey trig points (transparent)                             | `data/tiles/trigs/<version>/{z}/{x}/{y}.png`    |
| `transport` | Railways (one solid dark grey line) and stations (dark circles with names) (transparent) | `data/tiles/transport/<version>/{z}/{x}/{y}.png` |
| `roads` | Main roads as thin grey lines, quieter than the railways (transparent) | `data/tiles/roads/<version>/{z}/{x}/{y}.png` |
| `shelters` | Bothies (blue discs) and shelters (hollow discs) with names (transparent) | `data/tiles/shelters/<version>/{z}/{x}/{y}.png` |
| `waternames` | Names of lochs and reservoirs: label lines as GeoJSON (vector), drawn in the browser | `data/tiles/waternames/<version>/water-names.geojson` |

## Data sources

- **Elevation**: [ViewfinderPanoramas](http://viewfinderpanoramas.org/dem3.html) DEM
  (SRTM-derived), downloaded as 4° × 6° block zips (`N29 N30 O29 O30` cover Scotland).
- **Water and forest**: OpenStreetMap, read by QGIS from the ArcGIS OSM vector tile
  service referenced in the project, so rendering needs internet access.
- **Hills**: `sources/dobih.csv`, the [Database of British and Irish Hills](https://www.hills-database.co.uk).
- **Trig points**: `sources/trigs.csv`.
- **Railways and stations**: `railway=*` ways and `railway=station|halt` nodes from the same
  Geofabrik extract (`make data/transport.gpkg`).
- **Water names**: the named water polygons in the OpenStreetMap
  [Geofabrik extract for Scotland](https://download.geofabrik.de/europe/united-kingdom/scotland.html)
  (about 300 MB, downloaded to `data/scotland.osm.pbf`).

## Prerequisites

- GNU Make, `curl`, `unzip`
- Fonts: Lato (hill and trig names) and Inter (heights and other labels), e.g.
  `fonts-lato fonts-inter` on Ubuntu
- GDAL command-line tools (`gdalbuildvrt`, `gdal_translate`, `gdaldem`, `gdal_contour`)
- Python with `shapely`, `scipy`, `numpy` and the GDAL bindings, for the water name lines
  (`python3-shapely python3-scipy python3-numpy python3-gdal` on Ubuntu)
- QGIS **3.40 or newer** with its Python bindings. The project was saved with QGIS 3.38,
  and the older QGIS 3.34 in Ubuntu 24.04 renders rasters blocky, so on Ubuntu use the
  [QGIS LTR repository](https://qgis.org/resources/installation-guide/#debianubuntu).
  Run `make` with a Python that can `import qgis`, which is the system Python on
  Debian/Ubuntu (`make QGIS_PYTHON=/usr/bin/python3 ...`).

## Usage

```bash
make sample          # Ben Ledi area, zooms 9-12, all three tile sets (~2 minutes)
make dem             # only the DEM, hillshade and contours
make topology        # one tile set for all of Scotland (zooms 9-13)
make tiles           # all three tile sets (slow; see below)
```

Useful variables (all have defaults in the Makefile):

```bash
make topology TILE_BBOX=-5,56,-4,57 TILE_ZMIN=9 TILE_ZMAX=12   # west,south,east,north
make dem HILLSHADE_Z=3 CONTOUR_INTERVAL=25
make sample QGIS_PYTHON=/usr/bin/python3
```

To look at the result, serve the tiles and point Leaflet at them:

```bash
python3 -m http.server -d data/tiles 8000
# L.tileLayer('http://localhost:8000/topology/<version>/{z}/{x}/{y}.png')
```

### How long does it take?

The topology tiles are slow to render, because QGIS fetches the OSM vector tiles
and renders every tile. Scotland at zoom 13 is roughly 40,000 tiles per tile set, so
a full build is a many-hour job. The release workflow builds each tile set in its own
job to stay inside GitHub's per-job limit.

## Water names

The names of lochs are placed along each loch's main axis, and unlike the other layers they
are vector data: the browser draws the text, so it uses the site's own fonts and stays sharp.

`scripts/water_centerlines.py` takes the named OSM water polygons and, for each one, finds
the longest path through its medial axis, so the line follows a winding loch rather than
cutting across it. It smooths the line (written to `data/water-names.gpkg`), and
`make waternames` converts the lines to a small GeoJSON file (`name`, `length_m`).

`preview/water-names.js` is a Leaflet layer that draws them with
[Leaflet.TextPath](https://github.com/makinacorpus/Leaflet.TextPath): size and letter
spacing grow with the loch's length, small lochs only appear at higher zooms, and names
that do not fit along their loch are dropped. Use it from your own map with:

```js
import { WaterNames } from './water-names.js';
new WaterNames('https://tiles.daniel-williams.co.uk/waternames/<version>/water-names.geojson').addTo(map);
```

`preview/index.html` shows all the layers together: run `python3 -m http.server` in the
repository root and open <http://localhost:8000/preview/> (add `?v=<version>` to see another
build).

Lochs that are arms of the sea (Loch Fyne, Loch Linnhe and so on) have no water polygon in
OSM, so they are not labelled by this layer.

## Transport

The `transport` tile set is a prototype of the transport network, with railways and stations
drawn to stand out against the terrain. It is rendered by QGIS from `data/transport.gpkg`
(layers `rail_lines` and `rail_stations`, extracted from the OSM file by `make`). Like the
water names it is not in `basemap.qgz`: `scripts/render_tiles.py` loads the layers and styles
them with `styling/Rail Lines.qml` and `styling/Rail Stations.qml`.

- Every railway is drawn as one solid dark grey line with a thin white edge so it reads over
  forest. The style deliberately drops detail: no tunnels, bridges or railway types, and
  sidings, yards and spurs (anything with `service=*`) are left out, which hides the number of
  tracks.
- Stations are dark circles with a white outline, sized by zoom, with bold Lato names; halts
  are slightly smaller and appear from zoom 11.

### Roads

The `roads` tile set is a deliberately quiet companion to the railways: thin mid-grey lines with
no casing or labels, drawn from `data/roads.gpkg` (`make data/roads.gpkg`) with
`styling/Roads.qml`. Only main roads are included (motorway down to residential), not tracks,
paths or service roads. Bigger roads are slightly darker and heavier and draw on top. Add it
beneath the `transport` layer so the railways stay on top.

Zoomed out (zoom 9 and 10) only motorways, trunk roads and primary roads are shown. Secondary
roads join at zoom 11, tertiary and unclassified roads at zoom 12 and residential streets at
zoom 13.

## Bothies and shelters

The `shelters` tile set (`make data/shelters.gpkg`, styled by `styling/Shelters.qml`) marks
bothies and shelters from OSM:

- **Bothies**: `tourism=wilderness_hut` or `bothy=yes`. Solid blue discs (the blue the QGIS
  project already uses for bothies) with a white edge, shown at every zoom, with names from
  zoom 11.
- **Shelters**: `amenity=shelter`, leaving out bus stop and picnic shelters (those with
  `shelter_type=public_transport` or `picnic_shelter`, or tagged `bus`/`public_transport`).
  Smaller hollow discs from zoom 12, with italic names from zoom 13.

Mapped buildings are reduced to a point inside them. The extraction uses
`scripts/osmconf.ini`, GDAL's default OSM configuration with the bothy and shelter tags
added as columns.

## Editing the styling

Layer styles are stored as `.qml` files in `styling/` so they can be diffed.

```bash
make export-styles          # project -> styling/
make apply-styles           # styling/ -> project
```

Hill and trig point names are drawn in Lato rather than the font stored in the project;
change it with `--name-font` (`''` keeps the project's font).

`scripts/render_tiles.py` chooses which project layers each tile set draws, and in
what order (it draws the contours above the forest, which the project itself does not).

## GitHub Actions

`.github/workflows/build-tiles.yml` builds on:

- **Push to main**: sample tiles for each tile set.
- **Release**: full tile sets. The release tag is the version in the tile URLs
  (`{tileset}/{tag}/{z}/{x}/{y}.png`), and each tile set is attached to the release as
  `<tileset>-<tag>.tar.gz`.
- **Manual run**: sample only (version `sample`). Full builds only happen on a release.

## Lowland colours

The DEM colour ramp (`styling/merged-dem.qml`) originally gave everything below 100 m one
almost white colour, so hills disappeared in flat country such as Glasgow. `scripts/lowland_ramp.py`
rewrites the levels below 200 m as 15 bands (every 10 m to 100 m, then every 20 m) running from a
pale sage green at sea level to the beige of the old 100-200 m band. Levels from 200 m up are
unchanged, so mountains look as before. Change `LOW`, `HIGH` or `BREAKS` in the script and run
`python3 scripts/lowland_ramp.py` to adjust it.

`scripts/render_tiles.py` applies this QML to the topology tiles. `projects/basemap.qgz` still has
the old ramp, so load `styling/merged-dem.qml` onto the `merged-dem` layer in QGIS (or run
`make apply-styles` and save) to see the same colours there.

## Notes

- `HILLSHADE_Z` (vertical exaggeration) was tuned by eye against the live tiles. If
  the shading differs from the site, adjust it and rebuild with `make dem`.
- The DEM covers 54°N to 60°N. Shetland north of 60°N is not included.
