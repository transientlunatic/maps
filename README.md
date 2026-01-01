# Basemap project

This repository builds a basemap from SRTM-style HGT tiles, generates contours and hillshade, and tiles the raster for use with Leaflet.

# Basemap project

This repository builds a basemap from SRTM-style HGT tiles, generates contours and hillshade, and tiles the raster for use with Leaflet.

## Data source
- Elevation tiles are fetched from ViewfinderPanoramas: http://viewfinderpanoramas.org/dem3
  - Tiles are downloaded as `.zip` archives (e.g. `N49E000.zip`) and contain `.hgt` files.
  - Credit: ViewfinderPanoramas (SRTM-derived DEMs).

## Prerequisites
- GNU Make
- GDAL command-line tools: `gdal_merge.py`, `gdaldem`, `gdal_contour`, `gdal2tiles.py`
- `wget` or `curl` and `unzip`

## Usage
- Edit `mergeInputFiles.txt` to list the tile names you want to include (the Makefile accepts either absolute `/tmp/N49E000.hgt`-style lines or basenames like `N49E000.hgt`).
- Default download base is ViewfinderPanoramas; to download tiles and unzip them into `data/hgt` run:

```
make hgt
```

- To override the download base (if you mirror tiles elsewhere):

```
make HGT_BASE_URL=https://my-mirror.example.org/dem3 hgt
```

- To build the merged DEM and derived products:

```
make        # builds data/merged-dem.tif
make data/tiles  # generates tiled output in data/tiles
```

## Area options
- By default the Makefile builds the `uk` area. You can also build a much smaller sample area for quick testing.

- Build the default UK basemap (uses `mergeInputFiles.txt`):

```
make uk
```

- Build the small sample basemap (uses `mergeInputFiles-sample.txt`):

```
make sample
```

- To download the HGT tiles for the currently-selected `AREA` run:

```
make hgt
```

## Notes
- The Makefile will download zip archives from the base URL and unzip the contained `.hgt` file into `data/hgt`.
- If tiles are already present in `data/hgt`, `make` will use them and not re-download.
