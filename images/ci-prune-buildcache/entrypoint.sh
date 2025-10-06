#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

echo "Input: $@"

# Clone spack
echo "Cloning spack..."
git clone --depth 1 --branch direct-pruning https://github.com/mvandenburgh/spack.git
echo "Cloning spack...done"

# Configure spack
echo "Configuring spack shell..."
. /opt/spack/share/spack/setup-env.sh
echo "Configuring spack shell...done"

# Use the $SPACKROOT/etc/ dir for configs
export SPACK_DISABLE_LOCAL_CONFIG=1

# Environment variables from cronjob
echo "Configuration:"
echo "  GITLAB_URL: ${GITLAB_URL}"
echo "  GITLAB_PROJECT: ${GITLAB_PROJECT}"
echo "  BUILDCACHE_URL: ${BUILDCACHE_URL}"
echo "  PRUNE_REF: ${PRUNE_REF}"
echo "  PRUNE_SINCE_DAYS: ${PRUNE_SINCE_DAYS}"

# Calculate date range
now=$(date --iso-8601)
since_date=$(date --iso-8601 -d "${PRUNE_SINCE_DAYS} days ago")
echo "Pruning binaries older than: ${since_date}"

# Create keep list from GitLab pipelines
keeplist_file="keeplist.txt"
echo "Fetching keep hashes from GitLab pipelines..."
python3 ${SCRIPT_DIR}/fetch_keeplist.py \
  --gitlab-url "${GITLAB_URL}" \
  --project "${GITLAB_PROJECT}" \
  --ref "${PRUNE_REF}" \
  --since-days "${PRUNE_SINCE_DAYS}" \
  --output "${keeplist_file}"
echo "Keep list created with $(wc -l < ${keeplist_file}) hashes"

# Add the mirror
echo "Adding mirror..."
spack mirror add mirror-to-prune "${BUILDCACHE_URL}"
echo "Adding mirror...done"

# Run pruning with keeplist
echo "Running buildcache prune with keeplist..."
spack python prune.py --mirror mirror-to-prune --keeplist "${keeplist_file}"
echo "Running buildcache prune...done"

# Update the mirror index
echo "Updating mirror index..."
spack buildcache update-index mirror-to-prune
echo "Updating mirror index...done"

echo ""
echo "Pruning complete"
