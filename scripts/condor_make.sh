#!/usr/bin/env bash
# Run `make` with the given arguments, inside the conda environment if CONDA_RUN is set.
#
# Usage: scripts/condor_make.sh <make arguments>
#
# This is what the data node of the DAG from scripts/make_dag.py runs. CONDA_RUN is a command
# prefix such as "conda run --no-capture-output -p /shared/path/scotland-maps" (make_dag.py sets it
# from --conda-env). Without it, make runs in the environment HTCondor gives the job.
set -euo pipefail
# shellcheck disable=SC2086  # CONDA_RUN is a command prefix and is split on purpose
exec ${CONDA_RUN:-} make "$@"
