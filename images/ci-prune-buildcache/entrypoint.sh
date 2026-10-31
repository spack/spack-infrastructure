#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# Configure spack
echo "Configuring spack shell..."
. ${SPACK_ROOT:-/app/spack}/share/spack/setup-env.sh
echo "Configuring spack shell...done"

# Use the $SPACKROOT/etc/ dir for configs
export SPACK_DISABLE_LOCAL_CONFIG=1

# Load the environment configs
gitlab_url=${GITLAB_URL:-"https://gitlab.spack.io"}
readonly gitlab_url
gitlab_project=${GITLAB_PROJECT:-"spack/spack-packages"}
readonly gitlab_project
buildcache_url=${BUILDCACHE_URL:-"s3://spack-binaries/develop/"}
readonly buildcache_url
ref="${PRUNE_REF:-develop}"
readonly ref
since_days="${PRUNE_SINCE_DAYS:-14}"
readonly since_days

# Environment variables from cronjob
echo "Configuration:"
echo "  GITLAB_URL: ${gitlab_url}"
echo "  GITLAB_PROJECT: ${gitlab_project}"
echo "  BUILDCACHE_URL: ${buildcache_url}"
echo "  PRUNE_REF: ${ref}"
echo "  PRUNE_SINCE_DAYS: ${since_days}"
echo "  PRUNE_DRY_RUN: ${PRUNE_DRY_RUN:=false}"

readonly PRUNE_DRY_RUN

maybe() {
  if [[ "${PRUNE_DRY_RUN}" == "true" ]]; then
    echo "$@"
  else
    "$@"
  fi
}

dry_run_args=()
if [[ "${PRUNE_DRY_RUN}" == "true" ]]; then
  dry_run_args=(--dry-run)
fi

# Calculate date range
now=$(date --iso-8601)
since_date=$(date --iso-8601 -d "${since_days} days ago")
echo "Pruning binaries older than: ${since_date}"

# Create keep list from GitLab pipelines
keeplist_file="keeplist.txt"
echo "Fetching keep hashes from GitLab pipelines..."
python3 ${SCRIPT_DIR}/fetch_keeplists.py \
  --gitlab-url "${gitlab_url}" \
  --project "${gitlab_project}" \
  --ref "${ref}" \
  --pipelines-since "${since_days} days ago" \
  --snapshots-since "2 months ago" # This is the max age of artifacts, make this shorted if needed
echo "Keep lists created with $(wc -l < ${keeplist_file}) total hashes"

prune_stack() {
  # Pruning a stack with views is effectively generating a new index for the view.
  # Use the concatenated environment created by fetch_keeplists.txt to update the view index.
  env_dir=$1
  stack=$(basename ${env_dir})
  # Update the mirror index (nothing was deleted on a dry run, so leave the index alone)
  echo "Updating mirror index for $stack..."
  maybe spack buildcache update-index --force --view "${stack}" "${buildcache_url}" "${env_dir}"
  echo "Updating mirror index for $stack... done!"
  echo ""
}

# Prune each stack-specific buildcache.
for env_dir in stacks/*; do
  prune_stack "$env_dir"
done

echo "Start pruning process for buildcache"
# Store keeplist in S3 for potential future debugging
aws s3 cp ${keeplist_file} s3://spack-logs/pruning/${now}/${keeplist_file}
# Run pruning with keeplist
echo "Running buildcache prune for $stack..."
maybe spack --debug python prune.py --mirror "${stack}" --keeplist "${keeplist_file}" "${dry_run_args[@]}"
echo "Running buildcache prune for $stack... done!"

echo "Pruning PR Mirrors"

maybe python3 ${SCRIPT_DIR}/prune_pr_mirrors.py "${dry_run_args[@]}" \
  -r "spack/spack" \
  -r "spack/spack-packages" \
  -b "${PR_BUILDCACHE_BUCKET}"

echo "Pruning complete!!!"
