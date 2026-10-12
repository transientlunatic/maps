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
#   data/tiles/roads/<version>/{z}/{x}/{y}.png      roads (a quiet layer)
#   data/tiles/shelters/<version>/{z}/{x}/{y}.png   bothies and shelters
#   data/tiles/paths/<version>/{z}/{x}/{y}.png      footpaths and tracks
#   data/tiles/rivers/<version>/{z}/{x}/{y}.png     rivers, streams and waterfalls
#   data/tiles/facilities/<version>/{z}/{x}/{y}.png car parks, campsites, hostels and so on
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
TILESETS     := topology dbobih trigs transport roads shelters paths rivers facilities

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

.PHONY: all dem tiles sample samples waternames $(TILESETS) clean distclean \
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

# Main roads (not tracks, paths or service roads), to keep the layer quiet.
ROAD_TYPES := 'motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link','unclassified','residential','living_street'

data/roads.gpkg: data/scotland.osm.pbf
	rm -f $@
	ogr2ogr -f GPKG $@ $< lines -nln roads -select name,highway -where "highway IN ($(ROAD_TYPES))"

# Rivers, streams and canals (not underground culverts) and waterfalls, with names.
# Waterfalls are points tagged waterway=waterfall, which sits in other_tags.
data/rivers.gpkg: data/scotland.osm.pbf
	rm -f $@
	ogr2ogr -f GPKG $@ $< -dialect SQLITE -nln rivers -sql "SELECT geometry, name, waterway FROM lines \
		WHERE waterway IN ('river','stream','canal') AND COALESCE(hstore_get_value(other_tags, 'tunnel'), '') <> 'culvert'"
	ogr2ogr -f GPKG -update $@ $< -dialect SQLITE -nln waterfalls -sql "SELECT geometry, name, \
		hstore_get_value(other_tags, 'height') AS height FROM points \
		WHERE hstore_get_value(other_tags, 'waterway') = 'waterfall'"

# Trailheads and facilities: car parks, campsites, hostels, toilets, viewpoints, visitor
# centres, ferry terminals and mountain rescue posts, as points (areas are reduced to a point
# inside them), and ferry routes as lines. Car parks that are multi-storey, underground, on
# the street or private are left out. Uses scripts/osmconf.ini so the tags are real columns.
FACILITY_KIND := CASE \
	WHEN amenity = 'parking' THEN 'parking' \
	WHEN tourism = 'camp_site' THEN 'camp' \
	WHEN tourism = 'hostel' THEN 'hostel' \
	WHEN amenity = 'toilets' THEN 'toilets' \
	WHEN tourism = 'viewpoint' THEN 'viewpoint' \
	WHEN tourism = 'information' THEN 'info' \
	WHEN amenity = 'ferry_terminal' THEN 'ferry' \
	ELSE 'rescue' END
FACILITY_WHERE := (amenity = 'parking' AND COALESCE(parking, '') NOT IN ('multi-storey','underground','street_side','lane','rooftop') \
	AND COALESCE(access, '') NOT IN ('private','customers','no','permit','delivery')) \
	OR amenity IN ('toilets','ferry_terminal') OR tourism IN ('camp_site','hostel','viewpoint') \
	OR (tourism = 'information' AND information = 'visitor_centre') OR emergency = 'mountain_rescue'
OGR_FAC := ogr2ogr -f GPKG --config OSM_CONFIG_FILE scripts/osmconf.ini -dialect SQLITE

data/facilities.gpkg: data/scotland.osm.pbf scripts/osmconf.ini
	rm -f $@
	$(OGR_FAC) $@ $< -nln facilities -sql "SELECT geometry, name, $(FACILITY_KIND) AS kind FROM points WHERE $(FACILITY_WHERE)"
	$(OGR_FAC) -update -append $@ $< -nln facilities -sql "SELECT ST_PointOnSurface(geometry) AS geometry, name, $(FACILITY_KIND) AS kind FROM multipolygons WHERE $(FACILITY_WHERE)"
	$(OGR_FAC) -update $@ $< -nln ferries -sql "SELECT geometry, name FROM lines WHERE hstore_get_value(other_tags, 'route') = 'ferry'"

# Footpaths, tracks and bridleways, for walkers. Pavements and crossings (footway=sidewalk,
# crossing), ways closed to walkers (foot=no) and private ways are left out.
data/paths.gpkg: data/scotland.osm.pbf
	rm -f $@
	ogr2ogr -f GPKG $@ $< -dialect SQLITE -nln paths -sql "SELECT geometry, name, highway, \
		hstore_get_value(other_tags, 'tracktype') AS tracktype, hstore_get_value(other_tags, 'sac_scale') AS sac_scale, \
		hstore_get_value(other_tags, 'trail_visibility') AS trail_visibility FROM lines \
		WHERE highway IN ('path','track','bridleway','footway') \
		AND COALESCE(hstore_get_value(other_tags, 'footway'), '') NOT IN ('sidewalk','crossing','traffic_island') \
		AND COALESCE(hstore_get_value(other_tags, 'foot'), '') <> 'no' \
		AND COALESCE(hstore_get_value(other_tags, 'access'), '') NOT IN ('private','no')"

# Bothies (tourism=wilderness_hut, bothy=yes) and shelters (amenity=shelter, leaving
# out bus shelters and picnic shelters), as points: mapped buildings are reduced to
# a point inside them. Uses scripts/osmconf.ini so the tags are real columns.
SHELTER_KIND := CASE WHEN tourism = 'wilderness_hut' OR bothy = 'yes' THEN 'bothy' ELSE 'shelter' END
SHELTER_WHERE := tourism = 'wilderness_hut' OR bothy = 'yes' OR (amenity = 'shelter' AND \
	(shelter_type IN ('basic_hut','lean_to','weather_shelter','rock_shelter') OR \
	(shelter_type IS NULL AND public_transport IS NULL AND bus IS NULL)))
OGR_OSM := ogr2ogr -f GPKG --config OSM_CONFIG_FILE scripts/osmconf.ini -dialect SQLITE -nln shelters

data/shelters.gpkg: data/scotland.osm.pbf scripts/osmconf.ini
	rm -f $@
	$(OGR_OSM) $@ $< -sql "SELECT geometry, name, $(SHELTER_KIND) AS kind, shelter_type FROM points WHERE $(SHELTER_WHERE)"
	$(OGR_OSM) -update -append $@ $< -sql "SELECT ST_PointOnSurface(geometry) AS geometry, name, $(SHELTER_KIND) AS kind, shelter_type FROM multipolygons WHERE $(SHELTER_WHERE)"

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

roads: data/roads.gpkg
	$(RENDER) --tileset roads --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

shelters: data/shelters.gpkg
	$(RENDER) --tileset shelters --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

paths: data/paths.gpkg
	$(RENDER) --tileset paths --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

rivers: data/rivers.gpkg
	$(RENDER) --tileset rivers --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

facilities: data/facilities.gpkg
	$(RENDER) --tileset facilities --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

tiles: $(TILESETS) waternames

sample: $(DATA_FILES) $(WATERNAMES_JSON) data/transport.gpkg data/roads.gpkg data/shelters.gpkg data/paths.gpkg data/rivers.gpkg data/facilities.gpkg
	for t in $(TILESETS); do \
		$(RENDER) --tileset $$t --extent=$(SAMPLE_BBOX) --zmin $(SAMPLE_ZMIN) --zmax $(SAMPLE_ZMAX) || exit 1; \
	done

# Sample images for the README (docs/samples), from the data in data/
samples:
	QT_QPA_PLATFORM=offscreen $(QGIS_PYTHON) scripts/make_samples.py

# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------

clean:
	rm -rf data/tiles data/merged-dem.tif data/hill-shade-merged.tif \
		data/contours-merged.gpkg data/merged.vrt data/water-polygons.gpkg \
		data/water-names.gpkg data/transport.gpkg data/roads.gpkg data/shelters.gpkg data/paths.gpkg data/rivers.gpkg data/facilities.gpkg

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
