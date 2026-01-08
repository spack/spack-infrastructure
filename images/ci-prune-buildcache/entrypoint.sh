#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# Clone spack
echo "Cloning spack..."
git clone --depth 1 https://github.com/spack/spack.git
echo "Cloning spack...done"

# Configure spack
echo "Configuring spack shell..."
. /app/spack/share/spack/setup-env.sh
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
echo "Fetching keep hashes from GitLab pipelines..."
python3 ${SCRIPT_DIR}/fetch_keeplists.py \
  --gitlab-url "${GITLAB_URL}" \
  --project "${GITLAB_PROJECT}" \
  --ref "${PRUNE_REF}" \
  --since-days "${PRUNE_SINCE_DAYS}"
echo "Keep lists created with $(wc -l < develop_keeplist.txt) total hashes"

# Prune each buildcache
for file in *_keeplist.txt; do
  stack="${file%_keeplist.txt}"
  echo "Start pruning process for $stack buildcache"
  keeplist_file="${stack}_keeplist.txt"

  echo "Contents of $keeplist_file:"
  cat $keeplist_file
  echo ""

  # Add the mirror
  echo "Adding mirror $stack..."
  if [[ "$stack" == "develop" ]]; then
    spack mirror add "${stack}" "${BUILDCACHE_URL}"
  else
    spack mirror add "${stack}" "${BUILDCACHE_URL}/${stack}"
  fi
  echo "Adding mirror $stack... done!"

  # Run pruning with keeplist
  echo "Running buildcache prune for $stack..."
  spack --debug python prune.py --mirror "${stack}" --keeplist "${keeplist_file}"
  echo "Running buildcache prune for $stack... done!"

  # Update the mirror index
  echo "Updating mirror index for $stack..."
  spack buildcache update-index "${stack}"
  echo "Updating mirror index for $stack... done!"
  echo ""

done

echo "Pruning complete!!!"
