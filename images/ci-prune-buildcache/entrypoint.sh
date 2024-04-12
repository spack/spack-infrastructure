#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

now=${1:-$(date --iso-8601)}

snapshot_dir="$PWD/snapshot-${now}"

# Configure spack
if [ ! -d spack ]; then
  git clone --depth 1 --branch develop https://github.com/spack/spack.git
fi
. ./spack/share/spack/setup-env.sh

# Use the $SPACKROOT/etc/ dir for configs
export SPACK_DISABLE_LOCAL_CONFIG=1

function add_mirrors() {
  # Add the mirrors
  # Don't fail if they are already there... || true may be too heavy haned but I don't think there is any other reason for this command to fail if the
  cat ${snapshot_dir}/config | jq '.stacks | keys[] as $k | "echo Adding mirror for \($k) \(.[$k]) && spack mirror add \($k) \(.[$k]) || true"' | sed 's/"//g' | bash
}

function update_index() {
  # Update the mirror indices
  cat ${snapshot_dir}/config | jq '.stacks | keys[] as $k | "echo Updating index for \($k); spack buildcache update-index \($k)"' | sed 's/"//g' | bash
}

# Perform direct pruning
python3 ${SCRIPT_DIR}/ci_buildcache_prune.py --start-date ${now} --snapshot-dir ${snapshot_dir} --output-dir ./out --direct --delete

# Add the mirrors detected by direct pruning
add_mirrors

# Perform orphan pruning
python3 ${SCRIPT_DIR}/ci_buildcache_prune.py --start-date ${now} --snapshot-dir ${snapshot_dir} --output-dir ./out --orphaned --config ${snapshot_dir}/config --delete

update_index
