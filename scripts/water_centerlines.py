#!/usr/bin/env python3
"""Compute a label line along the main axis of each named water body.

Usage:
    water_centerlines.py <water-polygons.gpkg> <out-centerlines.gpkg> [--min-area 20000]

The input is a polygon layer with a `name` field (see `make data/water-polygons.gpkg`).
For every polygon the script finds the longest path through its medial axis
(skeleton), so the line follows a winding loch rather than cutting across it,
then smooths it so QGIS can curve a label along it.

Output (EPSG:4326 lines) fields: name, area_m2, length_m.

Needs shapely, numpy, scipy and the GDAL Python bindings.
"""
import argparse
import os
import sys

import numpy as np
import shapely
from osgeo import gdal, ogr, osr
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import Voronoi
from shapely.ops import substring

gdal.UseExceptions()
ogr.UseExceptions()
osr.UseExceptions()

# Work in British National Grid so that distances are in metres.
METRIC_EPSG = 27700


def srs_from_epsg(code):
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(code)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return srs


def transformer(src, dst):
    ct = osr.CoordinateTransformation(src, dst)

    def apply(coords):
        pts = ct.TransformPoints(coords.tolist())
        return np.array([(x, y) for x, y, _ in pts])

    return apply


def densify_ring(ring, spacing):
    """Sample points along a ring at roughly `spacing` metres."""
    line = shapely.LinearRing(ring)
    n = max(int(line.length / spacing), 8)
    return shapely.get_coordinates(
        shapely.line_interpolate_point(line, np.linspace(0, line.length, n, endpoint=False))
    )


def skeleton_longest_path(poly, spacing):
    """Longest path through the Voronoi skeleton of `poly`, as an (N, 2) array."""
    points = densify_ring(poly.exterior.coords, spacing)
    # Islands pull the skeleton towards them; ignoring them keeps the line
    # running down the middle of the loch, and a label over an island is fine.
    if len(points) < 4:
        return None
    vor = Voronoi(points)

    verts = vor.vertices
    inside = shapely.contains_xy(poly, verts[:, 0], verts[:, 1])
    ridges = np.array(vor.ridge_vertices)
    ridges = ridges[(ridges >= 0).all(axis=1)]
    ridges = ridges[inside[ridges[:, 0]] & inside[ridges[:, 1]]]
    if len(ridges) < 2:
        return None

    # Re-index to the vertices actually used and build a weighted graph.
    used, flat = np.unique(ridges, return_inverse=True)
    ridges = flat.reshape(-1, 2)
    xy = verts[used]
    w = np.hypot(*(xy[ridges[:, 0]] - xy[ridges[:, 1]]).T)
    n = len(xy)
    graph = coo_matrix(
        (np.r_[w, w], (np.r_[ridges[:, 0], ridges[:, 1]], np.r_[ridges[:, 1], ridges[:, 0]])),
        shape=(n, n),
    ).tocsr()

    # Keep the largest connected piece, then find its diameter with two
    # Dijkstra sweeps (exact on a tree, a good approximation on a skeleton).
    _, labels = connected_components(graph, directed=False)
    biggest = np.argmax(np.bincount(labels))
    nodes = np.flatnonzero(labels == biggest)
    d0 = dijkstra(graph, indices=nodes[0], directed=False)
    a = nodes[np.argmax(np.where(np.isfinite(d0[nodes]), d0[nodes], -1))]
    da, pred = dijkstra(graph, indices=a, directed=False, return_predecessors=True)
    b = nodes[np.argmax(np.where(np.isfinite(da[nodes]), da[nodes], -1))]

    path = [b]
    while path[-1] != a:
        path.append(pred[path[-1]])
    return xy[path]


def resample(line, step):
    n = max(int(line.length / step), 2)
    return shapely.get_coordinates(
        shapely.line_interpolate_point(line, np.linspace(0, line.length, n))
    )


def smooth(coords, sigma_points):
    """Gaussian smooth, keeping the end points fixed."""
    if len(coords) < 5 or sigma_points < 1:
        return coords
    radius = int(3 * sigma_points)
    kernel = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma_points) ** 2)
    out = coords.copy()
    padded = np.vstack([
        2 * coords[0] - coords[radius:0:-1],
        coords,
        2 * coords[-1] - coords[-2:-radius - 2:-1],
    ])
    for axis in (0, 1):
        out[:, axis] = np.convolve(padded[:, axis], kernel / kernel.sum(), mode="valid")
    return out


def centerline(poly):
    """Smoothed main-axis line for a shapely Polygon in metres, or None."""
    # Fine enough to follow narrow arms, coarse enough to stay fast on big lochs.
    spacing = float(np.clip(np.sqrt(poly.area) / 60, 4, 60))
    poly = poly.simplify(spacing / 4)
    if poly.is_empty:
        return None
    if poly.geom_type == "MultiPolygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    raw = skeleton_longest_path(poly, spacing)
    if raw is None or len(raw) < 2:
        return None

    line = shapely.LineString(raw)
    # The skeleton runs right into the shoreline corners; trim the ends back so
    # the label sits in the body of the water rather than in the tips.
    trim = min(line.length * 0.04, 2 * spacing)
    if line.length > 4 * trim:
        line = substring(line, trim, line.length - trim)

    step = max(line.length / 150, spacing / 2)
    coords = smooth(resample(line, step), sigma_points=max(line.length / step / 25, 2))
    line = shapely.LineString(coords)

    # Read west to east, so labels are not upside down.
    if line.coords[0][0] > line.coords[-1][0]:
        line = shapely.LineString(list(line.coords)[::-1])
    return line


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--min-area", type=float, default=20000, help="smallest area in m2")
    args = ap.parse_args()

    src = ogr.Open(args.src)
    layer = src.GetLayer(0)
    to_metric = transformer(layer.GetSpatialRef(), srs_from_epsg(METRIC_EPSG))
    to_wgs84 = transformer(srs_from_epsg(METRIC_EPSG), srs_from_epsg(4326))

    drv = ogr.GetDriverByName("GPKG")
    if os.path.exists(args.dst):
        os.remove(args.dst)
    dst = drv.CreateDataSource(args.dst)
    out = dst.CreateLayer("water_names", srs_from_epsg(4326), ogr.wkbLineString)
    out.CreateField(ogr.FieldDefn("name", ogr.OFTString))
    out.CreateField(ogr.FieldDefn("area_m2", ogr.OFTReal))
    out.CreateField(ogr.FieldDefn("length_m", ogr.OFTReal))

    kept = skipped = 0
    for feat in layer:
        name = feat.GetField("name")
        geom = feat.GetGeometryRef()
        if not name or geom is None:
            continue
        poly = shapely.from_wkb(bytes(geom.ExportToWkb()))
        parts = list(poly.geoms) if hasattr(poly, "geoms") else [poly]
        # One label line per named part (a multipolygon can be several lochans).
        for part in parts:
            if part.geom_type != "Polygon":
                continue
            metric = shapely.transform(part, to_metric)
            if metric.area < args.min_area:
                skipped += 1
                continue
            line = centerline(metric)
            if line is None:
                skipped += 1
                continue
            f = ogr.Feature(out.GetLayerDefn())
            f.SetField("name", name)
            f.SetField("area_m2", round(float(metric.area)))
            f.SetField("length_m", round(float(line.length)))
            f.SetGeometry(ogr.CreateGeometryFromWkb(
                shapely.to_wkb(shapely.transform(line, to_wgs84))))
            out.CreateFeature(f)
            kept += 1
    dst = None
    print(f"Wrote {kept} label lines to {args.dst} ({skipped} skipped)", file=sys.stderr)


if __name__ == "__main__":
    main()
