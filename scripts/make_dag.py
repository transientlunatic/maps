#!/usr/bin/env python3
"""Write an HTCondor DAG that renders the tile sets, one job per tile set and shard.

Usage:
    python3 scripts/make_dag.py --version v0.1 [--tilesets heavy|light|all|a,b,c] [--cols 4 --rows 8]
    condor_submit_dag -usedagdir condor/tiles.dag

GitHub Actions cannot render the heavy tile sets (the topology, the Imhof style, the forests and
the big line layers) because a job may run for at most six hours, so this makes the same work
for a cluster you control. The default is the heavy tile sets; the light ones are built by the
workflow on a release. The shards are the same ones the workflow makes (see scripts/shards.py),
cut along zoom 9 tile edges, and each job writes the same archive, `<tileset>-<version>-<shard>.tar.gz`,
so the result can be attached to the release or published with scripts/publish_tiles.sh.

The DAG is written to --out (default `condor/`):

    tiles.dag       the DAG: one node per tile set and shard
    render.sub      submit file for the render nodes (runs scripts/condor_render.sh)
    data.sub        submit file for the data node (only with --data)
    shards/         the finished archives
    logs/           HTCondor's output, error and log files

It assumes the repository sits on a file system the execute machines share (the jobs run in it,
read data/ and write to condor/shards/) and that they have QGIS, GDAL and make installed. Build the
data first (`make data-all`, which needs the OSM extract), or add --data to make that the first
node of the DAG, with --data-requirements if it needs a particular machine. Nothing here needs
the HTCondor Python bindings; the files are plain text, so check them before submitting.

For a quick check, `--bbox` and `--zmax` render a small area, for example
`--bbox=-4.5,56.2,-4.2,56.35 --zmax 12 --cols 1 --rows 1`.
"""
import argparse
import os
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shards as shard_cuts  # noqa: E402  (scripts/shards.py)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_var(name):
    """Value of a Makefile variable (so the lists stay in one place)."""
    out = subprocess.run(
        ["make", "-s", "-C", REPO, f"print-{name}"], check=True, capture_output=True, text=True
    )
    return out.stdout.split()


def pick_tilesets(spec):
    if spec == "all":
        return make_var("TILESETS")
    if spec in ("heavy", "light"):
        return make_var(f"TILESETS_{spec.upper()}")
    return [t for t in spec.split(",") if t]


def render_submit(args, out):
    lines = [
        "# Written by scripts/make_dag.py: renders one tile set for one shard.",
        "universe       = vanilla",
        f"initialdir     = {REPO}",
        "executable     = scripts/condor_render.sh",
        # Condor's new-style arguments: one double-quoted string, split on spaces
        f'arguments      = "$(tileset) $(shard) $(bbox) {args.version} {args.zmin} {args.zmax} {out}"',
        f"environment    = \"QGIS_PYTHON={args.python} QT_QPA_PLATFORM=offscreen\"",
        "getenv         = False",
        "should_transfer_files = NO",
        f"request_cpus   = {args.cpus}",
        f"request_memory = {args.memory}",
        f"request_disk   = {args.disk}",
        f"output         = {out}/logs/$(tileset)-$(shard).out",
        f"error          = {out}/logs/$(tileset)-$(shard).err",
        f"log            = {out}/logs/tiles.log",
        "queue",
    ]
    if args.requirements:
        lines.insert(-1, f"requirements   = {args.requirements}")
    return "\n".join(lines) + "\n"


def data_submit(args, out):
    lines = [
        "# Written by scripts/make_dag.py: builds the data files the tile sets need, once.",
        "universe       = vanilla",
        f"initialdir     = {REPO}",
        "executable     = /usr/bin/make",
        f"arguments      = \"data-all QGIS_PYTHON={args.python} TILE_BBOX={args.bbox}\"",
        "should_transfer_files = NO",
        f"request_cpus   = {args.cpus}",
        f"request_memory = {args.memory}",
        f"request_disk   = {args.disk}",
        f"output         = {out}/logs/data.out",
        f"error          = {out}/logs/data.err",
        f"log            = {out}/logs/tiles.log",
    ]
    if args.data_requirements:
        lines.append(f"requirements   = {args.data_requirements}")
    lines.append("queue")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--version", required=True, help="release tag, the version directory in the tile URLs")
    ap.add_argument("--tilesets", default="heavy", help="heavy, light, all, or a comma separated list")
    ap.add_argument("--bbox", help="west,south,east,north (default: TILE_BBOX in the Makefile)")
    ap.add_argument("--zmin", type=int, help="default: TILE_ZMIN in the Makefile")
    ap.add_argument("--zmax", type=int, help="default: TILE_ZMAX in the Makefile")
    ap.add_argument("--cols", type=int, default=4, help="shard columns (default 4)")
    ap.add_argument("--rows", type=int, default=8, help="shard rows (default 8)")
    ap.add_argument("--out", default="condor", help="directory for the DAG, logs and shards")
    ap.add_argument("--python", default="python3", help="interpreter on the workers that can import qgis")
    ap.add_argument("--cpus", type=int, default=1)
    ap.add_argument("--memory", default="8GB")
    ap.add_argument("--disk", default="20GB")
    ap.add_argument("--requirements", help="HTCondor requirements for the render jobs")
    ap.add_argument("--data", action="store_true", help="build the data first, as the first node")
    ap.add_argument("--data-requirements", help="HTCondor requirements for the data job")
    ap.add_argument("--retries", type=int, default=2, help="times to retry a failed node")
    args = ap.parse_args()

    args.bbox = args.bbox or make_var("TILE_BBOX")[0]
    args.zmin = args.zmin if args.zmin is not None else int(make_var("TILE_ZMIN")[0])
    args.zmax = args.zmax if args.zmax is not None else int(make_var("TILE_ZMAX")[0])
    tilesets = pick_tilesets(args.tilesets)
    if not tilesets:
        sys.exit("No tile sets chosen")

    bbox = tuple(float(v) for v in args.bbox.split(","))
    parts = [("all", bbox)] if args.cols == 1 and args.rows == 1 else shard_cuts.shards(bbox, args.cols, args.rows)

    out = args.out if os.path.isabs(args.out) else os.path.join(REPO, args.out)
    for sub in ("logs", "shards"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)

    dag = [
        f"# Tile sets {','.join(tilesets)}, version {args.version}, {len(parts)} shard(s) each.",
        f"# Written by scripts/make_dag.py. Submit with: condor_submit_dag -usedagdir {os.path.join(args.out, 'tiles.dag')}",
        "",
    ]
    if args.data:
        dag += ["JOB data data.sub", f"RETRY data {args.retries}", ""]
    for tileset in tilesets:
        for name, box in parts:
            node = f"{tileset}_{name}"
            dag += [
                f"JOB {node} render.sub",
                f'VARS {node} tileset="{tileset}" shard="{name}" bbox="{",".join(f"{v:.7f}" for v in box)}"',
                f"RETRY {node} {args.retries}",
            ]
            if args.data:
                dag.append(f"PARENT data CHILD {node}")
            dag.append("")

    with open(os.path.join(out, "tiles.dag"), "w") as f:
        f.write("\n".join(dag))
    with open(os.path.join(out, "render.sub"), "w") as f:
        f.write(render_submit(args, out))
    if args.data:
        with open(os.path.join(out, "data.sub"), "w") as f:
            f.write(data_submit(args, out))

    nodes = len(tilesets) * len(parts)
    print(f"Wrote {os.path.join(args.out, 'tiles.dag')}: {nodes} render node(s)"
          f"{' and a data node' if args.data else ''}", file=sys.stderr)
    print(f"Submit it with: condor_submit_dag -usedagdir {shlex.quote(os.path.join(args.out, 'tiles.dag'))}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
