#!/bin/bash
set -Eeuo pipefail

# Pre-flight

command -v gpg >/dev/null 2>&1 || { echo >&2 "Command 'gpg' not found.  Aborting."; exit 1; }
command -v aws-encryption-cli >/dev/null 2>&1 || { echo >&2 "Command 'aws-encryption-cli' not found.  Aborting."; exit 1; }


# Remove the access key and secret key environment variables that come in from
# the CI pipeline. This script relies on permissions confired to the pod via the
# service account assigned to it. That means it requires an AWS_ROLE_ARN and
# AWS_WEB_IDENTITY_TOKEN_FILE variables from EKS. Because of credential
# discovery precidence, boto (used by aws-encryption-cli) will find the
# AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY first if they are not unset.
#
# See Also:
# https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts-technical-overview.html#pod-configuration
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY


WORKINGDIR=${WORKINGDIR:-/tmp}
mkdir -p $WORKINGDIR

KMS_KEY_ARN=arn:aws:kms:us-east-1:588562868276:key/bc739d17-8569-4741-9385-9264715b90b6

SIGNING_KEY=/mnt/keys/signing/signing_key.encrypted.gpg
SIGNING_PUBLIC_KEY=/mnt/keys/signing/signing_key_public.gpg
SIGNING_KEY_ID=2C8DD3224EF3573A42BD221FA8E0CA3C1C2ADA2F

INTERMEDIATE_CI_PUBLIC_KEY=/mnt/keys/signing/intermediate_ci_public_key.gpg
INTERMEDIATE_CI_PUBLIC_KEY_ID=78F3726939CA1B94893B66E8BC86F6FB94429164

UO_INTERMEDIATE_CI_PUBLIC_KEY=/mnt/keys/signing/uo_intermediate_ci_public_key.gpg
UO_INTERMEDIATE_CI_PUBLIC_KEY_ID=0ACDCFDA91DB974A68C3DDC2F85815B32355CB19


# Generate temporary directory
GNUPGHOME=/mnt/gnupg/$(echo $RANDOM | md5sum | head -c 20)
mkdir -p -m 0700 $GNUPGHOME
export GNUPGHOME

# Remove keyring on exit
trap "rm -rf $GNUPGHOME" EXIT


# Import public keys
gpg --no-tty --import $INTERMEDIATE_CI_PUBLIC_KEY
gpg --no-tty --import $UO_INTERMEDIATE_CI_PUBLIC_KEY
gpg --no-tty --import $SIGNING_PUBLIC_KEY

# Trust public keys
gpg --import-ownertrust <(echo -e "${INTERMEDIATE_CI_PUBLIC_KEY_ID}:6:\n${UO_INTERMEDIATE_CI_PUBLIC_KEY_ID}:6:\n${SIGNING_KEY_ID}:6:")


# Check downloaded spec files,  die if not signed/verified
for FILE in $WORKINGDIR/*; do
    echo "VERIFY: ${FILE}"
    gpg --no-tty --quiet ${FILE}
    rm ${FILE}
done


# Import the private key for signing
gpg --no-tty --import <(aws-encryption-cli --decrypt -S -w "key=${KMS_KEY_ARN}" -i ${SIGNING_KEY} -o -)


# Sign Keys with reputational key
for FILE in $WORKINGDIR/*; do
   echo "SIGN: ${FILE}"
   gpg --no-tty --output ${FILE}.sig --clearsign ${FILE}
   rm ${FILE}
done


# Armor/export public key into expected location
mkdir -p /tmp/public_keys
gpg --export --armor ${SIGNING_KEY_ID} > "/tmp/public_keys/${SIGNING_KEY_ID}.pub"
