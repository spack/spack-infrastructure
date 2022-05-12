#!/usr/bin/env bash

# Pre-flight

# TODO uncomment when ready to take inputs
# [ "$#" -lt 1 ] && { echo >&2 "No arguments. Aborting."; exit 1; }
command -v gpg >/dev/null 2>&1 || { echo >&2 "Command 'gpg' not found.  Aborting."; exit 1; }
command -v aws-encryption-cli >/dev/null 2>&1 || { echo >&2 "Command 'aws-encryption-cli' not found.  Aborting."; exit 1; }

WORKINGDIR=/mnt/gnupg

KMS_KEY_ARN=arn:aws:kms:us-east-1:588562868276:key/e811e4c5-ea63-4da3-87d4-664dc5395169

SIGNING_KEY=/mnt/keys/signing/signing_key.encrypted.gpg
SIGNING_KEY_ID=CA0118FBB810A56C120BA6DF5D70BDA102F772BA

INTERMEDIATE_CI_KEY=/mnt/keys/signing/intermediate_ci_public_key.gpg
INTERMEDIATE_CI_KEY_ID=78F3726939CA1B94893B66E8BC86F6FB94429164


# Generate temporary directory
# TODO  this template doesn't work,  only last 8 are random ?
export GNUPGHOME=$(mktemp -d -t XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX -p $WORKINGDIR)

# TODO Uncomment when ready to deploy
# trap "rm -rf $GNUGPDIR" EXIT

# Decrypt private signing key, import and trust
# 78F3726939CA1B94893B66E8BC86F6FB94429164
gpg --import <( aws-encryption-cli --decrypt -S \
                -w "key=${KMS_KEY_ARN}" \
                -i ${SIGNING_KEY} -o -)
echo -e "5\ny\n" | gpg --command-fd 0 --edit-key "$SIGNING_KEY_ID" trust


# Import public intermediate key and trust
gpg --import $INTERMEDIATE_CI_KEY
echo -e "5\ny\n" | gpg --command-fd 0 --edit-key "$INTERMEDIATE_CI_KEY_ID" trust



# TODO Check downloaded spec files,  die if not signed/verified

# TODO Find all intermediate signed files and strip/resign




# Sign files
# for FILE; do
#    [ -f "${FILE}" ] && gpg --homedir "${GNUGPDIR}" --output "${FILE}.sig" --detach-sig "${FILE}"
# done
