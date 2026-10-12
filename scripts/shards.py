#!/usr/bin/env python3
"""Split the tile area into shards, and print a GitHub Actions job matrix as JSON.

Usage:
    python3 scripts/shards.py --bbox W,S,E,N --cols 2 --rows 4 --tilesets topology,roads

Every tile set is rendered once per shard, so the work is spread over many jobs. The area is
cut along zoom 9 tile edges, so the tiles of every zoom from 9 up fall in exactly one shard and
the shards can simply be merged. Use --cols 1 --rows 1 for a single shard covering the bbox.

Output: {"include": [{"tileset": ..., "shard": "r0c1", "bbox": "W,S,E,N"}, ...]}
"""
import argparse
import json
import math

ZOOM = 9            # shards follow the tile grid at this zoom
EPSILON = 1e-7      # shrink each shard a little so it does not touch its neighbours' tiles


def tile_x(lon, z=ZOOM):
    return (lon + 180) / 360 * 2 ** z


def tile_y(lat, z=ZOOM):
    return (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 2 ** z


def lon_of(x, z=ZOOM):
    return x / 2 ** z * 360 - 180


def lat_of(y, z=ZOOM):
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2 ** z))))


def split(count, parts):
    """Sizes of `parts` nearly equal blocks that add up to `count`."""
    parts = max(1, min(parts, count))
    return [count // parts + (1 if i < count % parts else 0) for i in range(parts)]


def shards(bbox, cols, rows):
    west, south, east, north = bbox
    x0, x1 = math.floor(tile_x(west)), math.floor(tile_x(east))
    y0, y1 = math.floor(tile_y(north)), math.floor(tile_y(south))
    out, y = [], y0
    for r, height in enumerate(split(y1 - y0 + 1, rows)):
        x = x0
        for c, width in enumerate(split(x1 - x0 + 1, cols)):
            w, e = lon_of(x) + EPSILON, lon_of(x + width) - EPSILON
            n, s = lat_of(y) - EPSILON, lat_of(y + height) + EPSILON
            out.append((f"r{r}c{c}", (w, s, e, n)))
            x += width
        y += height
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bbox", required=True, help="west,south,east,north in degrees")
    ap.add_argument("--cols", type=int, default=1)
    ap.add_argument("--rows", type=int, default=1)
    ap.add_argument("--tilesets", required=True, help="comma separated tile set names")
    args = ap.parse_args()

    bbox = tuple(float(v) for v in args.bbox.split(","))
    if args.cols == 1 and args.rows == 1:
        parts = [("all", bbox)]
    else:
        parts = shards(bbox, args.cols, args.rows)
    include = [
        {"tileset": t, "shard": name, "bbox": ",".join(f"{v:.7f}" for v in box)}
        for t in args.tilesets.split(",")
        for name, box in parts
    ]
    print(json.dumps({"include": include}))


if __name__ == "__main__":
    main()
