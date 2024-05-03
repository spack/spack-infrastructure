#!/bin/bash

export WORK_DIR="/data/scott/Documents/spack/two_protected_publish"
export FILES_DIR="${WORK_DIR}/files"
export TOP_LEVEL_MIRROR_PREFIX="s3://spack-binaries/develop/build_cache"
export ALL_MIRRORS_PREFIX="s3://spack-binaries/develop/"

mkdir -p ${FILES_DIR}

# List the top level only
aws s3 ls --recursive ${TOP_LEVEL_MIRROR_PREFIX} > "${FILES_DIR}/top_level_listing.txt"

# List everything under the top level (includes stacks)
aws s3 ls --recursive ${ALL_MIRRORS_PREFIX} > "${FILES_DIR}/full_listing.txt"

python find_missing.py --full "${FILES_DIR}/full_listing.txt"

# That should have written two parallel files, one containing meta, one archives

while IFS= read -r meta_url && IFS= read -r archive_url <&3; do
  echo "meta: $meta_url"
  echo "archive: $archive_url"
done < "${FILES_DIR}/meta_urls.txt" 3< "${FILES_DIR}/archive_urls.txt"

