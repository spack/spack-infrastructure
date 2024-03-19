#!/usr/bin/env bash

###
### Requires some python packages, which could be installed with:
###
###     $ python3.10 -m venv venv
###     $ source venv/bin/activate
###     $ pip install --upgrade pip
###     $ pip install -r requirements.txt
###
### To run, first activate the environment:
###
###     $ source venv/bin/activate
###
### Then set up AWS credentials:
###
###     $ export AWS_PROFILE=boop...
###
### or:
###
###     $ export AWS_ACCESS_KEY_ID=blip...
###     $ export AWS_SECRET_ACCESS_KEY=blap...
###
### Then set gitlab token:
###
###     $ export GITLAB_PRIVATE_TOKEN=bloop...
###
### And finally, run the script:
###
###     # ./prune.sh
###

# Agree on the now for all pruning
NOW="$(date --utc +%Y-%m-%dT%H:%M:%SZ)"

OUTPUT_DIRECTORY=$1
mkdir -p ${OUTPUT_DIRECTORY}
if [ -z "$OUTPUT_DIRECTORY" ] ; then
    echo "Error: output directory required."
    exit 1
fi

BUCKET_LISTING="${OUTPUT_DIRECTORY}/develop_bucket_contents.txt"
ARTIFACTS_DIR="${OUTPUT_DIRECTORY}/jobs_artifacts"
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

echo "Generating bucket listing"
aws s3 ls --recursive s3://spack-binaries/develop/ > ${BUCKET_LISTING} &

echo "Retrieving artifacts for pipeline generation jobs"
python "${SCRIPT_DIR}/get_pipelines.py" \
  https://gitlab.spack.io \
  spack/spack \
  --artifacts-dir ${ARTIFACTS_DIR} \
  --updated-before ${NOW} &

wait

echo "Generating pruning lists"
python "${SCRIPT_DIR}/generate_pruning_lists.py" \
  ${BUCKET_LISTING} \
  ${ARTIFACTS_DIR} \
  --output-dir ${OUTPUT_DIRECTORY}
  --updated-before ${NOW}
