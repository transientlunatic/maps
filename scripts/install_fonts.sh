#!/usr/bin/env bash
# Install the Lato font, which the map's names are drawn in and which is not on conda-forge.
#
# Usage: scripts/install_fonts.sh [directory]
#
# The default directory is the active conda environment's fonts/ directory ($CONDA_PREFIX/fonts,
# which the environment's fontconfig reads), or ~/.fonts outside conda. Lato comes from the Google
# Fonts repository and is licensed under the SIL Open Font License. Without it QGIS silently draws
# the names in a fallback font.
set -euo pipefail

dest=${1:-${CONDA_PREFIX:+$CONDA_PREFIX/fonts}}
dest=${dest:-$HOME/.fonts}
mkdir -p "$dest"

base=https://raw.githubusercontent.com/google/fonts/main/ofl/lato
for style in Regular Italic Bold BoldItalic Light LightItalic; do
  file="$dest/Lato-$style.ttf"
  if [ ! -s "$file" ]; then
    curl -fsSL -o "$file.part" "$base/Lato-$style.ttf"
    mv "$file.part" "$file"
  fi
done
command -v fc-cache >/dev/null && fc-cache -f "$dest"
echo "Installed Lato in $dest"
