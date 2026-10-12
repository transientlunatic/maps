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

## Data sources

- **Elevation**: [ViewfinderPanoramas](http://viewfinderpanoramas.org/dem3.html) DEM
  (SRTM-derived), downloaded as 4° × 6° block zips (`N29 N30 O29 O30` cover Scotland).
- **Water and forest**: OpenStreetMap, read by QGIS from the ArcGIS OSM vector tile
  service referenced in the project, so rendering needs internet access.
- **Hills**: `sources/dobih.csv`, the [Database of British and Irish Hills](https://www.hills-database.co.uk).
- **Trig points**: `sources/trigs.csv`.

## Prerequisites

- GNU Make, `curl`, `unzip`
- Fonts: Lato (hill and trig names) and Inter (heights and other labels), e.g.
  `fonts-lato fonts-inter` on Ubuntu
- GDAL command-line tools (`gdalbuildvrt`, `gdal_translate`, `gdaldem`, `gdal_contour`)
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

## Notes

- `HILLSHADE_Z` (vertical exaggeration) was tuned by eye against the live tiles. If
  the shading differs from the site, adjust it and rebuild with `make dem`.
- The DEM covers 54°N to 60°N. Shetland north of 60°N is not included.
