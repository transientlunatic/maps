# Sourced by scripts/condor_render.sh and scripts/condor_make.sh: activates the conda environment
# at CONDA_ENV_PATH with the program CONDA_TOOL (conda, micromamba or mamba 2; default conda), so
# the job runs with its PATH and the activation scripts (GDAL, PROJ, QGIS) set. Without
# CONDA_ENV_PATH it does nothing and the job runs in the environment HTCondor gives it.
#
# This uses the shell hook rather than `conda run` / `micromamba run`, because `micromamba run`
# fails inside an HTCondor job ("Invalid argument") while activation works.
if [ -n "${CONDA_ENV_PATH:-}" ]; then
  tool=${CONDA_TOOL:-conda}
  # The activation scripts read variables that may be unset
  set +u
  case $(basename "$tool") in
    conda*)
      eval "$("$tool" shell.bash hook)"
      conda activate "$CONDA_ENV_PATH"
      ;;
    *)
      eval "$("$tool" shell hook -s bash)"
      "$(basename "$tool")" activate "$CONDA_ENV_PATH"
      ;;
  esac
  set -u
fi
