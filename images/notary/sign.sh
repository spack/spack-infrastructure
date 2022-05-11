#!/usr/bin/env bash

# Pre-flight
[ "$#" -lt 1 ] && { echo >&2 "No arguments. Aborting."; exit 1; }
command -v gpg >/dev/null 2>&1 || { echo >&2 "Command 'gpg' not found.  Aborting."; exit 1; }
command -v aws-encryption-cli >/dev/null 2>&1 || { echo >&2 "Command 'aws-encryption-cli' not found.  Aborting."; exit 1; }

# TODO Set this to wherever we mount the tmpfs filesystem
WORKINGDIR=$(pwd)

ENCRYPTED_SUBKEY=subkey.encrypted.gpg
KMS_KEY_ARN=arn:aws:kms:us-east-1:588562868276:key/e811e4c5-ea63-4da3-87d4-664dc5395169

# Generate temporary directory
GNUGPDIR=$(mktemp -d -t XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX -p $WORKINGDIR)
trap "rm -rf $GNUGPDIR" EXIT

# Decrypt private signing key
gpg --homedir $GNUGPDIR \
    --no-options \
    --require-secmem \
    --quiet \
    --import <( aws-encryption-cli --decrypt -S \
                -w key=${KMS_KEY_ARN}\
                -i ${ENCRYPTED_SUBKEY} -o -)

# Sign files
for FILE; do
    [ -f "${FILE}" ] && gpg --homedir "${GNUGPDIR}" --output "${FILE}.sig" --detach-sig "${FILE}"
done
