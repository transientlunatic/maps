# Basemap project

This repository builds map tiles for Scotland showing:
1. **Basemap**: Elevation-based hillshade with forest and water overlays from OpenStreetMap
2. **Trig Points**: Triangulation points from the Ordnance Survey
3. **Hills**: Markers for hills from the Database of British and Irish Hills (DoBIH)

The tiles are suitable for use with Leaflet and other web mapping libraries.

## Data sources
- **Elevation**: ViewfinderPanoramas SRTM-derived DEMs: http://viewfinderpanoramas.org/dem3
  - Tiles are downloaded as `.zip` archives (e.g. `N49E000.zip`) and contain `.hgt` files.
  - Credit: ViewfinderPanoramas (SRTM-derived DEMs).
- **Trig Points**: `sources/trigs.csv` - UK triangulation point database
- **Hills**: `sources/dobih.csv` - Database of British and Irish Hills
- **Forest/Water overlays**: OpenStreetMap data (via Overpass API)

## Prerequisites
- GNU Make
- Python 3.x
- GDAL command-line tools: `gdal_merge.py`, `gdaldem`, `gdal_contour`, `gdal2tiles.py`, `gdal_calc.py`, `gdal_rasterize`
- `wget` or `curl` and `unzip`
- `jq` (for JSON processing)
- Optional: `tippecanoe` for generating vector tiles (https://github.com/felt/tippecanoe)

## Quick Start

### Build all tile sets (sample area for testing)

```bash
make sample         # Build sample basemap tiles
make geojson        # Generate GeoJSON from CSV files
make point-tiles    # Generate point tiles (requires tippecanoe)
```

### Build specific tile sets

```bash
# Generate GeoJSON files from CSV data
make geojson

# Generate basemap tiles (UK)
make uk
make data/tiles

# Generate point data tiles
make point-tiles
```

## Usage

### Basemap tiles

Edit `mergeInputFiles.txt` to list the HGT tile names you want to include (the Makefile accepts either absolute `/tmp/N49E000.hgt`-style lines or basenames like `N49E000.hgt`).

Download elevation tiles:
```bash
make hgt
```

To override the download base (if you mirror tiles elsewhere):
```bash
make HGT_BASE_URL=https://my-mirror.example.org/dem3 hgt
```

Build the merged DEM and derived products:
```bash
make                # builds data/merged-dem.tif
make data/tiles     # generates tiled output in data/tiles
```

### Point data tiles

The repository includes two point datasets that are automatically converted to GeoJSON:

1. **Trig Points** (`sources/trigs.csv` → `data/points/trig-points.geojson`)
2. **Hills** (`sources/dobih.csv` → `data/points/hills.geojson`)

Generate GeoJSON files:
```bash
make geojson
```

If you have `tippecanoe` installed, generate vector tiles:
```bash
make point-tiles
```

This creates:
- `data/tiles/trig-points.mbtiles`
- `data/tiles/hills.mbtiles`

Without tippecanoe, the GeoJSON files can be used directly with Leaflet or other web mapping libraries.

## Area options

By default the Makefile builds the `uk` area. You can also build a much smaller sample area for quick testing.

Build the default UK basemap (uses `mergeInputFiles.txt`):
```bash
make uk
```

Build the small sample basemap (uses `mergeInputFiles-sample.txt`):
```bash
make sample
```

To download the HGT tiles for the currently-selected `AREA`:
```bash
make hgt
```

## GitHub Actions

The repository includes a GitHub Actions workflow that automatically builds tiles:

- **On push**: Builds a small sample tile set for testing
- **On release**: Builds the full Scotland tile set and attaches it to the release
- **Manual trigger**: Can be triggered manually via workflow_dispatch to build either sample or full tiles

The workflow generates all three tile sets (basemap, trig points, and hills) and uploads them as artifacts.

## Output structure

```
data/
├── tiles/
│   ├── sample/          # Sample basemap tiles (single zoom level)
│   ├── full/            # Full UK basemap tiles (zoom 0-13)
│   ├── trig-points.mbtiles   # Trig points vector tiles
│   └── hills.mbtiles          # Hills vector tiles
├── points/
│   ├── trig-points.geojson    # Trig points GeoJSON
│   └── hills.geojson          # Hills GeoJSON
└── [intermediate files]
```

## Notes
- The Makefile will download zip archives from the base URL and unzip the contained `.hgt` file into `data/hgt`.
- If tiles are already present in `data/hgt`, `make` will use them and not re-download.
- Point data GeoJSON files are large (18MB for trig points, 59MB for hills). Consider using vector tiles (MBTiles) for better performance.
- The basemap overlay blending uses colors extracted from QGIS QML style files in `styling/`.
