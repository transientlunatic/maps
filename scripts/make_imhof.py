#!/usr/bin/env python3
"""Mix the two hillshades into the single shading value that the `imhof` basemap style colours.

Usage:
    python3 scripts/make_imhof.py [data/hill-shade-merged.tif data/hill-shade-multi.tif data/imhof-shade.tif]

Eduard Imhof coloured his relief shading instead of just darkening the map: slopes that face the
light are a pale warm yellow, and slopes in shadow are a cool blue-violet. The colour comes from
a gradient in styling/Imhof Shading.qml; this script makes the value that goes through it, from

  * the traditional hillshade (one light, from the north-west), which gives the form of the
    mountains a clear direction, and
  * the multidirectional hillshade (light from several directions), which keeps ridges and gullies
    that run towards the light readable.

The output is one byte band (0 = darkest, 255 = brightest) on the same grid. The Makefile then
enlarges it threefold with cubic resampling (data/imhof-shade-3x.tif), because QGIS shows the
90 m cells of a coloured raster as blocks when zoomed in, but draws an enlarged one smoothly.
Needs numpy and the GDAL Python bindings.
"""
import sys

import numpy as np
from osgeo import gdal

gdal.UseExceptions()

# How much of each hillshade goes into the shading (they add up to 1)
TRADITIONAL = 0.45
MULTIDIRECTIONAL = 0.55

def main():
    args = sys.argv[1:] + [None] * 3
    trad_path = args[0] or "data/hill-shade-merged.tif"
    multi_path = args[1] or "data/hill-shade-multi.tif"
    dst = args[2] or "data/imhof-shade.tif"

    trad = gdal.Open(trad_path)
    multi = gdal.Open(multi_path)
    out = gdal.GetDriverByName("GTiff").Create(
        dst, trad.RasterXSize, trad.RasterYSize, 1, gdal.GDT_Byte, ["COMPRESS=LZW", "TILED=YES"]
    )
    out.SetGeoTransform(trad.GetGeoTransform())
    out.SetProjection(trad.GetProjection())

    # Work in strips of rows to keep the memory use down
    step = 1024
    for y in range(0, trad.RasterYSize, step):
        rows = min(step, trad.RasterYSize - y)
        a = trad.GetRasterBand(1).ReadAsArray(0, y, trad.RasterXSize, rows).astype(np.float32)
        b = multi.GetRasterBand(1).ReadAsArray(0, y, trad.RasterXSize, rows).astype(np.float32)
        shade = (TRADITIONAL * a + MULTIDIRECTIONAL * b).round().astype(np.uint8)
        out.GetRasterBand(1).WriteArray(shade, 0, y)
    out.FlushCache()
    print(f"Wrote {dst}", file=sys.stderr)


if __name__ == "__main__":
    main()
