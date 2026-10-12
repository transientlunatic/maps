#!/usr/bin/env python3
"""Make a valley mist raster from the DEM, in the manner of Eduard Imhof's aerial perspective.

Usage:
    python3 scripts/make_mist.py [data/merged-dem.tif] [data/mist.tif]

The output is a one-band byte raster of mist density (0 = clear, 255 = thickest) on the DEM's
grid. Mist collects on valley floors and thins up the slopes:

    1. Find the valley floor near each point: the lowest ground within FLOOR_RADIUS.
    2. Mist is thickest at the floor and fades to nothing FADE_HEIGHT above it.
    3. It also thins with altitude, and only forms where the land is rugged (the local relief
       is more than a few hundred metres), so a flat plain does not get a blanket of haze.

The colour and opacity are set by styling/Valley Mist.qml. Needs numpy, scipy and the GDAL
Python bindings.
"""
import sys

import numpy as np
from osgeo import gdal
from scipy.ndimage import gaussian_filter, maximum_filter1d, minimum_filter1d

gdal.UseExceptions()

FLOOR_RADIUS_M = 3000    # how far to look for the valley floor
FADE_HEIGHT_M = 220      # mist fades out this far above the valley floor
CEILING_M = 800          # no mist above about this altitude
RELIEF_FULL_M = 450      # local relief at which mist forms fully
RELIEF_NONE_M = 120      # ... and below which it does not form at all


def smoothstep(x, lo, hi):
    t = np.clip((x - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "data/merged-dem.tif"
    dst = sys.argv[2] if len(sys.argv) > 2 else "data/mist.tif"
    ds = gdal.Open(src)
    dem = ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
    gt = ds.GetGeoTransform()

    # Pixel size in metres at the middle of the raster (3 arc second data is ~50-90 m)
    mid_lat = gt[3] + gt[5] * dem.shape[0] / 2
    px = abs(gt[1]) * 111320 * np.cos(np.radians(mid_lat))
    size = int(2 * FLOOR_RADIUS_M / px) | 1

    # Lowest and highest ground within the radius (a square window, done one axis at a time)
    low = minimum_filter1d(minimum_filter1d(dem, size, axis=0), size, axis=1)
    high = maximum_filter1d(maximum_filter1d(dem, size, axis=0), size, axis=1)
    # Smooth the floor so the mist edge does not follow the window's square corners
    sigma = size / 4
    floor = gaussian_filter(low, sigma)
    relief = gaussian_filter(high - low, sigma)

    above = np.clip(dem - floor, 0, None)
    near_floor = 1 - smoothstep(above, 0, FADE_HEIGHT_M)
    low_down = 1 - smoothstep(dem, CEILING_M * 0.4, CEILING_M)
    rugged = smoothstep(relief, RELIEF_NONE_M, RELIEF_FULL_M)
    mist = near_floor * low_down * rugged
    mist[dem <= 0] = 0

    out = gdal.GetDriverByName("GTiff").Create(
        dst, dem.shape[1], dem.shape[0], 1, gdal.GDT_Byte, ["COMPRESS=LZW", "TILED=YES"]
    )
    out.SetGeoTransform(gt)
    out.SetProjection(ds.GetProjection())
    band = out.GetRasterBand(1)
    band.WriteArray((mist * 255).round().astype(np.uint8))
    band.SetNoDataValue(0)
    out.FlushCache()
    print(f"Wrote {dst} ({size} px window, mean density {mist.mean():.2f})", file=sys.stderr)


if __name__ == "__main__":
    main()
