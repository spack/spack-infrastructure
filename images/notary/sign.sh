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
INPUTDIR="${WORKINGDIR}/input"
OUTPUTDIR="${WORKINGDIR}/output"
VERIFYDIR="${WORKINGDIR}/verified"
mkdir -p $INPUTDIR
mkdir -p $OUTPUTDIR
mkdir -p $VERIFYDIR

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


# Print "<label>: <count>/<total>" every PROGRESS_INTERVAL files and after the
# last one, so long jobs show how far along they are without a line per file
PROGRESS_INTERVAL=1000
progress() {
    local label=$1 count=$2 total=$3
    if (( count % PROGRESS_INTERVAL == 0 || count == total )); then
        echo "${label}: ${count}/${total} ($(( count * 100 / total ))%), ${SECONDS}s elapsed"
    fi
}


# Check downloaded spec files,  die if not signed/verified
#
# Only problems are logged per file: lines for each of the ~100k manifests a
# job can download would push the job log past the runner's output limit and
# hide the error that stops it.
to_verify=$(( $(find $INPUTDIR -type f | wc -l) ))
echo "Verifying ${to_verify} manifests"
verified=0
for FILE in $( find $INPUTDIR -type f ); do
    # preserve path structure within /tmp/input/ when writing output to /tmp/verified/
    output="${VERIFYDIR}/${FILE#$INPUTDIR}"
    mkdir -p $(dirname -- $output)
    # gpg prints a few lines per file to stderr even with --quiet, so keep them
    # and only show them when verification fails
    if ! gpg --verify --no-tty --quiet --output ${output} ${FILE} 2> ${WORKINGDIR}/verify.err; then
        cat ${WORKINGDIR}/verify.err >&2
        echo "ERROR: failed to verify the signature on ${FILE}" >&2
        exit 1
    fi
    rm ${FILE}
    verified=$((verified + 1))
    progress "Verified" ${verified} ${to_verify}
done
echo "Verified ${verified} manifests"


# Import the private key for signing
gpg --no-tty --import <(aws-encryption-cli --decrypt -S -w "key=${KMS_KEY_ARN}" -i ${SIGNING_KEY} -o -)


# Sign Keys with reputational key
to_sign=$(( $(find $VERIFYDIR -type f | wc -l) ))
echo "Signing ${to_sign} manifests"
signed=0
for FILE in $( find $VERIFYDIR -type f ); do
    # preserve path structure within /tmp/verified when writing output to /tmp/output/
    output="${OUTPUTDIR}/${FILE#$VERIFYDIR}"
    mkdir -p $(dirname -- $output)
    if ! gpg --no-tty --output ${output} --clearsign ${FILE}; then
        echo "ERROR: failed to sign ${FILE}" >&2
        exit 1
    fi
    rm ${FILE}
    signed=$((signed + 1))
    progress "Signed" ${signed} ${to_sign}
done


# Armor/export public key into expected location
mkdir -p /tmp/public_keys
gpg --export --armor ${SIGNING_KEY_ID} > "/tmp/public_keys/${SIGNING_KEY_ID}.pub"
