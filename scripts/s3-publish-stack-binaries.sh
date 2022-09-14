#!/bin/bash
set -e

# Script used to brute force the removal of duplicate buildcache entries in
# the top level buildcache. This cleans up errors introduced by a race condition
# when updating the .spack files and the .sig files. Ideally, this script should
# only be run once (8 September 2022).

if [[ "$1" == "-h" ]]; then
  echo ""
  echo "Usage:"
  echo ""
  echo "    Print this help message:"
  echo ""
  echo "        ${0//*\//} -h"
  echo ""
  echo "    Update common buildcache for a <commit_ref> (default: 'develop')"
  echo ""
  echo "        ${0//*\//} <commit_ref>"
  echo ""
  echo "Set environment variables with AWS access secrets"
  echo ""
  echo "    export AWS_ACCESS_KEY_ID=<KEY_ID>"
  echo "    export AWS_SECRET_ACCESS_KEY=<ACCESS_KEY>"
  echo ""
  echo "Pre-requisite software:"
  echo ""
  echo "    AWS CLI (aws)"
  echo "    Spack (spack)"
  echo ""

  exit 0
fi

# Check that access keys are present
meets_req=1
if [[ -z $AWS_ACCESS_KEY_ID ]]; then
  echo "Missing AWS_ACCESS_KEY_ID"
  meets_req=0
fi
if [[ -z $AWS_SECRET_ACCESS_KEY ]]; then
  echo "Missing AWS_SECRET_ACCESS_KEY"
  meets_req=0
fi

if [[ ! $(command -v spack) ]]; then
  echo "Cannout find spack"
  meets_req=0
fi

if [[ ! $(command -v aws) ]]; then
  echo "Cannout find aws"
  meets_req=0
fi

if [[ $meets_req == 0 ]]; then
  exit 1
fi

set -x

# Setup the binaries to sync
if [[ ! -z $1 ]]; then
  commit_ref_name=$1
else
  commit_ref_name=develop
fi

# List of stacks to copy
stacks=(
  e4s
  e4s-oneapi
  build_systems
  radiuss
  radiuss-aws
  radiuss-aws-aarch64
  data-vis-sdk
  aws-ahug
  aws-ahug-aarch64
  aws-isc
  aws-isc-aarch64
  tutorial
)

exclude_stack_mirrors=
for stack in "${stacks[@]}"; do
  exclude_stack_mirrors="--exclude *${stack}* ${exclude_stack_mirrors}"
done

# Remove all of the old binaries
aws s3 rm "s3://spack-binaries/${commit_ref_name}" --recursive --exclude *pgp* ${exclude_stack_mirrors}
# Copy the binaries from the stack caches with their corresponding sig files
for stack in "${stacks[@]}"; do
  echo "copy: $stack"
  echo "aws s3 cp 's3://spack-binaries/${commit_ref_name}/${stack}' 's3://spack-binaries/${commit_ref_name}' --recursive --exclude *index.json* --exclude *pgp*"
  aws s3 cp "s3://spack-binaries/${commit_ref_name}/${stack}" "s3://spack-binaries/${commit_ref_name}" --recursive --exclude *index.json* --exclude *pgp*
done
spack buildcache update-index --mirror-url "s3://spack-binaries/${commit_ref_name}"
