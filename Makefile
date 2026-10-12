# Makefile for the Scotland basemap tiles served at tiles.daniel-williams.co.uk
#
# The tiles are rendered by QGIS (headless) from projects/basemap.qgz, so the
# cartography lives in the QGIS project and styling/*.qml. This Makefile
# prepares the data files that the project expects in data/ and then calls
# scripts/render_tiles.py to produce one XYZ PNG tile tree per tile set:
#
#   data/tiles/topology/<version>/{z}/{x}/{y}.png   terrain, contours, water, forest
#   data/tiles/dbobih/<version>/{z}/{x}/{y}.png     hill markers and names
#   data/tiles/trigs/<version>/{z}/{x}/{y}.png      trig points
#   data/tiles/transport/<version>/{z}/{x}/{y}.png  railways and stations
#   data/tiles/waternames/<version>/water-names.geojson
#                                            names of lochs, as lines to label (vector)
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

# Version directory in the tile URLs; releases set this to the release tag
TILE_VERSION ?= dev
TILE_DIR     ?= data/tiles
# Raster tile sets rendered by QGIS; the water names are vector data (below)
TILESETS     := topology dbobih trigs transport

PROJECT ?= projects/basemap.qgz

# OpenStreetMap extract used for the names of lochs and for railways and stations.
OSM_PBF_URL ?= https://download.geofabrik.de/europe/united-kingdom/scotland-latest.osm.pbf

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

.PHONY: all dem tiles sample waternames $(TILESETS) clean distclean \
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

# ---------------------------------------------------------------------------
# Water names
# ---------------------------------------------------------------------------

data/scotland.osm.pbf:
	mkdir -p $(dir $@)
	curl -sSfL -o $@.part $(OSM_PBF_URL)
	mv $@.part $@

# Named water polygons (lochs, reservoirs, wide rivers) from OSM.
data/water-polygons.gpkg: data/scotland.osm.pbf
	rm -f $@
	ogr2ogr -f GPKG $@ $< multipolygons -nln multipolygons -select name \
		-where "name IS NOT NULL AND (\"natural\" = 'water' OR landuse = 'reservoir')"

# Railways and railway stations from the same extract. Station and track details
# (railway=*, service=*, tunnel=* ...) are in the other_tags column.
RAIL_TYPES := 'rail','light_rail','narrow_gauge','tram','subway','preserved','funicular'

data/transport.gpkg: data/scotland.osm.pbf
	rm -f $@
	ogr2ogr -f GPKG $@ $< -dialect SQLITE -nln rail_lines -sql "SELECT geometry, name, railway, \
		hstore_get_value(other_tags, 'service') AS service, hstore_get_value(other_tags, 'usage') AS usage, \
		hstore_get_value(other_tags, 'tunnel') AS tunnel FROM lines WHERE railway IN ($(RAIL_TYPES))"
	ogr2ogr -f GPKG -update -append $@ $< -dialect SQLITE -nln rail_stations -sql "SELECT geometry, name, \
		hstore_get_value(other_tags, 'railway') AS railway, hstore_get_value(other_tags, 'station') AS station \
		FROM points WHERE hstore_get_value(other_tags, 'railway') IN ('station','halt')"

# One label line per water body, along its main axis.
data/water-names.gpkg: data/water-polygons.gpkg scripts/water_centerlines.py
	$(QGIS_PYTHON) scripts/water_centerlines.py $< $@

# Label lines as GeoJSON for the browser, which draws the names (see
# preview/water-names.js). Simplified to about 5 m and rounded to 5 decimals.
WATERNAMES_JSON := $(TILE_DIR)/waternames/$(TILE_VERSION)/water-names.geojson

$(WATERNAMES_JSON): data/water-names.gpkg
	mkdir -p $(dir $@)
	rm -f $@
	ogr2ogr -f GeoJSON $@ $< water_names -select name,length_m -simplify 0.00005 \
		-lco COORDINATE_PRECISION=5 -lco RFC7946=YES

waternames: $(WATERNAMES_JSON)

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

transport: data/transport.gpkg
	$(RENDER) --tileset transport --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

tiles: $(TILESETS) waternames

sample: $(DATA_FILES) $(WATERNAMES_JSON) data/transport.gpkg
	for t in $(TILESETS); do \
		$(RENDER) --tileset $$t --extent=$(SAMPLE_BBOX) --zmin $(SAMPLE_ZMIN) --zmax $(SAMPLE_ZMAX) || exit 1; \
	done

# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------

clean:
	rm -rf data/tiles data/merged-dem.tif data/hill-shade-merged.tif \
		data/contours-merged.gpkg data/merged.vrt data/water-polygons.gpkg \
		data/water-names.gpkg data/transport.gpkg

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
