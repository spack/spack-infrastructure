#!/bin/bash
set -Eeuo pipefail

# Pre-flight

# TODO uncomment when ready to take inputs
# [ "$#" -lt 1 ] && { echo >&2 "No arguments. Aborting."; exit 1; }
command -v gpg >/dev/null 2>&1 || { echo >&2 "Command 'gpg' not found.  Aborting."; exit 1; }
command -v aws-encryption-cli >/dev/null 2>&1 || { echo >&2 "Command 'aws-encryption-cli' not found.  Aborting."; exit 1; }

WORKINGDIR=${WORKINGDIR:-/tmp}
mkdir -p $WORKINGDIR

KMS_KEY_ARN=arn:aws:kms:us-east-1:588562868276:key/e811e4c5-ea63-4da3-87d4-664dc5395169

SIGNING_KEY=/mnt/keys/signing/signing_key.encrypted.gpg
SIGNING_PUBLIC_KEY=/mnt/keys/signing/signing_key_public.gpg
SIGNING_KEY_ID=CA0118FBB810A56C120BA6DF5D70BDA102F772BA

INTERMEDIATE_CI_PUBLIC_KEY=/mnt/keys/signing/intermediate_ci_public_key.gpg
INTERMEDIATE_CI_PUBLIC_KEY_ID=78F3726939CA1B94893B66E8BC86F6FB94429164



# Generate temporary directory
GNUPGHOME=/mnt/gnupg/$(echo $RANDOM | md5sum | head -c 20)
mkdir -p -m 0700 $GNUPGHOME
export GNUPGHOME

# TODO Uncomment when ready to deploy
trap "rm -rf $GNUPGHOME" EXIT




# Import public intermediate key and trust
gpg --import $INTERMEDIATE_CI_PUBLIC_KEY
echo -e "5\ny\n" | gpg --command-fd 0 --edit-key "$INTERMEDIATE_CI_PUBLIC_KEY_ID" trust


# Import public reputational key and trust
gpg --import $SIGNING_PUBLIC_KEY
echo -e "5\ny\n" | gpg --command-fd 0 --edit-key "$SIGNING_KEY_ID" trust

# TODO Check downloaded spec files,  die if not signed/verified



for FILE in $WORKINGDIR/*; do
    echo "VERIFY: ${FILE}"
    gpg --quiet ${FILE}
    rm ${FILE}
done


# Decrypt private signing key, and import
# 78F3726939CA1B94893B66E8BC86F6FB94429164
gpg --import <( aws-encryption-cli --decrypt -S \
                -w "key=${KMS_KEY_ARN}" \
                -i ${SIGNING_KEY} -o -)


for FILE in $WORKINGDIR/*; do
   echo "SIGN: ${FILE}"
   gpg --output ${FILE}.sig --clearsign ${FILE}
   rm ${FILE}
done
