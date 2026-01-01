
# This is the makefile for the basemap

# Where to read the list of HGT tiles (one path per line). The file can
# contain absolute paths (e.g. /tmp/N49E000.hgt) or basenames. It will be
# mapped into $(HGT_DIR).

# Area selection: `AREA` can be `uk` (default) or `sample` (smaller test set)
AREA ?= uk

# HGT lists for different areas
HGT_LIST_UK := mergeInputFiles.txt
HGT_LIST_SAMPLE := mergeInputFiles-sample.txt

HGT_LIST = $(if $(filter sample,$(AREA)),$(HGT_LIST_SAMPLE),$(HGT_LIST_UK))

HGT_DIR := data/hgt
# Default to ViewfinderPanoramas distribution of tiles
HGT_BASE_URL ?= https://viewfinderpanoramas.org/dem3

# Extract basenames from the HGT list (works with absolute paths or basenames)
HGT_NAMES = $(shell sed '/^\s*$$/d' $(HGT_LIST) | sed 's@^.*/@@')
HGT_FILES = $(patsubst %, $(HGT_DIR)/%, $(HGT_NAMES))

.PHONY: all hgt uk sample tiles clean distclean apply-styles export-styles export-styles-force geojson point-tiles

PROJECT ?= projects/basemap.qgz

# Tile generation defaults
TILE_ZOOMS ?= 0-13
TILE_OUTPUT_DIR ?= data/tiles/full
SAMPLE_TILE_DIR ?= data/tiles/sample
GDAL2TILES_PROCS ?= 4

# QML style files for overlays
FOREST_QML ?= styling/OSM - Forestry.qml
WATER_QML ?= styling/OSM - Water.qml

# Overlay geojsons (fetch with scripts/fetch_overpass_geojson.py)
FOREST_GEOJSON ?= data/overlays/forest.geojson
WATER_GEOJSON ?= data/overlays/water.geojson

# Point data sources and outputs
TRIG_POINTS_CSV ?= sources/trigs.csv
HILLS_CSV ?= sources/dobih.csv
TRIG_POINTS_GEOJSON ?= data/points/trig-points.geojson
HILLS_GEOJSON ?= data/points/hills.geojson

# QML style files for point layers
TRIG_POINTS_QML ?= styling/Trig Points.qml
HILLS_QML ?= styling/Database of British and Irish Hills.qml

all: data/merged-dem.tif

# Convenience targets to select area and build
uk: AREA = uk
uk: all

# Build a small sample project: only produce a single zoom level to keep
# the sample quick to generate. The zoom used can be overridden with
# `make sample SAMPLE_ZOOM=12`.
SAMPLE_ZOOM ?= 13

sample: AREA = sample
sample: data/tiles/sample

# Download rule: make hgt downloads all listed HGT files into $(HGT_DIR)
hgt: $(HGT_FILES)

$(HGT_DIR)/%.hgt:
	mkdir -p $(HGT_DIR)
	@echo Downloading $(@F) to $@
	# ViewfinderPanoramas provides tiles as ZIP files named like N49E000.zip
	# Download the zip, unzip the .hgt into $(HGT_DIR), then remove the zip.
	base=$$(basename $@)
	base=$${base%.hgt}
	zipfile=$(HGT_DIR)/$${base}.zip
	zipurl=$(HGT_BASE_URL)/$${base}.zip
	@if command -v wget >/dev/null 2>&1; then \
		wget -q -c -O "$${zipfile}" "$${zipurl}"; \
	else \
		curl -sSf -o "$${zipfile}" "$${zipurl}"; \
	fi
	unzip -o -d $(HGT_DIR) "$${zipfile}"
	rm -f "$${zipfile}"

# Build merged DEM from the downloaded HGT files
data/merged-dem.tif: $(HGT_FILES)
	mkdir -p $(dir $@)
	gdal_merge.py \
		-ot Float32 \
		-of GTiff \
		-o $@ \
		$^

data/hill-shade-merged.tif: data/merged-dem.tif
	gdaldem hillshade \
		$< \
		$@ \
		-of GTiff \
		-b 1 -z 1.0 -s 1.0 \
		-alt 45.0 \
		-multidirectional

data/contour-merged.gpkg: data/merged-dem.tif
	gdal_contour \
		-b 1 \
		-a ELEV \
		-i 50.0 \
		-f "GPKG" \
		$< $@



# VRT workflow: build a virtual mosaic and a projected VRT for tiling
data/merged.vrt: $(HGT_FILES)
	mkdir -p $(dir $@)
	# Build a virtual mosaic referencing individual HGT files
	gdalbuildvrt $@ $^

data/merged-3857.vrt: data/merged.vrt
	# Reproject into Web Mercator as a VRT (no large disk raster created)
	gdalwarp -of VRT -t_srs EPSG:3857 -r bilinear $< $@

# Build a shaded RGB basemap from the merged DEM (full-resolution)
data/shaded-basemap.tif: data/merged-dem.tif data/hill-shade-merged.tif data/hillmap-colors.txt
	mkdir -p $(dir $@) data/tmp
	gdaldem color-relief $< data/hillmap-colors.txt data/tmp/merged-dem-colored.tif -of GTiff -co COMPRESS=LZW
	gdal_translate -b 1 data/tmp/merged-dem-colored.tif data/tmp/color_b1.tif
	gdal_translate -b 2 data/tmp/merged-dem-colored.tif data/tmp/color_b2.tif
	gdal_translate -b 3 data/tmp/merged-dem-colored.tif data/tmp/color_b3.tif
	gdal_calc.py -A data/tmp/color_b1.tif -B data/hill-shade-merged.tif --outfile=data/tmp/shaded_b1.tif --calc='(A*0.7 + B*0.3)' --type=Byte --overwrite
	gdal_calc.py -A data/tmp/color_b2.tif -B data/hill-shade-merged.tif --outfile=data/tmp/shaded_b2.tif --calc='(A*0.7 + B*0.3)' --type=Byte --overwrite
	gdal_calc.py -A data/tmp/color_b3.tif -B data/hill-shade-merged.tif --outfile=data/tmp/shaded_b3.tif --calc='(A*0.7 + B*0.3)' --type=Byte --overwrite
	gdal_merge.py -separate -o data/tmp/shaded_rgb.tif data/tmp/shaded_b1.tif data/tmp/shaded_b2.tif data/tmp/shaded_b3.tif
	gdal_translate -co COMPRESS=LZW data/tmp/shaded_rgb.tif $@

# Reproject the shaded basemap to Web Mercator for tiling
data/shaded-basemap-3857.tif: data/shaded-basemap.tif
	gdalwarp -of GTiff -t_srs EPSG:3857 -r bilinear -co COMPRESS=LZW -co TILED=YES $< $@

# Convenience target to generate tiles from the shaded basemap without overlays
basemap-tiles-no-overlays: data/shaded-basemap-3857.tif
	mkdir -p $(TILE_OUTPUT_DIR)
	gdal2tiles.py \
		-p mercator \
		-z $(TILE_ZOOMS) \
		-w all \
		--processes=$(GDAL2TILES_PROCS) \
		--xyz \
		-r average \
		-a 0.0 \
		$< $(TILE_OUTPUT_DIR)


# Rasterize overlay GeoJSONs to masks aligned with the shaded basemap
data/overlays/forest_mask.tif: $(FOREST_GEOJSON) data/shaded-basemap.tif
	@echo "Rasterizing forest overlay to $@ aligned with shaded basemap"
	@info=$$(gdalinfo -json data/shaded-basemap.tif); \
	 xmin=$$(echo "$$info" | jq -r '.cornerCoordinates.upperLeft[0]'); \
	 ymax=$$(echo "$$info" | jq -r '.cornerCoordinates.upperLeft[1]'); \
	 xmax=$$(echo "$$info" | jq -r '.cornerCoordinates.lowerRight[0]'); \
	 ymin=$$(echo "$$info" | jq -r '.cornerCoordinates.lowerRight[1]'); \
	 xs=$$(echo "$$info" | jq -r '.size[0]'); \
	 ys=$$(echo "$$info" | jq -r '.size[1]'); \
	mkdir -p $(dir $@); \
	gdal_rasterize -burn 1 -ot Byte -co COMPRESS=LZW -te $$xmin $$ymin $$xmax $$ymax -ts $$xs $$ys -a_nodata 0 "$(FOREST_GEOJSON)" $@

data/overlays/water_mask.tif: $(WATER_GEOJSON) data/shaded-basemap.tif
	@echo "Rasterizing water overlay to $@ aligned with shaded basemap"
	@info=$$(gdalinfo -json data/shaded-basemap.tif); \
	 xmin=$$(echo "$$info" | jq -r '.cornerCoordinates.upperLeft[0]'); \
	 ymax=$$(echo "$$info" | jq -r '.cornerCoordinates.upperLeft[1]'); \
	 xmax=$$(echo "$$info" | jq -r '.cornerCoordinates.lowerRight[0]'); \
	 ymin=$$(echo "$$info" | jq -r '.cornerCoordinates.lowerRight[1]'); \
	 xs=$$(echo "$$info" | jq -r '.size[0]'); \
	 ys=$$(echo "$$info" | jq -r '.size[1]'); \
	mkdir -p $(dir $@); \
	gdal_rasterize -burn 1 -ot Byte -co COMPRESS=LZW -te $$xmin $$ymin $$xmax $$ymax -ts $$xs $$ys -a_nodata 0 "$(WATER_GEOJSON)" $@

# Build effective forest mask = forest * (1 - water)
data/overlays/forest_effective_mask.tif: data/overlays/forest_mask.tif data/overlays/water_mask.tif
	@gdal_calc.py -A data/overlays/forest_mask.tif -B data/overlays/water_mask.tif --outfile=$@ --calc="A*(1-B)" --type=Byte --overwrite

# Blend overlays into the shaded basemap using colors from QML
data/shaded-basemap-overlays.tif: data/shaded-basemap.tif data/overlays/forest_effective_mask.tif data/overlays/water_mask.tif $(FOREST_QML) $(WATER_QML)
	python3 scripts/blend_overlay.py $< data/overlays/water_mask.tif data/overlays/forest_effective_mask.tif $(WATER_QML) $(FOREST_QML) $@

# Reproject the overlayed shaded basemap for tiling
data/shaded-basemap-overlays-3857.tif: data/shaded-basemap-overlays.tif
	gdalwarp -of GTiff -t_srs EPSG:3857 -r bilinear -co COMPRESS=LZW -co TILED=YES $< $@

# Tiles target depending on overlays (full)
data/tiles: data/shaded-basemap-overlays-3857.tif
	mkdir -p $(TILE_OUTPUT_DIR)
	gdal2tiles.py \
		-p mercator \
		-z $(TILE_ZOOMS) \
		-w all \
		--processes=$(GDAL2TILES_PROCS) \
		--xyz \
		-r average \
		-a 0.0 \
		$< $(TILE_OUTPUT_DIR)

# For the small sample we build a single-zoom tiled basemap that uses the
# hillmap colour ramp in `scripts/hillmap-colours.txt`. Convert the QGIS
# exported colormap into a gdaldem-friendly color file, then produce a
# shaded RGB and tile just `$(SAMPLE_ZOOM)`.
data/hillmap-colors.txt: scripts/hillmap-colours.txt
	mkdir -p $(dir $@)
	awk -F',' 'BEGIN{OFS=" "} /^#/ {next} /^INTERPOLATION/ {next} {v=$$1; gsub(/ /,"",v); if(v=="inf") v=1000000; print v, $$2, $$3, $$4}' $< > $@

data/shaded-basemap-sample.tif: data/merged-dem.tif data/hill-shade-merged.tif data/hillmap-colors.txt
	mkdir -p $(dir $@) data/tmp
	# color-relief: convert DEM to RGB using the colour ramp
	gdaldem color-relief $< data/hillmap-colors.txt data/tmp/merged-dem-colored.tif -of GTiff -co COMPRESS=LZW
	# split channels and blend with hillshade (simple mix)
	gdal_translate -b 1 data/tmp/merged-dem-colored.tif data/tmp/color_b1.tif
	gdal_translate -b 2 data/tmp/merged-dem-colored.tif data/tmp/color_b2.tif
	gdal_translate -b 3 data/tmp/merged-dem-colored.tif data/tmp/color_b3.tif
	gdal_calc.py -A data/tmp/color_b1.tif -B data/hill-shade-merged.tif --outfile=data/tmp/shaded_b1.tif --calc='(A*0.7 + B*0.3)' --type=Byte --overwrite
	gdal_calc.py -A data/tmp/color_b2.tif -B data/hill-shade-merged.tif --outfile=data/tmp/shaded_b2.tif --calc='(A*0.7 + B*0.3)' --type=Byte --overwrite
	gdal_calc.py -A data/tmp/color_b3.tif -B data/hill-shade-merged.tif --outfile=data/tmp/shaded_b3.tif --calc='(A*0.7 + B*0.3)' --type=Byte --overwrite
	gdal_merge.py -separate -o data/tmp/shaded_rgb_sample.tif data/tmp/shaded_b1.tif data/tmp/shaded_b2.tif data/tmp/shaded_b3.tif
	gdal_translate -co COMPRESS=LZW data/tmp/shaded_rgb_sample.tif $@

data/tiles/sample: data/shaded-basemap-sample-overlays.tif
	mkdir -p $(SAMPLE_TILE_DIR)
	gdal2tiles.py -p mercator -z $(SAMPLE_ZOOM)-$(SAMPLE_ZOOM) -w leaflet $< $(SAMPLE_TILE_DIR)

# Sample overlay targets (aligned to sample shaded basemap)

data/overlays/forest_mask-sample.tif: $(FOREST_GEOJSON) data/shaded-basemap-sample.tif
	@echo "Rasterizing forest overlay (sample) to $@ aligned with shaded sample basemap"
	@info=$$(gdalinfo -json data/shaded-basemap-sample.tif); \
	 xmin=$$(echo "$$info" | jq -r '.cornerCoordinates.upperLeft[0]'); \
	 ymax=$$(echo "$$info" | jq -r '.cornerCoordinates.upperLeft[1]'); \
	 xmax=$$(echo "$$info" | jq -r '.cornerCoordinates.lowerRight[0]'); \
	 ymin=$$(echo "$$info" | jq -r '.cornerCoordinates.lowerRight[1]'); \
	 xs=$$(echo "$$info" | jq -r '.size[0]'); \
	 ys=$$(echo "$$info" | jq -r '.size[1]'); \
	mkdir -p $(dir $@); \
	gdal_rasterize -burn 1 -ot Byte -co COMPRESS=LZW -te $$xmin $$ymin $$xmax $$ymax -ts $$xs $$ys -a_nodata 0 "$(FOREST_GEOJSON)" $@


data/overlays/water_mask-sample.tif: $(WATER_GEOJSON) data/shaded-basemap-sample.tif
	@echo "Rasterizing water overlay (sample) to $@ aligned with shaded sample basemap"
	@info=$$(gdalinfo -json data/shaded-basemap-sample.tif); \
	 xmin=$$(echo "$$info" | jq -r '.cornerCoordinates.upperLeft[0]'); \
	 ymax=$$(echo "$$info" | jq -r '.cornerCoordinates.upperLeft[1]'); \
	 xmax=$$(echo "$$info" | jq -r '.cornerCoordinates.lowerRight[0]'); \
	 ymin=$$(echo "$$info" | jq -r '.cornerCoordinates.lowerRight[1]'); \
	 xs=$$(echo "$$info" | jq -r '.size[0]'); \
	 ys=$$(echo "$$info" | jq -r '.size[1]'); \
	mkdir -p $(dir $@); \
	gdal_rasterize -burn 1 -ot Byte -co COMPRESS=LZW -te $$xmin $$ymin $$xmax $$ymax -ts $$xs $$ys -a_nodata 0 "$(WATER_GEOJSON)" $@

data/overlays/forest_effective_mask-sample.tif: data/overlays/forest_mask-sample.tif data/overlays/water_mask-sample.tif
	@gdal_calc.py -A data/overlays/forest_mask-sample.tif -B data/overlays/water_mask-sample.tif --outfile=$@ --calc="A*(1-B)" --type=Byte --overwrite


data/shaded-basemap-sample-overlays.tif: data/shaded-basemap-sample.tif data/overlays/forest_effective_mask-sample.tif data/overlays/water_mask-sample.tif $(FOREST_QML) $(WATER_QML)
	python3 scripts/blend_overlay.py $< data/overlays/water_mask-sample.tif data/overlays/forest_effective_mask-sample.tif $(WATER_QML) $(FOREST_QML) $@


# Remove generated products (safe clean)
clean:
	@echo "Removing generated rasters and tiles..."
	-rm -f data/merged-dem.tif data/merged-dem.tif.aux.xml
	-rm -f data/hill-shade-merged.tif
	-rm -f data/contour-merged.gpkg data/contour-merged.gpkg-* 
	-rm -rf data/tiles

# Remove downloaded HGTs as well (destructive)
distclean: clean
	@echo "Removing downloaded HGT tiles in $(HGT_DIR) ..."
	-rm -rf $(HGT_DIR)

# Apply or export QGIS layer styles stored in `styling/`.
apply-styles:
	python3 scripts/apply_styles.py $(PROJECT) styling

# Export styles from an existing QGIS project into `styling/`.
# Use `make export-styles-force` to overwrite existing files.
export-styles:
	python3 scripts/export_styles.py $(PROJECT) styling

export-styles-force:
	python3 scripts/export_styles.py --force $(PROJECT) styling

# ============================================================================
# Point data (hills and trig points) tile generation
# ============================================================================

# Convert CSV files to GeoJSON
$(TRIG_POINTS_GEOJSON): $(TRIG_POINTS_CSV)
	mkdir -p $(dir $@)
	python3 scripts/csv_to_geojson.py $< $@ --lat-col lat --lon-col long --name-col tp_name

$(HILLS_GEOJSON): $(HILLS_CSV)
	mkdir -p $(dir $@)
	python3 scripts/csv_to_geojson.py $< $@ --lat-col Latitude --lon-col Longitude --name-col Name

# Convenience target to generate all GeoJSON files
geojson: $(TRIG_POINTS_GEOJSON) $(HILLS_GEOJSON)

# Generate MBTiles from GeoJSON for web mapping
# Note: This requires tippecanoe to be installed
# For systems without tippecanoe, the GeoJSON can be served directly by web mapping libraries
data/tiles/trig-points.mbtiles: $(TRIG_POINTS_GEOJSON)
	@if command -v tippecanoe >/dev/null 2>&1; then \
		mkdir -p $(dir $@); \
		tippecanoe -o $@ -z 13 -Z 7 -r1 --drop-densest-as-needed \
			--name="Trig Points" \
			--layer=trig-points \
			--minimum-zoom=7 \
			--maximum-zoom=13 \
			--no-tile-compression \
			$(TRIG_POINTS_GEOJSON); \
	else \
		echo "WARNING: tippecanoe not found. Skipping vector tile generation."; \
		echo "To generate vector tiles, install tippecanoe: https://github.com/felt/tippecanoe"; \
		echo "Alternatively, use the GeoJSON file directly with Leaflet or other web mapping libraries."; \
	fi

data/tiles/hills.mbtiles: $(HILLS_GEOJSON)
	@if command -v tippecanoe >/dev/null 2>&1; then \
		mkdir -p $(dir $@); \
		tippecanoe -o $@ -z 13 -Z 7 -r1 --drop-densest-as-needed \
			--name="Database of British and Irish Hills" \
			--layer=hills \
			--minimum-zoom=7 \
			--maximum-zoom=13 \
			--no-tile-compression \
			$(HILLS_GEOJSON); \
	else \
		echo "WARNING: tippecanoe not found. Skipping vector tile generation."; \
		echo "To generate vector tiles, install tippecanoe: https://github.com/felt/tippecanoe"; \
		echo "Alternatively, use the GeoJSON file directly with Leaflet or other web mapping libraries."; \
	fi

# Convenience target to generate point tiles (or just GeoJSON if tippecanoe unavailable)
point-tiles: geojson
	@if command -v tippecanoe >/dev/null 2>&1; then \
		$(MAKE) data/tiles/trig-points.mbtiles data/tiles/hills.mbtiles; \
	else \
		echo "Point data available as GeoJSON in data/points/"; \
		echo "Install tippecanoe to generate vector tiles."; \
	fi

# Target to build all three tile sets
all-tiles: data/tiles point-tiles
