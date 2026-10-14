#!/usr/bin/env bash
# Publish built tile shards to a tile server.
#
# Usage: scripts/publish_tiles.sh <directory of shard .tar.gz files> <destination>
#
# <destination> is anything rsync accepts: a local directory, or user@host:/path/to/tiles/.
# For a remote one, set RSYNC_RSH to the ssh command to use (for example
# RSYNC_RSH="ssh -i key"). Every shard archive holds <tileset>/<version>/..., so they are
# unpacked into one tree, and that tree is copied to the destination. Nothing is deleted
# there: a release adds a new version directory next to the older ones.
set -euo pipefail

assets=${1:?usage: publish_tiles.sh <shard directory> <destination>}
dest=${2:?usage: publish_tiles.sh <shard directory> <destination>}

shopt -s nullglob
archives=("$assets"/*.tar.gz)
if [ ${#archives[@]} -eq 0 ]; then
  echo "No shard archives in $assets" >&2
  exit 1
fi

work=$(mktemp -d)
for archive in "${archives[@]}"; do
  tar -xzf "$archive" -C "$work"
done

# The loch names and the hills are fetched by the browser from another origin (the blog), so the
# server must allow that and serve them with the right type. The rule lives in each of their
# directories, so it does not touch whatever else the server's root holds.
for dir in waternames hills; do
  if [ -d "$work/$dir" ]; then
    cat > "$work/$dir/.htaccess" <<'HT'
<IfModule mod_headers.c>
  Header set Access-Control-Allow-Origin "*"
</IfModule>
AddType application/geo+json .geojson
AddType application/json .json
<IfModule mod_deflate.c>
  AddOutputFilterByType DEFLATE application/geo+json application/json
</IfModule>
HT
  fi
done

echo "Publishing $(find "$work" -type f | wc -l) files to $dest"
rsync -rt --info=stats1 "$work"/ "$dest"
