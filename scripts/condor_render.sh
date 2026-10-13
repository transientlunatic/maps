#!/usr/bin/env bash
# Render one tile set for one shard and pack it as <tileset>-<version>-<shard>.tar.gz.
#
# Usage: scripts/condor_render.sh <tileset> <shard> <west,south,east,north> <version> <zmin> <zmax> <out dir>
#
# This is what each node of the DAG from scripts/make_dag.py runs (HTCondor starts it in the
# repository). It does the same as one `tiles` job in the GitHub workflow: `make render-<tileset>`
# for the shard, then a tar.gz with <tileset>/<version>/... in it, which scripts/publish_tiles.sh
# unpacks. It renders into a directory of its own, so shards never touch each other's files, and
# it only moves the archive into place when it is complete, so a half-finished one is never seen.
# Set QGIS_PYTHON to the interpreter that can `import qgis` (default python3).
set -euo pipefail

tileset=${1:?usage: condor_render.sh <tileset> <shard> <bbox> <version> <zmin> <zmax> <out dir>}
shard=${2:?}
bbox=${3:?}
version=${4:?}
zmin=${5:?}
zmax=${6:?}
out=${7:?}

mkdir -p "$out/shards"
work=$(mktemp -d "${TMPDIR:-/tmp}/tiles-${tileset}-${shard}.XXXXXX")
trap 'rm -rf "$work"' EXIT

make render-"$tileset" \
  QGIS_PYTHON="${QGIS_PYTHON:-python3}" TILE_DIR="$work" TILE_VERSION="$version" \
  TILE_BBOX="$bbox" TILE_ZMIN="$zmin" TILE_ZMAX="$zmax"

archive="$out/shards/${tileset}-${version}-${shard}.tar.gz"
# A shard that has no tiles (open sea, say) leaves no directory; make an empty archive of one
if [ ! -d "$work/$tileset" ]; then
  mkdir -p "$work/$tileset/$version"
fi
tar -C "$work" -czf "$archive.part" "$tileset"
mv "$archive.part" "$archive"
du -sh "$archive"
