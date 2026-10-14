#!/usr/bin/env python3
"""Make the hills file the map draws in the browser, from the Database of British and Irish Hills.

Usage:
    python3 scripts/make_hills.py --bbox=W,S,E,N [sources/dobih.csv] [out/hills.json]

Writes compact JSON for preview/hills.js (the `HillsLayer`): every hill inside the box, with its
position, name, height, drop and the lists it is on. The hills are drawn client side, as markers
and labels on a canvas, so they are crisp at any pixel density, can be clicked and filtered by
list, and need no tile rendering.

Output:  {"source": ..., "fields": [...], "hills": [[lon, lat, name, metres, drop, "M Ma Sim", id, "S"], ...]}
`lists` holds the codes of the lists a hill is on, in the order of LISTS below. The DoBIH number
(`id`) and country letter give the link to the hill's page on hill-bagging.co.uk.
"""
import argparse
import csv
import json
import os
import sys

# DoBIH list columns, most important first (the order they are written in)
LISTS = [
    "M", "MT", "xMT", "F", "C", "CT", "G", "GT", "D", "DT", "Dil", "W", "Hew", "N",
    "Ma", "Hu", "Sim",
]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bbox", required=True, help="west,south,east,north in degrees (use --bbox=...)")
    ap.add_argument("src", nargs="?", default="sources/dobih.csv")
    ap.add_argument("dst", nargs="?", default="data/tiles/hills/dev/hills.json")
    args = ap.parse_args()

    west, south, east, north = (float(v) for v in args.bbox.split(","))
    hills = []
    with open(args.src, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                lon, lat = float(row["Longitude"]), float(row["Latitude"])
                metres, drop = round(float(row["Metres"])), round(float(row["Drop"] or 0))
            except ValueError:
                continue
            if not (west <= lon <= east and south <= lat <= north):
                continue
            lists = " ".join(code for code in LISTS if (row.get(code) or "0").strip() not in ("", "0"))
            country = (row.get("Country") or "S").strip()[:1] or "S"
            hills.append([round(lon, 5), round(lat, 5), row["Name"].strip(), metres, drop, lists, int(row["Number"]), country])

    # Highest first, so the file reads in the order the map prefers hills
    hills.sort(key=lambda h: -h[3])
    out = {
        "source": "Database of British and Irish Hills, https://www.hills-database.co.uk",
        "fields": ["lon", "lat", "name", "metres", "drop", "lists", "id", "country"],
        "hills": hills,
    }
    os.makedirs(os.path.dirname(args.dst) or ".", exist_ok=True)
    with open(args.dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    size = os.path.getsize(args.dst)
    print(f"Wrote {len(hills)} hills to {args.dst} ({size / 1e6:.2f} MB)", file=sys.stderr)


if __name__ == "__main__":
    main()
