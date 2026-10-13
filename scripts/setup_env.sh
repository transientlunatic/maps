#!/usr/bin/env bash
# Create (or update) the conda environment that builds the tiles, and check that it works.
#
# Usage: scripts/setup_env.sh <environment path>
#
# For an HTCondor build, give a path every worker can see, then pass the same path to
# scripts/make_dag.py with --conda-env. It uses whichever of micromamba, mamba or conda is on the
# PATH (set CONDA_EXE_CMD to choose one).
set -euo pipefail

prefix=${1:?usage: setup_env.sh <environment path>}
here=$(cd "$(dirname "$0")/.." && pwd)

tool=${CONDA_EXE_CMD:-$(command -v micromamba || command -v mamba || command -v conda || true)}
[ -n "$tool" ] || { echo "No micromamba, mamba or conda on the PATH" >&2; exit 1; }

# micromamba spells these `create` and `install`; conda and mamba use `env create` and `env update`
case "$(basename "$tool")" in
  micromamba*) create=(create -y); update=(install -y) ;;
  *)           create=(env create -y); update=(env update --prune) ;;
esac
if [ -d "$prefix/conda-meta" ]; then
  "$tool" "${update[@]}" -p "$prefix" -f "$here/environment.yml"
else
  "$tool" "${create[@]}" -p "$prefix" -f "$here/environment.yml"
fi

run() { "$tool" run -p "$prefix" "$@"; }
run "$here/scripts/install_fonts.sh"

# Check the parts the build needs: PyQGIS and its processing plugin, GDAL's OSM driver, Lato
QT_QPA_PLATFORM=offscreen run python -c "
import qgis.core, osgeo.gdal, numpy, scipy, shapely, PIL
print('QGIS', qgis.core.Qgis.version(), '| GDAL', osgeo.gdal.__version__)"
formats=$(run ogr2ogr --formats)
if grep -q ' OSM ' <<<"$formats"; then echo "GDAL OSM driver: ok"; else echo "GDAL OSM driver: NOT found" >&2; fi
families=$(run fc-list : family)
if grep -qi '^lato' <<<"$families"; then echo "Lato font: ok"; else echo "Lato font: NOT found" >&2; fi
echo "Environment ready: $prefix"
