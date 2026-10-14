# Sourced by scripts/condor_render.sh and scripts/condor_make.sh: activates the conda environment
# at CONDA_ENV_PATH, so the job runs with its PATH and the activation scripts (GDAL, PROJ, QGIS)
# set. Without CONDA_ENV_PATH it does nothing and the job runs in the environment HTCondor gives it.
#
# An HTCondor job starts with a minimal PATH, so `conda` is normally not found in it. The
# environment is therefore activated by hand, which needs no conda program: the environment's bin
# directory goes on the PATH, CONDA_PREFIX is set and the scripts in etc/conda/activate.d run, which
# is what `conda activate` does. If CONDA_TOOL names a conda or micromamba program that the job can
# run (an absolute path, as scripts/make_dag.py writes it), that is used instead.
#
# (`micromamba run` and `conda run` fail inside an HTCondor job ("Invalid argument"), so they are
# not used.)
if [ -n "${CONDA_ENV_PATH:-}" ]; then
  if [ ! -d "$CONDA_ENV_PATH/conda-meta" ]; then
    echo "condor_env.sh: $CONDA_ENV_PATH is not a conda environment (create it with scripts/setup_env.sh)" >&2
    exit 1
  fi
  # The activation scripts read variables that may be unset
  set +u
  tool=${CONDA_TOOL:-}
  if [ -n "$tool" ] && command -v "$tool" >/dev/null 2>&1; then
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
  else
    [ -n "$tool" ] && echo "condor_env.sh: $tool not found; activating $CONDA_ENV_PATH directly" >&2
    export CONDA_PREFIX="$CONDA_ENV_PATH"
    export CONDA_DEFAULT_ENV="$CONDA_ENV_PATH"
    export PATH="$CONDA_ENV_PATH/bin:$PATH"
    for script in "$CONDA_ENV_PATH"/etc/conda/activate.d/*.sh; do
      [ -r "$script" ] && . "$script"
    done
  fi
  set -u
fi
