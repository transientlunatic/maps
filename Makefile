# Makefile for the Scotland basemap tiles served at tiles.daniel-williams.co.uk
#
# The tiles are rendered by QGIS (headless) from projects/basemap.qgz, so the
# cartography lives in the QGIS project and styling/*.qml. This Makefile
# prepares the data files that the project expects in data/ and then calls
# scripts/render_tiles.py to produce one XYZ PNG tile tree per tile set:
#
#   data/tiles/topology/<version>/{z}/{x}/{y}.png   terrain, contours and water
#   data/tiles/forests/<version>/{z}/{x}/{y}.png    forest (use mix-blend-mode: multiply)
#   data/tiles/mist/<version>/{z}/{x}/{y}.png       valley mist (a pale haze, zoomed out)
#   data/tiles/elevmist/<version>/{z}/{x}/{y}.png   mist that rises to 914 m (overlay)
#   data/tiles/imhof/<version>/{z}/{x}/{y}.png      a second basemap style, instead of the topology
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
# Raster tile sets rendered by QGIS; the water names are vector data (below).
# The light ones render in a few minutes per shard, so GitHub Actions builds them on a release.
# The heavy ones (the full-colour terrain, the ESRI forest tiles and the big line layers) take
# hours per shard, more than an Actions job is allowed, so build them with HTCondor
# (scripts/make_dag.py) and publish the result with scripts/publish_tiles.sh.
TILESETS_LIGHT := mist elevmist dbobih trigs transport shelters facilities crags geology
TILESETS_HEAVY := topology imhof forests roads paths rivers
TILESETS       := $(TILESETS_LIGHT) $(TILESETS_HEAVY)

PROJECT ?= projects/basemap.qgz

# OpenStreetMap extract used for the names of lochs and for railways and stations.
OSM_PBF_URL ?= https://download.geofabrik.de/europe/united-kingdom/scotland-latest.osm.pbf

# Python interpreter that can `import qgis` (on Debian/Ubuntu this is the
# system python, not a venv).
QGIS_PYTHON ?= python3
CONTOUR_INTERVAL ?= 50

# The vertical exaggeration (Z) of the hillshades is tuned by eye to match the live tiles.
HILLSHADE_Z     ?= 4

RENDER = QT_QPA_PLATFORM=offscreen $(QGIS_PYTHON) scripts/render_tiles.py \
	--project $(PROJECT) --out $(TILE_DIR) --version $(TILE_VERSION)

# A recipe that fails must not leave a half-made or empty file behind, which make would then take as up to date
.DELETE_ON_ERROR:

.PHONY: all dem data-light data-all tiles sample samples waternames hills $(TILESETS) clean distclean \
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

# Hillshades are computed on a metric copy of the DEM (British National Grid). Done on the lat/lon
# DEM, an east-west metre is longer than a north-south one at Scottish latitudes (cos 56 deg = 0.56),
# which tilts the apparent direction of the light. The results are warped back onto the DEM grid,
# so the files keep the names and geometry that the QGIS project expects.
data/dem-bng.tif: data/merged-dem.tif
	gdalwarp -q -t_srs EPSG:27700 -tr 60 60 -r cubic -dstnodata -32768 -co COMPRESS=LZW -co TILED=YES $< $@

data/hill-shade-bng.tif: data/dem-bng.tif
	gdaldem hillshade $< $@ -of GTiff -co COMPRESS=LZW -co TILED=YES \
		-compute_edges -s 1 -z $(HILLSHADE_Z) -az 315 -alt 45

data/hill-shade-multi-bng.tif: data/dem-bng.tif
	gdaldem hillshade $< $@ -of GTiff -co COMPRESS=LZW -co TILED=YES \
		-compute_edges -s 1 -z $(HILLSHADE_Z) -multidirectional

# Warp a metric hillshade onto the DEM's grid (a blank copy of the DEM grid, then warped into)
data/hill-shade-merged.tif: data/hill-shade-bng.tif data/merged-dem.tif
	gdal_translate -q -ot Byte -scale 0 1 0 0 -a_nodata none -co COMPRESS=LZW -co TILED=YES data/merged-dem.tif $@
	gdalwarp -q -r cubic $< $@

data/hill-shade-multi.tif: data/hill-shade-multi-bng.tif data/merged-dem.tif
	gdal_translate -q -ot Byte -scale 0 1 0 0 -a_nodata none -co COMPRESS=LZW -co TILED=YES data/merged-dem.tif $@
	gdalwarp -q -r cubic $< $@

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

# Crags: cliffs (natural=cliff, a line with the drop on its right), scree and bare rock
# (natural=scree, bare_rock, rock) as polygons. Uses scripts/osmconf.ini for the `natural` column.
OGR_CRAGS := ogr2ogr -f GPKG --config OSM_CONFIG_FILE scripts/osmconf.ini -dialect SQLITE

data/crags.gpkg: data/scotland.osm.pbf scripts/osmconf.ini
	rm -f $@
	$(OGR_CRAGS) $@ $< -nln cliffs -sql "SELECT geometry, name FROM lines WHERE hstore_get_value(other_tags, 'natural') = 'cliff'"
	$(OGR_CRAGS) -update $@ $< -nln rock -nlt MULTIPOLYGON -sql "SELECT geometry, name, \
		CASE WHEN \"natural\" = 'scree' THEN 'scree' ELSE 'bare_rock' END AS kind FROM multipolygons \
		WHERE \"natural\" IN ('scree','bare_rock','rock')"

# BGS 1:50k bedrock geology for the tile area, from the BGS web map service (see
# scripts/fetch_geology.py). It changes rarely, so it is not rebuilt unless it is missing.
data/geology.tif:
	$(QGIS_PYTHON) scripts/fetch_geology.py --bbox=$(TILE_BBOX) $@

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

# The hills as JSON for the browser, which draws them (see preview/hills.js and scripts/make_hills.py)
HILLS_JSON := $(TILE_DIR)/hills/$(TILE_VERSION)/hills.json

$(HILLS_JSON): sources/dobih.csv scripts/make_hills.py
	python3 scripts/make_hills.py --bbox=$(TILE_BBOX) $< $@

hills: $(HILLS_JSON)

# The shading value for the Imhof basemap style (see scripts/make_imhof.py), and a threefold
# enlarged copy of it, which QGIS draws smoothly where it would show the cells of the original
data/imhof-shade.tif: data/hill-shade-merged.tif data/hill-shade-multi.tif scripts/make_imhof.py
	$(QGIS_PYTHON) scripts/make_imhof.py data/hill-shade-merged.tif data/hill-shade-multi.tif $@

data/imhof-shade-3x.tif: data/imhof-shade.tif
	gdal_translate -q -outsize 300% 300% -r cubic -co COMPRESS=LZW -co PREDICTOR=2 -co TILED=YES -co BIGTIFF=IF_SAFER $< $@

# Sea polygons with a detailed coastline, from the DEM (see scripts/make_sea.py)
data/sea.gpkg: data/merged-dem.tif scripts/make_sea.py
	$(QGIS_PYTHON) scripts/make_sea.py $< $@

# Valley mist density, from the DEM (see scripts/make_mist.py)
data/mist.tif: data/merged-dem.tif scripts/make_mist.py
	$(QGIS_PYTHON) scripts/make_mist.py $< $@

dem: data/merged-dem.tif data/hill-shade-merged.tif data/hill-shade-multi.tif data/contours-merged.gpkg data/mist.tif data/sea.gpkg data/imhof-shade-3x.tif

# The data the light tile sets need, and all of it. `data-light` is what a release build on
# GitHub Actions makes; the sample build and the heavy tile sets need `data-all`.
DATA_LIGHT := data/merged-dem.tif data/mist.tif data/transport.gpkg data/shelters.gpkg \
	data/facilities.gpkg data/crags.gpkg data/geology.tif
DATA_ALL   := $(DATA_LIGHT) data/hill-shade-merged.tif data/hill-shade-multi.tif data/contours-merged.gpkg \
	data/sea.gpkg data/imhof-shade-3x.tif data/roads.gpkg data/paths.gpkg data/rivers.gpkg

data-light: $(DATA_LIGHT)
data-all: $(DATA_ALL)

# ---------------------------------------------------------------------------
# Tiles (rendered by QGIS)
# ---------------------------------------------------------------------------

DATA_FILES := data/merged-dem.tif data/hill-shade-merged.tif data/contours-merged.gpkg data/sea.gpkg data/imhof-shade-3x.tif

topology: $(DATA_FILES)
	$(RENDER) --tileset topology --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

imhof: data/imhof-shade-3x.tif data/sea.gpkg
	$(RENDER) --tileset imhof --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

elevmist: data/merged-dem.tif
	$(RENDER) --tileset elevmist --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

mist: data/mist.tif
	$(RENDER) --tileset mist --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

forests:
	$(RENDER) --tileset forests --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

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

crags: data/crags.gpkg
	$(RENDER) --tileset crags --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

geology: data/geology.tif
	$(RENDER) --tileset geology --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

paths: data/paths.gpkg
	$(RENDER) --tileset paths --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

rivers: data/rivers.gpkg
	$(RENDER) --tileset rivers --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

facilities: data/facilities.gpkg
	$(RENDER) --tileset facilities --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

tiles: $(TILESETS) waternames

sample: $(DATA_FILES) $(WATERNAMES_JSON) data/transport.gpkg data/roads.gpkg data/shelters.gpkg data/paths.gpkg data/rivers.gpkg data/facilities.gpkg data/crags.gpkg data/mist.tif data/geology.tif
	for t in $(TILESETS); do \
		$(RENDER) --tileset $$t --extent=$(SAMPLE_BBOX) --zmin $(SAMPLE_ZMIN) --zmax $(SAMPLE_ZMAX) || exit 1; \
	done

# Render one tile set without (re)building its data, for sharded builds: the data files are
# made once, then each job renders a slice of the area, e.g.
#   make render-roads TILE_BBOX=-9.1,55.7,-4.2,57.3
render-%:
	$(RENDER) --tileset $* --extent=$(TILE_BBOX) --zmin $(TILE_ZMIN) --zmax $(TILE_ZMAX)

# Print a Makefile variable, e.g. `make -s print-TILE_BBOX` (used by the workflow)
print-%:
	@echo $($*)

# Sample images for the README (docs/samples), from the data in data/
samples:
	QT_QPA_PLATFORM=offscreen $(QGIS_PYTHON) scripts/make_samples.py

# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------

clean:
	rm -rf data/tiles data/merged-dem.tif data/hill-shade-merged.tif data/hill-shade-multi.tif \
		data/dem-bng.tif data/hill-shade-bng.tif data/hill-shade-multi-bng.tif \
		data/imhof-shade.tif data/imhof-shade-3x.tif \
		data/contours-merged.gpkg data/merged.vrt data/mist.tif data/sea.gpkg data/water-polygons.gpkg \
		data/water-names.gpkg data/transport.gpkg data/roads.gpkg data/shelters.gpkg data/paths.gpkg data/rivers.gpkg data/facilities.gpkg data/crags.gpkg

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
