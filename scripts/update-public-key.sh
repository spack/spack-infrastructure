#!/usr/bin/env bash

set -Eeuo pipefail

PUBLIC_KEY_ID=2C8DD3224EF3573A42BD221FA8E0CA3C1C2ADA2F
PUBLIC_KEY_FILE=${PUBLIC_KEY_ID}.pub

# Pre-flight checks
command -v aws >/dev/null 2>&1 || { echo >&2 "Command 'aws' not found. Aborting."; exit 1; }
command -v gpg > /dev/null 2>&1 || { echo >&2 "COmmand 'gpg' not found. Aborting."; exit 1; }
command -v parallel >/dev/null 2>&1 || { echo >&2 "Command 'parallel' not found. Aborting."; exit 1; }


[ "$#" -eq 1 ] || { echo >&2 "One argument required, $# provided."; exit 1; }

[ ! -f "$PUBLIC_KEY_FILE" ] && { echo >&2 "$PUBLIC_KEY_FILE not present. Aborting."; exit 1; }


# Seach the file and make sure the first key id found is the expected key id.
FOUND_KEY_ID=$(gpg --with-colons --show-keys $PUBLIC_KEY_FILE | grep "^fpr" | head -n1 | cut -f10 -d":")
if [[ "$FOUND_KEY_ID" != "$PUBLIC_KEY_ID" ]]; then
    echo >&2 "Key id: ${FOUND_KEY_ID} from ${PUBLIC_KEY_FILE} did not match expected key id: ${PUBLIC_KEY_ID}"
    exit 1
fi


# Note: "aws s3 ls --recursive" is a little wonky. If we do a recursive ls on say
# s3://spack-binaries/develop/ it returns the complete path to the bucket for
# all items under develop/ if we just take what was passed in (e.g. $1) and
# append what we find we may end up with repeated path elements. So here we
# strip out just the bucket name for use in the upload command.
S3_BUCKET=$(echo $1 | cut -f3 -d"/")


# Upload
# 1. Search the passed in bucket + optional path
# 2. Return only paths that end in _pgp/
# 3. Strip out everything but the partial object path
# 4. Remove the trailing slash on _pgp/
# 5. Upload the public key file to the found pgp folders
aws s3 ls --recursive "$1" | \
    grep "_pgp/$" | \
    tr -s " " | cut -f4 -d " " | \
    sed -e 's:/*$::' | \
    parallel aws s3 cp ${PUBLIC_KEY_FILE} s3://${S3_BUCKET}/{}/${PUBLIC_KEY_FILE}
