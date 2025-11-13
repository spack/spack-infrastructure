#!/bin/bash
set -Eeuo pipefail

# Performs in-place migration of a list of mirrors to new buildcache
# layout. The list can come from the command line, or else be read from
# stdin.  The migrate.py script expects to operate within a context where
# the GNUPGHOME environment variable is set to a location that already
# has the expected public/secret parts of the target key imported.  This
# scripts creates that environment with the reputational signing key.

# Pre-flight
command -v gpg >/dev/null 2>&1 || { echo >&2 "Command 'gpg' not found.  Aborting."; exit 1; }
command -v aws-encryption-cli >/dev/null 2>&1 || { echo >&2 "Command 'aws-encryption-cli' not found.  Aborting."; exit 1; }

if [ $# -eq 0 ]; then
  while IFS= read -r line; do
    MIRROR_URLS+=($line)
  done < /dev/stdin
else
  MIRROR_URLS=$@
fi

WORKINGDIR=${WORKINGDIR:-/tmp}
mkdir -p $WORKINGDIR

KMS_KEY_ARN=arn:aws:kms:us-east-1:588562868276:key/bc739d17-8569-4741-9385-9264715b90b6

SIGNING_KEY=/mnt/keys/signing/signing_key.encrypted.gpg
SIGNING_PUBLIC_KEY=/mnt/keys/signing/signing_key_public.gpg
SIGNING_KEY_ID=2C8DD3224EF3573A42BD221FA8E0CA3C1C2ADA2F

# Generate temporary directory
GNUPGHOME=/mnt/gnupg/$(echo $RANDOM | md5sum | head -c 20)
mkdir -p -m 0700 $GNUPGHOME
export GNUPGHOME

# Remove keyring on exit
trap "rm -rf $GNUPGHOME" EXIT

# Import public key
gpg --no-tty --import $SIGNING_PUBLIC_KEY

# Trust public keys
gpg --import-ownertrust <(echo -e "${SIGNING_KEY_ID}:6:")

# Import the private key for signing
gpg --no-tty --import <(aws-encryption-cli --decrypt -S -w "key=${KMS_KEY_ARN}" -i ${SIGNING_KEY} -o -)

cd /srcs

echo "migrate.sh: Mirrors to process:"
for url in ${MIRROR_URLS[@]}; do
  echo "migrate.sh: python -m pkg.migrate --parallel 16 ${url}"
  python -m pkg.migrate --parallel 16 $url || true
  echo "migrate.sh: python -m pkg.migrate --parallel 16 ${url} exited ${?}"
done
