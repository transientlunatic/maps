#!/usr/bin/env python3
"""Make the sample images used in the README (docs/samples/<name>.png).

Usage:
    QT_QPA_PLATFORM=offscreen python3 scripts/make_samples.py [name ...]

Each sample is a window of the map at one zoom level: the layer being shown drawn over
the topology (and, for the railways and paths, the roads), rendered with
scripts/render_tiles.py from the data in data/. Samples whose data is missing are skipped.
The water names sample is a screenshot of preview/index.html, so it is not made here.
"""
import math
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

WIDTH, HEIGHT = 640, 400

# Layers that the map blends with multiply (CSS mix-blend-mode), so the terrain shows through
MULTIPLY = {"forests"}

# name: (centre lon, centre lat, zoom, layers from the bottom up)
SAMPLES = {
    "topology": (-4.55, 56.10, 11, ["topology"]),
    "imhof": (-4.80, 56.60, 10, ["imhof"]),
    "elevmist": (-4.80, 56.55, 10, ["topology", "elevmist"]),
    "forests": (-4.42, 56.35, 12, ["topology", "forests"]),
    "mist": (-4.80, 56.55, 10, ["topology", "mist"]),
    "dbobih": (-4.63, 56.19, 12, ["topology", "forests", "dbobih"]),
    "trigs": (-4.32, 56.25, 12, ["topology", "forests", "trigs"]),
    "roads": (-4.31, 55.865, 12, ["topology", "forests", "roads"]),
    "transport": (-4.30, 55.86, 13, ["topology", "forests", "roads", "transport"]),
    "paths": (-3.80, 57.17, 13, ["topology", "forests", "paths"]),
    "rivers": (-4.42, 56.35, 12, ["topology", "forests", "rivers"]),
    "shelters": (-3.64, 57.08, 12, ["topology", "forests", "shelters"]),
    "facilities": (-3.68, 57.145, 12, ["topology", "forests", "facilities"]),
}

# Data each tile set needs (the topology needs the DEM files)
NEEDS = {
    "topology": ["data/merged-dem.tif", "data/hill-shade-merged.tif", "data/contours-merged.gpkg", "data/sea.gpkg"],
    "forests": [],
    "imhof": ["data/imhof-shade-3x.tif", "data/sea.gpkg"],
    "elevmist": ["data/merged-dem.tif"],
    "mist": ["data/mist.tif"],
    "dbobih": ["sources/dobih.csv"],
    "trigs": ["sources/trigs.csv"],
    "roads": ["data/roads.gpkg"],
    "transport": ["data/transport.gpkg"],
    "paths": ["data/paths.gpkg"],
    "rivers": ["data/rivers.gpkg"],
    "shelters": ["data/shelters.gpkg"],
    "facilities": ["data/facilities.gpkg"],
}


def to_pixel(lon, lat, zoom):
    size = 256 * 2 ** zoom
    x = (lon + 180) / 360 * size
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * size
    return x, y


def to_lonlat(x, y, zoom):
    size = 256 * 2 ** zoom
    lon = x / size * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / size))))
    return lon, lat


def make(name, outdir):
    lon, lat, zoom, layers = SAMPLES[name]
    missing = [f for t in layers for f in NEEDS[t] if not os.path.exists(f)]
    if missing:
        print(f"skipping {name}: missing {', '.join(missing)}")
        return
    cx, cy = to_pixel(lon, lat, zoom)
    left, top = cx - WIDTH / 2, cy - HEIGHT / 2
    west, north = to_lonlat(left, top, zoom)
    east, south = to_lonlat(left + WIDTH, top + HEIGHT, zoom)

    with tempfile.TemporaryDirectory() as tmp:
        for tileset in layers:
            subprocess.run(
                [sys.executable, "scripts/render_tiles.py", "--project", "projects/basemap.qgz",
                 "--tileset", tileset, f"--extent={west},{south},{east},{north}",
                 "--zmin", str(zoom), "--zmax", str(zoom), "--out", tmp, "--version", "s"],
                check=True, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        x0, x1 = int(left // 256), int((left + WIDTH) // 256)
        y0, y1 = int(top // 256), int((top + HEIGHT) // 256)
        canvas = Image.new("RGBA", ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256), (255, 255, 255, 255))
        for tileset in layers:
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    path = os.path.join(tmp, tileset, "s", str(zoom), str(x), f"{y}.png")
                    if os.path.exists(path):
                        tile = Image.open(path).convert("RGBA")
                        at = ((x - x0) * 256, (y - y0) * 256)
                        if tileset in MULTIPLY:
                            box = (*at, at[0] + 256, at[1] + 256)
                            under = np.array(canvas.crop(box)).astype(float)
                            over = np.array(tile).astype(float)
                            alpha = over[:, :, 3:4] / 255
                            under[:, :, :3] = under[:, :, :3] * (1 - alpha) + alpha * under[:, :, :3] * over[:, :, :3] / 255
                            canvas.paste(Image.fromarray(under.astype("uint8")), at)
                        else:
                            canvas.alpha_composite(tile, at)
        ox, oy = int(left - x0 * 256), int(top - y0 * 256)
        image = canvas.crop((ox, oy, ox + WIDTH, oy + HEIGHT)).convert("RGB")
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"{name}.png")
    image.convert("P", palette=Image.ADAPTIVE, colors=256).save(out, optimize=True)
    print("wrote", out)


def main():
    names = sys.argv[1:] or list(SAMPLES)
    for name in names:
        make(name, "docs/samples")


if __name__ == "__main__":
    main()
