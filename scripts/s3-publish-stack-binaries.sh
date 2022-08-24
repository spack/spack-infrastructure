#!/bin/bash
set -x
set -e

# Check that access keys are present
has_access_key=1
if [[ -z $AWS_ACCESS_KEY_ID ]]; then
  echo "Missing AWS_ACCESS_KEY_ID"
  has_access_key=0
fi
if [[ -z $AWS_SECRET_ACCESS_KEY ]]; then
  echo "Missing AWS_SECRET_ACCESS_KEY"
  has_access_key=0
fi
if [[ $has_access_key == 0 ]]; then
  exit 1
fi

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

# Remove all of the old binaries
aws s3 rm "s3://spack-binaries/${commit_ref_name}" --recursive --exclude *pgp*
# Copy the binaries from the stack caches with their corresponding sig files
for stack in "${stacks[@]}"; do
  echo "copy: $stack"
  echo "aws s3 cp 's3://spack-binaries/${commit_ref_name}/${stack}' 's3://spack-binaries/${commit_ref_name}' --recursive --exclude *index.json* --exclude *pgp*"
  aws s3 cp "s3://spack-binaries/${commit_ref_name}/${stack}" "s3://spack-binaries/${commit_ref_name}" --recursive --exclude *index.json* --exclude *pgp*
done
