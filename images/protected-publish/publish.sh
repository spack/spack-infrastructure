#!/bin/bash

#
# To run:
#
#     $ source /data/scott/Documents/spack/new_protected_publish/script/venv/bin/activate
#     $ source <path-to>/spack/share/spack/setup-env.sh
#     $ ./publish.sh
#

export AWS_PROFILE=spack-llnl
SPACK_REF="develop-2023-06-25"
WORKING_DIR="/data/scott/Documents/spack/new_protected_publish/working_dir/${SPACK_REF}"
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
SRC_MIRROR_ROOT="s3://spack-binaries/${SPACK_REF}"
DEST_MIRROR=${SRC_MIRROR_ROOT}
MIRROR_REGEX="mirror:[[:space:]]+s3://spack-binaries/develop/([^[:space:]]+)"

# Download the public key and trust it, also copy it to the root
mkdir -p /tmp/temp_gpg_home && chmod 700 /tmp/temp_gpg_home
curl -fLsS https://spack.github.io/keys/spack-public-binary-key.pub -o /tmp/spack-public-binary-key.pub
aws s3 cp /tmp/spack-public-binary-key.pub "${DEST_MIRROR}/build_cache/_pgp/spack-public-binary-key.pub"
export SPACK_GNUPGHOME=/tmp/temp_gpg_home
spack gpg trust /tmp/spack-public-binary-key.pub

# Download artifacts for each stack, we need the spack.lock and spack.yaml
mapfile -t lock_paths < <( python "${SCRIPT_DIR}/download_artifacts.py" "${SPACK_REF}" "--working-dir" "${WORKING_DIR}")

# Copy each stack's binaries to the root
for lock_file in "${lock_paths[@]}"
do
    CONCRETE_ENV_DIR=$(dirname $lock_file)
    SPACK_YAML_PATH="${CONCRETE_ENV_DIR}/spack.yaml"
    SPACK_YAML_CONTENTS="$(< ${SPACK_YAML_PATH})"

    if [[ $SPACK_YAML_CONTENTS =~ $MIRROR_REGEX ]]
    then
        SPACK_STACK_NAME="${BASH_REMATCH[1]}"
        SRC_MIRROR="${SRC_MIRROR_ROOT}/${SPACK_STACK_NAME}"
        echo "Sync $SPACK_STACK_NAME FROM ${SRC_MIRROR} TO ${DEST_MIRROR}"
        STACK_ENV_DIR="${WORKING_DIR}/envs/${SPACK_STACK_NAME}"
        mkdir -p "${STACK_ENV_DIR}"

        spack env create --without-view --dir "${STACK_ENV_DIR}"
        cp $lock_file "${STACK_ENV_DIR}/"
        spack env activate "${STACK_ENV_DIR}"
        spack env status

        time spack buildcache sync --only-verified "${SRC_MIRROR}" "${DEST_MIRROR}"

        spack env deactivate
    else
        echo "Skip publishing specs from ${$lock_file}"
    fi
done

# Update the buildcache index at the root
echo "Updating the buildcache index at ${DEST_MIRROR}"
time spack buildcache update-index --keys "${DEST_MIRROR}"

# Clean up
rm -rf /tmp/temp_gpg_home
rm /tmp/spack-public-binary-key.pub
