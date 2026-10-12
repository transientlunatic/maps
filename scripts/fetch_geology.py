#!/usr/bin/env python3
"""Download the BGS 1:50,000 bedrock geology for an area as one GeoTIFF.

Usage:
    fetch_geology.py --bbox=<west,south,east,north> <out.tif> [--cell 52.9] [--block 100000]

The BGS web map service (BGS.50k.Bedrock) draws nothing when it is zoomed out further than about
1:94,000, so it cannot be used for tiles directly. Instead this script asks for the area in blocks
of 100 km, each as a 3,800 pixel image at about 26 m per pixel (the coarsest the service will
draw), joins them, and writes a British National Grid GeoTIFF (RGBA, tiled, with overviews) at
`--cell` metres per pixel (default 52.9, or twice the service's finest cell, which keeps the
file manageable). QGIS then draws that at every zoom (see styling/Geology.qml).

Contains British Geological Survey materials (c) UKRI. Needs the GDAL Python bindings.
"""
import argparse
import math
import os
import shutil
import sys
import tempfile
import time
import urllib.request

from osgeo import gdal, osr

gdal.UseExceptions()

URL = (
    "https://map.bgs.ac.uk/arcgis/services/BGS_Detailed_Geology/MapServer/WMSServer"
    "?service=WMS&version=1.3.0&request=GetMap&layers=BGS.50k.Bedrock&styles="
    "&crs=EPSG:27700&bbox={w},{s},{e},{n}&width={px}&height={px}"
    "&format=image/png&transparent=true"
)
# The service draws down to a scale of 1:94,495 (at 96 dpi), which is 26.46 m per pixel
FETCH_CELL = 26.4


def bng_envelope(bbox):
    west, south, east, north = bbox
    src = osr.SpatialReference()
    src.ImportFromEPSG(4326)
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    dst = osr.SpatialReference()
    dst.ImportFromEPSG(27700)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(src, dst)
    # Sample along the edges, as the box is curved in the grid
    pts = []
    for i in range(21):
        t = i / 20
        lon, lat = west + (east - west) * t, south + (north - south) * t
        pts += [(lon, south), (lon, north), (west, lat), (east, lat)]
    xy = [ct.TransformPoint(lon, lat)[:2] for lon, lat in pts]
    xs, ys = zip(*xy)
    return min(xs), min(ys), max(xs), max(ys)


def download(url, path, tries=4):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=240) as r, open(path, "wb") as f:
                shutil.copyfileobj(r, f)
            return
        except Exception as err:  # the service is slow and sometimes drops a request
            if attempt == tries - 1:
                raise
            print(f"  retrying after {err}", file=sys.stderr)
            time.sleep(5 * 2 ** attempt)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bbox", required=True, help="west,south,east,north in degrees (use --bbox=...)")
    ap.add_argument("dst")
    ap.add_argument("--cell", type=float, default=52.9, help="output cell size in metres")
    ap.add_argument("--block", type=int, default=100000, help="block size in metres")
    args = ap.parse_args()

    bbox = [float(v) for v in args.bbox.split(",")]
    x0, y0, x1, y1 = bng_envelope(bbox)
    block = args.block
    x0, y0 = math.floor(x0 / block) * block, math.floor(y0 / block) * block
    x1, y1 = math.ceil(x1 / block) * block, math.ceil(y1 / block) * block
    px = round(block / FETCH_CELL)

    tmp = tempfile.mkdtemp(prefix="geology-")
    tiles = []
    todo = [(x, y) for y in range(y0, y1, block) for x in range(x0, x1, block)]
    for i, (x, y) in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] block {x},{y}", file=sys.stderr, flush=True)
        png = os.path.join(tmp, f"{x}_{y}.png")
        download(URL.format(w=x, s=y, e=x + block, n=y + block, px=px), png)
        tif = os.path.join(tmp, f"{x}_{y}.tif")
        gdal.Translate(tif, png, outputBounds=[x, y + block, x + block, y], outputSRS="EPSG:27700")
        os.remove(png)
        tiles.append(tif)

    vrt = os.path.join(tmp, "all.vrt")
    gdal.BuildVRT(vrt, tiles)
    if os.path.exists(args.dst):
        os.remove(args.dst)
    gdal.Warp(
        args.dst, vrt, xRes=args.cell, yRes=args.cell, resampleAlg="average",
        creationOptions=["COMPRESS=DEFLATE", "PREDICTOR=2", "TILED=YES", "BIGTIFF=IF_SAFER"],
    )
    ds = gdal.Open(args.dst, gdal.GA_Update)
    ds.BuildOverviews("AVERAGE", [2, 4, 8, 16])
    ds = None
    shutil.rmtree(tmp)
    print(f"Wrote {args.dst}", file=sys.stderr)


if __name__ == "__main__":
    main()
