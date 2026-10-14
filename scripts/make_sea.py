#!/usr/bin/env python3
"""Make sea polygons with a detailed, smooth coastline from the DEM.

Usage:
    python3 scripts/make_sea.py [data/merged-dem.tif] [data/sea.gpkg]

The project's sea comes from the ESRI OSM service as a coarse, generalised polygon, which only
looked acceptable because the style blurred it. Here the sea is the part of the DEM at or
below sea level (the DEM is 0 over the sea). The coast is contoured at 0.5 m so that it
follows the real shoreline to a fraction of a pixel, then lightly smoothed.

Output: data/sea.gpkg, layer `sea` (EPSG:4326 polygons). Needs numpy, shapely and the GDAL
Python bindings.
"""
import sys

import numpy as np
import shapely
from osgeo import gdal, ogr, osr

gdal.UseExceptions()
ogr.UseExceptions()
osr.UseExceptions()

LEVEL = 0.5            # contour level in metres: below this is sea
FLOOR = -1.0           # a second level below the sea, so the sea is a band with a bound on both sides
SIMPLIFY = 0.00003     # degrees, about 3 m: drop vertices that do not change the shape
CHAIKIN_PASSES = 2     # corner cutting rounds, to take the pixel stair-steps off the coast


def chaikin(coords, passes):
    pts = np.asarray(coords)
    for _ in range(passes):
        a, b = pts[:-1], pts[1:]
        q, r = 0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b
        pts = np.empty((len(q) * 2 + 1, 2))
        pts[0:-1:2], pts[1:-1:2], pts[-1] = q, r, pts[0]
    return pts


def smooth_polygon(poly):
    ring = lambda r: chaikin(shapely.get_coordinates(r), CHAIKIN_PASSES)
    shell = shapely.Polygon(ring(poly.exterior), [ring(i) for i in poly.interiors])
    return shell if shell.is_valid else shell.buffer(0)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "data/merged-dem.tif"
    dst = sys.argv[2] if len(sys.argv) > 2 else "data/sea.gpkg"
    ds = gdal.Open(src)
    dem = ds.GetRasterBand(1).ReadAsArray().astype(np.float32)

    # Missing tiles (nodata) are sea, so treat everything at or below zero as level ground at 0
    field = np.where(dem <= 0, 0.0, dem).astype(np.float32)
    mem = gdal.GetDriverByName("MEM").Create("", dem.shape[1], dem.shape[0], 1, gdal.GDT_Float32)
    mem.SetGeoTransform(ds.GetGeoTransform())
    mem.SetProjection(ds.GetProjection())
    mem.GetRasterBand(1).WriteArray(field)

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tmp = ogr.GetDriverByName("Memory").CreateDataSource("")
    contours = tmp.CreateLayer("c", srs, ogr.wkbMultiPolygon)
    contours.CreateField(ogr.FieldDefn("lo", ogr.OFTReal))
    contours.CreateField(ogr.FieldDefn("hi", ogr.OFTReal))
    # The sea is the band between FLOOR and LEVEL. GDAL 3.13 and newer leave out the two open-ended
    # bands (below the lowest level, above the highest) when polygonizing, so a single level gives no
    # polygons at all; a band with both bounds is kept by every version.
    gdal.ContourGenerateEx(
        mem.GetRasterBand(1), contours,
        options=[f"FIXED_LEVELS={FLOOR},{LEVEL}", "POLYGONIZE=YES", "ELEV_FIELD_MIN=0", "ELEV_FIELD_MAX=1"],
    )

    out = ogr.GetDriverByName("GPKG").CreateDataSource(dst)
    layer = out.CreateLayer("sea", srs, ogr.wkbMultiPolygon, ["OVERWRITE=YES"])
    kept = 0
    for feat in contours:
        # The band that ends at the contour level is the sea
        hi = feat.GetField("hi")
        if hi is None or abs(hi - LEVEL) > 1e-6:
            continue
        geom = shapely.from_wkb(bytes(feat.GetGeometryRef().ExportToWkb()))
        parts = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
        smoothed = [smooth_polygon(p.simplify(SIMPLIFY)) for p in parts if not p.is_empty]
        multi = shapely.MultiPolygon([p for g in smoothed for p in (g.geoms if hasattr(g, "geoms") else [g])])
        f = ogr.Feature(layer.GetLayerDefn())
        f.SetGeometry(ogr.CreateGeometryFromWkb(shapely.to_wkb(multi)))
        layer.CreateFeature(f)
        kept += 1
    out = None
    print(f"Wrote {dst} ({kept} feature(s))", file=sys.stderr)
    if kept == 0:
        # An empty sea would silently draw the sea white, so fail the build instead
        sys.exit("No sea polygons were found in the DEM")


if __name__ == "__main__":
    main()
