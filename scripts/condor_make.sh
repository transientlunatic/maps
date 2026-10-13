#!/usr/bin/env bash
# Run `make` with the given arguments, inside the conda environment if CONDA_ENV_PATH is set.
#
# Usage: scripts/condor_make.sh <make arguments>
#
# This is what the data node of the DAG from scripts/make_dag.py runs. CONDA_ENV_PATH and CONDA_TOOL
# name the environment and the program that activates it (see scripts/condor_env.sh; make_dag.py
# sets them from --conda-env and --conda-exe). Without them, make runs in the environment HTCondor
# gives the job.
set -euo pipefail
# shellcheck source=scripts/condor_env.sh
. "$(dirname "$0")/condor_env.sh"
exec make "$@"
