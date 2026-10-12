# Makefile for the Scotland basemap tiles served at tiles.daniel-williams.co.uk
#
# The tiles are rendered by QGIS (headless) from projects/basemap.qgz, so the
# cartography lives in the QGIS project and styling/*.qml. This Makefile
# prepares the data files that the project expects in data/ and then calls
# scripts/render_tiles.py to produce one XYZ PNG tile tree per tile set:
#
#   data/tiles/topology/v0/{z}/{x}/{y}.png   terrain, contours, water, forest
#   data/tiles/dbobih/v0/{z}/{x}/{y}.png     hill markers and names
#   data/tiles/trigs/v0/{z}/{x}/{y}.png      trig points
#
# Quick start:   make sample     (one small area, a few zoom levels)
#                make tiles      (all of Scotland, zooms 9-13; slow)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# ViewfinderPanoramas distributes DEMs as zips of 4 deg x 6 deg blocks (named
# by UTM-style block, e.g. O30 = 56-60N, 6W-0), each containing the .hgt tiles
# that have land in them. N/O 29/30 cover Scotland.
HGT_BASE_URL ?= https://viewfinderpanoramas.org/dem3
DEM_BLOCKS   ?= N29 N30 O29 O30

# Extent for the merged DEM and contours: west south east north (degrees)
DEM_BBOX ?= -9 54 -0.5 60

# Tile extent as west,south,east,north (degrees) and zoom range
TILE_BBOX  ?= -9,54.5,-0.5,60
TILE_ZMIN  ?= 9
TILE_ZMAX  ?= 13

# Small test area (Ben Ledi / the Trossachs) and its zoom range
SAMPLE_BBOX ?= -4.5,56.2,-4.2,56.35
SAMPLE_ZMIN ?= 9
SAMPLE_ZMAX ?= 12

TILE_VERSION ?= v0
TILE_DIR     ?= data/tiles
TILESETS     := topology dbobih trigs

PROJECT ?= projects/basemap.qgz

# Python interpreter that can `import qgis` (on Debian/Ubuntu this is the
# system python, not a venv).
QGIS_PYTHON ?= python3
CONTOUR_INTERVAL ?= 50

# gdaldem needs the horizontal scale in metres per degree for lat/lon DEMs.
# The vertical exaggeration (Z) is tuned by eye to match the live tiles.
HILLSHADE_SCALE ?= 111120
HILLSHADE_Z     ?= 4

RENDER = QT_QPA_PLATFORM=offscreen $(QGIS_PYTHON) scripts/render_tiles.py \
	--project $(PROJECT) --out $(TILE_DIR) --version $(TILE_VERSION)

.PHONY: all dem tiles sample $(TILESETS) clean distclean \
	apply-styles export-styles export-styles-force

all: tiles

# ---------------------------------------------------------------------------
# Elevation data
# ---------------------------------------------------------------------------

data/dem-blocks/%.zip:
	mkdir -p $(dir $@)
	curl -sSfL -o $@.part $(HGT_BASE_URL)/$*.zip
	mv $@.part $@

# Unzip every block flat into data/hgt (the zips contain a block directory).
data/hgt/.stamp: $(patsubst %,data/dem-blocks/%.zip,$(DEM_BLOCKS))
	mkdir -p data/hgt
	for z in $^; do unzip -joq $$z '*.hgt' -d data/hgt; done
	touch $@

data/merged.vrt: data/hgt/.stamp
	gdalbuildvrt $@ data/hgt/*.hgt

# The project expects these exact file names (see projects/basemap.qgz).
data/merged-dem.tif: data/merged.vrt
	gdal_translate -ot Float32 -of GTiff -co COMPRESS=LZW -co TILED=YES \
		-projwin $(word 1,$(DEM_BBOX)) $(word 4,$(DEM_BBOX)) $(word 3,$(DEM_BBOX)) $(word 2,$(DEM_BBOX)) \
		$< $@

data/hill-shade-merged.tif: data/merged-dem.tif
	gdaldem hillshade $< $@ -of GTiff -co COMPRESS=LZW -co TILED=YES \
		-compute_edges -s $(HILLSHADE_SCALE) -z $(HILLSHADE_Z) -az 315 -alt 45

data/contours-merged.gpkg: data/merged-dem.tif
	rm -f $@
	gdal_contour -b 1 -a ELEV -i $(CONTOUR_INTERVAL) -f GPKG -nln contours $< $@

dem: data/merged-dem.tif data/hill-shade-merged.tif data/contours-merged.gpkg

# ---------------------------------------------------------------------------
# Tiles (rendered by QGIS)
# ---------------------------------------------------------------------------

DATA_FILES := data/merged-dem.tif data/hill-shade-merged.tif data/contours-merged.gpkg

topology: $(DATA_FILES)
	$(RENDER) --tileset topology --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

dbobih: sources/dobih.csv
	$(RENDER) --tileset dbobih --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

trigs: sources/trigs.csv
	$(RENDER) --tileset trigs --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

tiles: $(TILESETS)

sample: $(DATA_FILES)
	for t in $(TILESETS); do \
		$(RENDER) --tileset $$t --extent=$(SAMPLE_BBOX) --zmin $(SAMPLE_ZMIN) --zmax $(SAMPLE_ZMAX) || exit 1; \
	done

# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------

clean:
	rm -rf data/tiles data/merged-dem.tif data/hill-shade-merged.tif \
		data/contours-merged.gpkg data/merged.vrt

# Also removes the downloaded DEM zips and unpacked HGT files.
distclean: clean
	rm -rf data

# Apply or export QGIS layer styles stored in `styling/`.
apply-styles:
	python3 scripts/apply_styles.py $(PROJECT) styling

# Use `make export-styles-force` to overwrite existing files.
export-styles:
	python3 scripts/export_styles.py $(PROJECT) styling

export-styles-force:
	python3 scripts/export_styles.py --force $(PROJECT) styling
