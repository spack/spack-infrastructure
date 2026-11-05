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
# update_views.py only carries over view entries CI pushed after this point
run_started=$(date +%s)
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
  --snapshots-since "2 months ago" # Keep safely below the 90-day GitLab artifact expiry (default_artifacts_expire_in)
echo "Keep lists created with $(wc -l < ${keeplist_file}) total hashes"

# Add the top-level mirror
mirror="develop"
echo "Adding mirror ${mirror}..."
spack mirror add "${mirror}" "${buildcache_url}"
echo "Adding mirror ${mirror}... done!"

# Regenerate each stack's view index before pruning, so that no view index still
# references specs that are about to be deleted from the mirror. update_views.py
# lists the mirror once and reuses that listing for every view.
stack_files=()
for stack_file in stacks/*.txt; do
  [[ -f "$stack_file" ]] || continue
  stack_files+=("$stack_file")
done

# No stacks means no successful generate jobs in the window; pruning with that
# keeplist would delete nearly everything, so stop here instead.
if (( ${#stack_files[@]} == 0 )); then
  echo "No stacks found in the last ${since_days} days; aborting to avoid over-pruning" >&2
  exit 1
fi

echo "Updating view indices for ${#stack_files[@]} stacks..."
spack --debug python update_views.py --mirror "${mirror}" --keeplist "${keeplist_file}" --run-started "${run_started}" \
  "${dry_run_args[@]}" "${stack_files[@]}"
echo "Updating view indices for ${#stack_files[@]} stacks... done!"
echo ""

echo "Start pruning process for buildcache"
# Store keeplist in S3 for potential future debugging
aws s3 cp ${keeplist_file} s3://spack-logs/pruning/${now}/${keeplist_file}

# Run pruning with keeplist (prune.py handles --dry-run itself)
echo "Running buildcache prune for ${mirror}..."
spack --debug python prune.py --mirror "${mirror}" --keeplist "${keeplist_file}" "${dry_run_args[@]}"
echo "Running buildcache prune for ${mirror}... done!"

# Update the mirror index (nothing was deleted on a dry run, so leave the index alone)
echo "Updating mirror index for ${mirror}..."
maybe spack buildcache update-index "${mirror}"
echo "Updating mirror index for ${mirror}... done!"
echo ""

echo "Pruning PR Mirrors"

python3 ${SCRIPT_DIR}/prune_pr_mirrors.py "${dry_run_args[@]}" \
  -r "spack/spack" \
  -r "spack/spack-packages" \
  -b "${PR_BUILDCACHE_BUCKET}"

echo "Pruning complete!!!"
