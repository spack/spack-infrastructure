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
# The primary key is kept offline; manifests are signed by this subkey
SIGNING_SUBKEY_ID=D2C7EB3F2B05FA86590D293C04001B2E3DB0C723

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


# Reads gpg's machine-readable status output from the file $1 (written with
# --status-file, which only gpg writes to, so the signed content can't add
# lines to it) in one pass, without starting any processes, and sets:
#   messages    number of signed messages (PLAINTEXT)
#   signatures  number of signatures (NEWSIG starts each one)
#   good        number of good signatures (GOODSIG: valid, and the key is
#               neither expired nor revoked)
#   signers     fingerprints of the keys that made the signatures (VALIDSIG)
#   revoked     fingerprints of those keys that are revoked. gpg --verify
#               still succeeds for these, and reports EXPKEYSIG rather than
#               REVKEYSIG for a key that is both expired and revoked, so
#               KEYREVOKED is checked too.
parse_status() {
    messages=0 signatures=0 good=0 signers=() revoked=()
    local tag keyword fpr rest signer="" is_revoked=0
    while read -r tag keyword fpr rest; do
        [[ $tag == "[GNUPG:]" ]] || continue
        case $keyword in
            PLAINTEXT) messages=$((messages + 1)) ;;
            NEWSIG)
                if (( is_revoked )); then revoked+=("${signer:-unknown}"); fi
                signer="" is_revoked=0
                signatures=$((signatures + 1)) ;;
            GOODSIG) good=$((good + 1)) ;;
            # [GNUPG:] VALIDSIG <signing key fpr> ...
            VALIDSIG) signer=$fpr; signers+=("$fpr") ;;
            REVKEYSIG|KEYREVOKED) is_revoked=1 ;;
        esac
    done < "$1"
    if (( is_revoked )); then revoked+=("${signer:-unknown}"); fi
}


# Succeeds if the file $1 is exactly one clearsigned message, with nothing
# before or after it that the signature doesn't cover. gpg ignores such text,
# but older Spack clients read the raw file.
single_clearsigned_block() {
    local header="-----BEGIN PGP SIGNED MESSAGE-----"
    local footer="-----END PGP SIGNATURE-----"
    local content inner
    # read stops early, and succeeds, only when the file contains a NUL byte,
    # which would hide everything after it from the checks below
    if IFS= read -r -d '' content < "$1"; then return 1; fi
    [[ $content == "${header}"$'\n'*$'\n'"${footer}"$'\n' ]] || return 1
    inner=${content#"${header}"$'\n'}
    inner=${inner%$'\n'"${footer}"$'\n'}
    [[ $inner != *"${header}"* && $inner != *"${footer}"* ]]
}


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
already_signed=0
for FILE in $( find $INPUTDIR -type f ); do
    # preserve path structure within /tmp/input/ when writing output to /tmp/verified/
    output="${VERIFYDIR}/${FILE#$INPUTDIR}"
    mkdir -p $(dirname -- $output)
    # gpg prints a few lines per file to stderr even with --quiet, so keep them
    # and only show them when verification fails
    #
    # Remove the previous file's status first, so the checks below can only
    # ever see the status gpg wrote for this file
    rm -f ${WORKINGDIR}/verify.status
    if ! gpg --verify --no-tty --quiet --status-file ${WORKINGDIR}/verify.status --output ${output} ${FILE} 2> ${WORKINGDIR}/verify.err; then
        cat ${WORKINGDIR}/verify.err >&2
        echo "ERROR: failed to verify the signature on ${FILE}" >&2
        exit 1
    fi
    if [[ ! -f ${WORKINGDIR}/verify.status ]]; then
        echo "ERROR: gpg wrote no status output for ${FILE}" >&2
        exit 1
    fi
    parse_status ${WORKINGDIR}/verify.status
    if (( signatures == 0 )); then
        echo "ERROR: gpg reported no signature on ${FILE}" >&2
        exit 1
    fi
    single_block=0
    if single_clearsigned_block ${FILE}; then single_block=1; fi
    rm ${FILE}
    verified=$((verified + 1))

    # The primary key is kept offline and never used for signing here, so a
    # signature from it means the key may be compromised. Stop before
    # anything is signed or uploaded so the manifest is left as evidence.
    if [[ " ${signers[*]} " == *" ${SIGNING_KEY_ID} "* ]]; then
        echo "ERROR: ${FILE} is signed by the reputational primary key ${SIGNING_KEY_ID} (not a subkey)" >&2
        exit 1
    fi

    # A revoked key may have been compromised, and signing the manifest again
    # would give whatever it signed a valid signature from the reputational
    # key. Stop instead, for the same reason as above. This applies to every
    # key, including the intermediate CI keys.
    if (( ${#revoked[@]} > 0 )); then
        echo "ERROR: ${FILE} is signed by revoked key ${revoked[*]}" >&2
        exit 1
    fi

    # Already signed by the reputational key, so don't sign it again. Leaving
    # it out of /tmp/output/ keeps the upload from rewriting it in the mirror.
    # Only a file that is one signed message with one good signature by the
    # subkey counts. Anything else is signed again, from the text gpg
    # verified, which also drops any text outside the signed message.
    if (( single_block && messages == 1 && signatures == 1 && good == 1 )) \
        && [[ ${signers[0]:-} == "${SIGNING_SUBKEY_ID}" ]]; then
        already_signed=$((already_signed + 1))
        rm ${output}
    fi
    progress "Verified" ${verified} ${to_verify}
done
echo "Verified ${verified} manifests, ${already_signed} already signed by the reputational key"


to_sign=$(( $(find $VERIFYDIR -type f | wc -l) ))
echo "Signing ${to_sign} manifests"

# Import the private key for signing, but don't decrypt it when there's
# nothing to sign
if (( to_sign > 0 )); then
    gpg --no-tty --import <(aws-encryption-cli --decrypt -S -w "key=${KMS_KEY_ARN}" -i ${SIGNING_KEY} -o -)
fi


# Sign Keys with reputational key
signed=0
for FILE in $( find $VERIFYDIR -type f ); do
    # preserve path structure within /tmp/verified when writing output to /tmp/output/
    output="${OUTPUTDIR}/${FILE#$VERIFYDIR}"
    mkdir -p $(dirname -- $output)
    # Sign with the subkey explicitly ("!" disables gpg's own key selection) so
    # signing always matches the already-signed check above
    if ! gpg --no-tty --local-user "${SIGNING_SUBKEY_ID}!" --output ${output} --clearsign ${FILE}; then
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
