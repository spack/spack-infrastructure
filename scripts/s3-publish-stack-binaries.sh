#!/bin/bash
set -e

function print_help()
{
  echo ""
  echo "Usage:"
  echo ""
  echo "    Print this help message:"
  echo ""
  echo "        ${0//*\//} -h"
  echo ""
  echo "    Update common buildcache for a <commit_ref> (default: 'develop')"
  echo ""
  echo "        ${0//*\//} --ref <commit_ref>"
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
}

# Script used to brute force the removal of duplicate buildcache entries in
# the top level buildcache. This cleans up errors introduced by a race condition
# when updating the .spack files and the .sig files. Ideally, this script should
# only be run once (8 September 2022).

local sargs='h?b:fn'
local largs='help,bucket:,override,dryrun,ref'
parsed=$(getopt --options ${sargs} --longoptions ${largs} --name "s3-publish-binaries" -- "$@")
eval set -- "$parsed"

bucket="spack-binaries"
commit_ref_name="develop"
dryrun=
while true; do
  case $1 in
    -h|--help) print_help; exit 0;;
    -b|--bucket) bucket="$2"; shift 2;;
    -f|--override) override=1; shift;;
    -n|--dryrun) dryrun="--dryrun"; shift;;
    --ref) commit_ref_name="$2"; shift 2;;
    --) break;;
    *) exit 1;;
  esac
done

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

# List of stacks to copy
stacks=(
  e4s
  e4s-oneapi
  e4s-power
  build_systems
  radiuss
  radiuss-aws
  radiuss-aws-aarch64
  data-vis-sdk
  aws-ahug
  aws-ahug-aarch64
  aws-isc
  aws-isc-aarch64
  aws-pcluster-icelake
  aws-pcluster-skylake
  aws-pcluster-neoverse_n1
  aws-pcluster-neoverse_v1
  tutorial
  deprecated
  ml-darwin-aarch64-mps
  ml-linux-x86_64-cpu
  ml-linux-x86_64-cude
  ml-linux-x86_64-rocm
)


if [[ ! -z $override ]]; then
  # Remove all of the old binaries
  aws s3 rm "s3://${bucket}/${commit_ref_name}/build_cache" --recursive --exclude *pgp*
fi

# Copy the binaries from the stack caches with their corresponding sig files
for stack in "${stacks[@]}"; do
  echo "copy: $stack"
  echo "aws s3 cp 's3://spack-binaries/${commit_ref_name}/${stack}' 's3://spack-binaries/${commit_ref_name}' --recursive --exclude *index.json* --exclude *pgp*"
  aws s3 cp "s3://spack-binaries/${commit_ref_name}/${stack}" "s3://spack-binaries/${commit_ref_name}" --recursive --exclude *index.json* --exclude *pgp* ${dryrun}
done

if [[ -z ${dryrun} ]]; then
  spack buildcache update-index --mirror-url "s3://spack-binaries/${commit_ref_name}"
fi
