#!/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

if [ -z $1 ]; then
  now=$(date --iso-8601)
else
  now=$1
fi

snapshot_dir="$PWD/snapshot-${now}"

# Use the $SPACKROOT/etc/ dir for configs
SPACK_DISABLE_LOCAL_CONFIG=1

# Get spack
git clone --depth 1 --branch develop https://github.com/spack/spack.git

function add_mirrors() {
  # Add the mirrors
  cat ${snapshot_dir}/config | jq '.stacks | keys[] as $k | "./spack/bin/spack mirror add \($k) \(.[$k])"' | sed 's/"//g' | bash
}

function update_index() {
  # Update the mirror indices
  cat ${snapshot_dir}/config | jq '.stacks | keys[] as $k | "./spack/bin/spack buildcache update-index \($k)"' | sed 's/"//g' | bash
}

# Perform direct pruning
python3 ${SCRIPT_DIR}/ci_buildcache_prune.py --start-date ${now} --snapshot-dir ${snapshot_dir} --output-dir ./out --direct

# Add the mirrors detected by direct pruning
add_mirrors

# Perform orphan pruning
python3 ${SCRIPT_DIR}/ci_buildcache_prune.py --start-date ${now} --snapshot-dir ${snapshot_dir} --output-dir ./out --orphaned --config ${snapshot_dir}/config

update_index
